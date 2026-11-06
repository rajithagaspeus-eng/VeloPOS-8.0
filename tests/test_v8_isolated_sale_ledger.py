"""RAM-only atomic sale rehearsal checks; never access a production DB."""
import unittest
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from velopos_qt.isolated_sale_ledger import IsolatedSaleLedger


class IsolatedSaleLedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = IsolatedSaleLedger({"RICE": "10", "SOAP": "3"})
        self.lines = [{"barcode": "RICE", "qty": "2", "price": "12.50"},
                      {"barcode": "SOAP", "qty": "1", "price": "0.10"}]

    def test_valid_persisted_request_id_reconciles_and_replays_exactly_once(self):
        result = self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(self.ledger.reconcile()["reconciled_requests"], 1)
        snapshot = self.ledger.snapshot()
        replay = self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(result.reference, replay.reference)
        self.assertTrue(replay.replayed)
        self.assertEqual(snapshot, self.ledger.snapshot())

    def test_persisted_request_id_with_literal_backslash_z_fails_closed(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE requests SET request_id=?",
            ("ram-sale-0001" + chr(92) + "Z",),
        )
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "request metadata mismatch"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_corrupt_persisted_request_id_blocks_replay_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE requests SET request_id=?",
            ("X" * 129,))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "request metadata mismatch"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_corrupt_persisted_request_id_blocks_new_rehearsal(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE requests SET request_id=?",
            ("invalid request id",))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "request metadata mismatch"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_blob_persisted_request_id_blocks_replay_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE requests SET request_id=?", (b"ram-sale-0001",))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "request metadata mismatch"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_corrupt_reference_sequence_blocks_new_rehearsal_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE requests SET reference='RAM-REHEARSAL-00000009'")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "request metadata mismatch"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_blob_line_amount_blocks_replay_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE items SET line_cents=? WHERE barcode='RICE'", (b"2500",))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "item amount mismatch"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_fractional_line_amount_blocks_new_rehearsal_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE items SET line_cents=? WHERE barcode='RICE'", (2500.5,))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "item amount mismatch"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_blob_item_quantity_blocks_replay_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE items SET qty=? WHERE barcode='RICE'", (b"2",))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "Invalid RAM rehearsal item quantity"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_oversized_item_quantity_blocks_new_rehearsal_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE items SET qty=? WHERE barcode='RICE'", ("9" * 129,))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "Invalid RAM rehearsal item quantity"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_blob_stock_quantity_blocks_replay_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE stock SET qty=? WHERE barcode='RICE'", (b"8",))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "Invalid RAM rehearsal stock"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_oversized_stock_quantity_blocks_new_rehearsal_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE stock SET qty=? WHERE barcode='RICE'", ("9" * 129,))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "Invalid RAM rehearsal stock"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

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

    def test_reconciliation_detects_stock_tampering(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE stock SET qty='9' WHERE barcode='RICE'")
        with self.assertRaisesRegex(ValueError, "stock movement mismatch"):
            self.ledger.reconcile()

    def test_reconciliation_detects_journal_tampering(self):
        result = self.ledger.inspect(
            request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE journal SET amount_cents=1 "
            "WHERE reference=? AND account='demo_sales'",
            (result.reference,))
        with self.assertRaisesRegex(ValueError, "accounting mismatch"):
            self.ledger.reconcile()

    def test_reconciliation_detects_orphan_rows(self):
        self.ledger._db.execute("PRAGMA foreign_keys=OFF")
        try:
            self.ledger._db.execute(
                "INSERT INTO journal VALUES ('ORPHAN','demo_sales',0)")
            with self.assertRaisesRegex(ValueError, "Orphan"):
                self.ledger.reconcile()
        finally:
            self.ledger._db.execute("PRAGMA foreign_keys=ON")

    def test_high_precision_stock_is_not_rounded_by_host_context(self):
        ledger = IsolatedSaleLedger({
            "RICE": "1.00000000000000000000000000000000001"})
        result = ledger.inspect(
            request_id="ram-precision-0001",
            lines=[{"barcode": "RICE", "qty": "1",
                    "price": "1.00"}])
        self.assertEqual(result.subtotal_cents, 100)
        self.assertEqual(Decimal(dict(ledger.snapshot()["stock"])["RICE"]),
                         Decimal("0.00000000000000000000000000000000001"))
        self.assertTrue(ledger.reconcile()["balanced"])

    def test_unbounded_initial_stock_representation_is_rejected(self):
        with self.assertRaises(ValueError):
            IsolatedSaleLedger({"RICE": "0." + "0" * 200 + "1"})

    def test_tampered_history_blocks_new_sale_without_mutation(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE journal SET amount_cents=999 "
            "WHERE account='demo_receivable'")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "accounting mismatch"):
            self.ledger.inspect(
                request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_tampered_history_blocks_replay_without_mutation(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE stock SET qty='999' WHERE barcode='RICE'")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "stock movement mismatch"):
            self.ledger.inspect(
                request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_metadata_reference_chain_tampering_blocks_replay(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE requests SET fingerprint=? WHERE request_id=?",
            ("not-a-digest", "ram-sale-0001"))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "metadata mismatch"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_invalid_item_amount_blocks_new_sale(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute("UPDATE items SET line_cents=-1")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "item amount mismatch"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_foreign_key_violation_blocks_rehearsal(self):
        self.ledger._db.execute("PRAGMA foreign_keys=OFF")
        try:
            self.ledger._db.execute(
                "INSERT INTO items VALUES ('MISSING','SOAP','1',100)")
        finally:
            self.ledger._db.execute("PRAGMA foreign_keys=ON")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "foreign key mismatch"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_missing_journal_leg_blocks_replay_without_writes(self):
        result = self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "DELETE FROM journal WHERE reference=? AND account='demo_sales'",
            (result.reference,))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "accounting mismatch"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_duplicate_journal_leg_blocks_new_sale_without_writes(self):
        result = self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "INSERT INTO journal VALUES (?,?,?)",
            (result.reference, "demo_sales", -result.subtotal_cents))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "accounting mismatch"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_missing_item_blocks_replay_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "DELETE FROM items WHERE barcode='SOAP'")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "item amount mismatch"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_nonfinite_item_quantity_blocks_new_rehearsal(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE items SET qty='NaN' WHERE barcode='RICE'")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "item quantity"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_unknown_item_barcode_blocks_replay_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE items SET barcode='UNREGISTERED' WHERE barcode='SOAP'")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "Unknown RAM rehearsal item"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_zero_item_quantity_blocks_new_rehearsal_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE items SET qty='0' WHERE barcode='SOAP'")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "Invalid RAM rehearsal item quantity"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_negative_item_quantity_blocks_replay_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE items SET qty='-1' WHERE barcode='SOAP'")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "Invalid RAM rehearsal item quantity"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_removed_stock_catalog_row_blocks_new_rehearsal(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute("DELETE FROM stock WHERE barcode='SOAP'")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "stock catalog mismatch"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_nonfinite_stock_blocks_replay_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE stock SET qty='NaN' WHERE barcode='RICE'")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "Invalid RAM rehearsal stock"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_negative_stock_blocks_new_rehearsal_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE stock SET qty='-1' WHERE barcode='SOAP'")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "Invalid RAM rehearsal stock"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_text_subtotal_corruption_blocks_replay_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE requests SET subtotal_cents='corrupt'")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "subtotal mismatch"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_negative_subtotal_corruption_blocks_new_sale_without_writes(self):
        self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE requests SET subtotal_cents=-1")
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "subtotal mismatch"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_blob_journal_amount_blocks_replay_without_writes(self):
        result = self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE journal SET amount_cents=? "
            "WHERE reference=? AND account='demo_receivable'",
            (b"2510", result.reference))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "accounting mismatch"):
            self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_real_journal_amount_blocks_new_sale_without_writes(self):
        result = self.ledger.inspect(request_id="ram-sale-0001", lines=self.lines)
        self.ledger._db.execute(
            "UPDATE journal SET amount_cents=? "
            "WHERE reference=? AND account='demo_sales'",
            (-2510.5, result.reference))
        before = self.ledger.snapshot()
        with self.assertRaisesRegex(ValueError, "accounting mismatch"):
            self.ledger.inspect(request_id="ram-sale-0002", lines=self.lines)
        self.assertEqual(before, self.ledger.snapshot())

    def test_commercial_commit_always_denied(self):
        before = self.ledger.snapshot()
        with self.assertRaises(PermissionError):
            self.ledger.commit(is_admin=True, license_valid=True)
        self.assertEqual(before, self.ledger.snapshot())


if __name__ == "__main__":
    unittest.main()
