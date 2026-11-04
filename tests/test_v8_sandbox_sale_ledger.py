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
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_stock_moves"
                ).fetchone()[0] == 2
                assert c.execute(
                    "SELECT status FROM main.v8_preview_request_journal"
                ).fetchone()[0] == "COMPLETED"
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
