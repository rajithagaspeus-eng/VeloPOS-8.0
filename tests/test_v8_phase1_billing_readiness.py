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
