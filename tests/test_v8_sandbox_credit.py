"""Disposable V8 credit invoice/limit/repayment integration (not payment capture)."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.test_v8_phase2_atomic_sale_boundary import FIXTURE
from tests.test_v8_sandbox_returns import EXTRA


CREDIT_FIXTURE = """
from velopos_qt.sandbox_credit_ledger import PreviewSandboxCreditLedger
credit_service = PreviewSandboxCreditLedger(
    database, license_public_key_b64=pub(license_signer)
)
services.save_user("manager", "ManagerStrongPass2026!", "Admin", "setup")
manager = PreviewAuthenticator(database).authenticate(
    "manager", "ManagerStrongPass2026!"
)
with database.db() as c:
    c.execute("INSERT INTO main.shifts(cashier,status) VALUES('manager','OPEN')")
    manager_shift = c.execute(
        "SELECT id FROM main.shifts WHERE cashier='manager' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    c.execute(
        "INSERT INTO main.v8_preview_branch_memberships "
        "(username,branch_id,active) VALUES('manager','BRANCH-001',1)"
    )
    c.execute(
        "INSERT INTO main.v8_preview_branch_shifts "
        "(shift_id,branch_id) VALUES(?,'BRANCH-001')",
        (manager_shift,)
    )
    c.execute(
        "INSERT INTO main.customers(name,phone) VALUES('TEST Credit Customer','90001')"
    )
    customer_id = c.execute(
        "SELECT id FROM main.customers WHERE phone='90001'"
    ).fetchone()[0]
    c.execute(
        "INSERT INTO main.customers(name,phone) VALUES('TEST Other Customer','90002')"
    )
    other_customer = c.execute(
        "SELECT id FROM main.customers WHERE phone='90002'"
    ).fetchone()[0]
credit_license, _ = sign(license_signer, dict(
    v=8,license_id="LIC-001",m="MACHINE-001",
    branch_id="BRANCH-001",actions=["sale","return","credit_payment"],
    expires="2030-01-01"
))
def ctx(**overrides):
    d = dict(
        identity=user,shift_id=shift,expected_branch_id="BRANCH-001",
        license_id="LIC-001",machine_id="MACHINE-001",
        license_key=credit_license,
        server_public_key_b64=pub(server_signer),
        previous_status=previous,current_status=current,
        today="2026-11-04",
        now=datetime(2026,11,4,10,tzinfo=timezone.utc),
    )
    d.update(overrides)
    return d
def open_account(credit_limit="300",customer=customer_id,**kw):
    admin_context = dict(identity=manager,shift_id=manager_shift)
    admin_context.update(kw)
    return credit_service.open_test_account(
        customer_id=customer,credit_limit=credit_limit,
        **ctx(**admin_context)
    )
def charge(ref,request_id="credit-charge-0001",customer=customer_id,**kw):
    return credit_service.attach_unpaid_invoice(
        customer_id=customer,invoice_ref=ref,request_id=request_id,
        **ctx(**kw)
    )
def repay(amount="100",request_id="credit-repayment-0001",customer=customer_id,**kw):
    return credit_service.declare_repayment(
        customer_id=customer,amount=amount,request_id=request_id,
        **ctx(**kw)
    )
