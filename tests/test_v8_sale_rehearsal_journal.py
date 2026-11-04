"""Preview-only in-memory request journal regressions."""
from concurrent.futures import ThreadPoolExecutor
import unittest

from velopos_qt.sale_rehearsal_journal import PreviewSaleRehearsalJournal


class SaleRehearsalJournalTests(unittest.TestCase):
    def setUp(self):
        self.journal = PreviewSaleRehearsalJournal()
        self.lines = [{"barcode": "SOAP", "qty": "2", "price": "0.50"}]

    def test_same_request_is_replayed_without_duplicate_reference(self):
        first = self.journal.inspect(request_id="journal-request-0001", lines=self.lines)
        replay = self.journal.inspect(
            request_id="journal-request-0001",
            lines=[{"price": "0.500", "barcode": "SOAP", "qty": "2.0"}],
        )
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(first.reference, replay.reference)
        self.assertEqual(first.fingerprint, replay.fingerprint)
        self.assertFalse(replay.can_checkout)
        self.assertFalse(replay.can_post)

    def test_changed_payload_with_same_id_is_rejected(self):
        first = self.journal.inspect(request_id="journal-request-0001", lines=self.lines)
        with self.assertRaisesRegex(ValueError, "different payload"):
            self.journal.inspect(
                request_id="journal-request-0001",
                lines=[{"barcode": "SOAP", "qty": "3", "price": "0.50"}],
            )
        replay = self.journal.inspect(
            request_id="journal-request-0001", lines=self.lines
        )
        self.assertEqual(first.reference, replay.reference)

    def test_invalid_request_never_consumes_reference(self):
        with self.assertRaises(ValueError):
            self.journal.inspect(
                request_id="invalid", lines=self.lines
            )
        result = self.journal.inspect(
            request_id="journal-request-0001", lines=self.lines
        )
        self.assertEqual(result.reference, "REHEARSAL-00000001")

    def test_parallel_replays_have_exactly_one_first_observation(self):
        def worker(_):
            return self.journal.inspect(
                request_id="parallel-request-0001", lines=self.lines
            )
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(worker, range(80)))
        self.assertEqual(len({r.reference for r in results}), 1)
        self.assertEqual(sum(not r.replayed for r in results), 1)
        self.assertEqual(sum(r.replayed for r in results), 79)

    def test_distinct_request_ids_receive_distinct_rehearsal_refs(self):
        first = self.journal.inspect(request_id="journal-request-0001", lines=self.lines)
        second = self.journal.inspect(request_id="journal-request-0002", lines=self.lines)
        self.assertNotEqual(first.reference, second.reference)

    def test_capacity_fails_closed_but_existing_replay_survives(self):
        journal = PreviewSaleRehearsalJournal(max_requests=1)
        first = journal.inspect(
            request_id="capacity-request-0001", lines=self.lines
        )
        with self.assertRaises(OverflowError):
            journal.inspect(
                request_id="capacity-request-0002", lines=self.lines
            )
        replay = journal.inspect(
            request_id="capacity-request-0001", lines=self.lines
        )
        self.assertEqual(replay.reference, first.reference)
        self.assertTrue(replay.replayed)

    def test_invalid_capacity_rejected(self):
        for value in (0, -1, True, 100001, "100"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    PreviewSaleRehearsalJournal(max_requests=value)

    def test_commit_always_denied(self):
        with self.assertRaises(PermissionError):
            self.journal.commit(license_valid=True, admin=True)


if __name__ == "__main__":
    unittest.main()
