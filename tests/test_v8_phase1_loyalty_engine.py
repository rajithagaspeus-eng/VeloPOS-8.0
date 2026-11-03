"""Original VeloPOS loyalty earn/redeem boundary, TEST database only.

Verifies the real service's immutable production behavior WITHOUT enabling any
transaction through the Qt preview. All writes are in a disposable subprocess.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class LegacyLoyaltyCompatibilityTests(unittest.TestCase):
    def test_full_paid_sale_earns_points_and_failed_redemption_rolls_back(self):
        with tempfile.TemporaryDirectory(prefix="v8_loyalty_legacy_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            script = textwrap.dedent(
                """
                from decimal import Decimal
                from velopos import database, services
                from velopos_qt.customer_loyalty import projected_points_for_paid_bill
                database.init_db()
                services.save_product(
                    "LOYAL-1", "Test Item", "preview",
                    cost=50, sell=125, stock=10,
                )
                with database.db() as c:
                    cid = c.execute(
                        "INSERT INTO customers(name,phone,loyalty_points) "
                        "VALUES('Test Buyer','0711234567',0)"
                    ).lastrowid
                cart = [{"barcode":"LOYAL-1", "name":"Test Item", "qty":2,
                         "price":125, "serial":"", "warranty":""}]
                preview = services.preview_bill(cart, 0, 0)
                before = projected_points_for_paid_bill(preview["net"])
                sale = services.create_sale(
                    cart, 0, 0, preview["net"], "Cash", "",
                    cid, "preview-cashier", shift_id=None,
                )
                assert sale["net"] == preview["net"]
                with database.db() as c:
                    points = c.execute(
                        "SELECT loyalty_points FROM customers WHERE id=?", (cid,)
                    ).fetchone()[0]
                    assert Decimal(str(points)).quantize(Decimal("0.01")) == before
                    assert c.execute(
                        "SELECT stock_qty FROM products WHERE barcode='LOYAL-1'"
                    ).fetchone()[0] == 8
                    bills_before = c.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
                    moves_before = c.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0]
                try:
                    services.create_sale(
                        cart, 0, 9999, preview["net"], "Cash", "",
                        cid, "preview-cashier", shift_id=None,
                    )
                except ValueError:
                    pass
                else:
                    raise AssertionError("Excess loyalty redemption was accepted")
                with database.db() as c:
                    assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == bills_before
                    assert c.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0] == moves_before
                    assert c.execute(
                        "SELECT stock_qty FROM products WHERE barcode='LOYAL-1'"
                    ).fetchone()[0] == 8
                    assert Decimal(str(c.execute(
                        "SELECT loyalty_points FROM customers WHERE id=?", (cid,)
                    ).fetchone()[0])).quantize(Decimal("0.01")) == before
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", script], env=env,
                capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
