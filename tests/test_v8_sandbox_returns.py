"""V8 sandbox-only return/refund declaration integration on disposable SQLite.

Requires signed 'return' action for the isolated preview license. The
simulation never issues a refund, restocks or changes any original V7 rows.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.test_v8_phase2_atomic_sale_boundary import FIXTURE


EXTRA = """
from velopos_qt.sandbox_sale_ledger import PreviewSandboxSaleLedger
from velopos_qt.sandbox_return_ledger import PreviewSandboxReturnLedger
from velopos_qt.idempotency_ledger import IdempotencyConflict
sale_service = PreviewSandboxSaleLedger(
    database, license_public_key_b64=pub(license_signer)
)
return_service = PreviewSandboxReturnLedger(
    database, license_public_key_b64=pub(license_signer)
)
return_license, _ = sign(license_signer, dict(
    v=8, license_id="LIC-001", m="MACHINE-001", branch_id="BRANCH-001",
    actions=["sale","return"], expires="2030-01-01",
))
def new_return(sale_ref, request_id="sandbox-return-0001", **overrides):
    opts = dict(
        identity=user, shift_id=shift, request_id=request_id,
        original_ref=sale_ref, returns=[{"line_no":1,"qty":"1"}],
        refund_mode="Cash", expected_branch_id="BRANCH-001",
        license_id="LIC-001", machine_id="MACHINE-001",
        license_key=return_license,
        server_public_key_b64=pub(server_signer),
        previous_status=previous, current_status=current,
        today="2026-11-04",
        now=datetime(2026,11,4,10,tzinfo=timezone.utc)
    )
    opts.update(overrides)
    return opts
