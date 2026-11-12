"""V8 rollback-only mixed-tender sale and stock-ledger return regressions.

Every child process uses disposable VeloPOS8PreviewData; none can create
a real sale, refund, payment, stock movement or claim after rollback.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.test_v8_phase2_atomic_sale_boundary import FIXTURE


RETURN_FIXTURE = """
from decimal import Decimal
from velopos import database, services
from velopos_qt.auth_model import PreviewAuthenticator
from velopos_qt.return_rehearsal import RollbackOnlyReturnRehearsal
database.init_db()
services.save_user("owner", "StrongReturnOwner2026!", "Admin", "setup")
session = PreviewAuthenticator(database).authenticate(
    "owner", "StrongReturnOwner2026!"
)
services.save_product("RICE", "Rice", "setup", sell=25, stock=8)
services.save_product("SOAP", "Soap", "setup", sell=10, stock=3)
with database.db() as c:
    c.execute("INSERT INTO shifts(cashier,status) VALUES('owner','OPEN')")
    shift_id = c.execute("SELECT id FROM shifts").fetchone()[0]
    c.execute("INSERT INTO sales(invoice_no,date,time,total_amount,status) "
              "VALUES('INV-OLD','2026-11-01','12:00:00',85,'OK')")
    c.execute("INSERT INTO sale_items(invoice_no,barcode,item_name,qty,"
              "selling_price,total) VALUES('INV-OLD','RICE','Rice',3,25,75)")
    rice_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.execute("INSERT INTO sale_items(invoice_no,barcode,item_name,qty,"
              "selling_price,total) VALUES('INV-OLD','SOAP','Soap',1,10,10)")
    soap_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.execute("INSERT INTO returns(return_no,invoice_no,date,amount,cashier) "
              "VALUES('RET-OLD','INV-OLD','2026-11-02',25,'owner')")
    c.execute("INSERT INTO return_items(return_no,sale_item_id,barcode,"
              "item_name,qty,price,total) VALUES"
              "('RET-OLD',?,'RICE','Rice',1,25,25)", (rice_id,))
engine = RollbackOnlyReturnRehearsal(database)
requested = [
    {"sale_item_id": rice_id, "qty": Decimal("1.0")},
    {"sale_item_id": rice_id, "qty": Decimal("1.000")},
    {"sale_item_id": soap_id, "qty": 1},
]
def snapshot():
    with database.db() as c:
        return {
            "stock": [(r["barcode"],r["stock_qty"]) for r in
                      c.execute("SELECT barcode,stock_qty FROM products ORDER BY barcode")],
            "stock_moves": c.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0],
            "sales": c.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
            "return": c.execute("SELECT COUNT(*) FROM returns").fetchone()[0],
            "return_items": c.execute("SELECT COUNT(*) FROM return_items").fetchone()[0],
            "audit": c.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0],
            "journal": c.execute("SELECT COUNT(*) FROM sqlite_master WHERE "
                                 "name='v8_preview_request_journal'").fetchone()[0],
        }
