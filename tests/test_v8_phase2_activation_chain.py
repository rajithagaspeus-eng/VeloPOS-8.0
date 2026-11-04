"""Adversarial signed activation history checks: disposable preview data only."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class SignedActivationChainTests(unittest.TestCase):
    def isolated(self, script, folder="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_signed_chain_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / folder)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_valid_chain_remains_denied_and_replay_tampering_fails(self):
        self.isolated(
            """
            import base64, hashlib, json
            from datetime import datetime, timezone
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.activation_chain import PreviewSignedActivationChainInspector

            enc = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
            key = Ed25519PrivateKey.generate()  # ephemeral test signer
            pub = enc(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
            database.init_db()
            policy = PreviewSignedActivationChainInspector(
                database, server_public_key_b64=pub)
            now = datetime(2026, 11, 4, 2, 0, tzinfo=timezone.utc)

            def sign(data):
                raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
                return enc(raw) + "." + enc(key.sign(raw)), hashlib.sha256(raw).hexdigest()

            previous = dict(
                v=8, machine_id="MACHINE-A", license_id="LICENSE-A",
                branch_id="BRANCH-A", status="active", sequence=20,
                observed_utc="2026-11-04T00:00:00Z",
                expires_utc="2026-11-06T00:00:00Z")
            old_token, old_digest = sign(previous)
            current = dict(
                v=8, machine_id="MACHINE-A", license_id="LICENSE-A",
                branch_id="BRANCH-A", status="active", sequence=21,
                observed_utc="2026-11-04T01:00:00Z",
                expires_utc="2026-11-06T00:00:00Z",
                previous_payload_sha256=old_digest)

            def inspect(new=None, old=None, clock=now, **kwargs):
                token, _ = sign(current if new is None else dict(current, **new))
                return policy.inspect(
                    previous_status=old_token if old is None else old,
                    current_status=token,
                    machine_id="MACHINE-A", license_id="LICENSE-A",
                    expected_branch_id="BRANCH-A", now=clock, **kwargs)
            good = inspect()
            assert good.signatures_valid and good.chain_consistent, good
            assert good.previous_sequence == 20 and good.current_sequence == 21
            assert good.reasons == ("preview_transactions_disabled",)
            assert good.can_execute is False
            try:
                policy.require(
                    previous_status=old_token, current_status=sign(current)[0],
                    machine_id="MACHINE-A", license_id="LICENSE-A",
                    expected_branch_id="BRANCH-A", now=now)
            except PermissionError:
                pass
            else:
                raise AssertionError("Consistent chain authorized checkout")

            bad = {
                "signed_sequence_not_increasing": dict(sequence=20),
                "signed_observation_time_rollback":
                    dict(observed_utc="2026-11-03T23:59:59Z"),
                "signed_previous_digest_mismatch":
                    dict(previous_payload_sha256="0" * 64),
                "current_activation_binding_mismatch": dict(branch_id="BRANCH-B"),
                "current_activation_not_active": dict(status="revoked"),
                "current_sequence_invalid": dict(sequence=True),
                "current_activation_version_invalid": dict(v=True),
                "current_expires_utc_invalid": dict(expires_utc="not-a-date"),
                "current_expiry_precedes_observation":
                    dict(expires_utc="2026-11-03T23:00:00Z"),
            }
            for expected, data in bad.items():
                result = inspect(data)
                assert expected in result.reasons, (expected, result)
                assert not result.chain_consistent and not result.can_execute

            assert "activation_signed_expiry_elapsed" in inspect(
                clock=datetime(2026, 11, 7, tzinfo=timezone.utc)
            ).reasons
            assert "activation_observation_stale" in inspect(
                max_offline_hours=0
            ).reasons
            assert "activation_observation_in_future" in inspect(
                clock=datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc)
            ).reasons
            wrong_license = policy.inspect(
                previous_status=old_token, current_status=sign(current)[0],
                machine_id="MACHINE-A", license_id="LICENSE-B",
                expected_branch_id="BRANCH-A", now=now)
            assert "previous_activation_binding_mismatch" in wrong_license.reasons
            assert "current_activation_binding_mismatch" in wrong_license.reasons
            assert not wrong_license.chain_consistent
            assert "previous_activation_binding_mismatch" in inspect(
                old=sign(dict(previous, machine_id="MACHINE-B"))[0]
            ).reasons
            assert "previous_activation_not_active" in inspect(
                old=sign(dict(previous, status="revoked"))[0]
            ).reasons

            tampered = sign(current)[0][:-3] + "abc"
            try:
                result = policy.inspect(
                    previous_status=old_token, current_status=tampered,
                    machine_id="MACHINE-A", license_id="LICENSE-A",
                    expected_branch_id="BRANCH-A", now=now)
            except Exception as exc:
                raise AssertionError("Malformed signature should deny, not crash") from exc
            assert "current_status_signature_invalid" in result.reasons
            assert not result.signatures_valid and not result.chain_consistent
            assert "previous_status_signature_invalid" in inspect(
                old="malformed"
            ).reasons

            # A fully rolled-back pair can still look valid if the caller
            # controls its clock. This proves that no trusted persistent
            # anti-rollback claim can be made from signed pairs alone.
            assert inspect().chain_consistent

            for table in ("sales", "sale_items", "stock_moves",
                          "returns", "supplier_payments"):
                with database.db() as c:
                    assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            """
        )

    def test_canonical_signed_schema_and_caller_validation(self):
        self.isolated(
            """
            import base64, json
            from datetime import datetime, timezone
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.activation_chain import PreviewSignedActivationChainInspector
            database.init_db()
            key = Ed25519PrivateKey.generate()
            enc = lambda raw: base64.urlsafe_b64encode(raw).decode().rstrip("=")
            pub = enc(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
            checker = PreviewSignedActivationChainInspector(
                database, server_public_key_b64=pub)
            def sign(raw):
                return enc(raw) + "." + enc(key.sign(raw))
            raw = b'{"v":8,"v":8,"sequence":1}'
            duplicate = sign(raw)
            args = dict(
                previous_status=duplicate, current_status=duplicate,
                machine_id="MACHINE-A", license_id="LICENSE-A",
                expected_branch_id="BRANCH-A",
                now=datetime(2026, 11, 4, tzinfo=timezone.utc))
            result = checker.inspect(**args)
            assert "previous_status_signature_invalid" in result.reasons
            assert "current_status_signature_invalid" in result.reasons
            for field, invalid in (
                    ("machine_id", True),
                    ("license_id", "BAD SPACE"),
                    ("expected_branch_id", 10),
                    ("max_offline_hours", 169),
                    ("max_offline_hours", True),
                    ("now", "2026-11-04")):
                try:
                    checker.inspect(**dict(args, **{field: invalid}))
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"Accepted invalid {field}")
            """
        )

    def test_production_data_path_is_rejected(self):
        self.isolated(
            """
            import base64
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.activation_chain import PreviewSignedActivationChainInspector
            database.init_db()
            key = Ed25519PrivateKey.generate()
            pub = base64.urlsafe_b64encode(
                key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            ).decode().rstrip("=")
            try:
                PreviewSignedActivationChainInspector(
                    database, server_public_key_b64=pub)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Production database was accepted")
            """,
            folder="VeloPOS",
        )


if __name__ == "__main__":
    unittest.main()
