"""Phase 1 authorization regression: UI must not be the only barrier.

Uses an isolated subprocess so original module-global services can never
point at the shop's installed database. Never creates a real invoice.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class PreviewWritePermissionTests(unittest.TestCase):
    def test_direct_editor_reads_are_denied_after_role_revocation(self):
        with tempfile.TemporaryDirectory(prefix="v8_editor_read_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            source = textwrap.dedent(
                """
                from velopos import database, services
                from velopos_qt.product_editor import PreviewProductEditor
                from velopos_qt.directory_editor import PreviewDirectoryEditor
                database.init_db()
                state = {"role": "Admin"}
                allowed = lambda: state["role"] == "Admin"
                product = PreviewProductEditor(database, authorize=allowed)
                directory = PreviewDirectoryEditor(database, authorize=allowed)
                product.save("READ-1", "Test item", sell="11", stock="2")
                customer = directory.save("customers", name="Private Customer", phone="0701231234")
                supplier = directory.save("suppliers", name="Private Supplier")
                assert product.get("READ-1")["name_en"] == "Test item"
                with database.db() as c:
                    cid = c.execute("SELECT id FROM customers WHERE name='Private Customer'").fetchone()[0]
                    sid = c.execute("SELECT id FROM suppliers WHERE name='Private Supplier'").fetchone()[0]
                assert directory.get("customers", cid)["name"] == "Private Customer"
                assert directory.get("suppliers", sid)["name"] == "Private Supplier"
                for role in (None, "Cashier"):
                    state["role"] = role
                    for read in (
                        lambda: product.get("READ-1"),
                        lambda: directory.get("customers", cid),
                        lambda: directory.get("suppliers", sid),
                    ):
                        try:
                            read()
                        except PermissionError:
                            pass
                        else:
                            raise AssertionError("Revoked editor read exposed sensitive details")
                state["role"] = "Admin"
                assert directory.get("customers", cid)["name"] == "Private Customer"
                """
            )
            p = subprocess.run([sys.executable, "-c", source],
                               env=env, text=True, capture_output=True, timeout=45)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_logout_and_cashier_cannot_mutate_directly(self):
        with tempfile.TemporaryDirectory(prefix="v8_permission_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            script = textwrap.dedent(
                """
                from velopos import database
                from velopos_qt.product_editor import PreviewProductEditor
                from velopos_qt.directory_editor import PreviewDirectoryEditor

                database.init_db()
                signed_in = {"role": None}
                def admin_allowed():
                    return signed_in["role"] == "Admin"
                inventory = PreviewProductEditor(database, authorize=admin_allowed)
                directory = PreviewDirectoryEditor(database, authorize=admin_allowed)
                for role in (None, "Cashier"):
                    signed_in["role"] = role
                    for operation in (
                        lambda: inventory.save("AUTH-01", "Restricted", sell="10", stock="2"),
                        lambda: directory.save("customers", name="Restricted Customer"),
                        lambda: directory.save("suppliers", name="Restricted Supplier"),
                    ):
                        try:
                            operation()
                        except PermissionError:
                            pass
                        else:
                            raise AssertionError("Unauthorized write succeeded")
                with database.db() as c:
                    assert c.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0
                    assert c.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0
                    assert c.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0] == 0

                signed_in["role"] = "Admin"
                inventory.save("AUTH-01", "Restricted", sell="10", stock="2")
                directory.save("customers", name="Restricted Customer")
                directory.save("suppliers", name="Restricted Supplier")
                signed_in["role"] = None
                try:
                    inventory.save("AUTH-01", "Attempt after logout", sell="9", stock="1")
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Stale editor must be blocked on logout")
                with database.db() as c:
                    assert c.execute(
                        "SELECT name_en FROM products WHERE barcode='AUTH-01'"
                    ).fetchone()[0] == "Restricted"
                """
            )
            r = subprocess.run(
                [sys.executable, "-c", script], env=env,
                text=True, capture_output=True, timeout=45,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
