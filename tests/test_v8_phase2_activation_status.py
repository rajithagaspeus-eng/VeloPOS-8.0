"""Signed activation status is diagnostic only; it cannot enable transactions."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class ActivationStatusTests(unittest.TestCase):
    def isolated(self, script, folder="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_activation_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / folder)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_signed_activation_status_and_fail_closed_cases(self):
        self.isolated(
            """
            import base64
            import json
            from datetime import datetime, timedelta, timezone
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.activation_status import PreviewActivationStatusInspector

            database.init_db()
            key = Ed25519PrivateKey.generate()
            enc = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
            pub = enc(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
            policy = PreviewActivationStatusInspector(database, server_public_key_b64=pub)
            now = datetime(2026, 11, 4, 3, 0, tzinfo=timezone.utc)
            def sign(**changes):
                data = dict(machine_id="MACHINE-A", license_id="LICENSE-A",
                            status="active", observed_utc="2026-11-04T02:00:00Z")
                data.update(changes)
                payload = json.dumps(data, sort_keys=True).encode()
                return enc(payload) + "." + enc(key.sign(payload))
            def check(token, **kwargs):
                return policy.inspect(
                    signed_status=token, machine_id="MACHINE-A",
                    license_id="LICENSE-A", now=now, **kwargs
                )
            valid = check(sign())
            assert valid.signature_valid and valid.current, valid
            assert valid.can_execute is False
            assert valid.reasons == ("preview_transactions_disabled",)
            assert "activation_status_stale" in check(
                sign(observed_utc="2026-11-01T02:00:00Z")
            ).reasons
            assert "activation_not_active" in check(sign(status="revoked")).reasons
            assert "activation_binding_mismatch" in check(
                sign(machine_id="MACHINE-B")
            ).reasons
            for malformed in (None, True, 7, [], {}, "LICENSE A", " LICENSE-A"):
                if isinstance(malformed, str) and " " in malformed:
                    try:
                        policy.inspect(signed_status=sign(), machine_id="MACHINE-A",
                                       license_id=malformed, now=now)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("Malformed caller license ID accepted")
                else:
                    assert "activation_binding_mismatch" in check(
                        sign(license_id=malformed)
                    ).reasons
            for malformed in (None, True, 7, [], {}):
                assert "activation_binding_mismatch" in check(
                    sign(machine_id=malformed)
                ).reasons
            assert "activation_not_active" in check(sign(status=True)).reasons
            assert "activation_timestamp_in_future" in check(
                sign(observed_utc="2026-11-04T05:00:00Z")
            ).reasons
            assert "activation_timestamp_invalid" in check(
                sign(observed_utc="2026-11-04")
            ).reasons
            assert "local_clock_rollback_suspected" in check(
                sign(), last_seen_utc=now + timedelta(hours=3)
            ).reasons
            assert check(sign(), max_offline_hours=0).current is False
            assert "activation_status_signature_invalid" in check("garbage").reasons
            assert "activation_status_signature_invalid" in check(
                sign()[:-2] + "XX"
            ).reasons
            for invalid in (True, -1, 169):
                try:
                    check(sign(), max_offline_hours=invalid)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Invalid grace window accepted")
            for table in ("sales", "sale_items", "stock_moves", "returns"):
                with database.db() as c:
                    assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            """
        )

    def test_rejects_production_path(self):
        self.isolated(
            """
            import base64
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.activation_status import PreviewActivationStatusInspector
            database.init_db()
            key = Ed25519PrivateKey.generate()
            pub = base64.urlsafe_b64encode(
                key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            ).decode().rstrip("=")
            try:
                PreviewActivationStatusInspector(database, server_public_key_b64=pub)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Production-like data path accepted")
            """,
            folder="VeloPOS",
        )


if __name__ == "__main__":
    unittest.main()
