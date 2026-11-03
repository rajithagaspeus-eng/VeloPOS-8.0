"""Phase 1 larger batch: report totals, audit history and data isolation."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import date
from pathlib import Path

from velopos_qt.reports_model import _date


class ReportingInputTests(unittest.TestCase):
    def test_strict_dates(self):
        self.assertEqual(_date("2026-11-04"), "2026-11-04")
        for value in ("2026-1-1", "2026-02-30", "abc", "", "2026-12-01' OR 1=1 --"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _date(value)


class ReportingIntegrationTests(unittest.TestCase):
    def isolated(self, code, directory="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_reporting_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / directory)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(code)],
                capture_output=True, text=True, timeout=40, env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_financial_totals_exclude_voids_and_read_only(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.reports_model import PreviewReportsReader
            database.init_db()
            with database.db() as c:
                c.execute(
                    "INSERT INTO sales(invoice_no,date,time,total_amount,profit,status,payment_method) "
                    "VALUES('INV-1','2026-11-01','10:00',100.50,30.25,'OK','Cash')"
                )
                c.execute(
                    "INSERT INTO sales(invoice_no,date,time,total_amount,profit,status,payment_method) "
                    "VALUES('INV-2','2026-11-02','10:00',200.00,70.00,'OK','Card')"
                )
                c.execute(
                    "INSERT INTO sales(invoice_no,date,time,total_amount,profit,status,payment_method) "
                    "VALUES('VOID-1','2026-11-02','10:00',500.00,500.00,'VOID','Cash')"
                )
                c.execute(
                    "INSERT INTO expenses(date,category,description,amount,added_by) "
                    "VALUES('2026-11-02','Rent','Test',25.50,'test')"
                )
                c.execute(
                    "INSERT INTO audit_log(ts,user,action,detail) "
                    "VALUES('2026-11-02','admin','TEST_EVENT','private detail')"
                )
            report = PreviewReportsReader(database)
            s = report.snapshot('2026-11-01','2026-11-04')
            assert s['sale_count'] == 2, s
            assert str(s['sales_total']) == '300.50', s
            assert str(s['recorded_gross_profit']) == '100.25', s
            assert str(s['expenses']) == '25.50', s
            assert str(s['indicative_net']) == '74.75', s
            assert len(s['recent_sales']) == 2, s
            assert report.snapshot('2026-11-03','2026-11-04')['sale_count'] == 0
            activity = report.staff_activity()
            assert activity[0]['action'] == 'TEST_EVENT'
            assert 'detail' not in activity[0]
            try:
                report.snapshot('2026-11-05','2026-11-01')
            except ValueError:
                pass
            else:
                raise AssertionError('invalid date interval accepted')
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 3
                assert c.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 1
            """
        )

    def test_shift_status_is_read_only_and_matches_original_schema(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.shift_model import PreviewShiftReader
            database.init_db()
            reader = PreviewShiftReader(database)
            assert reader.current() is None
            with database.db() as c:
                c.execute(
                    "INSERT INTO shifts(cashier,opened_at,status) "
                    "VALUES('cashier1','2026-11-04T10:00:00','OPEN')"
                )
            shift = reader.current()
            assert shift['cashier'] == 'cashier1' and shift['id'] > 0
            assert shift['opened_at'].startswith('2026-11-04')
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM shifts WHERE status='OPEN'"
                ).fetchone()[0] == 1
            """
        )

    def test_refuses_production_directory(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.reports_model import PreviewReportsReader
            database.init_db()
            try:
                PreviewReportsReader(database)
            except RuntimeError:
                pass
            else:
                raise AssertionError('production-like directory was allowed')
            """, directory="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
