"""Bounded offline-grace preview checks: disposable data, ephemeral signing keys."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class PreviewOfflineGraceTests(unittest.TestCase):
    def isolated(self, script, folder="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_offline_grace_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / folder)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_server_grant_bindings_and_all_checkout_stays_disabled(self):
        self.isolated("""
            import base64
            from datetime import datetime, timezone
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.offline_grace_reference import (
                PreviewOfflineGraceAuthority, PreviewOfflineGraceInspector)
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority

            def moment(hour, minute=0):
                return datetime(2026, 11, 4, hour, minute, tzinfo=timezone.utc)
            def pub(key):
                return base64.urlsafe_b64encode(key.public_key().public_bytes(
                    Encoding.Raw, PublicFormat.Raw)).decode().rstrip("=")
            key = Ed25519PrivateKey.generate()
            database.init_db()
            authority = PreviewServerActivationAuthority(database, signing_key=key)
            issuer = PreviewOfflineGraceAuthority(authority)
            inspector = PreviewOfflineGraceInspector(database, server_public_key_b64=pub(key))
            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                authority.initialize(c)
                authority.register(
                    c, license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", expires_utc="2026-11-06T00:00:00Z",
                    server_now=moment(8))
                receipt = authority.issue(
                    c, license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", server_now=moment(9))
                grant = issuer.issue(
                    c, signed_activation_receipt=receipt.signed_status,
                    license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", hours=4, server_now=moment(10))
                assert grant.valid_until_utc == "2026-11-04T14:00:00Z"
                assert not grant.can_execute
                c.commit()
            finally:
                c.close()

            def check(**changes):
                args = dict(
                    signed_activation_receipt=receipt.signed_status,
                    signed_grant=grant.signed_grant, license_id="LIC-A",
                    machine_id="MACHINE-A", branch_id="BRANCH-A",
                    now=moment(11),
                )
                return inspector.inspect(**dict(args, **changes))

            valid = check()
            assert valid.signature_valid and valid.window_consistent, valid
            assert not valid.can_execute
            assert valid.grant_expires_utc == grant.valid_until_utc
            assert valid.reasons == ("preview_transactions_disabled",)
            try:
                inspector.require_checkout(
                    signed_activation_receipt=receipt.signed_status,
                    signed_grant=grant.signed_grant,
                    license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", now=moment(11))
            except PermissionError:
                pass
            else:
                raise AssertionError("Offline grant authorized checkout")
            try:
                issuer.require_checkout()
            except PermissionError:
                pass
            else:
                raise AssertionError("Grant signer authorized checkout")

            for expected, overrides in (
                ("grace_window_expired", {"now":moment(15)}),
                ("grace_clock_before_issue", {"now":moment(9, 40)}),
                ("machine_id_binding_mismatch", {"machine_id":"MACHINE-B"}),
                ("branch_id_binding_mismatch", {"branch_id":"BRANCH-B"}),
                ("license_id_binding_mismatch", {"license_id":"LIC-B"}),
                ("local_clock_rollback_observed",
                 {"last_observed_utc":"2026-11-04T12:00:00Z"}),
            ):
                decision = check(**overrides)
                assert expected in decision.reasons, (expected, decision)
                assert not decision.window_consistent and not decision.can_execute
            bad_grant = grant.signed_grant[:-6] + "AAAAAA"
            altered = check(signed_grant=bad_grant)
            assert "grant_signature_invalid" in altered.reasons
            assert not altered.signature_valid
            altered_receipt = check(
                signed_activation_receipt=receipt.signed_status[:-6] + "AAAAAA")
            assert "receipt_signature_invalid" in altered_receipt.reasons
            assert not altered_receipt.signature_valid
            for table in ("sales","sale_items","returns","stock_moves",
                          "supplier_payments","credit_logs"):
                with database.db() as c:
                    assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        """)

    def test_expiry_revocation_reissue_and_bounded_grant_signatures(self):
        self.isolated("""
            import base64, json
            from datetime import datetime, timezone
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.offline_grace_reference import (
                PreviewOfflineGraceAuthority, PreviewOfflineGraceInspector)
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority

            def moment(hour):
                return datetime(2026,11,4,hour,tzinfo=timezone.utc)
            def enc(raw):
                return base64.urlsafe_b64encode(raw).decode().rstrip("=")
            key = Ed25519PrivateKey.generate()
            pub = enc(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
            database.init_db()
            auth = PreviewServerActivationAuthority(database, signing_key=key)
            grants = PreviewOfflineGraceAuthority(auth)
            inspector = PreviewOfflineGraceInspector(
                database, server_public_key_b64=pub)
            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                auth.initialize(c)
                auth.register(c,license_id="LIC-A",machine_id="MACHINE-A",
                              branch_id="BRANCH-A",
                              expires_utc="2026-11-04T13:00:00Z",
                              server_now=moment(8))
                first = auth.issue(c,license_id="LIC-A",
                                   machine_id="MACHINE-A",
                                   branch_id="BRANCH-A",server_now=moment(9))
                grant = grants.issue(
                    c, signed_activation_receipt=first.signed_status,
                    license_id="LIC-A",machine_id="MACHINE-A",
                    branch_id="BRANCH-A",hours=24,server_now=moment(10))
                assert grant.valid_until_utc == "2026-11-04T13:00:00Z"
                for h in (0,25,True):
                    try:
                        grants.issue(c,signed_activation_receipt=first.signed_status,
                                     license_id="LIC-A",machine_id="MACHINE-A",
                                     branch_id="BRANCH-A",hours=h,server_now=moment(10))
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("Accepted invalid grace hours")
                second = auth.issue(c,license_id="LIC-A",
                                    machine_id="MACHINE-A",
                                    branch_id="BRANCH-A",server_now=moment(11))
                try:
                    grants.issue(c,signed_activation_receipt=first.signed_status,
                                 license_id="LIC-A",machine_id="MACHINE-A",
                                 branch_id="BRANCH-A",server_now=moment(11))
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Issued grant for old server receipt")
                auth.revoke(c,license_id="LIC-A")
                try:
                    grants.issue(c,signed_activation_receipt=second.signed_status,
                                 license_id="LIC-A",machine_id="MACHINE-A",
                                 branch_id="BRANCH-A",server_now=moment(12))
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Issued grace after server revocation")
                c.commit()
            finally:
                c.close()

            params=dict(signed_activation_receipt=first.signed_status,
                        signed_grant=grant.signed_grant,
                        license_id="LIC-A", machine_id="MACHINE-A",
                        branch_id="BRANCH-A",now=moment(12))
            # Critical limit: offline PC does not learn that the server
            # superseded the receipt or revoked the license. It must NEVER
            # treat a signed-in-window grant as transaction permission.
            assert inspector.inspect(**params).window_consistent
            expired = inspector.inspect(**dict(params,now=moment(14)))
            assert "grace_window_expired" in expired.reasons

            def sign_payload(obj):
                raw=json.dumps(obj,sort_keys=True,separators=(",",":")).encode()
                return enc(raw)+"."+enc(key.sign(raw))
            raw = base64.urlsafe_b64decode(
                grant.signed_grant.split(".")[0] + "==")
            token = json.loads(raw)
            for expected, updates in (
                ("grace_duration_or_order_invalid",
                 {"valid_until_utc":"2026-11-05T22:00:00Z"}),
                ("grace_receipt_digest_mismatch",
                 {"receipt_payload_sha256":"0"*64}),
                ("grace_sequence_mismatch",{"sequence":True}),
                ("grace_license_expiry_mismatch",
                 {"license_expires_utc":"2026-11-07T00:00:00Z"}),
                ("grace_schema_invalid",{"kind":"other"}),
                ("valid_until_utc_invalid",{"valid_until_utc":"bad"}),
            ):
                altered = inspector.inspect(**dict(
                    params, signed_grant=sign_payload(dict(token,**updates))))
                assert expected in altered.reasons, (expected, altered)
                assert not altered.window_consistent

            duplicate = (b'{"kind":"offline_grace","kind":"offline_grace"}')
            invalid = inspector.inspect(**dict(
                params, signed_grant=enc(duplicate)+"."+enc(key.sign(duplicate))))
            assert "grant_signature_invalid" in invalid.reasons
            assert not invalid.signature_valid
        """)

    def test_canonical_transaction_and_production_storage_guards(self):
        self.isolated("""
            import base64
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.offline_grace_reference import (
                PreviewOfflineGraceAuthority,PreviewOfflineGraceInspector)
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority

            key=Ed25519PrivateKey.generate()
            pub=base64.urlsafe_b64encode(
                key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
            ).decode().rstrip("=")
            database.init_db()
            auth=PreviewServerActivationAuthority(database,signing_key=key)
            grants=PreviewOfflineGraceAuthority(auth)
            c=database.connect()
            try:
                try:
                    grants.issue(c,signed_activation_receipt="bad",
                                 license_id="LIC-A",machine_id="MACHINE-A",
                                 branch_id="BRANCH-A")
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Grant issued without server transaction")
            finally:
                c.close()
            inspector=PreviewOfflineGraceInspector(database,server_public_key_b64=pub)
            try:
                inspector.inspect(signed_activation_receipt="bad",
                                  signed_grant="bad",license_id=True,
                                  machine_id="MACHINE-A",branch_id="BRANCH-A")
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid typed license ID accepted")
        """)
        self.isolated("""
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from velopos import database
            from velopos_qt.offline_grace_reference import (
                PreviewOfflineGraceAuthority,PreviewOfflineGraceInspector)
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority
            database.init_db()
            try:
                authority = PreviewServerActivationAuthority(
                    database,signing_key=Ed25519PrivateKey.generate())
                PreviewOfflineGraceAuthority(authority)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Production storage was accepted")
        """,folder="VeloPOS")
        """)


if __name__ == "__main__":
    unittest.main()
