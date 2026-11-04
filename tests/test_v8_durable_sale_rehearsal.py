"""Disposable SQLite sale rehearsal crash recovery and idempotency tests."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
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
