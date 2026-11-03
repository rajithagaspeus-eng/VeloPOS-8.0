"""Batch 04: isolated subprocess tests for audited customer/supplier edits."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


class DirectoryEditIntegrationTests(unittest.TestCase):
    def run_isolated(self, script, folder):
        env = os.environ.copy()
        env["VELOPOS_HOME"] = str(folder)
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(script)],
            text=True, capture_output=True, env=env, timeout=35,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_customer_supplier_add_update_audit_and_balances(self):
        with tempfile.TemporaryDirectory(prefix="v8_directories_") as root:
            home = Path(root) / "VeloPOS8PreviewData"
            self.run_isolated(
                """
                from velopos import database
                from velopos_qt.directory_editor import PreviewDirectoryEditor
                database.init_db()
                editor = PreviewDirectoryEditor(database)
                cid = editor.save("customers", name="Test Customer", phone="0771234567", address="Galle")
                assert isinstance(cid, int)
                editor.save("customers", identifier=cid, name="Test Customer Updated",
                            phone="0771234567", address="Colombo")
                assert editor.get("customers", cid)["address"] == "Colombo"
                sid = editor.save("suppliers", name="Test Supplier", phone="0711112222", contact="Rep")
                editor.save("suppliers", identifier=sid, name="Test Supplier",
                            phone="0711112222", contact="Rep", active=False)
                assert editor.get("suppliers", sid)["active"] == 0
                with database.db() as con:
                    c = con.execute("SELECT credit_balance, loyalty_points FROM customers WHERE id=?", (cid,)).fetchone()
                    assert c["credit_balance"] == 0 and c["loyalty_points"] == 0
                    names = [r["action"] for r in con.execute("SELECT action FROM audit_log")]
                    for action in ("CUSTOMER_ADD", "CUSTOMER_EDIT", "SUPPLIER_ADD", "SUPPLIER_EDIT"):
                        assert action in names, (action, names)
                """, home,
            )

    def test_duplicate_and_invalid_contact_rejected(self):
        with tempfile.TemporaryDirectory(prefix="v8_directories_") as root:
            home = Path(root) / "VeloPOS8PreviewData"
            self.run_isolated(
                """
                from velopos import database
                from velopos_qt.directory_editor import PreviewDirectoryEditor
                database.init_db()
                editor = PreviewDirectoryEditor(database)
                editor.save("customers", name="First", phone="0771234567")
                for name, phone in (("Second", "0771234567"), ("Third", "123")):
                    try:
                        editor.save("customers", name=name, phone=phone)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("Expected customer validation failure")
                editor.save("suppliers", name="Acme")
                try:
                    editor.save("suppliers", name="ACME")
                except ValueError:
                    pass
                else:
                    raise AssertionError("Expected case-insensitive supplier duplicate guard")
                """, home,
            )

    def test_refuses_production_path(self):
        with tempfile.TemporaryDirectory(prefix="v8_directories_") as root:
            home = Path(root) / "VeloPOS"
            self.run_isolated(
                """
                from velopos import database
                from velopos_qt.directory_editor import PreviewDirectoryEditor
                database.init_db()
                try:
                    PreviewDirectoryEditor(database)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Production path must be refused")
                """, home,
            )


if __name__ == "__main__":
    unittest.main()
