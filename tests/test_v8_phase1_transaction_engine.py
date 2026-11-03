"""Phase 1: original transactional sale engine, isolated TEST database only.

This DOES NOT enable Qt checkout. It characterizes existing stock rollback
and audit behavior so a future authenticated wrapper can be integrated safely.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class LegacyTransactionEngineTests(unittest.TestCase):
    def run_in_preview(self, source):
        with tempfile.TemporaryDirectory(prefix="v8_engine_regression_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(source)],
                env=env, text=True, capture_output=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_successful_legacy_sale_commits_stock_and_audit_atomically(self):
        self.run_in_preview(
            """
            from velopos import database, services
            database.init_db()
            services.save_product("ENG-01", "Test Rice", "preview", cost=50, sell=100, stock=8)
            cart = [{"barcode": "ENG-01", "name": "Test Rice", "qty": 2,
                     "price": 100, "serial": "", "warranty": ""}]
            estimate = services.preview_bill(cart)
            sale = services.create_sale(cart, 0, 0, 1000, "Cash", "", None,
                                        "engine-test", shift_id=None)
            assert abs(sale["net"] - estimate["net"]) < 0.01
            with database.db() as c:
                stock = c.execute(
                    "SELECT stock_qty FROM products WHERE barcode='ENG-01'"
                ).fetchone()[0]
                bills = c.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
                audit = c.execute(
                    "SELECT COUNT(*) FROM audit_log WHERE action='SALE'"
                ).fetchone()[0]
                moves = c.execute(
                    "SELECT COALESCE(SUM(qty_change),0) FROM stock_moves "
                    "WHERE barcode='ENG-01' AND reason='SALE'"
                ).fetchone()[0]
                assert stock == 6 and bills == 1 and audit == 1
                assert moves == -2, (stock, moves)
            """
        )

    def test_not_enough_stock_rolls_back_all_sale_side_effects(self):
        self.run_in_preview(
            """
            from velopos import database, services
            database.init_db()
            services.save_product("ENG-02", "Test Notebook", "preview",
                                  cost=20, sell=80, stock=1)
            cart = [{"barcode": "ENG-02", "name": "Test Notebook",
                     "qty": 3, "price": 80}]
            with database.db() as c:
                before = (
                    c.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
                    c.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0],
                )
            try:
                services.create_sale(cart, 0, 0, 1000, "Cash", "", None,
                                     "engine-test", shift_id=None)
            except ValueError as error:
                assert "Not enough stock" in str(error), error
            else:
                raise AssertionError("Overselling must not succeed by default")
            with database.db() as c:
                after = (
                    c.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
                    c.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0],
                )
                assert before == after, (before, after)
                assert c.execute(
                    "SELECT stock_qty FROM products WHERE barcode='ENG-02'"
                ).fetchone()[0] == 1
            """
        )


if __name__ == "__main__":
    unittest.main()
