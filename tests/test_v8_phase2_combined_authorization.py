"""Combined authorization remains fail-closed under valid, revoked and forged credentials."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class CombinedAuthorizationTests(unittest.TestCase):
    def isolated(self, script, folder="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_combined_auth_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / folder)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_valid_license_and_cashier_are_still_denied_and_rechecked(self):
        self.isolated(
            """
            import base64
            import json
            from datetime import date
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database, services
            from velopos_qt.auth_model import PreviewAuthenticator
            from velopos_qt.combined_authorization import PreviewCombinedAuthorization

            encode = lambda data: base64.urlsafe_b64encode(data).decode().rstrip("=")
            signing = Ed25519PrivateKey.generate()  # Ephemeral and never saved.
            public = encode(signing.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
            payload = json.dumps({
                "m": "TEST-MACHINE", "expires": "2030-12-31",
                "actions": ["sale", "purchase"],
            }, sort_keys=True).encode()
            key = encode(payload) + "." + encode(signing.sign(payload))
            database.init_db()
            services.save_user("cashier", "SecurePassForCashier123!", "Cashier", "setup")
            auth = PreviewAuthenticator(database)
            identity = auth.authenticate("cashier", "SecurePassForCashier123!")
            policy = PreviewCombinedAuthorization(database, public_key_b64=public)
            with database.db() as c:
                c.execute("INSERT INTO shifts(cashier,status) VALUES('cashier','OPEN')")
                shift = c.execute("SELECT id FROM shifts").fetchone()[0]

            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                good = policy.inspect(
                    c, action="sale", identity=identity, shift_id=shift,
                    license_key=key, machine_id="TEST-MACHINE",
                    today=date(2026, 11, 4),
                )
                assert good.actor == "cashier" and good.role == "Cashier", good
                assert good.signature_valid and good.entitled
                assert good.license_reasons == ("preview_transactions_disabled",)
                assert "commercial_license_unverified" in good.session_reasons
                assert good.can_execute is False
                try:
                    policy.require(
                        c, action="sale", identity=identity, shift_id=shift,
                        license_key=key, machine_id="TEST-MACHINE",
                        today=date(2026, 11, 4),
                    )
                except PermissionError:
                    pass
                else:
                    raise AssertionError("License unlocked preview checkout")
                admin_only = policy.inspect(
                    c, action="purchase", identity=identity,
                    license_key=key, machine_id="TEST-MACHINE",
                )
                assert "role_not_permitted" in admin_only.session_reasons
                forged = key[:-1] + ("A" if key[-1] != "A" else "B")
                bad = policy.inspect(
                    c, action="sale", identity=identity, shift_id=shift,
                    license_key=forged, machine_id="TEST-MACHINE",
                )
                assert not bad.entitled
                assert bad.can_execute is False
                for table in ("sales", "sale_items", "stock_moves", "returns",
                              "supplier_payments", "credit_logs"):
                    assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
                c.rollback()
            finally:
                c.close()
            with database.db() as c:
                c.execute("UPDATE users SET pw_hash='rotated' WHERE username='cashier'")
            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                revoked = policy.inspect(
                    c, action="sale", identity=identity, shift_id=shift,
                    license_key=key, machine_id="TEST-MACHINE",
                )
                assert "verified_session_required" in revoked.session_reasons, revoked
                assert revoked.can_execute is False
                c.rollback()
            finally:
                c.close()
            """
        )

    def test_requires_canonical_transaction_and_rejects_production(self):
        self.isolated(
            """
            import base64
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.combined_authorization import PreviewCombinedAuthorization
            database.init_db()
            signing = Ed25519PrivateKey.generate()
            pub = base64.urlsafe_b64encode(
                signing.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            ).decode().rstrip("=")
            policy = PreviewCombinedAuthorization(database, public_key_b64=pub)
            connection = database.connect()
            try:
                try:
                    policy.inspect(
                        connection, action="sale",
                        license_key="invalid", machine_id="TEST-MACHINE",
                    )
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("No-transaction inspection allowed")
                connection.execute("BEGIN IMMEDIATE")
                try:
                    policy.inspect(
                        connection, action="unknown",
                        license_key="invalid", machine_id="TEST-MACHINE",
                    )
                except ValueError:
                    pass
                else:
                    raise AssertionError("Unknown protected action accepted")
                connection.rollback()
            finally:
                connection.close()
            """
        )
        self.isolated(
            """
            import base64
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.combined_authorization import PreviewCombinedAuthorization
            database.init_db()
            signing = Ed25519PrivateKey.generate()
            pub = base64.urlsafe_b64encode(
                signing.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            ).decode().rstrip("=")
            try:
                PreviewCombinedAuthorization(database, public_key_b64=pub)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Production data path accepted")
            """,
            folder="VeloPOS",
        )


if __name__ == "__main__":
    unittest.main()
