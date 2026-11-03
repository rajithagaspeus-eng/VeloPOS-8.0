"""Phase 1 purchasing: test original schema, read permissions and no writes."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from decimal import Decimal
from pathlib import Path

from velopos_qt.customer_loyalty import projected_points_for_paid_bill
from velopos_qt.purchasing_model import preview_purchase_line


class PurchaseAndLoyaltyRulesTests(unittest.TestCase):
    def test_line_cost_is_decimal_and_strictly_validated(self):
        self.assertEqual(preview_purchase_line("2.5", "16.25"), Decimal("40.62"))
        self.assertEqual(preview_purchase_line("1", "0"), Decimal("0.00"))
        for qty, cost in [
            ("0", 5), ("-1", 5), ("nan", 5), ("inf", 5),
            ("1000001", 5), ("1", -5), ("1", "NaN"), ("1", "bad")
        ]:
            with self.subTest(qty=qty, cost=cost), self.assertRaises(ValueError):
                preview_purchase_line(qty, cost)

    def test_legacy_points_projection_is_read_only(self):
        self.assertEqual(projected_points_for_paid_bill("250"), Decimal("2.50"))
        self.assertEqual(projected_points_for_paid_bill("0"), Decimal("0.00"))
        self.assertEqual(projected_points_for_paid_bill("1010.01"), Decimal("10.10"))
        for value in ("nan", "inf", "-1", "abc"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                projected_points_for_paid_bill(value)


class PurchaseOverviewIntegrationTests(unittest.TestCase):
    def isolated(self, source, folder="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_purchase_read_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / folder)
            r = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(source)],
                env=env, text=True, capture_output=True, timeout=50,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_original_grn_schema_and_audit_are_read_without_modification(self):
        self.isolated(
            """
            from decimal import Decimal
            from velopos import database, services
            from velopos_qt.purchasing_model import PurchaseOverviewReader
            database.init_db()
            supplier = services.add_supplier("Preview Supplier", "test")
            services.save_product("GRN-P1", "Test Rice", "test", cost=20, sell=40, stock=1)
            snapshot_reader = PurchaseOverviewReader(database, authorize=lambda: True)
            initial = snapshot_reader.snapshot()
            assert initial["purchase_count"] == 0
            assert len(initial["suppliers"]) == 1
            result = services.create_purchase(
                supplier, [{"barcode": "GRN-P1", "qty": 3, "cost": 20}],
                "test", date="2026-11-03", paid_now=0,
            )
            assert result["total"] == 60
            report = snapshot_reader.snapshot(start="2026-11-01", end="2026-11-04")
            assert report["purchase_count"] == 1, report
            assert report["total"] == Decimal("60.0"), report
            assert report["paid"] == Decimal("0.0"), report
            assert report["unpaid_estimate"] == Decimal("60.0"), report
            assert report["recent"][0]["grn_no"] == result["grn_no"]
            assert report["recent"][0]["supplier"] == "Preview Supplier"
            assert report["recent"][0]["status"] == "OK"
            assert snapshot_reader.snapshot(start="2026-11-04", end="2026-11-04")[
                "purchase_count"] == 0
            with database.db() as c:
                assert c.execute("SELECT stock_qty FROM products WHERE barcode='GRN-P1'").fetchone()[0] == 4
                assert c.execute("SELECT COUNT(*) FROM purchases").fetchone()[0] == 1
                assert c.execute("SELECT COUNT(*) FROM purchase_items").fetchone()[0] == 1
                assert c.execute("SELECT COUNT(*) FROM stock_moves WHERE reason='PURCHASE'").fetchone()[0] >= 1
            """
        )

    def test_reader_requires_admin_every_time_and_rejects_invalid_dates(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.purchasing_model import PurchaseOverviewReader
            database.init_db()
            gate = {"admin": False}
            reader = PurchaseOverviewReader(database, authorize=lambda: gate["admin"])
            try:
                reader.snapshot()
            except PermissionError:
                pass
            else:
                raise AssertionError("Purchases visible to non-Admin")
            gate["admin"] = True
            reader.snapshot()
            for settings in (
                {"start":"2026-11-05","end":"2026-11-01"},
                {"start":"2026-02-30"},
                {"limit":"broken"},
            ):
                try:
                    reader.snapshot(**settings)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"Invalid report parameters accepted {settings}")
            gate["admin"] = False
            try:
                reader.snapshot()
            except PermissionError:
                pass
            else:
                raise AssertionError("Purchasing data leaked after logout")
            """
        )

    def test_nonpreview_directory_is_blocked(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.purchasing_model import PurchaseOverviewReader
            database.init_db()
            try:
                PurchaseOverviewReader(database, authorize=lambda: True)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Production-like path accepted")
            """, folder="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
