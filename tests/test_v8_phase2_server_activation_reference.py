"""Preview SERVER activation state tests use disposable DB and ephemeral keys."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class PreviewServerActivationTests(unittest.TestCase):
    def isolated(self, script, folder="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_server_activation_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / folder)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_monotonic_server_state_rejects_replayed_signed_receipt(self):
        self.isolated(
            """
            import base64, sqlite3
            from datetime import datetime, timezone
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.activation_chain import PreviewSignedActivationChainInspector
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority

            def now(hour):
                return datetime(2026, 11, 4, hour, 0, tzinfo=timezone.utc)

            database.init_db()
            signer = Ed25519PrivateKey.generate()
            authority = PreviewServerActivationAuthority(
                database, signing_key=signer)
            pub = base64.urlsafe_b64encode(signer.public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw)).decode().rstrip("=")
            server = database.connect()
            try:
                server.execute("BEGIN IMMEDIATE")
                authority.initialize(server)
                authority.register(
                    server, license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", expires_utc="2026-11-06T00:00:00Z",
                    server_now=now(8))
                first = authority.issue(
                    server, license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", server_now=now(9))
                second = authority.issue(
                    server, license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", server_now=now(10))
                assert first.sequence == 1 and second.sequence == 2
                assert first.status == second.status == "active"
                assert not first.can_execute and not second.can_execute
                server.commit()
            finally:
                server.close()

            with database.db() as server:
                kwargs = dict(
                    license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", server_now=now(11))
                current = authority.inspect_current(
                    server, signed_status=second.signed_status, **kwargs)
                assert current.receipt_matches_server_state, current
                assert current.reasons == ("preview_transactions_disabled",)
                assert not current.can_execute
                prior = authority.inspect_current(
                    server, signed_status=first.signed_status, **kwargs)
                assert not prior.receipt_matches_server_state
                assert "server_receipt_sequence_or_digest_replay" in prior.reasons
                wrong_branch = authority.inspect_current(
                    server, signed_status=second.signed_status,
                    **dict(kwargs, branch_id="BRANCH-B"))
                assert "server_license_binding_mismatch" in wrong_branch.reasons
                forged = authority.inspect_current(
                    server, signed_status=second.signed_status[:-6] + "AAAAAA",
                    **kwargs)
                assert not forged.receipt_matches_server_state
                assert "server_receipt_signature_invalid" in forged.reasons
                try:
                    authority.require(
                        server, signed_status=second.signed_status, **kwargs)
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Reference granted commercial license")
                for table in ("sales", "sale_items", "returns", "stock_moves",
                              "supplier_payments", "credit_logs"):
                    assert server.execute(
                        f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0

            # The older pair can still pass a *client-only* chain inspector;
            # only separately maintained server state detects supersession.
            chain = PreviewSignedActivationChainInspector(
                database, server_public_key_b64=pub).inspect(
                previous_status=first.signed_status,
                current_status=second.signed_status,
                machine_id="MACHINE-A", license_id="LIC-A",
                expected_branch_id="BRANCH-A", now=now(11))
            assert chain.chain_consistent and not chain.can_execute, chain
            """
        )

    def test_revoke_expiry_duplicate_clock_rollback_and_atomic_rollback(self):
        self.isolated(
            """
            import sqlite3
            from datetime import datetime, timezone
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from velopos import database
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority

            def now(day=4, hour=10):
                return datetime(2026, 11, day, hour, tzinfo=timezone.utc)

            database.init_db()
            signer = Ed25519PrivateKey.generate()
            authority = PreviewServerActivationAuthority(
                database, signing_key=signer)
            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                authority.initialize(c)
                authority.register(
                    c, license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", expires_utc="2026-11-05T00:00:00Z",
                    server_now=now(hour=8))
                receipt = authority.issue(
                    c, license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", server_now=now(hour=10))
                c.commit()
            finally:
                c.close()

            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                for action in (
                    lambda: authority.register(
                        c, license_id="LIC-A", machine_id="MACHINE-A",
                        branch_id="BRANCH-A", expires_utc="2026-12-01T00:00:00Z",
                        server_now=now()),
                    lambda: authority.issue(
                        c, license_id="LIC-A", machine_id="MACHINE-B",
                        branch_id="BRANCH-A", server_now=now()),
                    lambda: authority.issue(
                        c, license_id="LIC-A", machine_id="MACHINE-A",
                        branch_id="BRANCH-A", server_now=now(hour=9)),
                    lambda: authority.issue(
                        c, license_id="LIC-A", machine_id="MACHINE-A",
                        branch_id="BRANCH-A", server_now=now(day=7)),
                ):
                    try:
                        action()
                    except (ValueError, PermissionError, sqlite3.IntegrityError):
                        pass
                    else:
                        raise AssertionError("Invalid registration/issue accepted")
                assert authority.inspect_current(
                    c, signed_status=receipt.signed_status,
                    license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", server_now=now()
                ).receipt_matches_server_state
                expiry = authority.inspect_current(
                    c, signed_status=receipt.signed_status,
                    license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", server_now=now(day=7))
                assert "server_license_expired" in expiry.reasons
                authority.revoke(c, license_id="LIC-A")
                revoked_old = authority.inspect_current(
                    c, signed_status=receipt.signed_status,
                    license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", server_now=now())
                assert "server_license_revoked" in revoked_old.reasons
                revoked_receipt = authority.issue(
                    c, license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", server_now=now(hour=11))
                assert revoked_receipt.status == "revoked"
                assert not authority.inspect_current(
                    c, signed_status=revoked_receipt.signed_status,
                    license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", server_now=now(hour=11)
                ).receipt_matches_server_state
                try:
                    authority.revoke(c, license_id="LIC-A")
                except ValueError:
                    pass
                else:
                    raise AssertionError("Double revocation accepted")
                c.commit()
            finally:
                c.close()

            # A receipt created in an uncommitted transaction must not become
            # the server's lasting state if the transaction rolls back.
            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                rolled_back = authority.issue(
                    c, license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", server_now=now(hour=12))
                assert rolled_back.sequence == revoked_receipt.sequence + 1
                c.rollback()
            finally:
                c.close()
            with database.db() as c:
                replay = authority.inspect_current(
                    c, signed_status=rolled_back.signed_status,
                    license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", server_now=now(hour=12))
                assert "server_receipt_sequence_or_digest_replay" in replay.reasons
                row = c.execute(
                    "SELECT status,last_sequence FROM v8_preview_server_license_state "
                    "WHERE license_id='LIC-A'").fetchone()
                assert row["status"] == "revoked"
                assert row["last_sequence"] == revoked_receipt.sequence
                for table in ("sales", "returns", "stock_moves",
                              "supplier_payments"):
                    assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            """
        )

    def test_rejects_missing_transaction_and_production_data(self):
        self.isolated(
            """
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from velopos import database
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority
            database.init_db()
            authority = PreviewServerActivationAuthority(
                database, signing_key=Ed25519PrivateKey.generate())
            c = database.connect()
            try:
                try:
                    authority.initialize(c)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Schema created without transaction")
                c.execute("BEGIN IMMEDIATE")
                authority.initialize(c)
                for bad in (None, True, 7, "WRONG ID"):
                    try:
                        authority.register(
                            c, license_id=bad, machine_id="MACHINE-A",
                            branch_id="BRANCH-A",
                            expires_utc="2026-11-06T00:00:00Z")
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("Malformed license identifier accepted")
                c.rollback()
            finally:
                c.close()
            """
        )
        self.isolated(
            """
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from velopos import database
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority
            database.init_db()
            try:
                PreviewServerActivationAuthority(
                    database, signing_key=Ed25519PrivateKey.generate())
            except RuntimeError:
                pass
            else:
                raise AssertionError("Production-like data path accepted")
            """,
            folder="VeloPOS",
        )


if __name__ == "__main__":
    unittest.main()
