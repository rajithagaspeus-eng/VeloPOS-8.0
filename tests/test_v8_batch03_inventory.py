"""Batch 03 preview-only inventory writer integration tests.

Runs the original database/service in a fresh subprocess with an isolated
VELOPOS_HOME, never touching any installed shop database.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class InventoryEditIntegrationTests(unittest.TestCase):
    def _child(self, code, home):
        env = os.environ.copy()
        env["VELOPOS_HOME"] = str(home)
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)],
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_add_and_edit_use_original_ledger_and_audit(self):
        with tempfile.TemporaryDirectory(prefix="velopos8_editor_") as folder:
            home = Path(folder) / "VeloPOS8PreviewData"
            self._child(
                """
                from velopos import database
                from velopos_qt.product_editor import PreviewProductEditor
                database.init_db()
                editor = PreviewProductEditor(database)
                result = editor.save("PREVIEW-B01", "Demo Pencil", sell="20.50", stock="7")
                assert result["created"] is True, result
                result = editor.save("PREVIEW-B01", "Demo Pencil", sell="25.00", stock="9")
                assert result["created"] is False, result
                assert editor.get("PREVIEW-B01")["stock_qty"] == 9
                with database.db() as c:
                    assert c.execute(
                        "SELECT COUNT(*) FROM stock_moves WHERE barcode=?",
                        ("PREVIEW-B01",)
                    ).fetchone()[0] >= 2
                    assert c.execute(
                        "SELECT COUNT(*) FROM audit_log WHERE action='PRODUCT_SAVE'"
                    ).fetchone()[0] == 2
                print("inventory ledger and audit OK")
                """,
                home,
            )

    def test_new_demo_stock_seeding_creates_ledger_once(self):
        with tempfile.TemporaryDirectory(prefix="velopos8_seed_") as folder:
            home = Path(folder) / "VeloPOS8PreviewData"
            self._child(
                """
                from velopos import database
                from velopos_qt.demo_data import ensure_preview_products
                database.init_db()
                assert ensure_preview_products(database) == 5
                assert ensure_preview_products(database) == 0
                with database.db() as c:
                    assert c.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 5
                    assert c.execute(
                        "SELECT COUNT(*) FROM stock_moves WHERE reason='OPENING'"
                    ).fetchone()[0] >= 5
                """,
                home,
            )

    def test_invalid_values_do_not_change_stock(self):
        with tempfile.TemporaryDirectory(prefix="velopos8_editor_") as folder:
            home = Path(folder) / "VeloPOS8PreviewData"
            self._child(
                """
                from velopos import database
                from velopos_qt.product_editor import PreviewProductEditor
                database.init_db()
                editor = PreviewProductEditor(database)
                editor.save("TEST-01", "Notebook", sell="10.00", stock="5")
                for bad in ("nan", "inf", "-1", "1000001"):
                    try:
                        editor.save("TEST-01", "Notebook", sell="10.00", stock=bad)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError(bad)
                assert editor.get("TEST-01")["stock_qty"] == 5
                """,
                home,
            )

    def test_production_folder_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="velopos8_editor_") as folder:
            home = Path(folder) / "VeloPOS"
            self._child(
                """
                from velopos import database
                from velopos_qt.product_editor import PreviewProductEditor
                database.init_db()
                try:
                    PreviewProductEditor(database)
                except RuntimeError:
                    print("blocked production-like path")
                else:
                    raise AssertionError("Editor must refuse production DB")
                """,
                home,
            )


if __name__ == "__main__":
    unittest.main()
