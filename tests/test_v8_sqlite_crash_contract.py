"""Dependency-free SQLite crash contract checks for disposable preview data."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class SQLiteCrashContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v8-preview-crash-")
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "journal.sqlite")
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE rehearsal (request_id TEXT PRIMARY KEY, reference INTEGER UNIQUE)")
            db.execute("CREATE TABLE sequence (next_number INTEGER NOT NULL)")
            db.execute("INSERT INTO sequence VALUES (1)")

    def _crash(self, *, commit):
        code = """
import os, sqlite3, sys
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute('PRAGMA synchronous=FULL')
conn.execute('BEGIN IMMEDIATE')
conn.execute('INSERT INTO rehearsal VALUES (?, ?)', ('request-0001', 1))
conn.execute('UPDATE sequence SET next_number=2')
if sys.argv[2] == 'commit':
    conn.execute('COMMIT')
os._exit(23)
"""
        result = subprocess.run([sys.executable, "-c", code, self.path,
                                 "commit" if commit else "abort"],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 23, result.stderr)

    def test_abrupt_exit_before_commit_rolls_back_both_tables(self):
        self._crash(commit=False)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM rehearsal").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT next_number FROM sequence").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA quick_check").fetchone()[0], "ok")

    def test_abrupt_exit_after_commit_persists_both_tables(self):
        self._crash(commit=True)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT reference FROM rehearsal").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT next_number FROM sequence").fetchone()[0], 2)
            self.assertEqual(db.execute("PRAGMA quick_check").fetchone()[0], "ok")

    def test_wal_abrupt_exit_before_commit_rolls_back_both_tables(self):
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        self._crash(commit=False)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM rehearsal").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT next_number FROM sequence").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_wal_abrupt_exit_after_commit_replays_exactly_once(self):
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        self._crash(commit=True)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM rehearsal").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT next_number FROM sequence").fetchone()[0], 2)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO rehearsal VALUES (?, ?)", ("request-0001", 2))
            db.rollback()
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        # Reopening after the WAL recovery must not regenerate a reference.
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT reference FROM rehearsal").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT next_number FROM sequence").fetchone()[0], 2)

    def test_unique_request_id_prevents_duplicate_after_restart(self):
        self._crash(commit=True)
        with sqlite3.connect(self.path) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO rehearsal VALUES (?, ?)", ('request-0001', 2))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM rehearsal").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT next_number FROM sequence").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