"""


class SaleTenderReturnIntegrationTests(unittest.TestCase):
    def isolated(self, fixture, source):
        with tempfile.TemporaryDirectory(prefix="v8_integrated_money_") as home:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(home) / "VeloPOS8PreviewData")
            result = subprocess.run(
                [sys.executable, "-c", fixture + "\n" + textwrap.dedent(source)],
                capture_output=True, text=True, env=env, timeout=75,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_multi_tender_sale_draft_is_never_paid_or_persisted(self):
        self.isolated(FIXTURE, """
            payment = [
                {"method": "Cash", "amount": "100.00"},
                {"method": "Card", "amount": "75.00", "reference": "TEST-CARD-101"},
                {"method": "QR", "amount": "75.00", "reference": "TEST-QR-102"},
            ]
            engine = RollbackOnlySaleRehearsal(database)
            with database.db() as c:
                before = snapshot(c)
            for _ in range(2):
                r = engine.simulate(
                    identity=user, shift_id=shift, lines=lines,
                    request_id="tender-sale-0001", tenders=payment,
                    today="2026-11-04",
                )
                assert r.persisted is False
                assert r.subtotal == Decimal("250.00")
                assert r.tender_preview.amount_due == Decimal("250.00")
                assert r.tender_preview.has_unverified_external_payments
                assert r.tender_preview.can_settle is False
                assert r.staged_stock_movements == 2
            with database.db() as c:
                assert snapshot(c) == before
        """)

    def test_credit_customer_binding_and_invalid_tender_fail_no_write(self):
        self.isolated(FIXTURE, """
            engine = RollbackOnlySaleRehearsal(database)
            with database.db() as c:
                before = snapshot(c)
            for proposed, customer in (
                ([{"method":"Credit","amount":"250"}], None),
                ([{"method":"Cash","amount":"249"}], None),
                ([{"method":"Card","amount":"250","reference":"x"}], None),
                ([{"method":"QR","amount":"250.001","reference":"TESTQR"}], None),
            ):
                try:
                    engine.simulate(
                        identity=user, shift_id=shift, lines=lines,
                        request_id="invalid-tender-0001",
                        tenders=proposed, customer_id=customer,
                        today="2026-11-04",
                    )
                except ValueError:
                    pass
                else:
                    raise AssertionError("Invalid tender passed")
            # This is still unverified credit, not a posted receivable.
            credit = engine.simulate(
                identity=user, shift_id=shift, lines=lines,
                request_id="credit-tender-0001", customer_id=15,
                tenders=[{"method":"Credit","amount":"250"}],
                today="2026-11-04",
            )
            assert credit.tender_preview.credit_due == Decimal("250.00")
            assert credit.tender_preview.credit_limit_unverified
            assert credit.tender_preview.can_settle is False
            with database.db() as c:
                assert snapshot(c) == before
        """)

    def test_return_stages_stock_ledger_and_same_request_replay_only_in_rollback(self):
        self.isolated(RETURN_FIXTURE, """
            before = snapshot()
            for _ in range(2):
                r = engine.simulate(
                    identity=session, shift_id=shift_id,
                    request_id="return-ledger-0001",
                    invoice_no="INV-OLD", items=requested,
                    today="2026-11-04",
                )
                assert r.persisted is False
                assert r.amount == Decimal("60.00")
                assert r.staged_items == 2
                assert r.staged_stock_movements == 2
            assert snapshot() == before, (before, snapshot())
        """)

    def test_return_injected_failure_never_strands_stock_or_request_claim(self):
        self.isolated(RETURN_FIXTURE, """
            before = snapshot()
            for point in ("after_stock", "after_stock_ledger",
                          "after_return", "after_journal_complete"):
                try:
                    engine.simulate(
                        identity=session, shift_id=shift_id,
                        request_id="return-failpoint-0001",
                        invoice_no="INV-OLD", items=requested,
                        today="2026-11-04", inject_failure_at=point,
                    )
                except RuntimeError as exc:
                    assert "Injected return failure" in str(exc), str(exc)
                else:
                    raise AssertionError("Failpoint did not raise: " + point)
                assert snapshot() == before, (point, before, snapshot())
            r = engine.simulate(
                identity=session, shift_id=shift_id,
                request_id="return-failpoint-0001",
                invoice_no="INV-OLD", items=requested,
                today="2026-11-04",
            )
            assert r.staged_items == 2
            assert snapshot() == before
        """)

    def test_return_quantity_over_original_and_foreign_invoice_fail_closed(self):
        self.isolated(RETURN_FIXTURE, """
            before = snapshot()
            for proposed in (
                [{"sale_item_id":rice_id,"qty":3}],
                [{"sale_item_id":rice_id,"qty":2},
                 {"sale_item_id":rice_id,"qty":1}],
                [{"sale_item_id":rice_id,"qty":1000000},
                 {"sale_item_id":rice_id,"qty":1}],
                [{"sale_item_id":soap_id,"qty":"NaN"}],
            ):
                try:
                    engine.simulate(
                        identity=session, shift_id=shift_id,
                        request_id="return-invalid-0001",
                        invoice_no="INV-OLD", items=proposed,
                        today="2026-11-04",
                    )
                except ValueError:
                    pass
                else:
                    raise AssertionError("Invalid return accepted: " + repr(proposed))
                assert snapshot() == before
            try:
                engine.simulate(
                    identity=session, shift_id=shift_id,
                    request_id="return-wrong-invoice-0001",
                    invoice_no="INV-OTHER", items=requested,
                    today="2026-11-04",
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Missing invoice accepted")
            assert snapshot() == before
        """)


if __name__ == "__main__":
    unittest.main()
