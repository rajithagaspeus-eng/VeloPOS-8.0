"""V8 Qt financial gateway is non-transactional even when forged as Admin."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class PreviewGatewayTests(unittest.TestCase):
    def isolated(self, source, directory="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_gateway_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / directory)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(source)],
                env=env, text=True, capture_output=True, timeout=40,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_all_transactions_blocked_before_legacy_side_effects(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.auth_model import PreviewIdentity
            from velopos_qt.transaction_gateway import PreviewTransactionGateway
            database.init_db()
            gateway = PreviewTransactionGateway(database)
            calls = (
                "sale", "return_sale", "purchase", "supplier_payment",
                "credit_payment", "redeem_points", "open_shift",
                "close_shift", "print_receipt", "void_sale", "void_purchase",
                "cash_move", "add_expense", "delete_expense", "adjust_stock",
                "finalize_stock_take", "receive_batch",
            )
            identities = [
                None, PreviewIdentity("cashier", "Cashier"),
                PreviewIdentity("owner", "Admin")
            ]
            for method in calls:
                for identity in identities:
                    try:
                        getattr(gateway, method)(
                            identity=identity,
                            amount=100, license_valid=True,
                            open_shift=True, request_id="REPLAY-1",
                        )
                    except PermissionError:
                        pass
                    else:
                        raise AssertionError(
                            f"Unauthorized preview transaction: {method}"
                        )
            with database.db() as c:
                for table in ("sales", "returns", "purchases",
                              "supplier_payments", "credit_logs", "stock_moves"):
                    assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
            """
        )

    def test_complete_forged_boundary_proofs_do_not_unlock_gateway(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.transaction_gateway import PreviewTransactionGateway
            database.init_db()
            gateway = PreviewTransactionGateway(database)
            for action, method in (
                ("sale", gateway.sale),
                ("return", gateway.return_sale),
                ("purchase", gateway.purchase),
            ):
                required = gateway.assess_future_boundary(action).required_proofs
                assessment = gateway.assess_future_boundary(
                    action, {key: True for key in required}
                )
                assert not assessment.missing_proofs
                assert assessment.unverified_proofs == required
                assert assessment.can_execute is False
                try:
                    method(identity=None, license_valid=True)
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Forged proofs unlocked " + action)
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM sales"
                ).fetchone()[0] == 0
            """
        )

    def test_gateway_rehearses_sale_without_posting_legacy_invoice(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.transaction_gateway import PreviewTransactionGateway
            database.init_db()
            gateway = PreviewTransactionGateway(database)
            lines = [{"barcode": "RICE", "qty": "2", "price": "12.50"}]
            preview = gateway.rehearse_sale(
                request_id="gateway-rehearsal-0001", lines=lines
            )
            assert preview.subtotal_cents == 2500
            assert preview.can_checkout is False
            assert preview.can_post is False
            try:
                gateway.sale(
                    identity=None, request_id="gateway-rehearsal-0001",
                    lines=lines, license_valid=True
                )
            except PermissionError:
                pass
            else:
                raise AssertionError("Preview rehearsal unlocked checkout")
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
            """
        )

    def test_production_like_folder_denied_at_construction(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.transaction_gateway import PreviewTransactionGateway
            database.init_db()
            try:
                PreviewTransactionGateway(database)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Non-preview transactions gateway constructed")
            """, directory="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