"""


class SandboxCreditIntegrationTests(unittest.TestCase):
    def isolated(self, body):
        with tempfile.TemporaryDirectory(prefix="v8_sandbox_credit_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            code = FIXTURE+"\n"+EXTRA+"\n"+CREDIT_FIXTURE+"\n"+textwrap.dedent(body)
            result = subprocess.run(
                [sys.executable,"-c",code],env=env,capture_output=True,
                text=True,timeout=100
            )
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_admin_registers_customer_limit_and_credit_attaches_unpaid_invoice(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            with database.db() as c:
                before = snapshot(c)
                customer_balance = c.execute(
                    "SELECT credit_balance FROM main.customers WHERE id=?",
                    (customer_id,)
                ).fetchone()[0]
            assert open_account() == 30000
            assert open_account() == 30000
            evidence = charge(sale.reference)
            assert evidence.amount_cents == 25000
            assert evidence.outstanding_cents == 25000
            assert not evidence.replayed
            assert not evidence.actual_payment_captured
            assert not evidence.real_customer_balance_changed
            assert not evidence.can_checkout
            again = charge(sale.reference)
            assert again.replayed and again.reference == evidence.reference
            audit = credit_service.reconcile()
            assert audit.balanced, audit
            assert audit.account_count == 1 and audit.total_charged_cents == 25000
            with database.db() as c:
                for field in ("sales","sale_items","returns","stock","moves","payments"):
                    assert snapshot(c)[field] == before[field],field
                assert c.execute(
                    "SELECT credit_balance FROM main.customers WHERE id=?",
                    (customer_id,)
                ).fetchone()[0] == customer_balance
                assert c.execute(
                    "SELECT COUNT(*) FROM main.credit_logs"
                ).fetchone()[0] == 0
        """)

    def test_cash_repayments_reduce_test_outstanding_without_real_payment(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            open_account()
            charge(sale.reference)
            p1 = repay("100")
            assert p1.outstanding_cents == 15000
            assert p1.amount_cents == 10000
            assert not p1.actual_payment_captured
            p2 = repay("100")
            assert p2.replayed and p2.outstanding_cents == 15000
            p3 = repay("150",request_id="credit-repayment-0002")
            assert p3.outstanding_cents == 0
            audit = credit_service.reconcile()
            assert audit.balanced and audit.total_charged_cents == 25000,audit
            assert audit.total_repayment_declared_cents == 25000
            assert audit.total_outstanding_cents == 0
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM main.credit_logs"
                ).fetchone()[0] == 0
        """)

    def test_limit_denial_then_declared_repayment_frees_available_limit(self):
        self.isolated("""
            first = sale_service.simulate_commit(**args)
            second = sale_service.simulate_commit(**dict(
                args,request_id="credit-sale-two-0001",
                lines=[
                    {"barcode":"RICE","qty":2,"price":45},
                    {"barcode":"SOAP","qty":2,"price":25}
                ]
            ))
            open_account("300")
            charge(first.reference)
            try:
                charge(second.reference,request_id="credit-charge-0002")
            except PermissionError as exc:
                assert "limit exceeded" in str(exc)
            else:
                raise AssertionError("Limit bypassed")
            repay("100")
            new = charge(second.reference,request_id="credit-charge-0002")
            assert new.outstanding_cents == 29000
            audit = credit_service.reconcile()
            assert audit.balanced, audit
            assert audit.total_charged_cents == 39000
            assert audit.total_repayment_declared_cents == 10000
        """)

    def test_denies_missing_customer_forged_actor_and_non_admin_limit_changes(self):
        self.isolated("""
            from velopos_qt.auth_model import PreviewIdentity
            for action in (
                lambda: credit_service.open_test_account(
                    customer_id=customer_id,credit_limit="300",**ctx()
                ),
                lambda: open_account(customer=123456789),
                lambda: open_account(credit_limit="300",identity=PreviewIdentity(
                    "manager","Admin","forged"
                )),
            ):
                try:
                    action()
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Unauthorized account setup")
            open_account()
            for action in (
                lambda: open_account("301"),
                lambda: credit_service.attach_unpaid_invoice(
                    customer_id=customer_id,invoice_ref="SBX-"+("a"*24),
                    request_id="credit-invalid-sale-0001",**ctx()
                ),
                lambda: charge("SBX-"+("a"*24)),
            ):
                try:
                    action()
                except (PermissionError,ValueError):
                    pass
                else:
                    raise AssertionError("Invalid credit charge")
        """)

    def test_refuses_double_paid_invoice_cross_customer_and_changed_key(self):
        self.isolated("""
            open_account()
            open_account(customer=other_customer)
            tendered = sale_service.simulate_commit(**dict(
                args,tenders=[{"method":"Cash","amount":"250"}]
            ))
            try:
                charge(tendered.reference)
            except PermissionError:
                pass
            else:
                raise AssertionError("Paid declaration was credited")
            unpaid = sale_service.simulate_commit(**dict(
                args,request_id="credit-unpaid-sale-0002",
                lines=[{"barcode":"SOAP","qty":1,"price":25}]
            ))
            charge(unpaid.reference)
            for kwargs in (
                dict(request_id="credit-charge-0002",customer=other_customer),
                dict(request_id="credit-charge-0001",customer=other_customer),
            ):
                try:
                    charge(unpaid.reference,**kwargs)
                except (PermissionError,IdempotencyConflict):
                    pass
                else:
                    raise AssertionError("Invoice attached to different customer")
            assert credit_service.reconcile().balanced
        """)

    def test_credit_charge_and_repayment_failpoints_never_commit_half_entries(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            open_account()
            for stage in ("after_claim","after_post","after_complete"):
                try:
                    charge(sale.reference,inject_failure_at=stage)
                except RuntimeError as exc:
                    assert "Injected credit failure" in str(exc),exc
                else:
                    raise AssertionError("Credit charge failpoint "+stage)
                with database.db() as c:
                    assert c.execute(
                        "SELECT COUNT(*) FROM main.v8_preview_sandbox_credit_charges"
                    ).fetchone()[0] == 0
            charge(sale.reference)
            for stage in ("after_claim","after_post","after_complete"):
                try:
                    repay(inject_failure_at=stage)
                except RuntimeError as exc:
                    assert "Injected credit failure" in str(exc),exc
                else:
                    raise AssertionError("Credit repayment failpoint "+stage)
                with database.db() as c:
                    assert c.execute(
                        "SELECT COUNT(*) FROM main.v8_preview_sandbox_credit_repayments"
                    ).fetchone()[0] == 0
            assert repay().outstanding_cents == 15000
            assert credit_service.reconcile().balanced
        """)

    def test_repayment_overdraft_bad_precision_non_cash_and_duplicate_conflict(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            open_account()
            charge(sale.reference)
            for attempt in (
                lambda: repay("251"),
                lambda: repay("0"),
                lambda: repay("10.001"),
                lambda: repay("10",method="Card"),
                lambda: repay("10",current_status="not-signed"),
                lambda: repay("10",shift_id=shift+1000),
            ):
                try:
                    attempt()
                except (PermissionError,ValueError):
                    pass
                else:
                    raise AssertionError("Invalid repayment declared")
            repay("100")
            for variant in (
                lambda: repay("101"),
                lambda: repay("100",customer=other_customer),
            ):
                try:
                    variant()
                except (IdempotencyConflict,PermissionError):
                    pass
                else:
                    raise AssertionError("Repayment request key mutated")
            assert credit_service.reconcile().balanced
        """)

    def test_return_on_credit_backed_invoice_denied_pending_credit_notes(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            open_account()
            charge(sale.reference)
            try:
                return_service.simulate_return(**new_return(sale.reference))
            except PermissionError as exc:
                assert "Credit-backed return" in str(exc),exc
            else:
                raise AssertionError("Return bypassed credit note policy")
            assert credit_service.reconcile().balanced
        """)

    def test_credit_audit_flags_tampered_invoice_and_unlinked_repayment(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            open_account()
            charge(sale.reference)
            repay()
            assert credit_service.reconcile().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_credit_charges "
                    "SET amount_cents=999999"
                )
            altered = credit_service.reconcile()
            assert not altered.balanced
            assert "credit_invoice_link_mismatch" in altered.reasons
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_credit_charges "
                    "SET amount_cents=25000"
                )
                c.execute(
                    "DELETE FROM main.v8_preview_sandbox_credit_repayments"
                )
            orphan = credit_service.reconcile()
            assert not orphan.balanced and "orphan_credit_journal" in orphan.reasons
        """)

    def test_partial_credit_note_reduces_outstanding_and_closeout_net(self):
        self.isolated("""
            from velopos_qt.sandbox_accounting import PreviewSandboxAccounting
            invoice = sale_service.simulate_commit(**args)
            open_account()
            initial = charge(invoice.reference)
            note = credit_service.declare_credit_note(
                customer_id=customer_id,charge_ref=initial.reference,
                sale_line_no=1,quantity="1",request_id="credit-note-0001",
                **ctx()
            )
            assert note.amount_cents == 4500
            assert note.outstanding_cents == 20500
            assert not note.actual_payment_captured
            assert not note.real_customer_balance_changed
            repaid = repay("100")
            assert repaid.outstanding_cents == 10500
            audit = credit_service.reconcile()
            assert audit.balanced, audit
            assert audit.total_credit_notes_cents == 4500
            assert audit.total_outstanding_cents == 10500
            closeout = PreviewSandboxAccounting(database).closeout()
            assert closeout.balanced, closeout
            assert closeout.declared_credit_notes_cents == 4500
            assert closeout.net_after_declared_returns_cents == 20500
            assert closeout.outstanding_credit_cents == 10500
            with database.db() as c:
                assert c.execute(
                    "SELECT credit_balance FROM main.customers WHERE id=?",
                    (customer_id,)
                ).fetchone()[0] == 0
                assert c.execute(
                    "SELECT COUNT(*) FROM main.credit_logs"
                ).fetchone()[0] == 0
                assert c.execute(
                    "SELECT remaining_qty FROM main.v8_preview_sandbox_stock "
                    "WHERE barcode='RICE'"
                ).fetchone()[0] == "5"
        """)

    def test_credit_note_replay_and_mutated_request_conflict(self):
        self.isolated("""
            from velopos_qt.idempotency_ledger import IdempotencyConflict
            invoice = sale_service.simulate_commit(**args)
            open_account()
            issued = charge(invoice.reference)
            opts = dict(
                customer_id=customer_id,charge_ref=issued.reference,
                sale_line_no=1,quantity="1",request_id="credit-note-0001",
                **ctx()
            )
            first = credit_service.declare_credit_note(**opts)
            replay = credit_service.declare_credit_note(**opts)
            assert replay.replayed and replay.reference == first.reference
            assert replay.outstanding_cents == 20500
            for variant in (
                dict(opts,quantity="2"), dict(opts,disposition="DISCARDED"),
                dict(opts,customer_id=other_customer)
            ):
                try:
                    credit_service.declare_credit_note(**variant)
                except (IdempotencyConflict,PermissionError):
                    pass
                else:
                    raise AssertionError("Mutated credit-note id reused")
            assert credit_service.reconcile().balanced
        """)

    def test_multiple_credit_notes_bound_to_original_line_and_sale_limit(self):
        self.isolated("""
            invoice = sale_service.simulate_commit(**args)
            open_account()
            issued = charge(invoice.reference)
            for n in (1,2):
                note = credit_service.declare_credit_note(
                    customer_id=customer_id,charge_ref=issued.reference,
                    sale_line_no=1,quantity="1",request_id="credit-note-000"+str(n),
                    disposition="DISCARDED",**ctx()
                )
                assert note.amount_cents == 4500
            assert credit_service.reconcile().total_credit_notes_cents == 9000
            for line_no, qty in ((1,"0.01"),(999,"1"),(2,"4")):
                try:
                    credit_service.declare_credit_note(
                        customer_id=customer_id,charge_ref=issued.reference,
                        sale_line_no=line_no,quantity=qty,
                        request_id="credit-note-invalid-"+str(line_no),**ctx()
                    )
                except (PermissionError,ValueError):
                    pass
                else:
                    raise AssertionError("Original sale quantity exceeded")
            assert credit_service.reconcile().balanced
        """)

    def test_credit_note_cannot_exceed_debt_after_repayments(self):
        self.isolated("""
            invoice = sale_service.simulate_commit(**args)
            open_account()
            issued = charge(invoice.reference)
            repay("250")
            try:
                credit_service.declare_credit_note(
                    customer_id=customer_id,charge_ref=issued.reference,
                    sale_line_no=1,quantity="1",request_id="credit-note-0001",
                    **ctx()
                )
            except PermissionError as exc:
                assert "unpaid debt" in str(exc)
            else:
                raise AssertionError("Credit note created cash refund from zero debt")
            audit = credit_service.reconcile()
            assert audit.balanced and audit.total_credit_notes_cents == 0
        """)

    def test_credit_note_failure_injection_rolls_back_journal_and_note(self):
        self.isolated("""
            invoice = sale_service.simulate_commit(**args)
            open_account()
            issued = charge(invoice.reference)
            for point in ("after_claim","after_post","after_complete"):
                try:
                    credit_service.declare_credit_note(
                        customer_id=customer_id,charge_ref=issued.reference,
                        sale_line_no=1,quantity="1",request_id="credit-note-0001",
                        inject_failure_at=point,**ctx()
                    )
                except RuntimeError as exc:
                    assert "Injected credit note failure" in str(exc)
                else:
                    raise AssertionError("Credit note failpoint did not trigger")
                with database.db() as c:
                    assert c.execute(
                        "SELECT COUNT(*) FROM main.v8_preview_sandbox_credit_notes"
                    ).fetchone()[0] == 0
                    assert c.execute(
                        "SELECT COUNT(*) FROM main.v8_preview_request_journal "
                        "WHERE scope='credit_note'"
                    ).fetchone()[0] == 0
            assert credit_service.reconcile().balanced
            assert credit_service.declare_credit_note(
                customer_id=customer_id,charge_ref=issued.reference,
                sale_line_no=1,quantity="1",request_id="credit-note-0001",
                **ctx()
            ).amount_cents == 4500
        """)

    def test_credit_note_tamper_detected_by_audit_and_closeout(self):
        self.isolated("""
            from velopos_qt.sandbox_accounting import PreviewSandboxAccounting
            invoice = sale_service.simulate_commit(**args)
            open_account()
            issued = charge(invoice.reference)
            credit_service.declare_credit_note(
                customer_id=customer_id,charge_ref=issued.reference,
                sale_line_no=1,quantity="1",request_id="credit-note-0001",
                **ctx()
            )
            assert credit_service.reconcile().balanced
            assert PreviewSandboxAccounting(database).closeout().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_credit_notes "
                    "SET amount_cents=9999"
                )
            assert not credit_service.reconcile().balanced
            checked = PreviewSandboxAccounting(database).closeout()
            assert not checked.balanced
            assert "sandbox_credit_note_quantity_mismatch" in checked.reasons
        """)

    def test_real_credit_is_never_enabled(self):
        self.isolated("""
            try:
                credit_service.require_real_credit()
            except PermissionError:
                pass
            else:
                raise AssertionError("Commercial credit accidentally enabled")
        """)


if __name__ == "__main__":
    unittest.main()
