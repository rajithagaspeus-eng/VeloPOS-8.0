"""Atomic V8 sale boundary integration: one SQLite snapshot, no commerce.

Uses independent temporary process per test to isolate VELOPOS_HOME.
No checkout UI, production DB, paid licenses, service secrets or stock writes.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


FIXTURE = """
import base64, hashlib, json
from datetime import datetime, timezone
from decimal import Decimal
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from velopos import database, services
from velopos_qt.auth_model import PreviewAuthenticator, PreviewIdentity
from velopos_qt.atomic_sale_boundary import PreviewAtomicSaleBoundary
from velopos_qt.sale_rehearsal import RollbackOnlySaleRehearsal

enc = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
def pub(key):
    return enc(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
def sign(key, payload):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return enc(raw) + "." + enc(key.sign(raw)), hashlib.sha256(raw).hexdigest()

license_signer = Ed25519PrivateKey.generate()
server_signer = Ed25519PrivateKey.generate()
license_key, _ = sign(license_signer, dict(
    v=8, license_id="LIC-001", m="MACHINE-001", branch_id="BRANCH-001",
    actions=["sale"], expires="2030-01-01",
))
prior = dict(
    v=8, machine_id="MACHINE-001", license_id="LIC-001",
    branch_id="BRANCH-001", status="active", sequence=13,
    observed_utc="2026-11-04T08:00:00Z",
    expires_utc="2026-11-05T00:00:00Z",
)
previous, digest = sign(server_signer, prior)
current, _ = sign(server_signer, dict(
    prior, sequence=14, observed_utc="2026-11-04T09:00:00Z",
    previous_payload_sha256=digest,
))
database.init_db()
services.save_user("cashier", "StrongCashierPass2026!", "Cashier", "setup")
user = PreviewAuthenticator(database).authenticate("cashier", "StrongCashierPass2026!")
services.save_product("RICE", "Sample Rice", "demo", sell=45, stock=10)
services.save_product("SOAP", "Sample Soap", "demo", sell=25, stock=4)
with database.db() as c:
    c.execute("INSERT INTO shifts(cashier,status) VALUES('cashier','OPEN')")
    shift = c.execute("SELECT id FROM shifts ORDER BY id DESC LIMIT 1").fetchone()[0]
    c.execute("CREATE TABLE v8_preview_branch_registry ("
              "branch_id TEXT PRIMARY KEY, active INTEGER NOT NULL)")
    c.execute("CREATE TABLE v8_preview_branch_memberships ("
              "username TEXT NOT NULL, branch_id TEXT NOT NULL, "
              "active INTEGER NOT NULL, PRIMARY KEY(username,branch_id))")
    c.execute("CREATE TABLE v8_preview_branch_shifts ("
              "shift_id INTEGER PRIMARY KEY, branch_id TEXT NOT NULL)")
    c.execute("INSERT INTO v8_preview_branch_registry VALUES('BRANCH-001',1)")
    c.execute("INSERT INTO v8_preview_branch_memberships "
              "VALUES('cashier','BRANCH-001',1)")
    c.execute("INSERT INTO v8_preview_branch_shifts VALUES(?,'BRANCH-001')", (shift,))
boundary = PreviewAtomicSaleBoundary(
    database, license_public_key_b64=pub(license_signer)
)
lines = [
    {"barcode": "RICE", "qty": 2, "price": 45},
    {"barcode": "RICE", "qty": 3, "price": 45},
    {"barcode": "SOAP", "qty": 1, "price": 25},
]
args = dict(
    identity=user, shift_id=shift, request_id="atomic-demo-request-0001",
    lines=lines, expected_branch_id="BRANCH-001", license_id="LIC-001",
    machine_id="MACHINE-001", license_key=license_key,
    server_public_key_b64=pub(server_signer), previous_status=previous,
    current_status=current, today="2026-11-04",
    now=datetime(2026,11,4,10,tzinfo=timezone.utc),
)
def snapshot(c):
    return {
        "sales": c.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
        "sale_items": c.execute("SELECT COUNT(*) FROM sale_items").fetchone()[0],
        "returns": c.execute("SELECT COUNT(*) FROM returns").fetchone()[0],
        "stock": tuple(
            (row["barcode"], row["stock_qty"])
            for row in c.execute(
                "SELECT barcode,stock_qty FROM products ORDER BY barcode")
        ),
        "moves": c.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0],
        "payments": c.execute(
            "SELECT COUNT(*) FROM supplier_payments").fetchone()[0],
        "journal": c.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='v8_preview_request_journal'"
        ).fetchone()[0],
    }
