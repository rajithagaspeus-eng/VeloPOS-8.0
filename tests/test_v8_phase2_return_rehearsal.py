"""Return rehearsal is rollback-only and respects existing partial refunds."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class ReturnRehearsalTests(unittest.TestCase):
    def isolated(self, source, dirname="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_return_rehearsal_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / dirname)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(source)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_partial_return_rehearsal_never_persists_stock_or_refund(self):
        self.isolated(
            """
            from decimal import Decimal
            from velopos import database, services
            from velopos_qt.auth_model import PreviewAuthenticator
            from velopos_qt.return_rehearsal import RollbackOnlyReturnRehearsal
            database.init_db()
            services.save_user("cashier", "StrongReturnPass2026!", "Cashier", "setup")
            session = PreviewAuthenticator(database).authenticate(
                "cashier", "StrongReturnPass2026!"
            )
            services.save_product("RICE", "Rice", "setup", sell=25, stock=8)
            services.save_product("SOAP", "Soap", "setup", sell=10, stock=3)
            with database.db() as c:
                c.execute("INSERT INTO shifts(cashier,status) VALUES('cashier','OPEN')")
                shift = c.execute("SELECT id FROM shifts").fetchone()[0]
                c.execute(
                    "INSERT INTO sales(invoice_no,date,time,total_amount,status) "
                    "VALUES('INV-OLD','2026-11-01','12:00:00',85,'OK')"
                )
                c.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,selling_price,total) "
                    "VALUES('INV-OLD','RICE','Rice',3,25,75)"
                )
                rice_item = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                c.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,selling_price,total) "
                    "VALUES('INV-OLD','SOAP','Soap',1,10,10)"
                )
                soap_item = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                # One historical unit of rice already refunded.
                c.execute(
                    "INSERT INTO returns(return_no,invoice_no,date,amount,cashier) "
                    "VALUES('RET-OLD','INV-OLD','2026-11-02',25,'cashier')"
                )
                c.execute(
                    "INSERT INTO return_items(return_no,sale_item_id,barcode,item_name,qty,price,total) "
                    "VALUES('RET-OLD',?,'RICE','Rice',1,25,25)", (rice_item,)
                )
                opening_moves = c.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0]
            rehearsal = RollbackOnlyReturnRehearsal(database)
            items = [
                {"sale_item_id":rice_item, "qty":1},
                {"sale_item_id":rice_item, "qty":1},
                {"sale_item_id":soap_item, "qty":1},
            ]
            for _ in range(2):
                result = rehearsal.simulate(
                    identity=session, shift_id=shift, request_id="refund-000001",
                    invoice_no="INV-OLD", items=items, today="2026-11-04",
                )
                assert result.persisted is False
                assert result.staged_items == 2
                assert result.amount == Decimal("60.00"), result
                assert result.return_preview.startswith("SIM-RET-")
            with database.db() as c:
                assert c.execute("SELECT stock_qty FROM products WHERE barcode='RICE'").fetchone()[0] == 8
                assert c.execute("SELECT stock_qty FROM products WHERE barcode='SOAP'").fetchone()[0] == 3
                assert c.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0] == opening_moves
                assert c.execute("SELECT COUNT(*) FROM returns").fetchone()[0] == 1
                assert c.execute("SELECT COUNT(*) FROM return_items").fetchone()[0] == 1
                assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 1
                assert not c.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='v8_preview_request_journal'"
                ).fetchone()
            """
        )

    def test_overreturn_invalid_invoice_and_failures_rollback(self):
        self.isolated(
            """
            from velopos import database, services
            from velopos_qt.auth_model import PreviewAuthenticator
            from velopos_qt.return_rehearsal import RollbackOnlyReturnRehearsal
            database.init_db()
            services.save_user("owner","StrongReturnOwner2026!","Admin","setup")
            identity = PreviewAuthenticator(database).authenticate(
                "owner","StrongReturnOwner2026!"
            )
            services.save_product("RICE","Rice","setup",sell=15,stock=4)
            with database.db() as c:
                c.execute("INSERT INTO shifts(cashier,status) VALUES('owner','OPEN')")
                shift = c.execute("SELECT id FROM shifts").fetchone()[0]
                c.execute(
                    "INSERT INTO sales(invoice_no,date,status) VALUES('INV-1','2026-11-01','OK')"
                )
                c.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,selling_price,total) "
                    "VALUES('INV-1','RICE','Rice',2,15,30)"
                )
                item_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                c.execute(
                    "INSERT INTO sales(invoice_no,date,status) VALUES('INV-VOID','2026-11-01','VOID')"
                )
            engine = RollbackOnlyReturnRehearsal(database)
            def simulate(items, **kwargs):
                return engine.simulate(
                    identity=identity, shift_id=shift, request_id="return-test-0001",
                    invoice_no="INV-1", items=items, today="2026-11-04", **kwargs
                )
            good = [{"sale_item_id":item_id,"qty":1}]
            for failure in ("after_stock","after_return"):
                try:
                    simulate(good, inject_failure_at=failure)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Failure injection did not rollback")
            for items in (
                [{"sale_item_id":item_id,"qty":2},{"sale_item_id":item_id,"qty":1}],
                [{"sale_item_id":item_id,"qty":-1}],
                [{"sale_item_id":item_id,"qty":"nan"}],
                [{"sale_item_id":99999,"qty":1}],
                [{"sale_item_id":True,"qty":1}],
            ):
                try:
                    simulate(items)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"Invalid return accepted: {items}")
            for invoice in ("INV-VOID","INV-MISSING"):
                try:
                    engine.simulate(
                        identity=identity, shift_id=shift, request_id="return-test-0001",
                        invoice_no=invoice, items=good, today="2026-11-04",
                    )
                except ValueError:
                    pass
                else:
                    raise AssertionError("Ineligible invoice returned")
            with database.db() as c:
                c.execute("UPDATE shifts SET status='CLOSED' WHERE id=?", (shift,))
            try:
                simulate(good)
            except PermissionError:
                pass
            else:
                raise AssertionError("Closed shift returned goods")
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM returns").fetchone()[0] == 0
                assert c.execute("SELECT COUNT(*) FROM return_items").fetchone()[0] == 0
                assert c.execute("SELECT stock_qty FROM products WHERE barcode='RICE'").fetchone()[0] == 4
                assert not c.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='v8_preview_request_journal'"
                ).fetchone()
            """
        )

    def test_nonpreview_db_is_never_accepted(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.return_rehearsal import RollbackOnlyReturnRehearsal
            database.init_db()
            try:
                RollbackOnlyReturnRehearsal(database)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Unsafe DB accepted")
            """, dirname="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
