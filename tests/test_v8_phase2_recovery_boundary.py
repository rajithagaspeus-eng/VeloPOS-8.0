"""Fail-closed recovery boundary regressions on disposable V8 preview data."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class RecoveryBoundaryTests(unittest.TestCase):
    def test_clock_rollback_and_expired_transfer_do_not_mutate_state(self):
        script = """
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from velopos import database
from velopos_qt.server_activation_reference import PreviewServerActivationAuthority
from velopos_qt.license_recovery_reference import PreviewLicenseRecoveryReference

def at(day, hour=9):
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)

database.init_db()
authority = PreviewServerActivationAuthority(
    database, signing_key=Ed25519PrivateKey.generate())
recovery = PreviewLicenseRecoveryReference(authority)
c = database.connect()
try:
    c.execute("BEGIN IMMEDIATE")
    authority.initialize(c)
    authority.register(
        c, license_id="LIC-BOUND", machine_id="MACHINE-A",
        branch_id="BRANCH-A", expires_utc="2026-11-05T00:00:00Z",
        server_now=at(4))
    authority.issue(
        c, license_id="LIC-BOUND", machine_id="MACHINE-A",
        branch_id="BRANCH-A", server_now=at(4))
    before = tuple(c.execute(
        "SELECT machine_id,branch_id,expires_utc,last_sequence,"
        "last_payload_sha256 FROM v8_preview_server_license_state "
        "WHERE license_id='LIC-BOUND'").fetchone())
    common = dict(
        license_id="LIC-BOUND", expected_sequence=1,
        expected_machine_id="MACHINE-A", expected_branch_id="BRANCH-A",
        new_machine_id="MACHINE-B", new_branch_id="BRANCH-B")
    for now in (at(3), at(5)):
        try:
            recovery.transfer(c, server_now=now, **common)
        except PermissionError:
            pass
        else:
            raise AssertionError("Rollback or expired transfer accepted")
        after = tuple(c.execute(
            "SELECT machine_id,branch_id,expires_utc,last_sequence,"
            "last_payload_sha256 FROM v8_preview_server_license_state "
            "WHERE license_id='LIC-BOUND'").fetchone())
        assert after == before, (now, before, after)
    try:
        recovery.require_checkout()
    except PermissionError:
        pass
    else:
        raise AssertionError("Recovery exposed checkout")
    c.rollback()
finally:
    c.close()
"""
        with tempfile.TemporaryDirectory(prefix="v8_recovery_boundary_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, text=True, capture_output=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
