"""Verify stale preview sessions lose access when roles/passwords change."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class PreviewSessionRevalidationTests(unittest.TestCase):
    def test_role_change_password_rotation_deletion_in_isolated_db(self):
        with tempfile.TemporaryDirectory(prefix="v8_session_guard_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            source = textwrap.dedent(
                """
                from velopos import database, services
                from velopos_qt.auth_model import PreviewAuthenticator, PreviewIdentity
                from velopos_qt.product_editor import PreviewProductEditor
                from velopos_qt.reports_model import PreviewReportsReader
                database.init_db()
                services.save_user(
                    "owner", "StrongUniquePassword2026!", "Admin", "setup"
                )
                auth = PreviewAuthenticator(database)
                session = auth.authenticate("owner", "StrongUniquePassword2026!")
                assert session.role == "Admin"
                assert session.credential_tag
                assert auth.current_role(session) == "Admin"
                # An identity manually fabricated from a username/role cannot
                # access protected adapters in a real preview DB.
                assert auth.current_role(PreviewIdentity("owner", "Admin")) is None
                admin = lambda: auth.current_role(session) == "Admin"
                editor = PreviewProductEditor(database, authorize=admin)
                reports = PreviewReportsReader(database, authorize=admin)
                editor.save("SESSION-1", "Rice", sell="20", stock="3")
                reports.snapshot("2026-11-01", "2026-11-04")
                with database.db() as c:
                    c.execute(
                        "UPDATE users SET role='Cashier' WHERE username='owner'"
                    )
                assert auth.current_role(session) is None
                try:
                    editor.save("SESSION-1", "Unauthorized", sell="15", stock="2")
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Demoted Admin retained editor access")
                try:
                    reports.snapshot("2026-11-01", "2026-11-04")
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Demoted Admin retained financial access")
                # A promotion is not accepted using an old Cashier identity.
                cashier = auth.authenticate("owner", "StrongUniquePassword2026!")
                with database.db() as c:
                    c.execute("UPDATE users SET role='Admin' WHERE username='owner'")
                assert auth.current_role(cashier) is None
                fresh = auth.authenticate("owner", "StrongUniquePassword2026!")
                assert auth.current_role(fresh) == "Admin"
                with database.db() as c:
                    c.execute(
                        "UPDATE users SET pw_hash='changed' WHERE username='owner'"
                    )
                assert auth.current_role(fresh) is None
                with database.db() as c:
                    c.execute("DELETE FROM users WHERE username='owner'")
                assert auth.current_role(fresh) is None
                with database.db() as c:
                    assert c.execute(
                        "SELECT name_en FROM products WHERE barcode='SESSION-1'"
                    ).fetchone()[0] == "Rice"
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", source], env=env,
                capture_output=True, text=True, timeout=50,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
