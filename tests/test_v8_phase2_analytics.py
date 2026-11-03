"""Admin historical analytics integration tests against the original report ledger."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class AnalyticsIntegrationTests(unittest.TestCase):
    def isolated(self, script, folder="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_analytics_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / folder)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_trend_reconciles_returns_expenses_and_original_reports(self):
        self.isolated(
            """
            from decimal import Decimal
            from velopos import database
            from velopos_qt.analytics_model import BusinessIntelligenceReader
            from velopos_qt.reports_model import PreviewReportsReader
            database.init_db()
            with database.db() as c:
                c.execute(
                    "INSERT INTO sales(invoice_no,date,time,total_amount,profit,status) "
                    "VALUES('SALE-A','2026-11-01','10:00',300,110,'OK')"
                )
                c.execute(
                    "INSERT INTO sales(invoice_no,date,time,total_amount,profit,status) "
                    "VALUES('SALE-B','2026-11-01','11:00',200,80,'OK')"
                )
                c.execute(
                    "INSERT INTO sales(invoice_no,date,time,total_amount,profit,status) "
                    "VALUES('VOID','2026-11-02','11:00',999,999,'VOID')"
                )
                c.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,total) "
                    "VALUES('SALE-A','RICE','Rice',2,200)"
                )
                c.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,total) "
                    "VALUES('SALE-A','SOAP','Soap',1,100)"
                )
                c.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,total) "
                    "VALUES('SALE-B','RICE','Rice',2,200)"
                )
                c.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,total) "
                    "VALUES('VOID','SOAP','Soap',20,999)"
                )
                c.execute(
                    "INSERT INTO returns(return_no,invoice_no,date,amount,profit_adj) "
                    "VALUES('RET-A','SALE-A','2026-11-02',50,-20)"
                )
                c.execute(
                    "INSERT INTO expenses(date,category,amount) "
                    "VALUES('2026-11-02','Rent',30)"
                )
                c.execute(
                    "INSERT INTO expenses(date,category,amount) "
                    "VALUES('2026-11-02','Electricity',10)"
                )
            analytic = BusinessIntelligenceReader(database, authorize=lambda: True)
            snap = analytic.snapshot("2026-11-01", "2026-11-03")
            legacy = PreviewReportsReader(database).snapshot("2026-11-01", "2026-11-03")
            assert snap["sales_total"] == legacy["sales_total"] == Decimal("500.00")
            assert snap["refunds_total"] == legacy["returns_total"] == Decimal("50.00")
            assert snap["net_revenue"] == legacy["net_revenue"] == Decimal("450.00")
            assert snap["indicative_net"] == legacy["indicative_net"] == Decimal("130.00")
            assert len(snap["daily"]) == 2, snap
            assert snap["daily"][0]["bills"] == 2
            assert snap["daily"][0]["net_revenue"] == Decimal("500.00")
            assert snap["daily"][1]["net_revenue"] == Decimal("-50.00")
            assert snap["daily"][1]["indicative_net"] == Decimal("-60.00")
            assert [p["barcode"] for p in snap["top_products"]] == ["RICE","SOAP"]
            assert snap["top_products"][0]["qty"] == 4
            assert len(snap["expenses_by_category"]) == 2
            assert sum(e["total"] for e in snap["expenses_by_category"]) == Decimal("40.00")
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 3
                assert c.execute("SELECT COUNT(*) FROM returns").fetchone()[0] == 1
                assert c.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 2
            """
        )

    def test_admin_revocation_input_limits_and_nonpreview_guard(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.analytics_model import BusinessIntelligenceReader
            database.init_db()
            state = {"admin": False}
            reader = BusinessIntelligenceReader(
                database, authorize=lambda: state["admin"]
            )
            try:
                reader.snapshot("2026-11-01", "2026-11-04")
            except PermissionError:
                pass
            else:
                raise AssertionError("Logged-out analytics exposed")
            state["admin"] = True
            reader.snapshot("2026-11-01", "2026-11-04")
            for start, end in (
                ("2026-11-05", "2026-11-01"),
                ("2025-01-01", "2026-11-04"),
                ("2026-02-30", "2026-11-04"),
            ):
                try:
                    reader.snapshot(start, end)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Bad analytics range passed")
            state["admin"] = False
            try:
                reader.snapshot("2026-11-01", "2026-11-04")
            except PermissionError:
                pass
            else:
                raise AssertionError("Logout did not revoke analytics")
            """
        )
        self.isolated(
            """
            from velopos import database
            from velopos_qt.analytics_model import BusinessIntelligenceReader
            database.init_db()
            try:
                BusinessIntelligenceReader(database, authorize=lambda: True)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Non-preview path permitted")
            """, folder="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
