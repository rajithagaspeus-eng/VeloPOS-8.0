"""Preview-only signed admin activation commands: isolated/adversarial tests."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class PreviewSignedAdminGatewayTests(unittest.TestCase):
    def isolated(self, script, folder="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_signed_admin_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / folder)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_admin_operator_signatures_idempotency_and_revocation(self):
        self.isolated("""
            import base64, json, sqlite3
            from datetime import datetime, timezone
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.activation_admin_gateway import PreviewSignedActivationGateway
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority

            def b64(data):
                return base64.urlsafe_b64encode(data).decode().rstrip("=")
            admin = Ed25519PrivateKey.generate()
            issuer = Ed25519PrivateKey.generate()
            forged_key = Ed25519PrivateKey.generate()
            def pub(key):
                return b64(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
            def sign(key, actor, op, request_id, payload, **overrides):
                obj = dict(v=8, operator_id=actor, operation=op,
                           request_id=request_id, payload=payload,
                           issued_utc="2026-11-04T09:00:00Z",
                           expires_utc="2026-11-04T09:05:00Z")
                obj.update(overrides)
                raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
                return b64(raw) + "." + b64(key.sign(raw))
            def clock(minute=1):
                return datetime(2026, 11, 4, 9, minute, tzinfo=timezone.utc)

            database.init_db()
            authority = PreviewServerActivationAuthority(database, signing_key=admin)
            api = PreviewSignedActivationGateway(database, authority=authority)
            reg = dict(license_id="LIC-A", machine_id="MACHINE-A",
                       branch_id="BRANCH-A", expires_utc="2026-11-05T00:00:00Z")
            issue = dict(license_id="LIC-A", machine_id="MACHINE-A",
                         branch_id="BRANCH-A")
            admin_register = sign(admin, "ADMIN-A", "register", "request-reg-0001", reg)
            issue_req = sign(issuer, "ISSUER-A", "issue", "request-issue-01", issue)
            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                api.initialize(c)
                api.provision_operator(c, operator_id="ADMIN-A",
                                       public_key_b64=pub(admin), role="Admin")
                api.provision_operator(c, operator_id="ISSUER-A",
                                       public_key_b64=pub(issuer), role="Issuer")
                registered = api.dispatch(
                    c, signed_request=admin_register, server_now=clock())
                assert registered.response["status"] == "registered"
                assert not registered.retry and not registered.can_execute
                repeat_reg = api.dispatch(
                    c, signed_request=admin_register, server_now=clock())
                assert repeat_reg.retry and repeat_reg.response == registered.response
                first = api.dispatch(c, signed_request=issue_req, server_now=clock())
                assert not first.retry and not first.can_execute
                assert first.response["sequence"] == 1
                repeated = api.dispatch(c, signed_request=issue_req, server_now=clock(2))
                assert repeated.retry and repeated.response == first.response
                assert c.execute(
                    "SELECT last_sequence FROM v8_preview_server_license_state "
                    "WHERE license_id='LIC-A'").fetchone()[0] == 1
                assert c.execute(
                    "SELECT COUNT(*) FROM v8_preview_activation_commands").fetchone()[0] == 2
                c.commit()
            finally:
                c.close()

            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                def forbidden(token, minute=3):
                    try:
                        api.dispatch(c, signed_request=token, server_now=clock(minute))
                    except (ValueError, PermissionError):
                        return
                    raise AssertionError("Unauthorized command accepted")
                forbidden(sign(issuer, "ISSUER-A", "revoke",
                               "request-badrole1", {"license_id":"LIC-A"}))
                forbidden(sign(issuer, "ISSUER-A", "register",
                               "request-badrole2", reg))
                forbidden(sign(forged_key, "ADMIN-A", "revoke",
                               "request-forged1", {"license_id":"LIC-A"}))
                forbidden(sign(issuer, "ISSUER-A", "issue",
                               "request-issue-01", dict(issue, branch_id="BRANCH-B")))
                forbidden(sign(admin, "ADMIN-A", "register",
                               "request-reg-0001", dict(reg, branch_id="BRANCH-B")))
                forbidden(sign(issuer, "ISSUER-A", "issue",
                               "request-issue-02", issue,
                               expires_utc="2026-11-04T09:01:00Z"))
                forbidden(sign(issuer, "ISSUER-A", "issue",
                               "request-issue-03", issue, v=True))
                forbidden(sign(issuer, "ISSUER-A", "issue",
                               "request-issue-04", issue,
                               issued_utc="2026-11-04T12:00:00Z",
                               expires_utc="2026-11-04T12:05:00Z"))
                forbidden("bad")
                assert c.execute(
                    "SELECT COUNT(*) FROM v8_preview_activation_commands").fetchone()[0] == 2

                revocation = sign(admin, "ADMIN-A", "revoke",
                                  "request-revoke01", {"license_id":"LIC-A"})
                revoked = api.dispatch(
                    c, signed_request=revocation, server_now=clock(3))
                assert revoked.response == {"status":"revoked", "license_id":"LIC-A"}
                assert api.dispatch(c, signed_request=revocation,
                                    server_now=clock(4)).retry
                forbidden(issue_req, minute=4)  # valid retry cannot leak active receipt
                api.disable_operator(c, operator_id="ISSUER-A")
                forbidden(sign(issuer, "ISSUER-A", "issue",
                               "request-issue-05", issue), minute=4)
                row = c.execute(
                    "SELECT last_sequence,status FROM v8_preview_server_license_state "
                    "WHERE license_id='LIC-A'").fetchone()
                assert row["last_sequence"] == 1 and row["status"] == "revoked"
                try:
                    api.require_checkout()
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Preview checkout was allowed")
                for table in ("sales", "sale_items", "returns",
                              "stock_moves", "supplier_payments", "credit_logs"):
                    assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
                c.commit()
            finally:
                c.close()
        """)

    def test_rollback_duplicate_claims_and_isolation_guards(self):
        self.isolated("""
            import base64, json
            from datetime import datetime, timezone
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from velopos import database
            from velopos_qt.activation_admin_gateway import PreviewSignedActivationGateway
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority

            key = Ed25519PrivateKey.generate()
            enc = lambda x: base64.urlsafe_b64encode(x).decode().rstrip("=")
            pub = enc(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
            database.init_db()
            auth = PreviewServerActivationAuthority(database, signing_key=key)
            api = PreviewSignedActivationGateway(database, authority=auth)
            c = database.connect()
            try:
                try:
                    api.initialize(c)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Initialized without caller transaction")
                c.execute("BEGIN IMMEDIATE")
                api.initialize(c)
                api.provision_operator(c, operator_id="ADMIN-A",
                                       public_key_b64=pub, role="Admin")
                # Duplicate operator registration cannot replace its public key.
                try:
                    api.provision_operator(c, operator_id="ADMIN-A",
                                           public_key_b64=pub, role="Admin")
                except Exception:
                    pass
                else:
                    raise AssertionError("Operator key overwrite accepted")
                c.commit()
            finally:
                c.close()

            def sign_request(payload_bytes):
                return enc(payload_bytes) + "." + enc(key.sign(payload_bytes))
            registration = json.dumps(dict(
                v=8, operator_id="ADMIN-A", request_id="request-register1",
                operation="register", payload=dict(
                    license_id="LIC-A", machine_id="MACHINE-A",
                    branch_id="BRANCH-A", expires_utc="2026-11-05T00:00:00Z"),
                issued_utc="2026-11-04T09:00:00Z",
                expires_utc="2026-11-04T09:04:00Z")).encode()
            moment = datetime(2026, 11, 4, 9, 1, tzinfo=timezone.utc)
            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                response = api.dispatch(
                    c, signed_request=sign_request(registration), server_now=moment)
                assert response.response["status"] == "registered"
                c.rollback()  # Simulated crash before commit / network response.
            finally:
                c.close()
            with database.db() as c:
                c.execute("BEGIN IMMEDIATE")
                assert c.execute(
                    "SELECT COUNT(*) FROM v8_preview_server_license_state").fetchone()[0] == 0
                assert c.execute(
                    "SELECT COUNT(*) FROM v8_preview_activation_commands").fetchone()[0] == 0
                fresh = api.dispatch(
                    c, signed_request=sign_request(registration), server_now=moment)
                assert not fresh.retry
                assert c.execute(
                    "SELECT COUNT(*) FROM v8_preview_activation_commands").fetchone()[0] == 1

            with database.db() as c:
                c.execute("BEGIN IMMEDIATE")
                duplicate_json = (
                    b'{"v":8,"v":8,"operator_id":"ADMIN-A","operation":"revoke",'
                    b'"request_id":"request-duplicate","issued_utc":"2026-11-04T09:00:00Z",'
                    b'"expires_utc":"2026-11-04T09:04:00Z",'
                    b'"payload":{"license_id":"LIC-A"}}'
                )
                try:
                    api.dispatch(c, signed_request=sign_request(duplicate_json),
                                 server_now=moment)
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Signed duplicate JSON accepted")
                assert c.execute(
                    "SELECT COUNT(*) FROM v8_preview_activation_commands").fetchone()[0] == 1
        """)
        self.isolated("""
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from velopos import database
            from velopos_qt.activation_admin_gateway import PreviewSignedActivationGateway
            from velopos_qt.server_activation_reference import PreviewServerActivationAuthority
            database.init_db()
            auth = PreviewServerActivationAuthority(database,
                                                    signing_key=Ed25519PrivateKey.generate())
            try:
                PreviewSignedActivationGateway(database, authority=auth)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Preview gateway allowed production path")
        """, folder="VeloPOS")


if __name__ == "__main__":
    unittest.main()
