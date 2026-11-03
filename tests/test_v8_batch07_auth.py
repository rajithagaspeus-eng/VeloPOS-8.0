"""Batch 07: authentication and trial integrity foundation tests.

All DB tests execute in fresh child processes; production storage is untouched.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from velopos_qt.auth_model import PreviewIdentity


class IdentityTests(unittest.TestCase):
    def test_roles_are_narrow_hints_only(self):
        self.assertTrue(PreviewIdentity("admin", "Admin").can_manage_staff)
        self.assertTrue(PreviewIdentity("cashier", "Cashier").can_open_draft)
        self.assertFalse(PreviewIdentity("cashier", "Cashier").can_manage_staff)
        self.assertFalse(PreviewIdentity("guest", "Guest").can_open_draft)


class PreviewAuthIntegrationTests(unittest.TestCase):
    def run_isolated(self, script, *, directory="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_auth_") as base:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(base) / directory)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=40,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_existing_hash_verification_and_roles(self):
        self.run_isolated(
            """
            from velopos import database, services
            from velopos_qt.auth_model import PreviewAuthenticator
            database.init_db()
            services.save_user("owner07", "OwnerPassStrong!2026", "Admin", "v8-preview")
            services.save_user("staff07", "StaffPassStrong!2026", "Cashier", "v8-preview")
            auth = PreviewAuthenticator(database)
            owner = auth.authenticate("OWNER07", "OwnerPassStrong!2026")
            assert owner.username == "owner07" and owner.can_manage_staff
            staff = auth.authenticate("staff07", "StaffPassStrong!2026")
            assert staff.role == "Cashier" and not staff.can_manage_staff
            for name, password in (("owner07", "wrong"), ("unknown", "wrong")):
                try:
                    auth.authenticate(name, password)
                except ValueError as error:
                    assert str(error) == "Invalid username or password"
                else:
                    raise AssertionError("Unknown/wrong credentials were accepted")
            """,
        )

    def test_persistent_wrong_password_lockout(self):
        self.run_isolated(
            """
            from velopos import database, services
            from velopos_qt.auth_model import PreviewAuthenticator
            database.init_db()
            services.save_user("clerk07", "StrongPass!321", "Cashier", "v8-preview")
            auth = PreviewAuthenticator(database)
            for _ in range(5):
                try:
                    auth.authenticate("clerk07", "WrongPassword")
                except ValueError:
                    pass
            assert services.login_locked_for("clerk07") > 0
            try:
                auth.authenticate("clerk07", "StrongPass!321")
            except ValueError as error:
                assert "Too many attempts" in str(error)
            else:
                raise AssertionError("Lockout must block valid password temporarily")
            """,
        )

    def test_cannot_authenticate_against_production_like_path(self):
        self.run_isolated(
            """
            from velopos import database
            from velopos_qt.auth_model import PreviewAuthenticator
            database.init_db()
            try:
                PreviewAuthenticator(database)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Must reject non-preview storage")
            """,
            directory="VeloPOS",
        )

    def test_missing_username_does_not_bypass_authentication(self):
        self.run_isolated(
            """
            from velopos import database
            from velopos_qt.auth_model import PreviewAuthenticator
            database.init_db()
            auth = PreviewAuthenticator(database)
            for user, password in (("", "pass"), ("admin", ""),
                                   ("a" * 31, "pass")):
                try:
                    auth.authenticate(user, password)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Invalid input was accepted")
            """,
        )


if __name__ == "__main__":
    unittest.main()
