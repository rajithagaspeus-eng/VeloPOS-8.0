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
                "close_shift", "print_receipt"
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
