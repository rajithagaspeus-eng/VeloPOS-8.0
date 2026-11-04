"""Disposable SQLite sale rehearsal crash recovery and idempotency tests."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import sys
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from velopos_qt.durable_sale_rehearsal import DurablePreviewSaleJournal


class DurablePreviewSaleJournalTests(unittest.TestCase):
    def setUp(self):
        self.path = str(Path(tempfile.gettempdir()) /
                        ("v8-preview-rehearsal-" + uuid4().hex + ".sqlite"))
        self.addCleanup(lambda: Path(self.path).unlink(missing_ok=True))
        self.lines = [{"barcode": "SOAP", "qty": "2", "price": "0.50"}]
        self.journal = DurablePreviewSaleJournal(self.path)

    def test_replay_survives_reopening_database(self):
        first = self.journal.inspect(
            request_id="durable-request-0001", lines=self.lines
        )
        restarted = DurablePreviewSaleJournal(self.path)
        second = restarted.inspect(
            request_id="durable-request-0001",
            lines=[{"price": "0.500", "qty": "2.0", "barcode": "SOAP"}],
        )
        self.assertEqual(first.reference, second.reference)
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertFalse(second.can_checkout)
        self.assertFalse(second.can_post)

    def test_conflicting_replay_refused_after_restart(self):
        self.journal.inspect(request_id="durable-request-0001", lines=self.lines)
        with self.assertRaisesRegex(ValueError, "different payload"):
            DurablePreviewSaleJournal(self.path).inspect(
                request_id="durable-request-0001",
                lines=[{"barcode": "SOAP", "qty": "3", "price": "0.50"}],
            )

    def test_concurrent_replay_one_first_writer(self):
        def worker(_):
            return DurablePreviewSaleJournal(self.path).inspect(
                request_id="parallel-durable-0001", lines=self.lines
            )
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(worker, range(24)))
        self.assertEqual(len({r.reference for r in results}), 1)
        self.assertEqual(sum(not r.replayed for r in results), 1)

    def test_concurrent_distinct_requests_have_gapless_references(self):
        def worker(number):
            request_id = f"parallel-unique-{number:04d}"
            return DurablePreviewSaleJournal(self.path).inspect(
                request_id=request_id, lines=self.lines
            )
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(worker, range(24)))
        self.assertEqual(sum(not item.replayed for item in results), 24)
        self.assertEqual(
            {item.reference for item in results},
            {f"REHEARSAL-{number:08d}" for number in range(1, 25)},
        )
        reopened = DurablePreviewSaleJournal(self.path)
        replay = reopened.inspect(
            request_id="parallel-unique-0000", lines=self.lines
        )
        self.assertTrue(replay.replayed)
        next_result = reopened.inspect(
            request_id="parallel-unique-0024", lines=self.lines
        )
        self.assertEqual(next_result.reference, "REHEARSAL-00000025")

    def test_failed_validation_does_not_consume_sequence(self):
        with self.assertRaises(ValueError):
            self.journal.inspect(
                request_id="durable-request-0001",
                lines=[{"barcode": "SOAP", "qty": "-1", "price": "1"}],
            )
        first = self.journal.inspect(
            request_id="durable-request-0001", lines=self.lines
        )
        self.assertEqual(first.reference, "REHEARSAL-00000001")

    def test_corrupt_fingerprint_fails_closed(self):
        self.journal.inspect(request_id="durable-request-0001", lines=self.lines)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "UPDATE preview_rehearsals SET fingerprint=? WHERE request_id=?",
                ("bad", "durable-request-0001"),
            )
        with self.assertRaises(PermissionError):
            self.journal.inspect(
                request_id="durable-request-0001", lines=self.lines
            )

    def test_unrelated_corrupt_record_blocks_all_replays(self):
        self.journal.inspect(request_id="durable-request-0001", lines=self.lines)
        self.journal.inspect(request_id="durable-request-0002", lines=self.lines)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "UPDATE preview_rehearsals SET fingerprint='bad' "
                "WHERE request_id='durable-request-0002'"
            )
        with self.assertRaises(PermissionError):
            self.journal.inspect(
                request_id="durable-request-0001", lines=self.lines
            )

    def test_deleted_middle_record_is_detected_after_restart(self):
        for i in range(3):
            self.journal.inspect(
                request_id=f"durable-request-{i:04d}", lines=self.lines
            )
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "DELETE FROM preview_rehearsals WHERE request_id=?",
                ("durable-request-0001",)
            )
        with self.assertRaises(PermissionError):
            DurablePreviewSaleJournal(self.path).inspect(
                request_id="durable-request-0000", lines=self.lines
            )

    def test_sequence_rewind_refuses_replay(self):
        self.journal.inspect(request_id="durable-request-0001", lines=self.lines)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "UPDATE preview_sequence SET next_number=1 WHERE singleton=1"
            )
        with self.assertRaises(PermissionError):
            self.journal.inspect(
                request_id="durable-request-0001", lines=self.lines
            )

    def test_sequence_jump_refuses_new_request(self):
        self.journal.inspect(request_id="durable-request-0001", lines=self.lines)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "UPDATE preview_sequence SET next_number=100 WHERE singleton=1"
            )
        with self.assertRaises(PermissionError):
            self.journal.inspect(
                request_id="durable-request-0002", lines=self.lines
            )

    def test_forged_reference_chain_refuses_replay(self):
        self.journal.inspect(request_id="durable-request-0001", lines=self.lines)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "UPDATE preview_rehearsals SET reference='REHEARSAL-00000099'"
            )
        with self.assertRaises(PermissionError):
            self.journal.inspect(
                request_id="durable-request-0001", lines=self.lines
            )

    def test_trigger_added_after_open_is_rejected_before_write(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "CREATE TRIGGER preview_late AFTER INSERT ON preview_rehearsals "
                "BEGIN UPDATE preview_sequence SET next_number=99; END"
            )
        with self.assertRaises(PermissionError):
            self.journal.inspect(
                request_id="durable-request-0001", lines=self.lines
            )
        with sqlite3.connect(self.path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM preview_rehearsals"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_existing_trigger_is_rejected_before_reopen(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "CREATE TRIGGER preview_tamper AFTER INSERT ON preview_rehearsals "
                "BEGIN UPDATE preview_sequence SET next_number=99; END"
            )
        with self.assertRaises(PermissionError):
            DurablePreviewSaleJournal(self.path)

    def test_extra_view_and_table_are_rejected(self):
        for statement in (
            "CREATE VIEW unexpected_view AS SELECT 1 AS value",
            "CREATE TABLE unexpected_table (value INTEGER)",
        ):
            with self.subTest(statement=statement):
                with sqlite3.connect(self.path) as conn:
                    conn.execute(statement)
                with self.assertRaises(PermissionError):
                    DurablePreviewSaleJournal(self.path)
                with sqlite3.connect(self.path) as conn:
                    conn.execute(
                        "DROP VIEW unexpected_view"
                        if "VIEW" in statement else "DROP TABLE unexpected_table"
                    )

    def test_altered_table_columns_refused_on_reopen(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("ALTER TABLE preview_rehearsals ADD COLUMN forged TEXT")
        with self.assertRaises(PermissionError):
            DurablePreviewSaleJournal(self.path)

    def test_missing_sequence_is_not_silently_recreated(self):
        self.journal.inspect(
            request_id="durable-request-0001", lines=self.lines
        )
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM preview_sequence")
        with self.assertRaises(PermissionError):
            DurablePreviewSaleJournal(self.path)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM preview_sequence").fetchone()[0],
                0,
            )

    def test_failed_initialization_rolls_back_partial_schema(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE preview_sequence")
            conn.execute("DROP TABLE preview_rehearsals")
            conn.execute("CREATE TABLE preview_rehearsals (unexpected INTEGER)")
        with self.assertRaises(PermissionError):
            DurablePreviewSaleJournal(self.path)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE name='preview_sequence'"
                ).fetchone()[0],
                0,
            )

    def test_conflicting_request_rolls_back_without_sequence_gap(self):
        self.journal.inspect(
            request_id="durable-request-0001", lines=self.lines
        )
        with self.assertRaises(ValueError):
            self.journal.inspect(
                request_id="durable-request-0001",
                lines=[{"barcode": "SOAP", "qty": "5", "price": "0.50"}],
            )
        restarted = DurablePreviewSaleJournal(self.path)
        next_result = restarted.inspect(
            request_id="durable-request-0002", lines=self.lines
        )
        self.assertEqual(next_result.reference, "REHEARSAL-00000002")

    def test_corrupt_sequence_rolls_back_without_new_row(self):
        self.journal.inspect(
            request_id="durable-request-0001", lines=self.lines
        )
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE preview_sequence SET next_number=50")
        with self.assertRaises(PermissionError):
            self.journal.inspect(
                request_id="durable-request-0002", lines=self.lines
            )
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM preview_rehearsals").fetchone()[0],
                1,
            )

    def test_empty_existing_journal_with_missing_sequence_is_rejected(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM preview_sequence")
        with self.assertRaises(PermissionError):
            DurablePreviewSaleJournal(self.path)

    def test_missing_reference_uniqueness_rejected(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE preview_rehearsals")
            conn.execute(
                "CREATE TABLE preview_rehearsals "
                "(request_id TEXT PRIMARY KEY, fingerprint TEXT, reference TEXT)"
            )
        with self.assertRaises(PermissionError):
            DurablePreviewSaleJournal(self.path)

    def test_missing_request_primary_key_rejected(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE preview_rehearsals")
            conn.execute(
                "CREATE TABLE preview_rehearsals "
                "(request_id TEXT, fingerprint TEXT, reference TEXT UNIQUE)"
            )
        with self.assertRaises(PermissionError):
            DurablePreviewSaleJournal(self.path)

    def test_database_file_replacement_after_open_fails_closed(self):
        old = Path(self.path)
        old.unlink()
        with sqlite3.connect(self.path) as conn:
            conn.execute("CREATE TABLE replacement(value INTEGER)")
        with self.assertRaises(PermissionError):
            self.journal.inspect(
                request_id="durable-request-0001", lines=self.lines
            )

    def test_database_symlink_replacement_after_open_fails_closed(self):
        target = Path(self.path + ".target")
        self.addCleanup(lambda: target.unlink(missing_ok=True))
        Path(self.path).rename(target)
        try:
            Path(self.path).symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unavailable on this platform")
        with self.assertRaises(PermissionError):
            self.journal.inspect(
                request_id="durable-request-0001", lines=self.lines
            )

    def test_missing_not_null_constraint_rejected(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE preview_rehearsals")
            conn.execute(
                "CREATE TABLE preview_rehearsals "
                "(request_id TEXT PRIMARY KEY, fingerprint TEXT, "
                "reference TEXT NOT NULL UNIQUE)"
            )
        with self.assertRaises(PermissionError):
            DurablePreviewSaleJournal(self.path)

    def test_post_commit_identity_error_is_not_masked_by_rollback(self):
        from unittest.mock import patch
        replacement = str(Path(tempfile.gettempdir()) /
                          ("v8-preview-rehearsal-" + uuid4().hex + ".sqlite"))
        self.addCleanup(lambda: Path(replacement).unlink(missing_ok=True))
        with patch.object(DurablePreviewSaleJournal, "_identity",
                          side_effect=PermissionError("identity check refused")):
            with self.assertRaisesRegex(PermissionError, "identity check refused"):
                DurablePreviewSaleJournal(replacement)

    def test_corrupt_unrelated_request_id_blocks_replay(self):
        self.journal.inspect(request_id="durable-request-0001", lines=self.lines)
        self.journal.inspect(request_id="durable-request-0002", lines=self.lines)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "UPDATE preview_rehearsals SET request_id='invalid id' "
                "WHERE request_id='durable-request-0002'"
            )
        with self.assertRaises(PermissionError):
            self.journal.inspect(
                request_id="durable-request-0001", lines=self.lines
            )

    def test_crash_before_commit_rolls_back_row_and_sequence(self):
        # Separate process terminates without closing the transaction.
        # SQLite recovery must leave no half-written rehearsal.
        script = """
