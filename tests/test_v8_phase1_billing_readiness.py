"""Phase 1: discount, cash estimate and stock readiness for draft-only billing."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from decimal import Decimal
from pathlib import Path

from velopos_qt.preview_models import (
    Cart, cash_estimate, preview_existing_bill, validated_discount,
)


class DraftAmountRulesTests(unittest.TestCase):
    def setUp(self):
        self.cart = Cart()
        self.cart.add({
            "barcode": "TEST-BILL",
            "name_en": "Test Rice",
            "selling_price": "120.00",
        }, quantity=2)

    def test_discount_is_bounded_and_not_written_to_cart(self):
        self.assertEqual(validated_discount("40", self.cart.subtotal()), Decimal("40.00"))
        before = dict(self.cart.lines["TEST-BILL"])
        for bad in ("-1", "nan", "inf", "241", "not-money"):
            with self.subTest(discount=bad), self.assertRaises(ValueError):
                preview_existing_bill(self.cart, lambda *args: None, bad)
        self.assertEqual(self.cart.lines["TEST-BILL"], before)

    def test_original_preview_callback_receives_validated_discount(self):
        observed = []
        def calculate(items, discount, redeem):
            observed.append((items, discount, redeem))
            return {"net": 200.0}
        result = preview_existing_bill(self.cart, calculate, "40")
        self.assertEqual(result["net"], 200)
        self.assertEqual(observed[0][1:], (40.0, 0.0))

    def test_cash_change_and_shortfall_are_read_only(self):
        self.assertEqual(cash_estimate("225.50", "300")["change"], Decimal("74.50"))
        self.assertEqual(cash_estimate("225.50", "200")["shortfall"], Decimal("25.50"))
        self.assertEqual(cash_estimate("225.50", "225.50")["change"], Decimal("0.00"))
        with self.assertRaises(ValueError):
            cash_estimate("100", "-1")


class StockReadinessIntegrationTests(unittest.TestCase):
    def test_discount_and_tax_preview_matches_original_service(self):
        with tempfile.TemporaryDirectory(prefix="v8_tax_preview_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            source = textwrap.dedent(
                """
                from velopos import database, services
                from velopos_qt.preview_models import Cart, preview_existing_bill
                database.init_db()
                services.save_product("TX-1", "Taxable", "preview", sell=100, stock=8, taxable=True)
                services.save_product("TX-2", "Untaxed", "preview", sell=60, stock=8, taxable=False)
                database.settings.set_many({
                    "feat_vat": "1", "vat_percent": "10",
                    "vat_mode": "Exclusive",
                })
                cart = Cart()
                cart.add({"barcode": "TX-1", "name_en": "Taxable", "selling_price": 100})
                cart.add({"barcode": "TX-2", "name_en": "Untaxed", "selling_price": 60})
                original = services.preview_bill([
                    {"barcode": "TX-1", "name": "Taxable", "qty": 1, "price": 100},
                    {"barcode": "TX-2", "name": "Untaxed", "qty": 1, "price": 60},
                ], 20, 0)
                draft = preview_existing_bill(cart, services.preview_bill, discount="20")
                assert draft == original, (draft, original)
                assert draft["net"] > 140, draft
                with database.db() as c:
                    assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", source],
                env=env, text=True, capture_output=True, timeout=40,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_expired_product_and_batch_are_flagged_without_writing(self):
        with tempfile.TemporaryDirectory(prefix="v8_expiry_draft_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            source = textwrap.dedent(
                """
                from velopos import database, services
                from velopos_qt.billing_readiness import DraftStockReader
                from velopos_qt.preview_models import Cart
                database.init_db()
                services.save_product("EXP-A", "Expired Product", "test",
                                      sell=20, stock=5, expiry="2026-11-01")
                services.save_product("EXP-B", "Expired Batch", "test",
                                      sell=30, stock=5)
                services.save_product("GOOD", "Not Expired", "test",
                                      sell=40, stock=5)
                with database.db() as connection:
                    connection.execute(
                        "INSERT INTO batches(barcode,batch_no,expiry_date,qty_remaining)"
                        "VALUES('EXP-B','B1','2026-10-31',3)"
                    )
                    connection.execute(
                        "INSERT INTO batches(barcode,batch_no,expiry_date,qty_remaining)"
                        "VALUES('GOOD','EMPTY','2026-10-31',0)"
                    )
                cart = Cart()
                for barcode, name, price in (
                    ("EXP-A", "Expired Product", 20),
                    ("EXP-B", "Expired Batch", 30),
                    ("GOOD", "Not Expired", 40),
                ):
                    cart.add({"barcode": barcode, "name_en": name,
                              "selling_price": price})
                reader = DraftStockReader(database)
                signals = {
                    x["barcode"]: x["status"]
                    for x in reader.inspect(cart, today="2026-11-04")
                }
                assert signals == {
                    "EXP-A": "expired", "EXP-B": "expired_batch"
                }, signals
                with database.db() as connection:
                    assert connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
                    assert connection.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0] == 3
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", source],
                env=env, text=True, capture_output=True, timeout=40,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_stock_and_changed_price_warnings_with_no_writes(self):
        with tempfile.TemporaryDirectory(prefix="v8_stock_readiness_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            source = textwrap.dedent(
                """
                from velopos import database, services
                from velopos_qt.billing_readiness import DraftStockReader
                from velopos_qt.preview_models import Cart
                database.init_db()
                services.save_product("ST-1", "Rice", "preview", sell=100, stock=2)
                services.save_product("ST-2", "Soap", "preview", sell=50, stock=10)
                cart = Cart()
                cart.add({"barcode": "ST-1", "name_en": "Rice", "selling_price": 100}, quantity=3)
                cart.add({"barcode": "ST-2", "name_en": "Soap", "selling_price": 40}, quantity=1)
                cart.add({"barcode": "ST-404", "name_en": "Gone", "selling_price": 10})
                reader = DraftStockReader(database)
                with database.db() as c:
                    before = c.total_changes
                    stock_before = [tuple(r) for r in c.execute(
                        "SELECT barcode,stock_qty FROM products ORDER BY barcode"
                    )]
                statuses = {r["barcode"]: r["status"] for r in reader.inspect(cart)}
                assert statuses == {
                    "ST-1": "insufficient",
                    "ST-2": "price_changed",
                    "ST-404": "missing",
                }, statuses
                with database.db() as c:
                    assert [tuple(r) for r in c.execute(
                        "SELECT barcode,stock_qty FROM products ORDER BY barcode"
                    )] == stock_before
                    assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", source],
                env=env, text=True, capture_output=True, timeout=40,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
