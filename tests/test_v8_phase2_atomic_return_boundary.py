"""Atomic return diagnostic validates policy and quantity in test data only."""
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
from velopos_qt.atomic_return_boundary import PreviewAtomicReturnBoundary

enc=lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
def pub(key):
    return enc(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw))
def sign(key,payload):
    raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
    return enc(raw)+"."+enc(key.sign(raw)),hashlib.sha256(raw).hexdigest()
license_signer=Ed25519PrivateKey.generate()
server_signer=Ed25519PrivateKey.generate()
license_key,_=sign(license_signer,dict(v=8,license_id="LIC-RET",
    m="MACHINE-RET",branch_id="BRANCH-RET",actions=["return"],expires="2030-01-01"))
prior=dict(v=8,machine_id="MACHINE-RET",license_id="LIC-RET",
    branch_id="BRANCH-RET",status="active",sequence=31,
    observed_utc="2026-11-04T08:00:00Z",expires_utc="2026-11-05T00:00:00Z")
previous,digest=sign(server_signer,prior)
current,_=sign(server_signer,dict(prior,sequence=32,
    observed_utc="2026-11-04T09:00:00Z",previous_payload_sha256=digest))
database.init_db()
services.save_user("cashier","StrongCashierPass2026!","Cashier","setup")
identity=PreviewAuthenticator(database).authenticate("cashier","StrongCashierPass2026!")
services.save_product("RICE","Sample Rice","demo",sell=25,stock=8)
services.save_product("SOAP","Sample Soap","demo",sell=10,stock=3)
with database.db() as c:
    c.execute("INSERT INTO shifts(cashier,status) VALUES('cashier','OPEN')")
    shift=c.execute("SELECT id FROM shifts ORDER BY id DESC LIMIT 1").fetchone()[0]
    c.execute("CREATE TABLE v8_preview_branch_registry (branch_id TEXT PRIMARY KEY, active INTEGER NOT NULL)")
    c.execute("CREATE TABLE v8_preview_branch_memberships (username TEXT NOT NULL, branch_id TEXT NOT NULL, active INTEGER NOT NULL, PRIMARY KEY(username,branch_id))")
    c.execute("CREATE TABLE v8_preview_branch_shifts (shift_id INTEGER PRIMARY KEY, branch_id TEXT NOT NULL)")
    c.execute("INSERT INTO v8_preview_branch_registry VALUES('BRANCH-RET',1)")
    c.execute("INSERT INTO v8_preview_branch_memberships VALUES('cashier','BRANCH-RET',1)")
    c.execute("INSERT INTO v8_preview_branch_shifts VALUES(?,'BRANCH-RET')",(shift,))
    c.execute("INSERT INTO sales(invoice_no,date,time,total_amount,status) VALUES('INV-RET','2026-11-01','12:00:00',85,'OK')")
    c.execute("INSERT INTO sale_items(invoice_no,barcode,item_name,qty,selling_price,total) VALUES('INV-RET','RICE','Rice',3,25,75)")
    rice_id=c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.execute("INSERT INTO sale_items(invoice_no,barcode,item_name,qty,selling_price,total) VALUES('INV-RET','SOAP','Soap',1,10,10)")
    soap_id=c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.execute("INSERT INTO returns(return_no,invoice_no,date,amount,cashier) VALUES('RET-OLD','INV-RET','2026-11-02',25,'cashier')")
    c.execute("INSERT INTO return_items(return_no,sale_item_id,barcode,item_name,qty,price,total) VALUES('RET-OLD',?,'RICE','Rice',1,25,25)",(rice_id,))
engine=PreviewAtomicReturnBoundary(database,license_public_key_b64=pub(license_signer))
items=[{"sale_item_id":rice_id,"qty":1},{"sale_item_id":rice_id,"qty":1},{"sale_item_id":soap_id,"qty":1}]
args=dict(identity=identity,shift_id=shift,request_id="atomic-return-request-001",
    invoice_no="INV-RET",items=items,expected_branch_id="BRANCH-RET",
    license_id="LIC-RET",machine_id="MACHINE-RET",license_key=license_key,
    server_public_key_b64=pub(server_signer),previous_status=previous,
    current_status=current,today="2026-11-04",
    now=datetime(2026,11,4,10,tzinfo=timezone.utc))
def snapshot(c):
    return (c.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
        c.execute("SELECT COUNT(*) FROM returns").fetchone()[0],
        c.execute("SELECT COUNT(*) FROM return_items").fetchone()[0],
        tuple((r["barcode"],r["stock_qty"]) for r in c.execute(
            "SELECT barcode,stock_qty FROM products ORDER BY barcode")),
        c.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0],
        c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                  "AND name='v8_preview_request_journal'").fetchone()[0])
