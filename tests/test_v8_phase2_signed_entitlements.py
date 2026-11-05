"""Cryptographic entitlement diagnostics: signed payloads cannot enable posting."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class PreviewSignedEntitlementTests(unittest.TestCase):
    def isolated(self, source, directory="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_entitlement_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / directory)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(source)],
                env=env, capture_output=True, text=True, timeout=40,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_signed_license_scope_expiry_machine_and_always_blocked_preview(self):
        self.isolated(
            """
            import base64
            import json
            from datetime import date
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.license_entitlements import PreviewSignedEntitlementInspector

            database.init_db()
            signer = Ed25519PrivateKey.generate()  # ephemeral test key, never persisted
            encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
            public = encode(signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
            policy = PreviewSignedEntitlementInspector(database, public_key_b64=public)
            def sign(payload):
                raw = json.dumps(payload, sort_keys=True).encode()
                return encode(raw) + "." + encode(signer.sign(raw))

            good = sign({"m":"POS-TEST-1234","actions":["sale","return"],
                         "expires":"2030-01-01"})
            decision = policy.inspect(action="sale", license_key=good,
                                      machine_id="POS-TEST-1234",today=date(2026,11,4))
            assert decision.signature_valid is True, decision
            assert decision.machine_matches is True
            assert decision.entitled is True
            assert decision.can_execute is False
            assert decision.reasons == ("preview_transactions_disabled",)
            wrong_machine = policy.inspect(action="sale",license_key=good,
                                           machine_id="POS-WRONG",today=date(2026,11,4))
            assert "license_machine_mismatch" in wrong_machine.reasons
            assert wrong_machine.entitled is False
            wrong_action = policy.inspect(action="purchase",license_key=good,
                                          machine_id="POS-TEST-1234",today=date(2026,11,4))
            assert "signed_action_entitlement_missing" in wrong_action.reasons
            expired = policy.inspect(action="sale",license_key=good,
                                     machine_id="POS-TEST-1234",today=date(2031,1,1))
            assert "signed_entitlement_expired" in expired.reasons
            assert expired.entitled is False
            legacy = sign({"m":"POS-TEST-1234","customer":"Original V7"})
            old = policy.inspect(action="sale",license_key=legacy,
                                 machine_id="POS-TEST-1234",today=date(2026,11,4))
            assert old.signature_valid is True
            assert old.entitled is False
            assert "signed_action_entitlement_missing" in old.reasons
            tampered = sign({"m":"POS-TEST-1234","actions":["sale"],
                             "expires":"2030-01-01"})
            payload, signature = tampered.split(".")
            forged = sign({"m":"POS-TEST-1234","actions":["purchase"],
                           "expires":"2030-01-01"}).split(".")[0] + "." + signature
            invalid = policy.inspect(action="purchase",license_key=forged,
                                     machine_id="POS-TEST-1234",today=date(2026,11,4))
            assert "invalid_license_signature" in invalid.reasons
            assert invalid.can_execute is False
            for bad in ("", "bad", "a.b.c", "A..", "x" * 9000):
                out = policy.inspect(action="sale",license_key=bad,
                                     machine_id="POS-TEST-1234")
                assert out.signature_valid is False
                assert out.can_execute is False
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
                assert c.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0] == 0
            """
        )

    def test_deeply_nested_validly_signed_entitlement_fails_closed(self):
        self.isolated(
            """
            import base64
            from datetime import date
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.license_entitlements import PreviewSignedEntitlementInspector

            database.init_db()
            signer = Ed25519PrivateKey.generate()  # disposable test key only
            encode = lambda raw: base64.urlsafe_b64encode(raw).decode().rstrip("=")
            public = encode(signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
            inspector = PreviewSignedEntitlementInspector(database, public_key_b64=public)
            # Valid Ed25519 signature and canonical base64url envelope; the
            # JSON decoder must reject excessive nesting without propagating.
            raw = b"[" * 1200 + b"0" + b"]" * 1200
            license_key = encode(raw) + "." + encode(signer.sign(raw))
            decision = inspector.inspect(
                action="sale", license_key=license_key,
                machine_id="POS-TEST-1234", today=date(2026, 11, 5))
            assert not decision.signature_valid, decision
            assert not decision.entitled and not decision.can_execute
            assert "invalid_license_signature" in decision.reasons
            with database.db() as connection:
                assert connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
                assert connection.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0] == 0
            """
        )

    def test_foreign_production_path_and_bogus_public_keys_rejected(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.license_entitlements import PreviewSignedEntitlementInspector
            database.init_db()
            for key in ("", "garbage", "AA==", "A" * 9000):
                try:
                    PreviewSignedEntitlementInspector(database, public_key_b64=key)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Invalid verification key accepted")
            """
        )
        self.isolated(
            """
            import base64
            from velopos import database
            from velopos_qt.license_entitlements import PreviewSignedEntitlementInspector
            database.init_db()
            try:
                PreviewSignedEntitlementInspector(
                    database, public_key_b64=base64.urlsafe_b64encode(b"0"*32).decode()
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("Production-like database accepted")
            """,
            directory="VeloPOS",
        )


if __name__ == "__main__":
    unittest.main()
