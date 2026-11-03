"""No atomic rehearsal can persist sales, inventory changes or claim entries."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class RollbackOnlySaleTests(unittest.TestCase):
    def isolated(self, script, directory="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_sale_rehearsal_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / directory)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=50,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_successful_rehearsal_rolls_back_staged_invoice_and_stock(self):
        self.isolated(
            """
            from decimal import Decimal
            from velopos import database, services
            from velopos_qt.auth_model import PreviewAuthenticator
            from velopos_qt.sale_rehearsal import RollbackOnlySaleRehearsal
            database.init_db()
            services.save_user("cashier", "VeryStrongCashier2026!", "Cashier", "setup")
            session = PreviewAuthenticator(database).authenticate(
                "cashier", "VeryStrongCashier2026!"
            )
            services.save_product("RICE", "Rice", "test", sell=20, stock=10)
            services.save_product("SOAP", "Soap", "test", sell=8, stock=3)
            with database.db() as c:
                c.execute("INSERT INTO shifts(cashier,status) VALUES('cashier','OPEN')")
                shift_id = c.execute("SELECT id FROM shifts").fetchone()[0]
                opening_moves = c.execute(
                    "SELECT COUNT(*) FROM stock_moves"
                ).fetchone()[0]
            rehearsal = RollbackOnlySaleRehearsal(database)
            lines = [
                {"barcode":"RICE","qty":2,"price":20},
                {"barcode":"RICE","qty":3,"price":20},
                {"barcode":"SOAP","qty":1,"price":8},
            ]
            result = rehearsal.simulate(
                identity=session, shift_id=shift_id, lines=lines,
                request_id="rehearsal-order-0001", today="2026-11-04",
            )
            assert result.persisted is False
            assert result.subtotal == Decimal("108.00"), result
            assert result.staged_items == 3
            assert result.invoice_preview.startswith("SIM-")
            # Even a second identical request is not persisted/replayed:
            again = rehearsal.simulate(
                identity=session, shift_id=shift_id, lines=lines,
                request_id="rehearsal-order-0001", today="2026-11-04",
            )
            assert again.invoice_preview == result.invoice_preview
            with database.db() as c:
                for table in ("sales","sale_items","returns","credit_logs"):
                    assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
                assert c.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0] == opening_moves
                stock = {r["barcode"]: r["stock_qty"] for r in c.execute(
                    "SELECT barcode,stock_qty FROM products"
                )}
                assert stock == {"RICE":10,"SOAP":3}, stock
                assert not c.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='v8_preview_request_journal'"
                ).fetchone()
            """
        )

    def test_failure_injection_stock_price_and_shift_leave_no_mutations(self):
        self.isolated(
            """
            from velopos import database, services
            from velopos_qt.auth_model import PreviewAuthenticator
            from velopos_qt.sale_rehearsal import RollbackOnlySaleRehearsal
            database.init_db()
            services.save_user("cashier", "StrongCashierPass2026!", "Cashier", "setup")
            user = PreviewAuthenticator(database).authenticate(
                "cashier", "StrongCashierPass2026!"
            )
            services.save_product("RICE", "Rice", "test", sell=20, stock=4)
            with database.db() as c:
                c.execute("INSERT INTO shifts(cashier,status) VALUES('cashier','OPEN')")
                shift_id = c.execute("SELECT id FROM shifts").fetchone()[0]
            rehearsal = RollbackOnlySaleRehearsal(database)
            def run(lines, **kwargs):
                return rehearsal.simulate(
                    identity=user, shift_id=shift_id, lines=lines,
                    request_id="rehearsal-failure-001", today="2026-11-04", **kwargs
                )
            lines = [{"barcode":"RICE","qty":2,"price":20}]
            for stage in ("after_stock","after_invoice"):
                try:
                    run(lines, inject_failure_at=stage)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError(f"Rehearsal did not fail at {stage}")
            for bad in (
                [{"barcode":"RICE","qty":5,"price":20}],
                [{"barcode":"RICE","qty":1,"price":19}],
                [{"barcode":"MISSING","qty":1,"price":1}],
                [{"barcode":"RICE","qty":-1,"price":20}],
            ):
                try:
                    run(bad)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"Invalid rehearsal passed: {bad!r}")
            with database.db() as c:
                c.execute("UPDATE shifts SET status='CLOSED' WHERE id=?", (shift_id,))
            try:
                run(lines)
            except PermissionError:
                pass
            else:
                raise AssertionError("Closed shift permitted")
            with database.db() as c:
                assert c.execute("SELECT stock_qty FROM products WHERE barcode='RICE'").fetchone()[0] == 4
                assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
                assert c.execute("SELECT COUNT(*) FROM sale_items").fetchone()[0] == 0
                assert not c.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='v8_preview_request_journal'"
                ).fetchone()
            """
        )

    def test_forged_identity_and_nonpreview_storage_rejected(self):
        self.isolated(
            """
            from velopos import database, services
            from velopos_qt.auth_model import PreviewIdentity, PreviewAuthenticator
            from velopos_qt.sale_rehearsal import RollbackOnlySaleRehearsal
            database.init_db()
            services.save_user("owner","StrongOwnerPassword2026!","Admin","setup")
            services.save_product("A", "Sample", "setup", sell=1, stock=2)
            with database.db() as c:
                c.execute("INSERT INTO shifts(cashier,status) VALUES('owner','OPEN')")
                shift_id = c.execute("SELECT id FROM shifts").fetchone()[0]
            rehearsal = RollbackOnlySaleRehearsal(database)
            def call(user):
                return rehearsal.simulate(
                    identity=user, shift_id=shift_id,
                    request_id="fake-owner-sale-0001",
                    lines=[{"barcode":"A","qty":1,"price":1}],
                    today="2026-11-04",
                )
            for user in (None, PreviewIdentity("owner","Admin","fake")):
                try:
                    call(user)
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Forged user was allowed")
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
            """
        )
        self.isolated(
            """
            from velopos import database
            from velopos_qt.sale_rehearsal import RollbackOnlySaleRehearsal
            database.init_db()
            try:
                RollbackOnlySaleRehearsal(database)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Non-preview rehearsal constructed")
            """, directory="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
