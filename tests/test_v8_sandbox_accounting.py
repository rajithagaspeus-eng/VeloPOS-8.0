"""Single-snapshot accounting acceptance for disposable V8 sandbox ledgers.

All tests are isolated subprocesses and only inspect sandbox declarations.
Neither recorded card/QR/cash tenders nor refund modes are proof of funds.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.test_v8_phase2_atomic_sale_boundary import FIXTURE
from tests.test_v8_sandbox_returns import EXTRA


class SandboxCloseoutTests(unittest.TestCase):
    def isolated(self, script):
        with tempfile.TemporaryDirectory(prefix="v8_sandbox_closeout_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            code = (
                FIXTURE + "\n" + EXTRA + "\n"
                + "from velopos_qt.sandbox_accounting import PreviewSandboxAccounting\n"
                + "closeout = PreviewSandboxAccounting(database)\n"
                + textwrap.dedent(script)
            )
            result = subprocess.run(
                [sys.executable, "-c", code], env=env,
                text=True, capture_output=True, timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_no_sale_yet_produces_fail_closed_missing_schema(self):
        self.isolated("""
            result = closeout.closeout()
            assert not result.balanced
            assert "sandbox_accounting_tables_missing" in result.reasons
            assert result.can_checkout is False
            try:
                closeout.require_certified_accounting()
            except PermissionError:
                pass
            else:
                raise AssertionError("Sandbox closeout authorized accounting")
        """)

    def test_single_sale_without_return_balances_but_never_certifies_payment(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            result = closeout.closeout()
            assert result.balanced and not result.reasons, result
            assert result.invoice_count == 1 and result.return_count == 0
            assert result.gross_cents == 25000
            assert result.declared_returns_cents == 0
            assert result.net_after_declared_returns_cents == 25000
            assert result.declared_cash_cents == 0
            assert result.captured_payment_cents == 0
            assert result.certified_profit_cents is None
        """)

    def test_cash_card_qr_allocation_and_partial_refund_net_revenue(self):
        self.isolated("""
            opts = dict(args,tenders=[
                {"method":"Card","amount":"100","reference":"CARDSBX-11"},
                {"method":"QR","amount":"50","reference":"QRSBX-22"},
                {"method":"Cash","amount":"120"},
            ])
            sale = sale_service.simulate_commit(**opts)
            r = return_service.simulate_return(**new_return(sale.reference))
            result = closeout.closeout()
            assert result.balanced, result
            assert result.invoice_count == 1 and result.return_count == 1
            assert result.gross_cents == 25000
            assert result.declared_returns_cents == 4500
            assert result.net_after_declared_returns_cents == 20500
            assert result.declared_cash_cents == 12000
            assert result.declared_external_cents == 15000
            assert result.declared_change_cents == 2000
            assert result.captured_payment_cents == 0
            assert result.actual_refunds_cents == 0
            assert result.certified_profit_cents is None
            assert result.can_checkout is False
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM main.sales"
                ).fetchone()[0] == 0
                assert c.execute(
                    "SELECT COUNT(*) FROM main.returns"
                ).fetchone()[0] == 0
                assert c.execute(
                    "SELECT stock_qty FROM main.products WHERE barcode='RICE'"
                ).fetchone()[0] == 10
        """)

    def test_two_partial_returns_on_original_line_reconcile_exact_cents(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            for i in (1,2):
                return_service.simulate_return(**new_return(
                    sale.reference,request_id="closeout-return-000"+str(i),
                    returns=[{"line_no":1,"qty":"1"}],
                ))
            result = closeout.closeout()
            assert result.balanced, result
            assert result.return_count == 2
            assert result.declared_returns_cents == 9000
            assert result.gross_cents == 25000
            assert result.net_after_declared_returns_cents == 16000
            assert result.actual_refunds_cents == 0
        """)

    def test_closeout_rejects_nonfinite_and_nonpositive_return_quantity(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            return_service.simulate_return(**new_return(sale.reference))
            assert closeout.closeout().balanced
            with database.db() as c:
                original = c.execute(
                    "SELECT quantity FROM main.v8_preview_sandbox_return_lines "
                    "WHERE sale_line_no=1"
                ).fetchone()[0]
            for corrupt in ("NaN", "Infinity", "-Infinity", "0", "-1"):
                with database.db() as c:
                    c.execute(
                        "UPDATE main.v8_preview_sandbox_return_lines "
                        "SET quantity=? WHERE sale_line_no=1", (corrupt,)
                    )
                result = closeout.closeout()
                assert not result.balanced, corrupt
                assert "invalid_return_quantity" in result.reasons, (corrupt,result)
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_return_lines "
                    "SET quantity=? WHERE sale_line_no=1", (original,)
                )
            assert closeout.closeout().balanced
        """)

    def test_closeout_detects_tampered_sale_tenders_stock_and_return_records(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**dict(
                args, tenders=[{"method":"Cash","amount":"260"}]
            ))
            return_service.simulate_return(**new_return(sale.reference))
            assert closeout.closeout().balanced
            mutations = (
                ("main.v8_preview_sandbox_sale_lines",
                 "UPDATE main.v8_preview_sandbox_sale_lines "
                 "SET line_cents=line_cents+5 WHERE line_no=1"),
                ("main.v8_preview_sandbox_tenders",
                 "UPDATE main.v8_preview_sandbox_tenders "
                 "SET amount_cents=25000"),
                ("main.v8_preview_sandbox_stock",
                 "UPDATE main.v8_preview_sandbox_stock "
                 "SET remaining_qty='99' WHERE barcode='SOAP'"),
                ("main.v8_preview_sandbox_return_lines",
                 "UPDATE main.v8_preview_sandbox_return_lines "
                 "SET refund_cents=refund_cents+1"),
            )
            for _, sql in mutations:
                with database.db() as c:
                    c.execute("SAVEPOINT tamper_test")
                    c.execute(sql)
                    c.execute("RELEASE tamper_test")
                # A mutation persists; restore original values via explicit
                # compensating SQL on disposable test data only.
                assert not closeout.closeout().balanced, sql
                with database.db() as c:
                    if "line_cents=line_cents+5" in sql:
                        c.execute(
                            "UPDATE main.v8_preview_sandbox_sale_lines "
                            "SET line_cents=line_cents-5 WHERE line_no=1"
                        )
                    elif "amount_cents=25000" in sql:
                        c.execute(
                            "UPDATE main.v8_preview_sandbox_tenders "
                            "SET amount_cents=26000"
                        )
                    elif "remaining_qty='99'" in sql:
                        c.execute(
                            "UPDATE main.v8_preview_sandbox_stock "
                            "SET remaining_qty='3' WHERE barcode='SOAP'"
                        )
                    else:
                        c.execute(
                            "UPDATE main.v8_preview_sandbox_return_lines "
                            "SET refund_cents=refund_cents-1"
                        )
                assert closeout.closeout().balanced, sql
        """)

    def test_closeout_detects_orphan_journals_and_overreturn(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            return_service.simulate_return(**new_return(sale.reference))
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_return_lines "
                    "SET quantity='99'"
                )
            too_many = closeout.closeout()
            assert not too_many.balanced
            assert "overreturned_original_quantity" in too_many.reasons
            with database.db() as c:
                c.execute(
                    "DELETE FROM main.v8_preview_sandbox_returns"
                )
            orphan = closeout.closeout()
            assert not orphan.balanced
            assert "unmatched_return_journal" in orphan.reasons
        """)

    def test_closeout_detects_nonrestock_disposition_corruption(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            return_service.simulate_return(**new_return(
                sale.reference,disposition="DISCARDED"
            ))
            assert closeout.closeout().balanced
            with database.db() as c:
                c.execute("PRAGMA ignore_check_constraints=ON")
                c.execute(
                    "UPDATE main.v8_preview_sandbox_return_lines "
                    "SET restocked=1"
                )
            checked = closeout.closeout()
            assert not checked.balanced
            assert "return_disposition_not_nonrestocking" in checked.reasons
            assert checked.can_checkout is False
        """)

    def test_closeout_rejects_line_price_tamper_even_if_invoice_total_unchanged(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            assert closeout.closeout().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_sale_lines "
                    "SET price='999' WHERE reference=? AND line_no=1",
                    (sale.reference,)
                )
            checked = closeout.closeout()
            assert not checked.balanced
            assert "sale_price_quantity_mismatch" in checked.reasons
            assert checked.gross_cents == 25000
            assert checked.can_checkout is False
        """)

    def test_duplicate_stock_move_fails_closed_even_with_coverage_intact(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            assert closeout.closeout().balanced
            # Rebuild ONLY the disposable sandbox movement table without
            # its uniqueness constraint, simulating a corrupted ledger.
            with database.db() as c:
                c.execute(
                    "CREATE TABLE main.corrupt_moves AS SELECT * FROM "
                    "main.v8_preview_sandbox_stock_moves"
                )
                c.execute("DROP TABLE main.v8_preview_sandbox_stock_moves")
                c.execute(
                    "ALTER TABLE main.corrupt_moves RENAME TO "
                    "v8_preview_sandbox_stock_moves"
                )
                c.execute(
                    "INSERT INTO main.v8_preview_sandbox_stock_moves "
                    "SELECT * FROM main.v8_preview_sandbox_stock_moves "
                    "WHERE reference=? AND barcode='RICE'",
                    (sale.reference,)
                )
            audited = closeout.closeout()
            assert not audited.balanced, audited
            assert "duplicate_sale_stock_movement" in audited.reasons
            assert audited.can_checkout is False
        """)

    def test_accounting_requires_a_complete_return_schema(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            return_service.simulate_return(**new_return(sale.reference))
            with database.db() as c:
                c.execute("DROP TABLE main.v8_preview_sandbox_return_lines")
            audited = closeout.closeout()
            assert not audited.balanced
            assert "sandbox_return_schema_partial" in audited.reasons
            assert audited.can_checkout is False
        """)


if __name__ == "__main__":
    unittest.main()
