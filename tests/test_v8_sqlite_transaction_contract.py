"""SQLite-only V8 preview crash, rollback and journal mode contract."""
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

class SQLiteTransactionContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "preview.sqlite")
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE preview_rehearsals (request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, reference TEXT NOT NULL UNIQUE)")
            db.execute("CREATE TABLE preview_sequence (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), next_number INTEGER NOT NULL CHECK(next_number > 0))")
            db.execute("INSERT INTO preview_sequence VALUES (1,1)")

    def test_journal_mode_switch_detection(self):
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "delete")
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        with sqlite3.connect(self.path) as db:
            self.assertNotEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "delete")

    def test_precommit_rollback_preserves_sequence(self):
        db = sqlite3.connect(self.path, isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO preview_rehearsals VALUES ('request0001','abc','REHEARSAL-00000001')")
            changed = db.execute("UPDATE preview_sequence SET next_number=2 WHERE singleton=1 AND next_number=1")
            self.assertEqual(changed.rowcount, 1)
            db.execute("ROLLBACK")
        finally:
            db.close()
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM preview_rehearsals").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT next_number FROM preview_sequence").fetchone()[0], 1)

    def test_crash_before_commit_rollback(self):
        script = ("import sqlite3,sys,os\n"
                  "db=sqlite3.connect(sys.argv[1],isolation_level=None)\n"
                  "db.execute('PRAGMA synchronous=FULL')\n"
                  "db.execute('BEGIN IMMEDIATE')\n"
                  "db.execute(\"INSERT INTO preview_rehearsals VALUES ('request0001','abc','REHEARSAL-00000001')\")\n"
                  "db.execute('UPDATE preview_sequence SET next_number=2 WHERE singleton=1')\n"
                  "os._exit(29)\n")
        child = subprocess.run([sys.executable, "-c", script, self.path],
                               capture_output=True, text=True, timeout=15)
        self.assertEqual(child.returncode, 29, child.stderr)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM preview_rehearsals").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT next_number FROM preview_sequence").fetchone()[0], 1)

    def test_crash_after_commit_persists_both_records(self):
        script = ("import sqlite3,sys,os\n"
                  "db=sqlite3.connect(sys.argv[1],isolation_level=None)\n"
                  "db.execute('PRAGMA synchronous=FULL')\n"
                  "db.execute('BEGIN IMMEDIATE')\n"
                  "db.execute(\"INSERT INTO preview_rehearsals VALUES ('request0001','abc','REHEARSAL-00000001')\")\n"
                  "db.execute('UPDATE preview_sequence SET next_number=2 WHERE singleton=1')\n"
                  "db.execute('COMMIT')\n"
                  "os._exit(31)\n")
        child = subprocess.run([sys.executable, "-c", script, self.path],
                               capture_output=True, text=True, timeout=15)
        self.assertEqual(child.returncode, 31, child.stderr)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM preview_rehearsals").fetchone()[0],
                1,
            )
            self.assertEqual(
                db.execute("SELECT next_number FROM preview_sequence").fetchone()[0],
                2,
            )
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_failed_sequence_compare_and_swap_rolls_back_insert(self):
        with sqlite3.connect(self.path, isolation_level=None) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(
                    "INSERT INTO preview_rehearsals VALUES (?,?,?)",
                    ("request0001", "abc", "REHEARSAL-00000001"),
                )
                changed = db.execute(
                    "UPDATE preview_sequence SET next_number=2 "
                    "WHERE singleton=1 AND next_number=999"
                )
                self.assertEqual(changed.rowcount, 0)
                db.execute("ROLLBACK")
            finally:
                if db.in_transaction:
                    db.execute("ROLLBACK")
        with sqlite3.connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM preview_rehearsals").fetchone()[0], 0
            )
            self.assertEqual(
                db.execute("SELECT next_number FROM preview_sequence").fetchone()[0], 1
            )

    def test_crash_between_insert_and_sequence_update_rolls_back(self):
        script = (
            "import sqlite3,sys,os\n"
            "db=sqlite3.connect(sys.argv[1],isolation_level=None)\n"
            "db.execute('PRAGMA synchronous=FULL')\n"
            "db.execute('BEGIN IMMEDIATE')\n"
            "db.execute(\"INSERT INTO preview_rehearsals VALUES "
            "('request0001','abc','REHEARSAL-00000001')\")\n"
            "os._exit(37)\n"
        )
        child = subprocess.run(
            [sys.executable, "-c", script, self.path],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(child.returncode, 37, child.stderr)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM preview_rehearsals").fetchone()[0], 0
            )
            self.assertEqual(
                db.execute("SELECT next_number FROM preview_sequence").fetchone()[0], 1
            )
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_crash_after_sequence_advance_before_commit_rolls_back_both(self):
        script = """
import os, sqlite3, sys
db = sqlite3.connect(sys.argv[1], isolation_level=None)
db.execute("BEGIN IMMEDIATE")
db.execute("INSERT INTO preview_rehearsals VALUES (?,?,?)",
           ("crashed-request", "c" * 64, "REHEARSAL-00000001"))
db.execute("UPDATE preview_sequence SET next_number=2 WHERE singleton=1")
os._exit(39)
"""
        result = subprocess.run(
            [sys.executable, "-c", script, self.path],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 39, result.stderr)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM preview_rehearsals"
            ).fetchone()[0], 0)
            self.assertEqual(db.execute(
                "SELECT next_number FROM preview_sequence"
            ).fetchone()[0], 1)
            self.assertEqual(db.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0], "ok")

    def test_concurrent_aborted_claims_do_not_consume_references(self):
        from concurrent.futures import ThreadPoolExecutor

        def attempt(index):
            db = sqlite3.connect(self.path, isolation_level=None, timeout=10)
            try:
                db.execute("PRAGMA busy_timeout=10000")
                db.execute("BEGIN IMMEDIATE")
                number = db.execute(
                    "SELECT next_number FROM preview_sequence WHERE singleton=1"
                ).fetchone()[0]
                db.execute(
                    "INSERT INTO preview_rehearsals VALUES (?,?,?)",
                    (f"request-{index:08d}", "b" * 64,
                     f"REHEARSAL-{number:08d}"),
                )
                if index % 3 == 0:
                    db.execute("ROLLBACK")
                    return None
                updated = db.execute(
                    "UPDATE preview_sequence SET next_number=? "
                    "WHERE singleton=1 AND next_number=?",
                    (number + 1, number),
                )
                self.assertEqual(updated.rowcount, 1)
                db.execute("COMMIT")
                return number
            finally:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                db.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            numbers = list(pool.map(attempt, range(30)))
        committed = [number for number in numbers if number is not None]
        self.assertEqual(sorted(committed), list(range(1, 21)))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM preview_rehearsals"
            ).fetchone()[0], 20)
            self.assertEqual(db.execute(
                "SELECT next_number FROM preview_sequence"
            ).fetchone()[0], 21)
            self.assertEqual(db.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0], "ok")

    def test_concurrent_connections_serialize_sequence_claims(self):
        from concurrent.futures import ThreadPoolExecutor

        def claim(index):
            db = sqlite3.connect(self.path, isolation_level=None, timeout=10)
            try:
                db.execute("PRAGMA busy_timeout=10000")
                db.execute("BEGIN IMMEDIATE")
                number = db.execute(
                    "SELECT next_number FROM preview_sequence WHERE singleton=1"
                ).fetchone()[0]
                db.execute(
                    "INSERT INTO preview_rehearsals VALUES (?,?,?)",
                    (f"request-{index:08d}", "a" * 64,
                     f"REHEARSAL-{number:08d}"),
                )
                changed = db.execute(
                    "UPDATE preview_sequence SET next_number=? "
                    "WHERE singleton=1 AND next_number=?",
                    (number + 1, number),
                )
                if changed.rowcount != 1:
                    raise AssertionError("sequence CAS lost")
                db.execute("COMMIT")
                return number
            finally:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                db.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            numbers = list(pool.map(claim, range(32)))
        self.assertEqual(set(numbers), set(range(1, 33)))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM preview_rehearsals"
            ).fetchone()[0], 32)
            self.assertEqual(db.execute(
                "SELECT next_number FROM preview_sequence"
            ).fetchone()[0], 33)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_sqlite_internal_stat_table_detectable(self):
        with sqlite3.connect(self.path) as db:
            db.execute("ANALYZE")
            objects = db.execute("SELECT type,name FROM sqlite_master WHERE name GLOB 'sqlite_*'").fetchall()
            self.assertTrue(any(name == "sqlite_stat1" for _, name in objects))
            self.assertTrue(all(kind == "index" for kind, name in objects
                                if name.startswith("sqlite_autoindex_")))

if __name__ == "__main__":
    unittest.main()