"""


class SandboxReturnTests(unittest.TestCase):
    def isolated(self, code):
        with tempfile.TemporaryDirectory(prefix="v8_return_sandbox_") as temp:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(temp) / "VeloPOS8PreviewData")
            result = subprocess.run(
                [sys.executable, "-c", FIXTURE+"\n"+EXTRA+"\n"+textwrap.dedent(code)],
                env=env, capture_output=True, text=True, timeout=90
            )
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_signed_partial_return_persists_only_sandbox_journal_and_refund_declaration(self):
        self.isolated("""
            original = sale_service.simulate_commit(**args)
            with database.db() as c:
                baseline = snapshot(c)
            returned = return_service.simulate_return(**new_return(original.reference))
            assert returned.reference.startswith("SRF-")
            assert returned.refund_cents == 4500, returned
            assert returned.items == 1
            assert returned.replayed is False
            assert returned.actual_refund_posted is False
            assert returned.stock_restocked is False
            assert returned.can_checkout is False
            with database.db() as c:
                after = snapshot(c)
                for field in ("sales","sale_items","returns","stock","moves","payments"):
                    assert after[field] == baseline[field],field
                sandbox_qty = c.execute(
                    "SELECT remaining_qty FROM main.v8_preview_sandbox_stock "
                    "WHERE barcode='RICE'"
                ).fetchone()[0]
                assert sandbox_qty == "5"
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_returns"
                ).fetchone()[0] == 1
            check = return_service.reconcile_returns()
            assert check.balanced and check.return_count == 1,check
            assert check.total_refund_cents == 4500
            assert sale_service.reconcile_sandbox().balanced
        """)

    def test_same_return_request_replays_without_second_refund(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            opts = new_return(sale.reference)
            first = return_service.simulate_return(**opts)
            again = return_service.simulate_return(**opts)
            assert again.replayed and again.reference == first.reference
            assert again.refund_cents == 4500
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM main.v8_preview_sandbox_returns"
                ).fetchone()[0] == 1
            for different in (
                new_return(sale.reference,returns=[{"line_no":1,"qty":"2"}]),
                new_return(sale.reference,refund_mode="Card"),
            ):
                try:
                    return_service.simulate_return(**different)
                except IdempotencyConflict:
                    pass
                else:
                    raise AssertionError("Changed refund reused request key")
        """)

    def test_two_partial_returns_cannot_exceed_original_quantity_or_cents(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            first = return_service.simulate_return(**new_return(
                sale.reference,returns=[{"line_no":1,"qty":"1"}],
            ))
            second = return_service.simulate_return(**new_return(
                sale.reference,request_id="sandbox-return-0002",
                returns=[{"line_no":1,"qty":"1"}],
            ))
            assert first.refund_cents == second.refund_cents == 4500
            extra = new_return(
                sale.reference,request_id="sandbox-return-0003",
                returns=[{"line_no":1,"qty":"0.01"}],
            )
            try:
                return_service.simulate_return(**extra)
            except PermissionError as exc:
                assert "exceeds original" in str(exc)
            else:
                raise AssertionError("Return quantity exceeded sold units")
            audited = return_service.reconcile_returns()
            assert audited.balanced and audited.total_refund_cents == 9000,audited
        """)

    def test_cross_branch_invalid_license_and_shift_denied_without_writes(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            denied = (
                new_return(sale.reference,expected_branch_id="BRANCH-OTHER"),
                new_return(sale.reference,license_key=license_key),
                new_return(sale.reference,shift_id=shift+99),
                new_return(sale.reference,current_status="bad-signature"),
            )
            with database.db() as c:
                before = snapshot(c)
            for opts in denied:
                try:
                    return_service.simulate_return(**opts)
                except (PermissionError,ValueError):
                    pass
                else:
                    raise AssertionError("Unauthorized return was recorded")
            with database.db() as c:
                assert snapshot(c) == before
                assert not c.execute(
                    "SELECT 1 FROM main.sqlite_master "
                    "WHERE name='v8_preview_sandbox_returns'"
                ).fetchone()
        """)

    def test_failure_injection_after_claim_lines_or_completion_rollback_everything(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            with database.db() as c:
                before = snapshot(c)
            for stage in ("after_claim","after_lines","after_complete"):
                try:
                    return_service.simulate_return(**new_return(
                        sale.reference,inject_failure_at=stage
                    ))
                except RuntimeError as exc:
                    assert "Injected return failure" in str(exc),exc
                else:
                    raise AssertionError("Return failpoint did not abort")
                with database.db() as c:
                    assert snapshot(c) == before
                    assert not c.execute(
                        "SELECT 1 FROM main.sqlite_master "
                        "WHERE name='v8_preview_sandbox_returns'"
                    ).fetchone()
            assert return_service.simulate_return(
                **new_return(sale.reference)
            ).refund_cents == 4500
        """)

    def test_return_audit_detects_tampered_cents_and_overreturned_quantity(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            return_service.simulate_return(**new_return(sale.reference))
            assert return_service.reconcile_returns().balanced
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_return_lines "
                    "SET refund_cents=9000"
                )
            wrong_cents = return_service.reconcile_returns()
            assert not wrong_cents.balanced
            assert "return_line_amount_mismatch" in wrong_cents.reasons
            with database.db() as c:
                c.execute(
                    "UPDATE main.v8_preview_sandbox_return_lines "
                    "SET quantity='100',refund_cents=9000"
                )
            excessive = return_service.reconcile_returns()
            assert not excessive.balanced
            assert "overreturned_sale_line" in excessive.reasons
        """)

    def test_missing_original_invoice_and_unsupported_refund_modes_fail_closed(self):
        self.isolated("""
            sale = sale_service.simulate_commit(**args)
            for opts in (
                new_return("SBX-"+("0"*24)),
                new_return(sale.reference,refund_mode="Credit"),
                new_return(sale.reference,returns=[{"line_no":999,"qty":"1"}]),
                new_return(sale.reference,returns=[{"line_no":1,"qty":"0"}]),
            ):
                try:
                    return_service.simulate_return(**opts)
                except (PermissionError,ValueError):
                    pass
                else:
                    raise AssertionError("Invalid return accepted")
            with database.db() as c:
                assert not c.execute(
                    "SELECT 1 FROM main.sqlite_master "
                    "WHERE name='v8_preview_sandbox_returns'"
                ).fetchone()
        """)

    def test_commercial_refunds_remain_hard_disabled(self):
        self.isolated("""
            try:
                return_service.require_real_refund()
            except PermissionError:
                pass
            else:
                raise AssertionError("Sandbox returned production refund permission")
        """)


if __name__ == "__main__":
    unittest.main()
