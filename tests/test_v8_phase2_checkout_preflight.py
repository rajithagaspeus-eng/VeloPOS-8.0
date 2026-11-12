"""Checkout preflight cannot authorize sales or write financial data."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class CheckoutPreflightIntegrationTests(unittest.TestCase):
    def isolated(self, script, directory="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_checkout_safety_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / directory)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_permission_shift_stock_price_and_rollback_diagnostics(self):
        self.isolated(
            """
            from decimal import Decimal
            from velopos import database, services
            from velopos_qt.auth_model import PreviewAuthenticator
            from velopos_qt.checkout_preflight import PreviewCheckoutPreflight
            database.init_db()
            services.save_user("cashier", "StrongCashierPass2026!", "Cashier", "setup")
            auth = PreviewAuthenticator(database)
            user = auth.authenticate("cashier", "StrongCashierPass2026!")
            services.save_product("RICE", "Rice", "test", sell=50, stock=8)
            services.save_product("SOAP", "Soap", "test", sell=20, stock=4)
            with database.db() as c:
                c.execute("INSERT INTO shifts(cashier,opened_at,status) "
                          "VALUES('cashier','2026-11-04T08:00:00','OPEN')")
                shift = c.execute("SELECT id FROM shifts ORDER BY id DESC LIMIT 1").fetchone()[0]
            preflight = PreviewCheckoutPreflight(database)
            draft = [{"barcode":"RICE","qty":2,"price":50},
                     {"barcode":"RICE","qty":3,"price":50},
                     {"barcode":"SOAP","qty":1,"price":20}]
            okay = preflight.inspect(
                identity=user, shift_id=shift, lines=draft,
                request_id="preview-request-001", today="2026-11-04"
            )
            assert okay.can_checkout is False, okay
            assert okay.subtotal == Decimal("270.00"), okay
            assert okay.line_count == 3
            assert "preview_checkout_disabled" in okay.reasons
            assert "idempotency_not_implemented" in okay.reasons
            assert "license_not_verified" in okay.reasons
            assert "verified_cashier_required" not in okay.reasons, okay
            assert "insufficient_stock:RICE" not in okay.reasons, okay
            restricted = preflight.inspect(
                identity=None, shift_id=shift,
                lines=[{"barcode":"RICE","qty":9,"price":49}],
                request_id="x", today="2026-11-04",
            )
            for reason in (
                "verified_cashier_required", "shift_cashier_mismatch",
                "invalid_request_id", "insufficient_stock:RICE",
                "price_changed:RICE",
            ):
                assert reason in restricted.reasons, (reason, restricted)
            with database.db() as c:
                c.execute("UPDATE shifts SET status='CLOSED' WHERE id=?", (shift,))
            closed = preflight.inspect(
                identity=user, shift_id=shift,
                lines=[{"barcode":"SOAP","qty":1,"price":20}],
                request_id="preview-request-002", today="2026-11-04",
            )
            assert "shift_not_open" in closed.reasons, closed
            with database.db() as c:
                c.execute("UPDATE users SET role='Admin' WHERE username='cashier'")
            old_identity = preflight.inspect(
                identity=user, shift_id=shift,
                lines=[{"barcode":"SOAP","qty":1,"price":20}],
                request_id="preview-request-003", today="2026-11-04",
            )
            assert "verified_cashier_required" in old_identity.reasons
            for _ in range(2):
                again = preflight.inspect(
                    identity=user, shift_id=shift, lines=draft,
                    request_id="preview-request-001", today="2026-11-04")
                assert again.can_checkout is False
            with database.db() as c:
                assert c.execute("SELECT stock_qty FROM products WHERE barcode='RICE'").fetchone()[0] == 8
                for table in ("sales", "sale_items", "stock_moves", "returns",
                              "supplier_payments", "credit_logs"):
                    count = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    # Product setup may populate OPENING stock movements.
                    assert count == (2 if table == "stock_moves" else 0), (table, count)
            """
        )

    def test_expired_missing_products_and_tampered_prices(self):
        self.isolated(
            """
            from velopos import database, services
            from velopos_qt.checkout_preflight import PreviewCheckoutPreflight
            database.init_db()
            services.save_product("EXPIRED", "Milk", "test", sell=40, stock=7,
                                  expiry="2026-11-01")
            services.save_product("BATCH", "Milk batch", "test", sell=90, stock=7)
            with database.db() as c:
                c.execute(
                    "INSERT INTO batches(barcode,batch_no,expiry_date,qty_remaining) "
                    "VALUES('BATCH','B1','2026-11-02',3)"
                )
            preflight = PreviewCheckoutPreflight(database)
            diagnosis = preflight.inspect(
                lines=[
                    {"barcode":"EXPIRED","qty":1,"price":40},
                    {"barcode":"BATCH","qty":1,"price":90},
                    {"barcode":"MISSING","qty":1,"price":1},
                ], request_id="purchase-0123", today="2026-11-04"
            )
            assert "expired_product:EXPIRED" in diagnosis.reasons, diagnosis
            assert "expired_batch_review:BATCH" in diagnosis.reasons, diagnosis
            assert "missing_product:MISSING" in diagnosis.reasons, diagnosis
            assert diagnosis.can_checkout is False
            """
        )

    def test_invalid_inputs_rejected_before_database_access(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.checkout_preflight import PreviewCheckoutPreflight
            database.init_db()
            reader = PreviewCheckoutPreflight(database)
            invalid_lines = (
                [], [{"barcode":"A","qty":0,"price":10}],
                [{"barcode":"A","qty":1,"price":-1}],
                [{"barcode":"A","qty":"nan","price":10}],
                [{"barcode":"A","qty":1,"price":"inf"}],
                [{"barcode":"A","qty":1000001,"price":10}],
                [{"barcode":"A","qty":1,"price":100000001}],
                [{"barcode":"","qty":1,"price":10}], ["not a line"],
            )
            for draft in invalid_lines:
                try:
                    reader.inspect(lines=draft, today="2026-11-04")
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"Invalid draft accepted: {draft!r}")
            for date_value in ("2026-02-30","2026-1-1","invalid"):
                try:
                    reader.inspect(lines=[{"barcode":"A","qty":1,"price":1}],
                                   today=date_value)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Invalid date accepted")
            """
        )

    def test_nonpreview_storage_is_rejected(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.checkout_preflight import PreviewCheckoutPreflight
            database.init_db()
            try:
                PreviewCheckoutPreflight(database)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Production-like storage accepted")
            """, directory="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
