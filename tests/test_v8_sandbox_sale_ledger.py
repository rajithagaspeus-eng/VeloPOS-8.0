"""Durable *sandbox-only* invoice/stock/idempotency integration regressions.

All tests use disposable VeloPOS8PreviewData. No original financial service
or UI checkout is invoked and original product/sale/stock tables are unchanged.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.test_v8_phase2_atomic_sale_boundary import FIXTURE


EXTENSION = """
from velopos_qt.sandbox_sale_ledger import PreviewSandboxSaleLedger
from velopos_qt.idempotency_ledger import IdempotencyConflict
sandbox = PreviewSandboxSaleLedger(
    database, license_public_key_b64=pub(license_signer)
)
def main_counts(c):
    return snapshot(c)
def sandbox_stock(c):
    return {
        r["barcode"]: r["remaining_qty"] for r in c.execute(
            "SELECT barcode,remaining_qty FROM main.v8_preview_sandbox_stock "
            "ORDER BY barcode"
        )
    }
"""


class SandboxSaleLedgerTests(unittest.TestCase):
    def isolated(self, script):
        with tempfile.TemporaryDirectory(prefix="v8_sandbox_sale_") as temp:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(temp) / "VeloPOS8PreviewData")
            p = subprocess.run(
                [sys.executable, "-c",
                 FIXTURE + "\n" + EXTENSION + "\n" + textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=85
            )
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_persistent_sandbox_invoice_stock_moves_and_journal_commit_together(self):
        self.isolated("""
            with database.db() as c:
                before = main_counts(c)
            evidence = sandbox.simulate_commit(**args)
            assert evidence.reference.startswith("SBX-"), evidence
            assert evidence.subtotal_cents == 25000
            assert evidence.items == 3
            assert evidence.replayed is False
            assert evidence.sandbox_persisted is True
            assert evidence.actual_invoice_posted is False
            assert evidence.payment_captured is False
            assert evidence.can_checkout is False
            with database.db() as c:
                after = main_counts(c)
                assert after["sales"] == before["sales"]
                assert after["sale_items"] == before["sale_items"]
                assert after["returns"] == before["returns"]
                assert after["stock"] == before["stock"]
                assert after["moves"] == before["moves"]
                assert after["payments"] == before["payments"]
                assert after["journal"] == 1
                assert sandbox_stock(c) == {"RICE": "5", "SOAP": "3"}
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_sales"
                ).fetchone()[0] == 1
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_sale_lines"
                ).fetchone()[0] == 3
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_stock_moves"
                ).fetchone()[0] == 2
                total = c.execute(
                    "SELECT SUM(line_cents) FROM main.v8_preview_sandbox_sale_lines"
                ).fetchone()[0]
                assert total == evidence.subtotal_cents
                journal_row = c.execute(
                    "SELECT status,result_ref FROM main.v8_preview_request_journal "
                    "WHERE scope='sale' AND request_id=?", (args["request_id"],)
                ).fetchone()
                assert tuple(journal_row) == ("COMPLETED", evidence.reference)
            try:
                sandbox.require_commercial_sale(**args)
            except PermissionError:
                pass
            else:
                raise AssertionError("Sandbox service enabled commercial checkout")
        """)

    def test_duplicate_replay_requires_matching_durable_invoice_and_stays_exactly_once(self):
        self.isolated("""
            original = sandbox.simulate_commit(**args)
            second = sandbox.simulate_commit(**args)
            assert second.replayed is True
            assert second.reference == original.reference
            assert second.subtotal_cents == original.subtotal_cents
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_sales"
                ).fetchone()[0] == 1
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_stock_moves"
                ).fetchone()[0] == 2
            different = dict(args, lines=[
                {"barcode": "RICE", "qty": 1, "price": 45}
            ])
            try:
                sandbox.simulate_commit(**different)
            except IdempotencyConflict:
                pass
            else:
                raise AssertionError("Reused id accepted different immutable draft")
            with database.db() as c:
                assert sandbox_stock(c) == {"RICE":"5", "SOAP":"3"}
        """)

    def test_replay_rejects_equal_total_line_tampering(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET barcode='FORGED' WHERE reference=? AND line_no=1",
                    (first.reference,)
                )
            try:
                sandbox.simulate_commit(**args)
            except RuntimeError as exc:
                assert "invoice lines" in str(exc), exc
            else:
                raise AssertionError("Tampered equal-total invoice replay accepted")
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_sales"
                ).fetchone()[0] == 1
        """)

    def test_replay_rejects_tampered_stock_arithmetic(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_stock_moves "
                    "SET after_qty='999' WHERE reference=? AND barcode='RICE'",
                    (first.reference,)
                )
            try:
                sandbox.simulate_commit(**args)
            except RuntimeError as exc:
                assert "stock movements" in str(exc), exc
            else:
                raise AssertionError("Broken stock arithmetic replayed")
        """)

    def test_replay_rejects_nonfinite_stock_move(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_stock_moves "
                    "SET before_qty='NaN' WHERE reference=? AND barcode='RICE'",
                    (first.reference,)
                )
            try:
                sandbox.simulate_commit(**args)
            except RuntimeError as exc:
                assert "stock movements" in str(exc), exc
            else:
                raise AssertionError("Nonfinite stock movement replayed")
        """)

    def test_replay_rejects_tampered_line_number_even_when_totals_match(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET line_no=99 WHERE reference=? AND line_no=1",
                    (first.reference,)
                )
            try:
                sandbox.simulate_commit(**args)
            except RuntimeError as exc:
                assert "invoice lines" in str(exc), exc
            else:
                raise AssertionError("Reordered invoice line accepted on replay")
        """)

    def test_audit_rejects_equal_subtotal_line_price_and_amount_tampering(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET price='46',line_cents=line_cents+100 "
                    "WHERE reference=? AND line_no=1", (first.reference,)
                )
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET line_cents=line_cents-100 "
                    "WHERE reference=? AND line_no=2", (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invoice_line_arithmetic_mismatch" in audited.reasons, audited
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_hostile_decimal_exponents(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET quantity='1E-999999999' "
                    "WHERE reference=? AND line_no=1", (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_invoice_line_quantity" in audited.reasons, audited
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET quantity='1',price='1E-999999999' "
                    "WHERE reference=? AND line_no=1", (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_invoice_line_price" in audited.reasons, audited
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_oversized_persisted_decimal_text(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET quantity=? WHERE reference=? AND line_no=1",
                    ("1" * 129, first.reference)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_invoice_line_quantity" in audited.reasons, audited
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET quantity='1',price=? WHERE reference=? AND line_no=1",
                    ("1" * 129, first.reference)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_invoice_line_price" in audited.reasons, audited
        """)

    def test_audit_rejects_invalid_invoice_price_without_crashing(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET price='NaN' WHERE reference=? AND line_no=1",
                    (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_invoice_line_price" in audited.reasons, audited
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_negative_invoice_line_cents_without_crashing(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET line_cents=-1 WHERE reference=? AND line_no=1",
                    (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_invoice_line_amount" in audited.reasons, audited
            assert audited.can_checkout is False
        """)

    def test_audit_handles_corrupt_subtotal_with_declared_tender(self):
        self.isolated("""
            first = sandbox.simulate_commit(**dict(
                args, tenders=[{"method":"Cash","amount":"250"}]
            ))
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sales "
                    "SET subtotal_cents='invalid' WHERE reference=?",
                    (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "settlement_invoice_amount_invalid:" + first.reference in audited.reasons
            assert "invalid_invoice_subtotal_encoding" in audited.reasons
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_text_invoice_subtotal_without_crashing(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sales "
                    "SET subtotal_cents='invalid' WHERE reference=?",
                    (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_invoice_subtotal:" + first.reference in audited.reasons
            assert "invalid_invoice_subtotal_encoding" in audited.reasons
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_zeroed_invoice_subtotal(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sales "
                    "SET subtotal_cents=0 WHERE reference=?", (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invoice_line_total_mismatch:" + first.reference in audited.reasons
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_invalid_persisted_invoice_barcode(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET barcode=' RICE ' WHERE reference=? AND line_no=1",
                    (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_invoice_line_barcode" in audited.reasons, audited
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_more_than_one_hundred_invoice_lines(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                for number in range(4, 102):
                    c.execute(
                        "INSERT INTO main.v8_preview_sandbox_sale_lines "
                        "(reference,line_no,barcode,quantity,price,line_cents) "
                        "VALUES (?,?,?,?,?,?)",
                        (first.reference,number,"RICE","1","0",0)
                    )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invoice_line_count_exceeded:" + first.reference in audited.reasons
            assert audited.can_checkout is False
        """)

    def test_independent_audit_rejects_renumbered_invoice_lines(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET line_no=99 WHERE reference=? AND line_no=1",
                    (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert ("invoice_line_sequence_mismatch:" + first.reference
                    in audited.reasons), audited
            assert audited.can_checkout is False
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM main.sales").fetchone()[0] == 0
        """)

    def test_independent_audit_rejects_missing_middle_invoice_line(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "DELETE FROM main.v8_preview_sandbox_sale_lines "
                    "WHERE reference=? AND line_no=2", (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert ("invoice_line_sequence_mismatch:" + first.reference
                    in audited.reasons), audited
            assert audited.can_checkout is False
        """)

    def test_replay_rejects_tampered_stock_movements(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_stock_moves "
                    "SET sold_qty='0' WHERE reference=? AND barcode='RICE'",
                    (first.reference,)
                )
            try:
                sandbox.simulate_commit(**args)
            except RuntimeError as exc:
                assert "stock movements" in str(exc), exc
            else:
                raise AssertionError("Tampered sandbox stock replay accepted")
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_sales"
                ).fetchone()[0] == 1
        """)

    def test_injected_failure_never_leaves_partial_sandbox_or_journal(self):
        self.isolated("""
            with database.db() as c:
                before = main_counts(c)
            for stage in ("after_claim", "after_stock",
                          "after_invoice", "after_complete"):
                try:
                    sandbox.simulate_commit(
                        **dict(args, inject_failure_at=stage)
                    )
                except RuntimeError as exc:
                    assert "Injected sandbox failure" in str(exc), exc
                else:
                    raise AssertionError("Failed to inject at " + stage)
                with database.db() as c:
                    assert main_counts(c) == before
                    assert not c.execute(
                        "SELECT 1 FROM main.sqlite_master "
                        "WHERE name='v8_preview_sandbox_sales'"
                    ).fetchone()
                    assert not c.execute(
                        "SELECT 1 FROM main.sqlite_master "
                        "WHERE name='v8_preview_request_journal'"
                    ).fetchone()
            assert sandbox.simulate_commit(**args).sandbox_persisted
        """)

    def test_sandbox_stock_shortage_blocks_followup_despite_unchanged_main_stock(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            second = dict(
                args, request_id="sandbox-second-request-0001",
                lines=[{"barcode":"RICE","qty":6,"price":45}]
            )
            try:
                sandbox.simulate_commit(**second)
            except PermissionError as exc:
                assert "stock" in str(exc).lower()
            else:
                raise AssertionError("Sandbox stock overdraft allowed")
            with database.db() as c:
                assert sandbox_stock(c) == {"RICE":"5", "SOAP":"3"}
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_sales"
                ).fetchone()[0] == 1
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_request_journal"
                ).fetchone()[0] == 1
                assert c.execute(
                    "SELECT stock_qty FROM main.products WHERE barcode='RICE'"
                ).fetchone()[0] == 10
        """)

    def test_signed_session_branch_and_shift_denials_write_no_sandbox_rows(self):
        self.isolated("""
            from velopos_qt.auth_model import PreviewIdentity
            altered = (
                dict(args, identity=PreviewIdentity("cashier","Admin","fake")),
                dict(args, expected_branch_id="OTHER-BRANCH"),
                dict(args, shift_id=shift+100),
                dict(args, license_key="INVALID"),
                dict(args, current_status="INVALID"),
            )
            with database.db() as c:
                before = main_counts(c)
            for invalid in altered:
                try:
                    sandbox.simulate_commit(**invalid)
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Forged client got sandbox writes")
            with database.db() as c:
                assert main_counts(c) == before
                assert not c.execute(
                    "SELECT 1 FROM main.sqlite_master "
                    "WHERE name='v8_preview_sandbox_sales'"
                ).fetchone()
        """)

    def test_completed_journal_without_matching_sandbox_invoice_fails_closed(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "DELETE FROM main.v8_preview_sandbox_sales WHERE reference=?",
                    (first.reference,)
                )
            try:
                sandbox.simulate_commit(**args)
            except RuntimeError as exc:
                assert "matching sandbox sale" in str(exc)
            else:
                raise AssertionError("Missing sandbox invoice was trusted")
            checked = sandbox.reconcile_sandbox()
            assert not checked.balanced, checked
            assert "orphan_completed_sale_journal" in checked.reasons, checked
            assert checked.can_checkout is False
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_stock_moves"
                ).fetchone()[0] == 2
                assert c.execute(
                    "SELECT status FROM main.v8_preview_request_journal"
                ).fetchone()[0] == "COMPLETED"
        """)

    def test_audit_rejects_second_completed_request_pointing_to_same_invoice(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "INSERT INTO main.v8_preview_request_journal "
                    "(scope,request_id,payload_sha256,status,result_ref) "
                    "SELECT scope,'forged-sandbox-request-0002',"
                    "payload_sha256,status,result_ref "
                    "FROM main.v8_preview_request_journal "
                    "WHERE scope='sale' AND request_id=?",
                    (args["request_id"],)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "completed_sale_journal_coverage_mismatch" in audited.reasons, audited
            assert audited.can_checkout is False
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_sales"
                ).fetchone()[0] == 1
                assert c.execute("SELECT COUNT(*) FROM main.sales").fetchone()[0] == 0
        """)

    def test_audit_flags_stranded_pending_sale_request(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "INSERT INTO main.v8_preview_request_journal "
                    "(scope,request_id,payload_sha256,status,result_ref) "
                    "SELECT scope,'stranded-sandbox-0002',payload_sha256,"
                    "'PENDING',NULL FROM main.v8_preview_request_journal "
                    "WHERE scope='sale' AND request_id=?",
                    (args["request_id"],)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "pending_sale_journal_requires_reconciliation" in audited.reasons
            assert audited.can_checkout is False
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM main.sales").fetchone()[0] == 0
        """)

    def test_audit_flags_invoice_with_all_lines_removed(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "DELETE FROM main.v8_preview_sandbox_sale_lines "
                    "WHERE reference=?", (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invoice_has_no_lines:" + first.reference in audited.reasons
            assert audited.can_checkout is False
        """)

    def test_sandbox_independent_audit_reconciles_invoice_stock_and_journal(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            second = sandbox.simulate_commit(**dict(
                args, request_id="sandbox-audit-sale-0002",
                lines=[{"barcode":"SOAP","qty":2,"price":25}]
            ))
            audited = sandbox.reconcile_sandbox()
            assert audited.balanced, audited
            assert audited.reasons == ()
            assert audited.invoice_count == 2
            assert audited.subtotal_cents == 30000
            assert audited.can_checkout is False
            with database.db() as c:
                assert sandbox_stock(c) == {"RICE":"5", "SOAP":"1"}
        """)

    def test_independent_audit_fails_closed_after_invoice_or_stock_tamper(self):
        self.isolated("""
            sandbox.simulate_commit(**args)
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET line_cents=line_cents+1 WHERE line_no=1"
                )
            bad_lines = sandbox.reconcile_sandbox()
            assert not bad_lines.balanced
            assert any(
                reason.startswith("invoice_line_total_mismatch")
                for reason in bad_lines.reasons
            ), bad_lines
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET line_cents=line_cents-1 WHERE line_no=1"
                )
                c.execute(
                    "UPDATE main.v8_preview_sandbox_stock "
                    "SET remaining_qty='999' WHERE barcode='RICE'"
                )
            bad_stock = sandbox.reconcile_sandbox()
            assert not bad_stock.balanced
            assert "stock_balance_mismatch:RICE" in bad_stock.reasons
            assert bad_stock.can_checkout is False
        """)

    def test_audit_detects_sold_stock_quantity_different_from_invoice_lines(self):
        self.isolated("""
            sandbox.simulate_commit(**args)
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_stock_moves "
                    "SET sold_qty='999' WHERE barcode='SOAP'"
                )
            checked = sandbox.reconcile_sandbox()
            assert not checked.balanced
            assert "stock_line_quantity_mismatch" in checked.reasons
            assert checked.can_checkout is False
        """)

    def test_cash_tender_allocation_commits_only_sandbox_declaration(self):
        self.isolated("""
            with database.db() as c:
                original = main_counts(c)
            tendered = dict(
                args, tenders=[{"method":"Cash","amount":"300.00"}]
            )
            first = sandbox.simulate_commit(**tendered)
            assert first.tender_declared and first.change_cents == 5000
            assert first.actual_invoice_posted is False
            assert first.payment_captured is False
            assert first.can_checkout is False
            replay = sandbox.simulate_commit(**tendered)
            assert replay.replayed and replay.reference == first.reference
            assert replay.change_cents == 5000
            checked = sandbox.reconcile_sandbox()
            assert checked.balanced, checked
            with database.db() as c:
                now = main_counts(c)
                for key in ("sales","sale_items","stock","moves","payments"):
                    assert original[key] == now[key], key
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_tenders"
                ).fetchone()[0] == 1
                declared = c.execute(
                    "SELECT declared,due_cents,cash_cents,noncash_cents,"
                    "change_cents FROM main.v8_preview_sandbox_settlements"
                ).fetchone()
                assert tuple(declared) == (1,25000,30000,0,5000), tuple(declared)
        """)

    def test_mixed_cash_card_qr_are_declarations_not_confirmed_payments(self):
        self.isolated("""
            tendered = [
                {"method":"Card","amount":"100","reference":"AUTH-TEST-01"},
                {"method":"QR","amount":"50","reference":"QR-TEST-02"},
                {"method":"Cash","amount":"120"},
            ]
            first = sandbox.simulate_commit(**dict(args,tenders=tendered))
            assert first.change_cents == 2000
            assert first.payment_captured is False
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                recorded = c.execute(
                    "SELECT method,amount_cents FROM "
                    "main.v8_preview_sandbox_tenders ORDER BY line_no"
                ).fetchall()
                assert [tuple(row) for row in recorded] == [
                    ("Card",10000),("QR",5000),("Cash",12000)
                ]
                assert c.execute(
                    "SELECT COUNT(*) FROM main.supplier_payments"
                ).fetchone()[0] == 0
        """)

    def test_same_request_changed_tender_declaration_is_idempotency_conflict(self):
        self.isolated("""
            original = [
                {"method":"Cash","amount":"250"}
            ]
            sandbox.simulate_commit(**dict(args,tenders=original))
            altered = [
                {"method":"Cash","amount":"300"}
            ]
            for variant in (
                dict(args,tenders=altered),
                dict(args),
            ):
                try:
                    sandbox.simulate_commit(**variant)
                except IdempotencyConflict:
                    pass
                else:
                    raise AssertionError("Changed tender allocation reused a key")
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_sales"
                ).fetchone()[0] == 1
                assert sandbox_stock(c) == {"RICE":"5","SOAP":"3"}
        """)

    def test_invalid_or_insufficient_tender_never_writes_sandbox_rows(self):
        self.isolated("""
            attempts = (
                [{"method":"Cash","amount":"10"}],
                [{"method":"Cash","amount":"250.001"}],
                [{"method":"Card","amount":"250","reference":""}],
                [{"method":"Credit","amount":"250"}],
            )
            with database.db() as c:
                before = main_counts(c)
            for attempt in attempts:
                try:
                    sandbox.simulate_commit(**dict(args,tenders=attempt))
                except (PermissionError,ValueError):
                    pass
                else:
                    raise AssertionError("Invalid settlement allocated")
            with database.db() as c:
                assert main_counts(c) == before
                assert not c.execute(
                    "SELECT 1 FROM main.sqlite_master "
                    "WHERE name='v8_preview_sandbox_sales'"
                ).fetchone()
        """)

    def test_tender_integrity_audit_detects_tampered_allocation(self):
        self.isolated("""
            sandbox.simulate_commit(**dict(
                args, tenders=[{"method":"Cash","amount":"270"}]
            ))
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_tenders "
                    "SET amount_cents=26000"
                )
            checked = sandbox.reconcile_sandbox()
            assert not checked.balanced
            assert "settlement_tender_total_mismatch:" in " ".join(checked.reasons)
            assert checked.can_checkout is False
        """)

    def test_replay_rejects_renumbered_tender_lines_with_same_totals(self):
        self.isolated("""
            allocation = [
                {"method":"Card","amount":"100","reference":"CARD-TEST-01"},
                {"method":"Cash","amount":"150"},
            ]
            first = sandbox.simulate_commit(**dict(args,tenders=allocation))
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_tenders SET line_no=99 "
                    "WHERE reference=? AND line_no=1", (first.reference,)
                )
            try:
                sandbox.simulate_commit(**dict(args,tenders=allocation))
            except RuntimeError as exc:
                assert "tender mismatch" in str(exc).lower(), exc
            else:
                raise AssertionError("Renumbered tender replay was accepted")
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM main.sales").fetchone()[0] == 0
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_sales"
                ).fetchone()[0] == 1
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert any(reason.startswith("settlement_tender_line_sequence_mismatch:")
                       for reason in audited.reasons), audited
            assert audited.can_checkout is False
        """)

    def test_independent_audit_rejects_tampered_external_tender_reference(self):
        self.isolated("""
            original = sandbox.simulate_commit(**dict(
                args, tenders=[
                    {"method":"Card","amount":"100","reference":"CARD-TEST-01"},
                    {"method":"Cash","amount":"150"},
                ]
            ))
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_tenders "
                    "SET reference_hint='' WHERE reference=? AND method='Card'",
                    (original.reference,)
                )
            checked = sandbox.reconcile_sandbox()
            assert not checked.balanced, checked
            assert "invalid_tender_reference" in checked.reasons
            assert checked.can_checkout is False
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM main.sales").fetchone()[0] == 0
        """)

    def test_replay_refuses_missing_or_changed_tender_rows(self):
        self.isolated("""
            first = sandbox.simulate_commit(**dict(
                args,tenders=[{"method":"Cash","amount":"250"}]
            ))
            with database.db() as c:
                c.execute(
                    "DELETE FROM main.v8_preview_sandbox_tenders"
                )
            try:
                sandbox.simulate_commit(**dict(
                    args,tenders=[{"method":"Cash","amount":"250"}]
                ))
            except RuntimeError as exc:
                assert "tender mismatch" in str(exc).lower(), exc
            else:
                raise AssertionError("Tampered allocation passed replay")
        """)

    def test_audit_handles_malformed_persisted_tender_amount(self):
        self.isolated("""
            first = sandbox.simulate_commit(**dict(
                args, tenders=[{"method":"Cash","amount":"250"}]
            ))
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_tenders "
                    "SET amount_cents='invalid' WHERE reference=?",
                    (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_tender_declaration" in audited.reasons, audited
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_invalid_tender_line_number(self):
        self.isolated("""
            first = sandbox.simulate_commit(**dict(
                args, tenders=[{"method":"Cash","amount":"250"}]
            ))
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_tenders "
                    "SET line_no=0 WHERE reference=?", (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_tender_line_number" in audited.reasons, audited
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_invalid_invoice_line_number(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET line_no=0 WHERE reference=? AND line_no=1",
                    (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_invoice_line_number:" + first.reference in audited.reasons
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_unknown_tender_method(self):
        self.isolated("""
            first = sandbox.simulate_commit(**dict(
                args, tenders=[{"method":"Cash","amount":"250"}]
            ))
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_tenders "
                    "SET method='Unknown' WHERE reference=?",
                    (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_tender_declaration" in audited.reasons, audited
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_negative_settlement_values(self):
        self.isolated("""
            first = sandbox.simulate_commit(**dict(
                args, tenders=[{"method":"Cash","amount":"250"}]
            ))
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_settlements "
                    "SET cash_cents=-1 WHERE reference=?", (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_settlement_amount:" + first.reference in audited.reasons
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_more_than_ten_declared_tenders(self):
        self.isolated("""
            first = sandbox.simulate_commit(**dict(
                args, tenders=[{"method":"Cash","amount":"250"}]
            ))
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                for number in range(2, 12):
                    c.execute(
                        "INSERT INTO main.v8_preview_sandbox_tenders "
                        "(reference,line_no,method,amount_cents,reference_hint) "
                        "VALUES (?,?,?,?,?)",
                        (first.reference,number,"Cash",100,"")
                    )
                c.execute(
                    "UPDATE main.v8_preview_sandbox_settlements "
                    "SET cash_cents=cash_cents+1000,change_cents=change_cents+1000 "
                    "WHERE reference=?", (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "settlement_tender_count_exceeded:" + first.reference in audited.reasons
            assert audited.can_checkout is False
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM main.sales").fetchone()[0] == 0
        """)

    def test_tender_failpoint_rolls_back_settlement_and_stock_together(self):
        self.isolated("""
            try:
                sandbox.simulate_commit(**dict(
                    args,
                    tenders=[{"method":"Cash","amount":"255"}],
                    inject_failure_at="after_complete"
                ))
            except RuntimeError as exc:
                assert "Injected sandbox failure" in str(exc)
            else:
                raise AssertionError("Tender completion failpoint did not abort")
            with database.db() as c:
                names = {
                    row[0] for row in c.execute(
                        "SELECT name FROM main.sqlite_master WHERE type='table'"
                    )
                }
                assert "v8_preview_sandbox_tenders" not in names
                assert "v8_preview_sandbox_settlements" not in names
                assert "v8_preview_request_journal" not in names
                assert c.execute(
                    "SELECT COUNT(*) FROM main.sales"
                ).fetchone()[0] == 0
            assert sandbox.simulate_commit(**dict(
                args,tenders=[{"method":"Cash","amount":"255"}]
            )).change_cents == 500
        """)

    def test_old_sandbox_invoice_missing_tender_tables_requires_reconciliation(self):
        self.isolated("""
            saved = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute("DROP TABLE main.v8_preview_sandbox_settlements")
                c.execute("DROP TABLE main.v8_preview_sandbox_tenders")
            try:
                sandbox.simulate_commit(**args)
            except RuntimeError as exc:
                assert "manual reconciliation" in str(exc), exc
            else:
                raise AssertionError("Old journal without settlement schema replayed")
            assert not sandbox.reconcile_sandbox().balanced
        """)


    def test_missing_settlement_row_fails_closed_on_replay_and_audit(self):
        self.isolated("""
            original = sandbox.simulate_commit(**dict(
                args, tenders=[{"method":"Cash","amount":"250"}]
            ))
            with database.db() as c:
                c.execute(
                    "DELETE FROM main.v8_preview_sandbox_settlements "
                    "WHERE reference=?", (original.reference,)
                )
            try:
                sandbox.simulate_commit(**dict(
                    args, tenders=[{"method":"Cash","amount":"250"}]
                ))
            except RuntimeError as exc:
                assert "settlement reconciliation" in str(exc).lower(), exc
            else:
                raise AssertionError("Missing settlement was accepted on replay")
            checked = sandbox.reconcile_sandbox()
            assert not checked.balanced, checked
            assert checked.can_checkout is False
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_sales"
                ).fetchone()[0] == 1
                assert c.execute(
                    "SELECT COUNT(*) FROM main.sales"
                ).fetchone()[0] == 0
        """)

    def test_corrupt_sale_line_quantity_is_reported_without_crashing(self):
        self.isolated("""
            sandbox.simulate_commit(**args)
            assert sandbox.reconcile_sandbox().balanced
            for invalid in ("NaN", "Infinity", "-Infinity", "broken", "0", "-1"):
                with database.db() as c:
                    c.execute(
                        "UPDATE main.v8_preview_sandbox_sale_lines "
                        "SET quantity=? WHERE line_no=1", (invalid,)
                    )
                result = sandbox.reconcile_sandbox()
                assert not result.balanced, invalid
                assert "invalid_invoice_line_quantity" in result.reasons, result
        """)

    def test_replay_rejects_hostile_stock_chain_decimal(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_stock_moves "
                    "SET before_qty='1E+999999999' "
                    "WHERE reference=? AND barcode='RICE'", (first.reference,)
                )
            try:
                sandbox.simulate_commit(**args)
            except RuntimeError as exc:
                assert "stock" in str(exc).lower(), exc
            else:
                raise AssertionError("Corrupted sandbox replay must be rejected")
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_sales"
                ).fetchone()[0] == 1
        """)

    def test_audit_rejects_extreme_stock_balance_and_chain_exponents(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_stock "
                    "SET opening_qty='1E+999999999' WHERE barcode='RICE'"
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_stock_decimal:RICE" in audited.reasons, audited
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_stock "
                    "SET opening_qty='10' WHERE barcode='RICE'"
                )
                c.execute(
                    "UPDATE main.v8_preview_sandbox_stock_moves "
                    "SET before_qty='1E+999999999' "
                    "WHERE reference=? AND barcode='RICE'", (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_stock_decimal:RICE" in audited.reasons, audited
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_oversized_stock_balance_and_chain_encodings(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_stock "
                    "SET opening_qty=? WHERE barcode='RICE'", ("1" * 129,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_stock_decimal:RICE" in audited.reasons, audited
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_stock "
                    "SET opening_qty='10' WHERE barcode='RICE'"
                )
                c.execute(
                    "UPDATE main.v8_preview_sandbox_stock_moves "
                    "SET before_qty=? WHERE reference=? AND barcode='RICE'",
                    ("1" * 129, first.reference)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_stock_decimal:RICE" in audited.reasons, audited
            assert audited.can_checkout is False
        """)

    def test_audit_rejects_hostile_stock_sold_decimal(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            assert sandbox.reconcile_sandbox().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_stock_moves "
                    "SET sold_qty='1E-999999999' "
                    "WHERE reference=? AND barcode='RICE'", (first.reference,)
                )
            audited = sandbox.reconcile_sandbox()
            assert not audited.balanced, audited
            assert "invalid_stock_move_quantity" in audited.reasons, audited
            assert audited.can_checkout is False
        """)

    def test_corrupt_stock_move_and_balance_decimals_fail_closed(self):
        self.isolated("""
            sandbox.simulate_commit(**args)
            assert sandbox.reconcile_sandbox().balanced
            for field, table, condition, expected in (
                ("sold_qty", "v8_preview_sandbox_stock_moves",
                 "barcode='RICE'", "invalid_stock_move_quantity"),
                ("before_qty", "v8_preview_sandbox_stock_moves",
                 "barcode='RICE'", "invalid_stock_decimal:RICE"),
                ("after_qty", "v8_preview_sandbox_stock_moves",
                 "barcode='RICE'", "invalid_stock_decimal:RICE"),
                ("opening_qty", "v8_preview_sandbox_stock",
                 "barcode='RICE'", "invalid_stock_decimal:RICE"),
                ("remaining_qty", "v8_preview_sandbox_stock",
                 "barcode='RICE'", "invalid_stock_decimal:RICE"),
            ):
                with database.db() as c:
                    original = c.execute(
                        f"SELECT {field} FROM main.{table} WHERE {condition}"
                    ).fetchone()[0]
                for invalid in ("NaN", "Infinity", "bad-decimal"):
                    with database.db() as c:
                        c.execute(
                            f"UPDATE main.{table} SET {field}=? WHERE {condition}",
                            (invalid,)
                        )
                    result = sandbox.reconcile_sandbox()
                    assert not result.balanced, (field, invalid, result)
                    assert expected in result.reasons, (field, invalid, result)
                with database.db() as c:
                    c.execute(
                        f"UPDATE main.{table} SET {field}=? WHERE {condition}",
                        (original,)
                    )
                assert sandbox.reconcile_sandbox().balanced
        """)

    def test_two_sequential_sandbox_sales_reconcile_invoice_and_remaining_stock(self):
        self.isolated("""
            first = sandbox.simulate_commit(**args)
            next_args = dict(
                args, request_id="sandbox-sale-0002",
                lines=[
                    {"barcode":"RICE","qty":2,"price":45},
                    {"barcode":"SOAP","qty":2,"price":25},
                ]
            )
            second = sandbox.simulate_commit(**next_args)
            assert first.subtotal_cents == 25000
            assert second.subtotal_cents == 14000
            with database.db() as c:
                assert sandbox_stock(c) == {"RICE":"3", "SOAP":"1"}
                sales_total = c.execute(
                    "SELECT SUM(subtotal_cents) FROM main.v8_preview_sandbox_sales"
                ).fetchone()[0]
                lines_total = c.execute(
                    "SELECT SUM(line_cents) FROM main.v8_preview_sandbox_sale_lines"
                ).fetchone()[0]
                assert sales_total == lines_total == 39000
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_stock_moves"
                ).fetchone()[0] == 4
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_request_journal"
                ).fetchone()[0] == 2
        """)


if __name__ == "__main__":
    unittest.main()
