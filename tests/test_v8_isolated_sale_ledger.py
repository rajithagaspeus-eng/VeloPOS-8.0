"""RAM-only atomic sale rehearsal checks; never access a production DB."""
import unittest
from concurrent.futures import ThreadPoolExecutor
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

    def test_reconciliation_before_and_after_sales(self):
        self.assertEqual(self.ledger.reconcile(),
                         {"reconciled_requests": 0, "total_cents": 0,
                          "balanced": True})
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(self.ledger.reconcile(),
                         {"reconciled_requests": 1, "total_cents": 2510,
                          "balanced": True})

    def test_parallel_identical_replays_are_exactly_once(self):
        def worker(_):
            return self.ledger.inspect(
                request_id="ram-parallel-0001", lines=self.lines)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(worker, range(32)))
        self.assertEqual(len({r.reference for r in results}), 1)
        self.assertEqual(sum(not r.replayed for r in results), 1)
        self.assertEqual(dict(self.ledger.snapshot()["stock"]),
                         {"RICE": "8", "SOAP": "2"})
        self.assertEqual(self.ledger.reconcile()["reconciled_requests"], 1)

    def test_parallel_distinct_requests_do_not_oversell(self):
        lines = [{"barcode": "SOAP", "qty": "2", "price": "1.00"}]
        def worker(i):
            try:
                self.ledger.inspect(request_id=f"ram-race-{i:04d}", lines=lines)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(worker, range(2)))
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), 1)
        self.assertEqual(dict(self.ledger.snapshot()["stock"])["SOAP"], "1")
        self.assertEqual(self.ledger.reconcile()["total_cents"], 200)

    def test_invalid_initial_stock_fails_closed(self):
        for stock in ({"RICE": "NaN"}, {"RICE": "-1"},
                      {" RICE": "1"}, {"RICE": True},
                      {"RICE": "Infinity"}):
            with self.subTest(stock=stock):
                with self.assertRaises(ValueError):
                    IsolatedSaleLedger(stock)

    def test_commercial_commit_always_denied(self):
        before = self.ledger.snapshot()
        with self.assertRaises(PermissionError):
            self.ledger.commit(is_admin=True, license_valid=True)
        self.assertEqual(before, self.ledger.snapshot())


if __name__ == "__main__":
    unittest.main()
