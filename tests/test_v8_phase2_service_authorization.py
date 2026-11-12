"""Test preview transaction-bound service policy; no checkout can execute."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class ServiceAuthorizationIntegrationTests(unittest.TestCase):
    def isolated(self, source, home="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_service_auth_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / home)
            run = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(source)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_live_role_shift_and_credential_revalidation(self):
        self.isolated(
            """
            from velopos import database, services
            from velopos_qt.auth_model import PreviewAuthenticator, PreviewIdentity
            from velopos_qt.service_authorization import PreviewServiceAuthorization
            database.init_db()
            services.save_user("owner", "SecurePassForOwner123!", "Admin", "setup")
            services.save_user("cashier", "SecurePassForCashier123!", "Cashier", "setup")
            auth = PreviewAuthenticator(database)
            owner = auth.authenticate("owner", "SecurePassForOwner123!")
            cashier = auth.authenticate("cashier", "SecurePassForCashier123!")
            policy = PreviewServiceAuthorization(database)
            with database.db() as c:
                c.execute("INSERT INTO shifts(cashier,status) VALUES('cashier','OPEN')")
                shift_id = c.execute("SELECT id FROM shifts").fetchone()[0]
            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                valid = policy.inspect(c, action="sale", identity=cashier, shift_id=shift_id)
                assert valid.actor == "cashier" and valid.role == "Cashier", valid
                assert valid.can_execute is False
                assert valid.reasons == (
                    "preview_transactions_disabled", "commercial_license_unverified"
                ), valid
                for action in ("purchase","supplier_payment"):
                    restricted = policy.inspect(c, action=action, identity=cashier)
                    assert "role_not_permitted" in restricted.reasons
                mismatched = policy.inspect(c, action="sale", identity=owner, shift_id=shift_id)
                assert "shift_actor_mismatch" in mismatched.reasons
                fabricated = policy.inspect(
                    c, action="sale",
                    identity=PreviewIdentity("owner","Admin"), shift_id=shift_id
                )
                assert "verified_session_required" in fabricated.reasons
                try:
                    policy.require(c, action="sale", identity=cashier, shift_id=shift_id)
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Preview payment allowed")
                c.rollback()
            finally:
                c.close()
            with database.db() as c:
                c.execute("UPDATE users SET role='Admin' WHERE username='cashier'")
            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                expired = policy.inspect(c, action="sale", identity=cashier, shift_id=shift_id)
                assert "verified_session_required" in expired.reasons, expired
                c.rollback()
            finally:
                c.close()
            with database.db() as c:
                c.execute("UPDATE users SET role='Cashier',pw_hash='rotated' "
                          "WHERE username='cashier'")
            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                revoked = policy.inspect(c, action="sale", identity=cashier, shift_id=shift_id)
                assert "verified_session_required" in revoked.reasons
                for table in ("sales","sale_items","returns","purchases",
                              "supplier_payments","stock_moves"):
                    assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
                c.rollback()
            finally:
                c.close()
            """
        )

    def test_shift_requirements_and_untrusted_connection(self):
        self.isolated(
            """
            import sqlite3
            from velopos import database
            from velopos_qt.service_authorization import PreviewServiceAuthorization
            database.init_db()
            guard = PreviewServiceAuthorization(database)
            c = database.connect()
            try:
                try:
                    guard.inspect(c,action="sale")
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Connection without transaction accepted")
                c.execute("BEGIN IMMEDIATE")
                for shift in (None, 0, True, "1"):
                    result = guard.inspect(c,action="sale",shift_id=shift)
                    assert "open_assigned_shift_required" in result.reasons
                try:
                    guard.inspect(c,action="unknown")
                except ValueError:
                    pass
                else:
                    raise AssertionError("Unknown action accepted")
                c.rollback()
            finally:
                c.close()
            other = sqlite3.connect(":memory:")
            try:
                other.execute("BEGIN IMMEDIATE")
                try:
                    guard.inspect(other,action="sale")
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Other DB authorized")
            finally:
                other.rollback()
                other.close()
            """
        )

    def test_nonpreview_storage_rejected(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.service_authorization import PreviewServiceAuthorization
            database.init_db()
            try:
                PreviewServiceAuthorization(database)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Non-preview DB permitted")
            """, home="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
