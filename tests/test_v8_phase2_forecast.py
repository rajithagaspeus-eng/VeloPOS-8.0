"""Historical demand baseline: sparse-data refusal, isolation and original sale ledger."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from decimal import Decimal
from pathlib import Path

from velopos_qt.forecast_model import demand_baseline, walk_forward_backtest


class DemandBaselineTests(unittest.TestCase):
    def test_weighted_7_and_28_day_baseline(self):
        history = [Decimal("1")] * 21 + [Decimal("3")] * 7
        result = demand_baseline(history, horizon=7, stock=21)
        self.assertEqual(result["status"], "baseline")
        self.assertEqual(result["observed_sale_days"], 28)
        self.assertEqual(result["units_28d"], Decimal("42"))
        self.assertEqual(result["units_7d"], Decimal("21"))
        self.assertEqual(result["units_expected"], Decimal("15.75"))
        self.assertEqual(result["stock_coverage_days"], Decimal("9.3"))

    def test_backtest_uses_three_prior_only_windows(self):
        regular = walk_forward_backtest([1] * 49)
        self.assertEqual(regular["evaluated_windows"], 3)
        self.assertEqual(regular["mean_absolute_error"], Decimal("0.00"))
        # The final seven held-out days must not influence any training
        # window that evaluates an earlier period.
        surprise = walk_forward_backtest([1] * 42 + [8] * 7)
        self.assertEqual(surprise["evaluated_windows"], 3)
        self.assertEqual(surprise["mean_absolute_error"], Decimal("16.33"))
        sparse = walk_forward_backtest([0] * 44 + [1] * 5)
        self.assertEqual(sparse["evaluated_windows"], 0)
        self.assertIsNone(sparse["mean_absolute_error"])
        for history in ([1]*48, [1]*48+[float("nan")], [1]*48+[-1]):
            with self.subTest(last=history[-1]), self.assertRaises(ValueError):
                walk_forward_backtest(history)

    def test_sparse_or_invalid_data_does_not_make_up_predictions(self):
        result = demand_baseline([0]*25+[1,2,3], horizon=7)
        self.assertEqual(result["status"], "insufficient")
        self.assertIsNone(result["units_expected"])
        self.assertIsNone(result["stock_coverage_days"])
        for history in ([0]*27, [0]*27+[float("nan")],
                        [0]*27+[-1], [0]*27+[float("inf")]):
            with self.subTest(history=history[-1]), self.assertRaises(ValueError):
                demand_baseline(history)
        for horizon in (0, 31, "1; DROP TABLE sales", True):
            with self.subTest(horizon=horizon), self.assertRaises(ValueError):
                demand_baseline([1]*28, horizon=horizon)


class DemandLedgerTests(unittest.TestCase):
    def isolated(self, script, directory="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_forecast_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / directory)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ledger_excludes_voids_incomplete_day_and_scarce_history(self):
        self.isolated(
            """
            from decimal import Decimal
            from datetime import date, timedelta
            from velopos import database
            from velopos_qt.forecast_model import DemandForecastReader
            database.init_db()
            as_of = date(2026,11,4)
            with database.db() as c:
                for barcode, stock in [("GOOD",20),("SPARSE",10)]:
                    c.execute(
                        "INSERT INTO products(barcode,name_en,stock_qty) VALUES(?,?,?)",
                        (barcode, barcode, stock),
                    )
                for n in range(28):
                    day = (as_of - timedelta(days=28-n)).isoformat()
                    c.execute(
                        "INSERT INTO sales(invoice_no,date,time,total_amount,profit,status)"
                        "VALUES(?,?,?,100,10,'OK')", (f"INV{n}",day,"10:00")
                    )
                    c.execute(
                        "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,total)"
                        "VALUES(?,?,?,?,?)", (f"INV{n}","GOOD","Good",2,100)
                    )
                c.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,total)"
                    "VALUES('INV27','SPARSE','Sparse',1,5)"
                )
                c.execute(
                    "INSERT INTO sales(invoice_no,date,time,total_amount,profit,status)"
                    "VALUES('VOID','2026-11-03','12:00',500,250,'VOID')"
                )
                c.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,total)"
                    "VALUES('VOID','GOOD','Good',100,500)"
                )
                c.execute(
                    "INSERT INTO sales(invoice_no,date,time,total_amount,profit,status)"
                    "VALUES('TODAY','2026-11-04','12:00',500,250,'OK')"
                )
                c.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,total)"
                    "VALUES('TODAY','GOOD','Good',100,500)"
                )
            state = {"admin": False}
            reader = DemandForecastReader(database, authorize=lambda: state["admin"])
            try:
                reader.snapshot(as_of="2026-11-04")
            except PermissionError:
                pass
            else:
                raise AssertionError("Unauthorized demand access")
            state["admin"] = True
            snap = reader.snapshot(as_of="2026-11-04", horizon=7)
            indexed = {x["barcode"]: x for x in snap["products"]}
            assert indexed["GOOD"]["units_28d"] == Decimal("56"), snap
            assert indexed["GOOD"]["units_7d"] == Decimal("14"), snap
            assert indexed["GOOD"]["units_expected"] == Decimal("14.00"), snap
            assert indexed["SPARSE"]["status"] == "insufficient", snap
            assert indexed["SPARSE"]["units_expected"] is None
            assert snap["history_to"] == "2026-11-03"
            assert snap["ready_products"] == 1
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 30
                assert c.execute("SELECT COUNT(*) FROM sale_items").fetchone()[0] == 31
            state["admin"] = False
            try:
                reader.snapshot(as_of="2026-11-04")
            except PermissionError:
                pass
            else:
                raise AssertionError("Logout did not revoke demand access")
            """
        )

    def test_historical_backtest_respects_voids_and_incomplete_day(self):
        self.isolated(
            """
            from datetime import date, timedelta
            from decimal import Decimal
            from velopos import database
            from velopos_qt.forecast_model import DemandForecastReader
            database.init_db()
            as_of = date(2026,11,4)
            with database.db() as c:
                c.execute("INSERT INTO products(barcode,name_en,stock_qty) "
                          "VALUES('BT-1','Backtest',30)")
                for n in range(49):
                    day = (as_of-timedelta(days=49-n)).isoformat()
                    c.execute(
                        "INSERT INTO sales(invoice_no,date,status) VALUES(?,?,'OK')",
                        (f"BT{n}",day)
                    )
                    c.execute(
                        "INSERT INTO sale_items(invoice_no,barcode,qty,total) "
                        "VALUES(?,'BT-1',1,10)", (f"BT{n}",)
                    )
                c.execute("INSERT INTO sales(invoice_no,date,status) "
                          "VALUES('BT-VOID','2026-11-02','VOID')")
                c.execute("INSERT INTO sale_items(invoice_no,barcode,qty,total) "
                          "VALUES('BT-VOID','BT-1',500,5000)")
                c.execute("INSERT INTO sales(invoice_no,date,status) "
                          "VALUES('BT-TODAY','2026-11-04','OK')")
                c.execute("INSERT INTO sale_items(invoice_no,barcode,qty,total) "
                          "VALUES('BT-TODAY','BT-1',500,5000)")
            reader = DemandForecastReader(database, authorize=lambda: True)
            snap = reader.snapshot(as_of="2026-11-04")
            record = snap["products"][0]
            assert record["units_28d"] == Decimal("28"), record
            assert record["backtest"]["evaluated_windows"] == 3
            assert record["backtest"]["mean_absolute_error"] == Decimal("0.00")
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 51
            """
        )

    def test_nonpreview_storage_denied(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.forecast_model import DemandForecastReader
            database.init_db()
            try:
                DemandForecastReader(database, authorize=lambda: True)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Production-like directory permitted")
            """, directory="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
