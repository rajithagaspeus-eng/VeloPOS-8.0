"""Branch-scope entitlement tests use ephemeral signing keys and preview data only."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class BranchScopeTests(unittest.TestCase):
    def test_signed_branch_scope_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="v8_branch_scope_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            script = """
                import base64, json
                from datetime import date
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
                from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
                from velopos import database
                from velopos_qt.license_entitlements import PreviewSignedEntitlementInspector
                enc = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
                signer = Ed25519PrivateKey.generate()
                public = enc(signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
                def sign(**overrides):
                    data = dict(v=8, license_id="LICENSE-A", m="MACHINE-A",
                                actions=["sale"], expires="2030-12-31",
                                branch_id="BRANCH-A")
                    data.update(overrides)
                    payload = json.dumps(data, sort_keys=True).encode()
                    return enc(payload) + "." + enc(signer.sign(payload))
                database.init_db()
                policy = PreviewSignedEntitlementInspector(database, public_key_b64=public)
                def inspect(token, branch="BRANCH-A"):
                    return policy.inspect(action="sale", license_key=token,
                        machine_id="MACHINE-A", today=date(2026,11,4),
                        expected_branch_id=branch)
                good = inspect(sign())
                assert good.signature_valid and good.entitled
                assert good.signed_branch_id == "BRANCH-A" and not good.can_execute
                mismatch = inspect(sign(), "BRANCH-B")
                assert "signed_branch_scope_mismatch" in mismatch.reasons
                assert not mismatch.entitled and not mismatch.can_execute
                for payload in (dict(branch_id=None), dict(branch_id=True),
                                dict(branch_id=123), dict(branch_id="BAD SPACE"),
                                dict(v=7), dict(branch_id="")):
                    decision = inspect(sign(**payload))
                    assert "signed_branch_scope_missing" in decision.reasons, decision
                    assert not decision.entitled and not decision.can_execute
                try:
                    inspect(sign(), True)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Boolean branch identity accepted")
                forged = sign()[:-4] + "AAAA"
                bad = inspect(forged)
                assert not bad.signature_valid and not bad.entitled
                for table in ("sales", "returns", "stock_moves", "supplier_payments"):
                    with database.db() as c:
                        assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            """
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