import os, sqlite3, sys
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute('BEGIN IMMEDIATE')
conn.execute(
    "INSERT INTO preview_rehearsals(request_id,fingerprint,reference) "
    "VALUES (?,?,?)",
    ('crashed-request-0001', 'a' * 64, 'REHEARSAL-00000001'))
conn.execute('UPDATE preview_sequence SET next_number=2 WHERE singleton=1')
os._exit(17)
"""
        child = subprocess.run(
            [sys.executable, "-c", script, self.path],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(child.returncode, 17, child.stderr)
        recovered = DurablePreviewSaleJournal(self.path)
        result = recovered.inspect(
            request_id="durable-request-0001", lines=self.lines
        )
        self.assertEqual(result.reference, "REHEARSAL-00000001")
        self.assertFalse(result.replayed)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM preview_rehearsals").fetchone()[0],
                1,
            )

    def test_crash_after_commit_preserves_idempotent_replay(self):
        script = """
import os, sqlite3, sys
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute('BEGIN IMMEDIATE')
conn.execute(
    "INSERT INTO preview_rehearsals(request_id,fingerprint,reference) "
    "VALUES (?,?,?)",
    (sys.argv[2], sys.argv[3], 'REHEARSAL-00000001'))
conn.execute('UPDATE preview_sequence SET next_number=2 WHERE singleton=1')
conn.execute('COMMIT')
os._exit(19)
"""
        from velopos_qt.sale_request_service import rehearse_sale_request
        request_id = "durable-request-0001"
        fingerprint = rehearse_sale_request(
            request_id=request_id, lines=self.lines
        ).fingerprint
        child = subprocess.run(
            [sys.executable, "-c", script, self.path, request_id, fingerprint],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(child.returncode, 19, child.stderr)
        recovered = DurablePreviewSaleJournal(self.path)
        replay = recovered.inspect(request_id=request_id, lines=self.lines)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.reference, "REHEARSAL-00000001")
        next_result = recovered.inspect(
            request_id="durable-request-0002", lines=self.lines
        )
        self.assertEqual(next_result.reference, "REHEARSAL-00000002")

    def test_connection_requests_full_synchronous_mode(self):
        with self.journal._connect() as conn:
            self.assertEqual(conn.execute("PRAGMA synchronous").fetchone()[0], 2)

    def test_sequence_check_constraints_cannot_be_removed(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE preview_sequence")
            conn.execute(
                "CREATE TABLE preview_sequence ("
                "singleton INTEGER PRIMARY KEY, next_number INTEGER NOT NULL)"
            )
            conn.execute("INSERT INTO preview_sequence VALUES (1,1)")
        with self.assertRaisesRegex(PermissionError, "CHECK constraints"):
            DurablePreviewSaleJournal(self.path)

    def test_sequence_check_tampering_after_open_blocks_new_request(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE preview_sequence")
            conn.execute(
                "CREATE TABLE preview_sequence ("
                "singleton INTEGER PRIMARY KEY, next_number INTEGER NOT NULL)"
            )
            conn.execute("INSERT INTO preview_sequence VALUES (1,1)")
        with self.assertRaisesRegex(PermissionError, "CHECK constraints"):
            self.journal.inspect(
                request_id="durable-request-0001", lines=self.lines
            )
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM preview_rehearsals").fetchone()[0],
                0,
            )

    def test_generated_hidden_column_is_rejected(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE preview_rehearsals")
            conn.execute(
                "CREATE TABLE preview_rehearsals ("
                "request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, "
                "reference TEXT NOT NULL UNIQUE, "
                "stealth TEXT GENERATED ALWAYS AS (request_id) VIRTUAL)"
            )
        with self.assertRaisesRegex(PermissionError, "Hidden or generated"):
            DurablePreviewSaleJournal(self.path)

    def test_foreign_key_schema_tamper_is_rejected_before_write(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE preview_rehearsals")
            conn.execute(
                "CREATE TABLE preview_rehearsals ("
                "request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, "
                "reference TEXT NOT NULL UNIQUE, "
                "FOREIGN KEY(fingerprint) REFERENCES preview_sequence(next_number))"
            )
        with self.assertRaisesRegex(PermissionError, "foreign keys"):
            self.journal.inspect(
                request_id="durable-request-0001", lines=self.lines
            )
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM preview_rehearsals").fetchone()[0],
                0,
            )

    def test_extra_index_is_rejected_on_reopen_and_active_journal(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "CREATE INDEX unexpected_preview_index "
                "ON preview_rehearsals(fingerprint)"
            )
        with self.assertRaisesRegex(PermissionError, "index schema"):
            DurablePreviewSaleJournal(self.path)
        with self.assertRaisesRegex(PermissionError, "index schema"):
            self.journal.inspect(
                request_id="durable-request-0001", lines=self.lines
            )
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM preview_rehearsals").fetchone()[0],
                0,
            )

    def test_full_sqlite_integrity_after_replay_and_restart(self):
        first = self.journal.inspect(
            request_id="durable-request-0001", lines=self.lines
        )
        replay = DurablePreviewSaleJournal(self.path).inspect(
            request_id="durable-request-0001", lines=self.lines
        )
        self.assertEqual(replay.reference, first.reference)
        self.assertTrue(replay.replayed)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchall(),
                             [("ok",)])
            self.assertEqual(
                conn.execute("SELECT next_number FROM preview_sequence").fetchone()[0],
                2,
            )

    def test_capacity_refuses_new_requests_but_allows_replay(self):
        limited = DurablePreviewSaleJournal(self.path, max_requests=1)
        first = limited.inspect(
            request_id="durable-request-0001", lines=self.lines
        )
        with self.assertRaises(OverflowError):
            limited.inspect(request_id="durable-request-0002", lines=self.lines)
        self.assertEqual(limited.inspect(
            request_id="durable-request-0001", lines=self.lines
        ).reference, first.reference)

    def test_non_preview_paths_and_commercial_commit_denied(self):
        for path in (":memory:", "/tmp/production.db", self.path + ".backup"):
            with self.subTest(path=path):
                with self.assertRaises((ValueError, PermissionError)):
                    DurablePreviewSaleJournal(path)
        with self.assertRaises(PermissionError):
            self.journal.commit(license_valid=True)


if __name__ == "__main__":
    unittest.main()
