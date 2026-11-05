"""RAM-only atomic sale rehearsal checks; never access a production DB."""
import unittest
from velopos_qt.isolated_sale_ledger import IsolatedSaleLedger


class IsolatedSaleLedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = IsolatedSaleLedger({"RICE": "10", "SOAP": "3"})
        self.lines = [{"barcode": "RICE", "qty": "2", "price": "12.50"},
                      {"barcode": "SOAP", "qty": "1", "price": "0.10"}]

    def test_atomic_lines_stock_and_balanced_journal(self):
        result = self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        snapshot = self.ledger.snapshot()
        self.assertEqual(result.subtotal_cents, 2510)
        self.assertEqual(dict(snapshot["stock"]), {"RICE": "8", "SOAP": "2"})
        self.assertEqual(sum(row[2] for row in snapshot["journal"]), 0)
        self.assertEqual(sum(row[3] for row in snapshot["items"]), 2510)
        self.assertFalse(result.can_checkout)
        self.assertFalse(result.can_post)

    def test_replay_does_not_double_deduct(self):
        first = self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        before = self.ledger.snapshot()
        replay = self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(first.reference, replay.reference)
        self.assertTrue(replay.replayed)
        self.assertEqual(before, self.ledger.snapshot())

    def test_changed_request_fails_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        before = self.ledger.snapshot()
        with self.assertRaises(ValueError):
            self.ledger.inspect(request_id="ram-sale-0001", lines=[
                {"barcode": "RICE", "qty": "3", "price": "12.50"}])
        self.assertEqual(before, self.ledger.snapshot())

    def test_insufficient_stock_is_atomic(self):
        before = self.ledger.snapshot()
        with self.assertRaises(ValueError):
            self.ledger.inspect(request_id="ram-sale-0001", lines=[
                {"barcode": "SOAP", "qty": "4", "price": "0.10"}])
        self.assertEqual(before, self.ledger.snapshot())

    def test_injected_failure_rolls_back_every_table(self):
        before = self.ledger.snapshot()
        with self.assertRaises(RuntimeError):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines,
                                inject_failure=True)
        self.assertEqual(before, self.ledger.snapshot())
        result = self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(result.reference, "RAM-REHEARSAL-00000001")

    def test_commercial_commit_always_denied(self):
        before = self.ledger.snapshot()
        with self.assertRaises(PermissionError):
            self.ledger.commit(is_admin=True, license_valid=True)
        self.assertEqual(before, self.ledger.snapshot())


if __name__ == "__main__":
    unittest.main()
