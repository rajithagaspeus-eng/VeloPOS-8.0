"""Admin-only license renewal and device recovery: adversarial preview regressions."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class PreviewLicenseRecoveryTests(unittest.TestCase):
    def isolated(self, script, folder="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_license_recovery_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / folder)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_signed_renewal_transfer_and_stale_receipts_fail_closed(self):
        self.isolated("""
            import base64, json
            from datetime import datetime, timezone
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.activation_admin_gateway import PreviewSignedActivationGateway
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority

            def b64(data):
                return base64.urlsafe_b64encode(data).decode().rstrip("=")
            def pub(key):
                return b64(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw))
            admin, issuer = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
            def signed(key, actor, operation, req_id, payload):
                raw=json.dumps(dict(
                    v=8, operator_id=actor, operation=operation,
                    request_id=req_id, payload=payload,
                    issued_utc="2026-11-04T09:00:00Z",
                    expires_utc="2026-11-04T09:09:00Z"),
                    sort_keys=True,separators=(",",":")).encode()
                return b64(raw)+"."+b64(key.sign(raw))
            def moment(minute):
                return datetime(2026,11,4,9,minute,tzinfo=timezone.utc)

            database.init_db()
            authority=PreviewServerActivationAuthority(database,signing_key=admin)
            gateway=PreviewSignedActivationGateway(database,authority=authority)
            init=signed(admin,"ADMIN-A","register","recover-reg-0001",
                        dict(license_id="LIC-A",machine_id="MACHINE-A",
                             branch_id="BRANCH-A",expires_utc="2026-11-05T00:00:00Z"))
            issueA=dict(license_id="LIC-A",machine_id="MACHINE-A",
                        branch_id="BRANCH-A")
            first_issue=signed(issuer,"ISSUER-A","issue","recover-issue-01",issueA)
            renew=dict(license_id="LIC-A",expected_sequence=1,
                       new_expires_utc="2026-12-04T00:00:00Z")
            renewal=signed(admin,"ADMIN-A","renew","recover-renew-01",renew)
            wrong_renew=signed(issuer,"ISSUER-A","renew","recover-forge-01",renew)
            transfer=dict(license_id="LIC-A",expected_sequence=2,
                          expected_machine_id="MACHINE-A",expected_branch_id="BRANCH-A",
                          new_machine_id="MACHINE-B",new_branch_id="BRANCH-B")
            device_move=signed(admin,"ADMIN-A","transfer","recover-transfer-01",transfer)
            c=database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                gateway.initialize(c)
                gateway.provision_operator(c,operator_id="ADMIN-A",
                                           public_key_b64=pub(admin),role="Admin")
                gateway.provision_operator(c,operator_id="ISSUER-A",
                                           public_key_b64=pub(issuer),role="Issuer")
                gateway.dispatch(c,signed_request=init,server_now=moment(1))
                old=gateway.dispatch(c,signed_request=first_issue,server_now=moment(1))
                assert old.response["sequence"]==1
                try:
                    gateway.dispatch(c,signed_request=wrong_renew,server_now=moment(2))
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Issuer performed admin-only renewal")
                r=gateway.dispatch(c,signed_request=renewal,server_now=moment(2))
                assert not r.can_execute and not r.retry
                assert r.response["new_expires_utc"]=="2026-12-04T00:00:00Z"
                again=gateway.dispatch(c,signed_request=renewal,server_now=moment(3))
                assert again.retry and again.response==r.response
                assert c.execute("SELECT last_sequence FROM "
                    "v8_preview_server_license_state WHERE license_id='LIC-A'"
                ).fetchone()[0]==1
                stale=authority.inspect_current(
                    c,signed_status=old.response["signed_status"],
                    license_id="LIC-A",machine_id="MACHINE-A",
                    branch_id="BRANCH-A",server_now=moment(3))
                assert not stale.receipt_matches_server_state
                assert "server_receipt_binding_mismatch" in stale.reasons
                new_issue=signed(issuer,"ISSUER-A","issue",
                                 "recover-issue-02",issueA)
                fresh=gateway.dispatch(c,signed_request=new_issue,server_now=moment(3))
                assert fresh.response["sequence"]==2
                try:
                    gateway.dispatch(c,signed_request=renewal,server_now=moment(4))
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Old renewal response replayed after issuance")

                t=gateway.dispatch(c,signed_request=device_move,server_now=moment(4))
                assert t.response["machine_id"]=="MACHINE-B"
                assert t.response["branch_id"]=="BRANCH-B"
                assert t.response["last_sequence"]==2 and not t.can_execute
                assert gateway.dispatch(c,signed_request=device_move,
                                        server_now=moment(5)).retry
                former=authority.inspect_current(
                    c,signed_status=fresh.response["signed_status"],
                    license_id="LIC-A",machine_id="MACHINE-A",
                    branch_id="BRANCH-A",server_now=moment(5))
                assert not former.receipt_matches_server_state
                try:
                    authority.issue(c,license_id="LIC-A",machine_id="MACHINE-A",
                                    branch_id="BRANCH-A",server_now=moment(5))
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Old device acquired new receipt")

                new_device=signed(issuer,"ISSUER-A","issue","recover-newdev-01",
                                  dict(license_id="LIC-A",machine_id="MACHINE-B",
                                       branch_id="BRANCH-B"))
                next_one=gateway.dispatch(c,signed_request=new_device,
                                          server_now=moment(5))
                assert next_one.response["sequence"]==3
                try:
                    gateway.dispatch(c,signed_request=device_move,server_now=moment(6))
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Transferred response replayed after issuance")
                row=c.execute(
                    "SELECT last_sequence,machine_id,branch_id,status,last_payload_sha256 "
                    "FROM v8_preview_server_license_state WHERE license_id='LIC-A'"
                ).fetchone()
                assert row["last_sequence"]==3
                assert row["machine_id"]=="MACHINE-B" and row["branch_id"]=="BRANCH-B"
                assert row["status"]=="active" and len(row["last_payload_sha256"])==64
                for table in ("sales","sale_items","returns","stock_moves",
                              "supplier_payments","credit_logs"):
                    assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]==0
                try:
                    gateway.require_checkout()
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Recovery authorized checkout")
                c.commit()
            finally:
                c.close()
        """)

    def test_recovery_guards_revoke_invalid_expiry_sequence_and_rollback(self):
        self.isolated("""
            import base64, json
            from datetime import datetime, timezone
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.activation_admin_gateway import PreviewSignedActivationGateway
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority
            def enc(raw):
                return base64.urlsafe_b64encode(raw).decode().rstrip("=")
            key=Ed25519PrivateKey.generate()
            pub=enc(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw))
            def moment(hour=9):
                return datetime(2026,11,4,hour,tzinfo=timezone.utc)
            def command(op,req,payload):
                raw=json.dumps(dict(
                    v=8,operator_id="ADMIN-A",operation=op,request_id=req,
                    payload=payload,issued_utc="2026-11-04T09:00:00Z",
                    expires_utc="2026-11-04T09:09:00Z"),
                    sort_keys=True,separators=(",",":")).encode()
                return enc(raw)+"."+enc(key.sign(raw))
            database.init_db()
            auth=PreviewServerActivationAuthority(database,signing_key=key)
            gw=PreviewSignedActivationGateway(database,authority=auth)
            c=database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                gw.initialize(c)
                gw.provision_operator(c,operator_id="ADMIN-A",
                                      public_key_b64=pub,role="Admin")
                gw.dispatch(c,signed_request=command("register","recover-reg-02",
                    dict(license_id="LIC-A",machine_id="MACHINE-A",
                         branch_id="BRANCH-A",expires_utc="2026-11-05T00:00:00Z")),
                    server_now=moment())
                first=auth.issue(c,license_id="LIC-A",machine_id="MACHINE-A",
                                 branch_id="BRANCH-A",server_now=moment())
                assert first.sequence==1
                renew_base=dict(license_id="LIC-A",expected_sequence=1,
                                new_expires_utc="2026-12-04T00:00:00Z")
                move_base=dict(license_id="LIC-A",expected_sequence=1,
                               expected_machine_id="MACHINE-A",
                               expected_branch_id="BRANCH-A",
                               new_machine_id="MACHINE-B",new_branch_id="BRANCH-B")
                for op,payload in (
                    ("renew",dict(renew_base,expected_sequence=True)),
                    ("renew",dict(renew_base,expected_sequence=2)),
                    ("renew",dict(renew_base,new_expires_utc="2026-11-01T00:00:00Z")),
                    ("renew",dict(renew_base,new_expires_utc="2028-11-04T00:00:00Z")),
                    ("renew",dict(renew_base,new_expires_utc="2026-11-05T00:00:00Z")),
                    ("transfer",dict(move_base,expected_machine_id="OTHER")),
                    ("transfer",dict(move_base,new_machine_id="MACHINE-A",
                                     new_branch_id="BRANCH-A")),
                    ("transfer",dict(move_base,expected_sequence=2)),
                ):
                    try:
                        gw.dispatch(c,signed_request=command(
                            op,"recover-neg-"+str(len(payload))+"-01",payload),
                            server_now=moment())
                    except (ValueError,PermissionError):
                        pass
                    else:
                        raise AssertionError("Invalid recovery accepted: "+op+str(payload))
                assert c.execute("SELECT COUNT(*) FROM "
                    "v8_preview_activation_commands").fetchone()[0]==1
                assert c.execute(
                    "SELECT expires_utc,machine_id,last_sequence FROM "
                    "v8_preview_server_license_state WHERE license_id='LIC-A'"
                ).fetchone()["machine_id"]=="MACHINE-A"
                c.rollback()
            finally:
                c.close()
            with database.db() as c:
                c.execute("BEGIN IMMEDIATE")
                assert c.execute("SELECT COUNT(*) FROM "
                    "v8_preview_server_license_state").fetchone()[0]==0
                assert c.execute("SELECT COUNT(*) FROM "
                    "v8_preview_activation_commands").fetchone()[0]==0
            # New independent fixture: revocation permanently prevents
            # renewal and recovery, including after commercial expiry.
            c=database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                gw.initialize(c)
                auth.register(c,license_id="LIC-B",machine_id="MACHINE-A",
                              branch_id="BRANCH-A",expires_utc="2026-11-05T00:00:00Z",
                              server_now=moment())
                auth.issue(c,license_id="LIC-B",machine_id="MACHINE-A",
                           branch_id="BRANCH-A",server_now=moment())
                auth.revoke(c,license_id="LIC-B")
                for op,payload in (
                    ("renew",dict(license_id="LIC-B",expected_sequence=1,
                                  new_expires_utc="2026-12-04T00:00:00Z")),
                    ("transfer",dict(license_id="LIC-B",expected_sequence=1,
                                     expected_machine_id="MACHINE-A",
                                     expected_branch_id="BRANCH-A",
                                     new_machine_id="MACHINE-B",
                                     new_branch_id="BRANCH-B")),
                ):
                    try:
                        gw.recovery.renew(c,server_now=moment(),**payload) if op=="renew" else (
                            gw.recovery.transfer(c,server_now=moment(),**payload))
                    except PermissionError:
                        pass
                    else:
                        raise AssertionError("Revoked license recovered")
                c.commit()
            finally:
                c.close()
        """)

    def test_production_path_guard(self):
        self.isolated("""
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from velopos import database
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority
            from velopos_qt.license_recovery_reference import PreviewLicenseRecoveryReference
            database.init_db()
            try:
                authority=PreviewServerActivationAuthority(
                    database,signing_key=Ed25519PrivateKey.generate())
                PreviewLicenseRecoveryReference(authority)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Production database path accepted")
        """,folder="VeloPOS")


if __name__=="__main__":
    unittest.main()