"""


class AtomicBoundaryIntegrationTests(unittest.TestCase):
    def isolated(self, script, directory="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_atomic_boundary_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / directory)
            result = subprocess.run(
                [sys.executable, "-c", FIXTURE + textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=75,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_all_local_checks_consistent_but_sale_always_denied(self):
        self.isolated("""
            from dataclasses import FrozenInstanceError
            with database.db() as c:
                before = snapshot(c)
            result = boundary.inspect(**args)
            assert result.line_count == 3 and result.subtotal == Decimal("250.00")
            assert result.local_checks_consistent and result.session_bound, result
            assert result.branch_verified and result.license_bound, result
            assert result.signed_chain_valid and result.policy_consistent, result
            assert result.can_execute is False and result.can_checkout is False
            for reason in ("preview_checkout_disabled",
                           "idempotency_not_implemented", "license_not_verified",
                           "preview_transactions_disabled",
                           "commercial_atomic_sale_unimplemented"):
                assert reason in result.reasons, (reason, result)
            try:
                result.can_checkout = True
            except FrozenInstanceError:
                pass
            else:
                raise AssertionError("Diagnostic is mutable")
            try:
                boundary.require(**args)
            except PermissionError:
                pass
            else:
                raise AssertionError("Simulated policy was promoted to checkout")
            with database.db() as c:
                assert snapshot(c) == before, (before, snapshot(c))
        """)

    def test_duplicate_lines_stock_price_and_expiry_fail_inside_one_snapshot(self):
        self.isolated("""
            shortage = boundary.inspect(**dict(
                args, lines=[
                    {"barcode":"RICE", "qty":7, "price":45},
                    {"barcode":"RICE", "qty":4, "price":45},
                ]))
            assert "insufficient_stock:RICE" in shortage.reasons, shortage
            assert not shortage.local_checks_consistent
            price = boundary.inspect(**dict(
                args, lines=[{"barcode":"RICE", "qty":1, "price":44}]))
            assert "price_changed:RICE" in price.reasons and not price.local_checks_consistent
            with database.db() as c:
                c.execute("UPDATE products SET expiry_date='2026-11-02' WHERE barcode='SOAP'")
                c.execute("INSERT INTO batches(barcode,batch_no,expiry_date,qty_remaining)"
                          " VALUES('RICE','BAD-EXPIRED','2026-11-01',2)")
                before = snapshot(c)
            expired = boundary.inspect(**args)
            assert "expired_product:SOAP" in expired.reasons, expired
            assert "expired_batch_review:RICE" in expired.reasons, expired
            assert not expired.local_checks_consistent
            with database.db() as c:
                assert snapshot(c) == before
        """)

    def test_revoked_session_closed_shift_and_branch_scope_do_not_inherit_permissions(self):
        self.isolated("""
            fake = PreviewIdentity("cashier", "Cashier", "forged")
            denied = boundary.inspect(**dict(args, identity=fake))
            assert not denied.session_bound and not denied.policy_consistent, denied
            assert "verified_cashier_required" in denied.reasons
            assert "verified_session_required" in denied.reasons
            with database.db() as c:
                c.execute("UPDATE shifts SET status='CLOSED' WHERE id=?", (shift,))
            closed = boundary.inspect(**args)
            assert "shift_not_open" in closed.reasons, closed
            assert not closed.local_checks_consistent and not closed.policy_consistent
            with database.db() as c:
                c.execute("UPDATE shifts SET status='OPEN' WHERE id=?", (shift,))
                c.execute("UPDATE v8_preview_branch_memberships SET active=0")
            branch = boundary.inspect(**args)
            assert not branch.branch_verified and not branch.policy_consistent
            assert "actor_branch_membership_required" in branch.reasons
            with database.db() as c:
                c.execute("UPDATE v8_preview_branch_memberships SET active=1")
            wrong_license, _ = sign(license_signer, dict(
                v=8, license_id="OTHER", m="MACHINE-001",
                branch_id="BRANCH-001", actions=["sale"], expires="2030-01-01"))
            mismatch = boundary.inspect(**dict(args, license_key=wrong_license))
            assert not mismatch.license_bound and not mismatch.policy_consistent
            assert "signed_license_activation_binding_unverified" in mismatch.reasons
            assert mismatch.can_execute is False
        """)

    def test_invalid_activation_chain_and_expired_observation_are_denied(self):
        self.isolated("""
            p, sig = current.split(".")
            bad_sig = ("B" if sig[0] == "A" else "A") + sig[1:]
            bad = boundary.inspect(**dict(args, current_status=p+"."+bad_sig))
            assert not bad.signed_chain_valid, bad
            assert "current_status_signature_invalid" in bad.reasons
            assert bad.can_checkout is False
            later = boundary.inspect(**dict(
                args, now=datetime(2026,11,8,10,tzinfo=timezone.utc)))
            assert "activation_observation_stale" in later.reasons
            assert "activation_signed_expiry_elapsed" in later.reasons
            assert not later.signed_chain_valid and not later.policy_consistent
        """)

    def test_caller_owned_transaction_never_committed_and_foreign_db_denied(self):
        self.isolated("""
            import sqlite3
            c = database.connect()
            try:
                try:
                    boundary.inspect_in_transaction(c, **args)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("A transaction is mandatory")
                c.execute("BEGIN IMMEDIATE")
                c.execute("CREATE TABLE boundary_caller_test (v TEXT)")
                c.execute("INSERT INTO boundary_caller_test VALUES ('uncommitted')")
                result = boundary.inspect_in_transaction(c, **args)
                assert result.local_checks_consistent
                assert c.in_transaction
                assert c.execute("SELECT COUNT(*) FROM boundary_caller_test").fetchone()[0] == 1
                c.rollback()
            finally:
                c.close()
            with database.db() as verify:
                assert not verify.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='boundary_caller_test'"
                ).fetchone()
            foreign = sqlite3.connect(":memory:")
            try:
                foreign.execute("BEGIN IMMEDIATE")
                try:
                    boundary.inspect_in_transaction(foreign, **args)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Foreign connection accepted")
            finally:
                foreign.rollback()
                foreign.close()
        """)

    def test_invalid_draft_rolls_back_and_writes_no_request_journal(self):
        self.isolated("""
            with database.db() as c:
                before = snapshot(c)
            for draft in ([], [{"barcode":"RICE","qty":0,"price":45}],
                          [{"barcode":"RICE","qty":"NaN","price":45}],
                          [{"barcode":"RICE","qty":1,"price":-1}]):
                try:
                    boundary.inspect(**dict(args, lines=draft))
                except ValueError:
                    pass
                else:
                    raise AssertionError("Bad draft accepted")
            try:
                boundary.inspect(**dict(args, today="2026-2-1"))
            except ValueError:
                pass
            else:
                raise AssertionError("Noncanonical date accepted")
            with database.db() as c:
                assert snapshot(c) == before
        """)

    def test_rehearsal_reuses_locked_preflight_and_rejects_expired_batch(self):
        self.isolated("""
            rehearsal = RollbackOnlySaleRehearsal(database)
            with database.db() as c:
                before = snapshot(c)
            result = rehearsal.simulate(
                identity=user, shift_id=shift,
                request_id="rehearsal-atomic-0001", lines=lines,
                today="2026-11-04")
            assert result.persisted is False and result.subtotal == Decimal("250.00")
            with database.db() as c:
                assert snapshot(c) == before
                c.execute("INSERT INTO batches(barcode,batch_no,expiry_date,qty_remaining)"
                          " VALUES('RICE','EXPIRED-BATCH','2026-11-01',2)")
                before_expiry = snapshot(c)
            try:
                rehearsal.simulate(
                    identity=user, shift_id=shift,
                    request_id="rehearsal-atomic-0002", lines=lines,
                    today="2026-11-04")
            except ValueError as exc:
                assert "expired_batch_review:RICE" in str(exc), str(exc)
            else:
                raise AssertionError("Expired batch passed rehearsal")
            with database.db() as c:
                assert snapshot(c) == before_expiry
        """)


if __name__ == "__main__":
    unittest.main()
