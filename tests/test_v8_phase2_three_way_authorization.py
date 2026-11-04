"""Regression for three-way authorization diagnostic; no financial posting."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class ThreeWayAuthorizationTests(unittest.TestCase):
    def test_signed_activation_is_not_permission(self):
        with tempfile.TemporaryDirectory(prefix="v8_three_way_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            script = """
                import base64
                import json
                from datetime import date, datetime, timezone
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
                from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
                from velopos import database, services
                from velopos_qt.auth_model import PreviewAuthenticator
                from velopos_qt.combined_authorization import PreviewCombinedAuthorization

                enc = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
                key = Ed25519PrivateKey.generate()
                pub = enc(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
                def sign(data):
                    payload = json.dumps(data, sort_keys=True).encode()
                    return enc(payload) + "." + enc(key.sign(payload))

                license_key = sign(dict(m="MACHINE", actions=["sale"], expires="2030-01-01"))
                status = sign(dict(machine_id="MACHINE", license_id="LICENSE",
                                   status="active", observed_utc="2026-11-04T02:00:00Z"))
                database.init_db()
                services.save_user("cashier", "SecurePassForCashier123!", "Cashier", "setup")
                identity = PreviewAuthenticator(database).authenticate("cashier", "SecurePassForCashier123!")
                with database.db() as c:
                    c.execute("INSERT INTO shifts(cashier,status) VALUES('cashier','OPEN')")
                    shift = c.execute("SELECT id FROM shifts").fetchone()[0]
                policy = PreviewCombinedAuthorization(database, public_key_b64=pub)
                conn = database.connect()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    args = dict(action="sale", identity=identity, shift_id=shift,
                                license_key=license_key, machine_id="MACHINE",
                                today=date(2026, 11, 4), server_public_key_b64=pub,
                                license_id="LICENSE",
                                now=datetime(2026, 11, 4, 3, tzinfo=timezone.utc))
                    good = policy.inspect_with_activation(conn, signed_status=status, **args)
                    assert good.authorization.entitled and good.activation_current
                    assert good.activation_signature_valid and not good.can_execute
                    assert "signed_license_id_binding_unverified" in good.activation_reasons
                    revoked = policy.inspect_with_activation(
                        conn, signed_status=sign(dict(machine_id="MACHINE",
                        license_id="LICENSE", status="revoked",
                        observed_utc="2026-11-04T02:00:00Z")), **args)
                    assert not revoked.activation_current
                    assert "activation_not_active" in revoked.activation_reasons
                    forged = policy.inspect_with_activation(conn, signed_status="bad", **args)
                    assert not forged.activation_signature_valid
                    try:
                        policy.require_with_activation(conn, signed_status=status, **args)
                    except PermissionError:
                        pass
                    else:
                        raise AssertionError("Preview transaction was authorized")
                    for table in ("sales", "returns", "stock_moves", "supplier_payments"):
                        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
                    conn.rollback()
                finally:
                    conn.close()
            """
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
