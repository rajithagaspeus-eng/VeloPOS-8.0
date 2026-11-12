"""Batch 07: Ed25519 verification regression tests using EPHEMERAL test keys only.

Never generate or replace real product signing keys.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class LicenseVerifierTests(unittest.TestCase):
    def test_signed_license_is_bound_to_the_intended_machine(self):
        with tempfile.TemporaryDirectory(prefix="v8_license_verifier_") as base:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(base) / "VeloPOS8PreviewData")
            script = textwrap.dedent(
                """
                import base64
                import json
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
                from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
                from velopos import license as verifier

                # In-memory test-only keypair. Never save a private key.
                private = Ed25519PrivateKey.generate()
                public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
                encode = lambda data: base64.urlsafe_b64encode(data).decode().rstrip("=")
                verifier.PUBLIC_KEY_B64 = encode(public)
                data = {"m": "POS-TEST-1234", "plan": "TEST"}
                payload = json.dumps(data, sort_keys=True).encode()
                signed = encode(payload) + "." + encode(private.sign(payload))
                assert verifier.verify_key(signed, "POS-TEST-1234") == data
                assert verifier.verify_key(signed, "POS-DIFFERENT") is None
                altered = json.dumps({**data, "plan": "LIFETIME"}).encode()
                assert verifier.verify_key(encode(altered) + "." + signed.split(".")[1],
                                           "POS-TEST-1234") is None
                assert verifier.verify_key(signed + "garbage", "POS-TEST-1234") is None
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", script], env=env,
                text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
