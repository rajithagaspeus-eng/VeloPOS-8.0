"""Fail-closed composition of session, branch, signed license and activation chain."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class ComposedActivationChainTests(unittest.TestCase):
    def isolated(self, script, folder="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_composed_chain_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / folder)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_signed_chain_and_real_session_are_still_read_only(self):
        self.isolated("""
            import base64, hashlib, json
            from datetime import date, datetime, timezone
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database, services
            from velopos_qt.auth_model import PreviewAuthenticator, PreviewIdentity
            from velopos_qt.combined_authorization import PreviewCombinedAuthorization

            b64 = lambda x: base64.urlsafe_b64encode(x).decode().rstrip("=")
            license_signer = Ed25519PrivateKey.generate()
            server_signer = Ed25519PrivateKey.generate()
            def pub(key):
                return b64(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
            def sign(key, payload):
                raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
                return b64(raw) + "." + b64(key.sign(raw)), hashlib.sha256(raw).hexdigest()

            def license_for(license_id="LIC-A", branch="BRANCH-A"):
                return sign(license_signer, dict(
                    v=8, license_id=license_id, m="MACHINE-A", branch_id=branch,
                    actions=["sale"], expires="2030-01-01"))[0]

            observed = dict(
                v=8, machine_id="MACHINE-A", license_id="LIC-A",
                branch_id="BRANCH-A", status="active", sequence=13,
                observed_utc="2026-11-04T08:00:00Z",
                expires_utc="2026-11-05T00:00:00Z")
            previous, digest = sign(server_signer, observed)
            current, _ = sign(server_signer, dict(
                observed, sequence=14, observed_utc="2026-11-04T09:00:00Z",
                previous_payload_sha256=digest))
            now = datetime(2026, 11, 4, 10, tzinfo=timezone.utc)
            database.init_db()
            services.save_user(
                "cashier", "SecurePassForCashier123!", "Cashier", "setup")
            identity = PreviewAuthenticator(database).authenticate(
                "cashier", "SecurePassForCashier123!")
            with database.db() as db:
                db.execute("CREATE TABLE v8_preview_branch_registry ("
                           "branch_id TEXT PRIMARY KEY, active INTEGER NOT NULL)")
                db.execute("CREATE TABLE v8_preview_branch_memberships ("
                           "username TEXT NOT NULL, branch_id TEXT NOT NULL, "
                           "active INTEGER NOT NULL, PRIMARY KEY(username,branch_id))")
                db.execute("CREATE TABLE v8_preview_branch_shifts ("
                           "shift_id INTEGER PRIMARY KEY, branch_id TEXT NOT NULL)")
                db.execute("INSERT INTO v8_preview_branch_registry VALUES('BRANCH-A',1)")
                db.execute("INSERT INTO v8_preview_branch_memberships "
                           "VALUES('cashier','BRANCH-A',1)")
                db.execute("INSERT INTO shifts(cashier,status) VALUES('cashier','OPEN')")
                shift = db.execute("SELECT id FROM shifts ORDER BY id DESC LIMIT 1").fetchone()[0]
                db.execute("INSERT INTO v8_preview_branch_shifts VALUES(?,'BRANCH-A')",
                           (shift,))

            policy = PreviewCombinedAuthorization(database, public_key_b64=pub(license_signer))
            conn = database.connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                args = dict(
                    action="sale", identity=identity, shift_id=shift,
                    expected_branch_id="BRANCH-A", license_id="LIC-A",
                    machine_id="MACHINE-A", license_key=license_for(),
                    today=date(2026, 11, 4), now=now,
                    server_public_key_b64=pub(server_signer),
                    previous_status=previous, current_status=current)
                def check(**changes):
                    return policy.inspect_with_activation_chain(
                        conn, **dict(args, **changes))
                healthy = check()
                assert healthy.policy_consistent and healthy.identity_bound, healthy
                assert healthy.branch_verified and healthy.chain_consistent
                assert healthy.chain_signatures_valid
                assert not healthy.can_execute and not healthy.authorization.can_execute
                try:
                    policy.require_with_activation_chain(conn, **args)
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Signed activation chain enabled posting")

                other_license = check(license_key=license_for("LIC-B"))
                assert not other_license.identity_bound and not other_license.policy_consistent
                assert "signed_license_activation_binding_unverified" in other_license.chain_reasons
                wrong_branch_license = check(license_key=license_for(branch="BRANCH-B"))
                assert not wrong_branch_license.identity_bound
                assert "signed_branch_scope_mismatch" in wrong_branch_license.authorization.license_reasons
                no_session = check(identity=PreviewIdentity("cashier", "Cashier", "forged"))
                assert not no_session.policy_consistent and not no_session.branch_verified
                no_shift = check(shift_id=None)
                assert not no_shift.policy_consistent and not no_shift.branch_verified
                assert "open_assigned_shift_required" in no_shift.branch_reasons
                with_wrong_action = check(action="purchase")
                assert not with_wrong_action.policy_consistent
                assert "role_not_permitted" in with_wrong_action.branch_reasons
                forged_status = check(current_status=current[:-2] + "AA")
                assert not forged_status.chain_signatures_valid
                assert not forged_status.chain_consistent
                stale = check(now=datetime(2026,11,8,10,tzinfo=timezone.utc))
                assert not stale.policy_consistent
                assert "activation_observation_stale" in stale.chain_reasons
                revoked, _ = sign(server_signer, dict(
                    observed, sequence=14, status="revoked",
                    observed_utc="2026-11-04T09:00:00Z",
                    previous_payload_sha256=digest))
                reject_revocation = check(current_status=revoked)
                assert not reject_revocation.chain_consistent
                assert "current_activation_not_active" in reject_revocation.chain_reasons
                cross_branch, _ = sign(server_signer, dict(
                    observed, sequence=14, branch_id="BRANCH-B",
                    observed_utc="2026-11-04T09:00:00Z",
                    previous_payload_sha256=digest))
                assert not check(current_status=cross_branch).policy_consistent

                conn.execute("UPDATE v8_preview_branch_memberships SET active=0 "
                             "WHERE username='cashier' AND branch_id='BRANCH-A'")
                revoked_member = check()
                assert not revoked_member.branch_verified
                assert "actor_branch_membership_required" in revoked_member.branch_reasons
                conn.execute("UPDATE v8_preview_branch_memberships SET active=1")
                conn.execute("DELETE FROM v8_preview_branch_registry")
                missing_registry = check()
                assert not missing_registry.policy_consistent and not missing_registry.branch_verified
                for table in ("sales", "sale_items", "returns", "stock_moves",
                              "supplier_payments", "credit_logs"):
                    assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
                conn.rollback()
            finally:
                conn.close()
        """)

    def test_requires_preview_transaction_and_rejects_production_path(self):
        self.isolated("""
            import base64
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.combined_authorization import PreviewCombinedAuthorization
            database.init_db()
            key = Ed25519PrivateKey.generate()
            pub = base64.urlsafe_b64encode(
                key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            ).decode().rstrip("=")
            policy = PreviewCombinedAuthorization(database, public_key_b64=pub)
            connection = database.connect()
            try:
                try:
                    policy.inspect_with_activation_chain(
                        connection, action="sale", expected_branch_id="BRANCH-A",
                        license_id="LIC-A", server_public_key_b64=pub,
                        previous_status="bad", current_status="bad",
                        machine_id="MACHINE-A")
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Preview authorization bypassed transaction")
            finally:
                connection.close()
        """)
        self.isolated("""
            import base64
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.combined_authorization import PreviewCombinedAuthorization
            database.init_db()
            key = Ed25519PrivateKey.generate()
            pub = base64.urlsafe_b64encode(
                key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            ).decode().rstrip("=")
            try:
                PreviewCombinedAuthorization(database, public_key_b64=pub)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Production data path allowed")
        """, folder="VeloPOS")


if __name__ == "__main__":
    unittest.main()
