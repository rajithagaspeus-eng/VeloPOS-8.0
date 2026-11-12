"""Batch 05: integration guard for the original read-only billing preview.

Runs in a disposable subprocess with VELOPOS_HOME set before any imports.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class ReadOnlyBillIntegrationTests(unittest.TestCase):
    def test_billing_draft_does_not_insert_sales_or_change_stock(self):
        with tempfile.TemporaryDirectory(prefix="v8_billing_") as root:
            home = Path(root) / "VeloPOS8PreviewData"
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(home)
            script = textwrap.dedent(
                """
                from velopos import database, services
                from velopos_qt.preview_models import Cart, preview_existing_bill
                database.init_db()
                services.save_product("TEST-BILL-01", "Test Rice", "v8-preview",
                                      sell=250, stock=8)
                cart = Cart()
                cart.add({"barcode": "TEST-BILL-01", "name_en": "Test Rice",
                          "selling_price": 250}, quantity=2)
                with database.db() as connection:
                    before = (
                        connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
                        connection.execute("SELECT stock_qty FROM products WHERE barcode=?",
                                           ("TEST-BILL-01",)).fetchone()[0],
                        connection.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0],
                    )
                estimate = preview_existing_bill(cart, services.preview_bill)
                assert estimate["sub"] == 500, estimate
                assert estimate["net"] >= 0, estimate
                with database.db() as connection:
                    after = (
                        connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
                        connection.execute("SELECT stock_qty FROM products WHERE barcode=?",
                                           ("TEST-BILL-01",)).fetchone()[0],
                        connection.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0],
                    )
                assert before == after, (before, after)
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", script],
                env=env, text=True, capture_output=True, timeout=35,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
