"""Canonical preview branch authorization: disposable SQLite, no financial writes."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class PreviewCanonicalBranchTests(unittest.TestCase):
    def isolated(self, script):
        with tempfile.TemporaryDirectory(prefix="v8_canonical_branch_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_persisted_actor_shift_and_signed_branch_must_agree(self):
        self.isolated(
            """
            import base64
            import json
            from datetime import date
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database, services
            from velopos_qt.auth_model import PreviewAuthenticator, PreviewIdentity
            from velopos_qt.combined_authorization import PreviewCombinedAuthorization

            encode = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
            private = Ed25519PrivateKey.generate()  # TEST key never persisted
            public = encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
            def license_for(branch_id):
                payload = json.dumps({
                    "v": 8, "license_id": "TRIALTEST", "m": "MACHINE-TEST",
                    "branch_id": branch_id, "actions": ["sale"],
                    "expires": "2030-12-31",
                }, sort_keys=True).encode()
                return encode(payload) + "." + encode(private.sign(payload))

            database.init_db()
            services.save_user("cashier", "SecurePassForCashier123!", "Cashier", "setup")
            identity = PreviewAuthenticator(database).authenticate(
                "cashier", "SecurePassForCashier123!"
            )
            policy = PreviewCombinedAuthorization(database, public_key_b64=public)
            with database.db() as c:
                c.execute("CREATE TABLE v8_preview_branch_registry ("
                          "branch_id TEXT PRIMARY KEY, active INTEGER NOT NULL)")
                c.execute("CREATE TABLE v8_preview_branch_memberships ("
                          "username TEXT NOT NULL, branch_id TEXT NOT NULL, "
                          "active INTEGER NOT NULL, PRIMARY KEY(username,branch_id))")
                c.execute("CREATE TABLE v8_preview_branch_shifts ("
                          "shift_id INTEGER PRIMARY KEY, branch_id TEXT NOT NULL)")
                c.execute("INSERT INTO v8_preview_branch_registry VALUES('BRANCH-A',1)")
                c.execute("INSERT INTO v8_preview_branch_registry VALUES('BRANCH-B',1)")
                c.execute("INSERT INTO v8_preview_branch_memberships "
                          "VALUES('cashier','BRANCH-A',1)")
                c.execute("INSERT INTO shifts(cashier,status) VALUES('cashier','OPEN')")
                shift = c.execute("SELECT id FROM shifts ORDER BY id DESC LIMIT 1").fetchone()[0]
                c.execute("INSERT INTO v8_preview_branch_shifts VALUES(?, 'BRANCH-A')",
                          (shift,))

            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                def inspect(branch_id="BRANCH-A", token=None, actor=identity):
                    return policy.inspect_with_branch_registry(
                        c, action="sale", expected_branch_id=branch_id,
                        identity=actor, shift_id=shift,
                        license_key=license_for(branch_id) if token is None else token,
                        machine_id="MACHINE-TEST", today=date(2026, 11, 4),
                    )
                good = inspect()
                assert good.branch_verified, good
                assert good.authorization.signature_valid
                assert good.authorization.entitled
                assert not good.authorization.can_execute and not good.can_execute
                try:
                    policy.require_with_branch_registry(
                        c, action="sale", expected_branch_id="BRANCH-A",
                        identity=identity, shift_id=shift,
                        license_key=license_for("BRANCH-A"),
                        machine_id="MACHINE-TEST", today=date(2026, 11, 4))
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Preview allowed commercial transaction")

                # Branch membership cannot override a persisted role denial.\n                role_denied = policy.branches.inspect(\n                    c, action="purchase", identity=identity,\n                    branch_id="BRANCH-A")\n                assert not role_denied.branch_verified, role_denied\n                assert "role_not_permitted" in role_denied.reasons\n                # A valid member with a missing shift must also fail closed.\n                no_shift = policy.branches.inspect(\n                    c, action="sale", identity=identity,\n                    branch_id="BRANCH-A", shift_id=None)\n                assert not no_shift.branch_verified\n                assert "open_assigned_shift_required" in no_shift.reasons\n                wrong_signed = inspect(token=license_for("BRANCH-B"))
                assert "signed_branch_scope_mismatch" in wrong_signed.authorization.license_reasons
                assert not wrong_signed.authorization.entitled
                assert not inspect(branch_id="BRANCH-B").branch_verified
                assert "actor_branch_membership_required" in inspect(
                    branch_id="BRANCH-B").branch_reasons
                forged = inspect(actor=PreviewIdentity("cashier", "Cashier", "fake"))
                assert not forged.branch_verified
                assert "verified_session_required" in forged.authorization.session_reasons
                assert "verified_branch_actor_required" in forged.branch_reasons
                c.execute("UPDATE v8_preview_branch_memberships SET active=0 "
                          "WHERE username='cashier'")
                revoked = inspect()
                assert "actor_branch_membership_required" in revoked.branch_reasons
                c.execute("UPDATE v8_preview_branch_memberships SET active=1 "
                          "WHERE username='cashier'")
                c.execute("UPDATE v8_preview_branch_shifts SET branch_id='BRANCH-B'")
                wrong_shift = inspect()
                assert "shift_branch_mismatch" in wrong_shift.branch_reasons
                c.execute("UPDATE v8_preview_branch_shifts SET branch_id='BRANCH-A'")
                # Corrupted legacy-style registry without a unique shift key:
                # a matching first row must not mask a conflicting second row.
                c.execute("DROP TABLE v8_preview_branch_shifts")
                c.execute("CREATE TABLE v8_preview_branch_shifts ("
                          "shift_id INTEGER, branch_id TEXT NOT NULL)")
                c.execute("INSERT INTO v8_preview_branch_shifts VALUES(?, 'BRANCH-A')",
                          (shift,))
                c.execute("INSERT INTO v8_preview_branch_shifts VALUES(?, 'BRANCH-B')",
                          (shift,))
                ambiguous = inspect()
                assert not ambiguous.branch_verified, ambiguous
                assert "branch_shift_not_open" in ambiguous.branch_reasons
                assert not ambiguous.can_execute
                c.execute("DELETE FROM v8_preview_branch_shifts WHERE branch_id='BRANCH-B'")
                assert inspect().branch_verified
                # Legacy/corrupt registries without uniqueness constraints must
                # reject duplicate rows even when the first one is active.
                c.execute("DROP TABLE v8_preview_branch_registry")
                c.execute("CREATE TABLE v8_preview_branch_registry ("
                          "branch_id TEXT, active INTEGER NOT NULL)")
                c.execute("INSERT INTO v8_preview_branch_registry VALUES('BRANCH-A',1)")
                c.execute("INSERT INTO v8_preview_branch_registry VALUES('BRANCH-A',0)")
                duplicate_branch = inspect()
                assert not duplicate_branch.branch_verified, duplicate_branch
                assert "branch_not_active" in duplicate_branch.branch_reasons
                assert not duplicate_branch.can_execute
                c.execute("DELETE FROM v8_preview_branch_registry WHERE active=0")
                assert inspect().branch_verified
                # Membership duplicates are equally ambiguous, including
                # when both rows are active and superficially agree.
                c.execute("DROP TABLE v8_preview_branch_memberships")
                c.execute("CREATE TABLE v8_preview_branch_memberships ("
                          "username TEXT, branch_id TEXT, active INTEGER NOT NULL)")
                c.execute("INSERT INTO v8_preview_branch_memberships "
                          "VALUES('cashier','BRANCH-A',1)")
                c.execute("INSERT INTO v8_preview_branch_memberships "
                          "VALUES('cashier','BRANCH-A',1)")
                duplicate_member = inspect()
                assert not duplicate_member.branch_verified, duplicate_member
                assert "actor_branch_membership_required" in duplicate_member.branch_reasons
                assert not duplicate_member.can_execute
                c.execute("DELETE FROM v8_preview_branch_memberships WHERE rowid IN ("
                          "SELECT rowid FROM v8_preview_branch_memberships LIMIT 1)")
                assert inspect().branch_verified
                c.execute("UPDATE v8_preview_branch_registry SET active=0 "
                          "WHERE branch_id='BRANCH-A'")
                disabled = inspect()
                assert "branch_not_active" in disabled.branch_reasons
                for table in ("sales", "returns", "stock_moves", "supplier_payments"):
                    assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
                c.rollback()
            finally:
                c.close()
            """
        )

    def test_missing_registry_and_transaction_rejected(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.branch_authorization import PreviewBranchAuthorization
            database.init_db()
            inspector = PreviewBranchAuthorization(database)
            c = database.connect()
            try:
                try:
                    inspector.inspect(c, action="sale", identity=None,
                                      branch_id="BRANCH-A", shift_id=1)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Inspected without caller-owned TX")
                c.execute("BEGIN IMMEDIATE")
                decision = inspector.inspect(
                    c, action="sale", identity=None,
                    branch_id="BRANCH-A", shift_id=1,
                )
                assert not decision.branch_verified and not decision.can_execute
                assert "canonical_branch_registry_missing" in decision.reasons
                bad_id = inspector.inspect(
                    c, action="sale", identity=None, branch_id=True, shift_id=1
                )
                assert "canonical_branch_id_required" in bad_id.reasons
                c.rollback()
            finally:
                c.close()
            """
        )


if __name__ == "__main__":
    unittest.main()