"""


class AtomicReturnBoundaryTests(unittest.TestCase):
    def isolated(self, source, dirname="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_atomic_return_") as root:
            env=os.environ.copy()
            env["VELOPOS_HOME"]=str(Path(root)/dirname)
            result=subprocess.run([sys.executable,"-c",FIXTURE+textwrap.dedent(source)],
                env=env,capture_output=True,text=True,timeout=75)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_valid_chain_and_partial_return_are_read_only_and_denied(self):
        self.isolated("""
            from dataclasses import FrozenInstanceError
            with database.db() as c: before=snapshot(c)
            result=engine.inspect(**args)
            assert result.item_count==2 and result.amount==Decimal("60.00"),result
            assert result.local_checks_consistent and result.session_bound
            assert result.branch_verified and result.license_bound
            assert result.signed_chain_valid and result.policy_consistent
            assert not result.can_execute and not result.can_refund
            assert "commercial_atomic_return_unimplemented" in result.reasons
            try: result.amount=Decimal("0")
            except FrozenInstanceError: pass
            else: raise AssertionError("Decision was mutable")
            try: engine.require(**args)
            except PermissionError: pass
            else: raise AssertionError("Return was authorized")
            with database.db() as c: assert snapshot(c)==before
        """)

    def test_overreturn_duplicate_lines_and_ineligible_invoices_fail(self):
        self.isolated("""
            over=engine.inspect(**dict(args,items=[
                {"sale_item_id":rice_id,"qty":"1.1"},
                {"sale_item_id":rice_id,"qty":"1.0"}]))
            assert "return_exceeds_remaining_quantity:%d"%rice_id in over.reasons
            assert not over.local_checks_consistent
            missing=engine.inspect(**dict(args,invoice_no="INV-MISSING"))
            assert "eligible_original_invoice_required" in missing.reasons
            wrong=engine.inspect(**dict(args,invoice_no="INV-OTHER",
                items=[{"sale_item_id":soap_id,"qty":1}]))
            assert "eligible_original_invoice_required" in wrong.reasons
            with database.db() as c:
                c.execute("UPDATE sales SET status='VOID' WHERE invoice_no='INV-RET'")
            void=engine.inspect(**args)
            assert "eligible_original_invoice_required" in void.reasons
        """)

    def test_session_branch_shift_signature_and_input_boundaries(self):
        self.isolated("""
            fake=PreviewIdentity("cashier","Cashier","forged")
            denied=engine.inspect(**dict(args,identity=fake))
            assert "verified_session_required" in denied.reasons
            assert not denied.session_bound and not denied.policy_consistent
            with database.db() as c:
                c.execute("UPDATE v8_preview_branch_memberships SET active=0")
            branch=engine.inspect(**args)
            assert "actor_branch_membership_required" in branch.reasons
            assert not branch.branch_verified
            with database.db() as c:
                c.execute("UPDATE v8_preview_branch_memberships SET active=1")
                c.execute("UPDATE shifts SET status='CLOSED' WHERE id=?",(shift,))
            closed=engine.inspect(**args)
            assert "shift_not_open" in closed.reasons
            p,sig=current.split(".")
            bad=engine.inspect(**dict(args,current_status=p+"."+("A" if sig[0]!="A" else "B")+sig[1:]))
            assert "current_status_signature_invalid" in bad.reasons
            for bad_items in ([],[{"sale_item_id":True,"qty":1}],
                [{"sale_item_id":rice_id,"qty":"NaN"}],
                [{"sale_item_id":rice_id,"qty":1,"extra":0}]):
                try: engine.inspect(**dict(args,items=bad_items))
                except ValueError: pass
                else: raise AssertionError("Invalid request accepted")
        """)

    def test_caller_transaction_is_preserved_and_production_path_denied(self):
        self.isolated("""
            with database.db() as c: before=snapshot(c)
            conn=database.connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("CREATE TABLE boundary_caller_test (v TEXT)")
                out=engine.inspect_in_transaction(conn,**args)
                assert out.local_checks_consistent and conn.in_transaction
                conn.rollback()
            finally: conn.close()
            with database.db() as c:
                assert snapshot(c)==before
                assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='boundary_caller_test'").fetchone()
            try: PreviewAtomicReturnBoundary(database,license_public_key_b64=pub(license_signer))
            except RuntimeError: pass
            else: raise AssertionError("Production-like storage accepted")
        """,dirname="VeloPOS")
        

if __name__ == "__main__":
    unittest.main()
