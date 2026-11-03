"""Smart inventory regression tests: real schema, ledger, batch expiry and role guard."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class SmartInventoryIntegrationTests(unittest.TestCase):
    def run_isolated(self, code, *, folder="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_smart_stock_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / folder)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(code)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_stock_and_expiry_use_original_schema_without_writes(self):
        self.run_isolated(
            """
            from velopos import database, services
            from velopos_qt.inventory_insights import InventoryInsightsReader
            database.init_db()
            services.save_product("LOW-01", "Low Rice", "demo", sell=80, stock=2)
            services.save_product("GOOD-01", "Long Life", "demo", sell=80, stock=20)
            services.save_product("OLD-01", "Expired Item", "demo", sell=80, stock=4,
                                  expiry="2026-11-01")
            services.save_product("BATCH-01", "Expiring Batch", "demo", sell=80, stock=10)
            with database.db() as c:
                c.execute(
                    "INSERT INTO batches(barcode,batch_no,expiry_date,qty_remaining) "
                    "VALUES('BATCH-01','B1','2026-11-12',5)"
                )
                c.execute(
                    "INSERT INTO batches(barcode,batch_no,expiry_date,qty_remaining) "
                    "VALUES('BATCH-01','B2','2026-11-20',5)"
                )
                c.execute(
                    "INSERT INTO batches(barcode,batch_no,expiry_date,qty_remaining) "
                    "VALUES('GOOD-01','DEPLETED','2026-10-01',0)"
                )
            reader = InventoryInsightsReader(database, authorize=lambda: True)
            snap = reader.snapshot(low_level=5, expiry_days=30, today="2026-11-04")
            assert snap["low_count"] == 2, snap
            suggested = {
                row["barcode"]: row["suggested_topup"]
                for row in snap["low_rows"]
            }
            assert suggested == {"LOW-01": 4, "OLD-01": 2}, suggested
            assert snap["expired_count"] == 1, snap
            assert snap["expiring_count"] == 1, snap
            assert [x["barcode"] for x in snap["expiry_rows"]] == [
                "OLD-01", "BATCH-01"
            ], snap
            assert snap["expiry_rows"][1]["expiry_date"] == "2026-11-12"
            assert len(snap["movements"]) >= 4
            assert "note" not in snap["movements"][0]
            assert reader.snapshot(low_level=5, expiry_days=30,
                                   limit=1, today="2026-11-04")["low_count"] == 2
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
                assert c.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0] == 4
            """
        )

    def test_reader_refuses_unauthorized_and_invalid_thresholds(self):
        self.run_isolated(
            """
            from velopos import database
            from velopos_qt.inventory_insights import InventoryInsightsReader
            database.init_db()
            state = {"allowed": False}
            reader = InventoryInsightsReader(
                database, authorize=lambda: state["allowed"])
            try:
                reader.snapshot()
            except PermissionError:
                pass
            else:
                raise AssertionError("Unauthorized stock insights")
            state["allowed"] = True
            reader.snapshot()
            for kwargs in ({"low_level": -1}, {"expiry_days": 366},
                           {"low_level": "bad"}, {"today": "2026-02-30"}):
                try:
                    reader.snapshot(**kwargs)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"Invalid filter passed: {kwargs}")
            state["allowed"] = False
            try:
                reader.snapshot()
            except PermissionError:
                pass
            else:
                raise AssertionError("Logout should revoke stock insights")
            """
        )

    def test_nonpreview_storage_is_blocked(self):
        self.run_isolated(
            """
            from velopos import database
            from velopos_qt.inventory_insights import InventoryInsightsReader
            database.init_db()
            try:
                InventoryInsightsReader(database)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Production-like DB must be blocked")
            """, folder="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
