"""Invoice, customer-credit and supplier liability reconciliation regressions."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class ExtendedLedgerAuditTests(unittest.TestCase):
    def isolated(self, script):
        with tempfile.TemporaryDirectory(prefix="v8_extended_audit_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            run = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_invoice_inclusive_exclusive_discounts_and_payment_errors(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.ledger_audit import PreviewLedgerAuditor
            database.init_db()
            audit = PreviewLedgerAuditor(database, authorize=lambda: True)
            with database.db() as c:
                c.execute(
                    "INSERT INTO sales(invoice_no,date,subtotal,discount,redeemed,"
                    "service_amount,vat_amount,vat_mode,total_amount,paid_amount,"
                    "balance,payment_method,status) VALUES"
                    "('EX-1','2026-11-04',100,10,5,3,8,'Exclusive',96,100,4,'Cash','OK')"
                )
                c.execute(
                    "INSERT INTO sales(invoice_no,date,subtotal,discount,redeemed,"
                    "service_amount,vat_amount,vat_mode,total_amount,paid_amount,"
                    "balance,payment_method,status) VALUES"
                    "('IN-1','2026-11-04',100,10,0,2,7,'Inclusive',92,92,0,'Card','OK')"
                )
            assert audit.audit_sale_totals("EX-1") == ()
            assert audit.audit_sale_totals("IN-1") == ()
            with database.db() as c:
                c.execute(
                    "UPDATE sales SET total_amount=91,paid_amount=50,balance=5 "
                    "WHERE invoice_no='EX-1'"
                )
            codes = {x.code for x in audit.audit_sale_totals("EX-1")}
            assert {"invoice_total_mismatch","underpaid_noncredit",
                    "change_mismatch"}.issubset(codes), codes
            with database.db() as c:
                c.execute(
                    "UPDATE sales SET discount=120 WHERE invoice_no='IN-1'"
                )
            codes = {x.code for x in audit.audit_sale_totals("IN-1")}
            assert "discount_over_subtotal" in codes, codes
            """
        )

    def test_customer_credit_ledger_balance_and_unjournaled_loyalty(self):
        self.isolated(
            """
            from decimal import Decimal
            from velopos import database
            from velopos_qt.ledger_audit import PreviewLedgerAuditor
            database.init_db()
            audit = PreviewLedgerAuditor(database, authorize=lambda: True)
            with database.db() as c:
                c.execute(
                    "INSERT INTO customers(name,credit_balance,loyalty_points) "
                    "VALUES('Customer A',25,2)"
                )
                cid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                for kind, amount in (
                    ("CREDIT_SALE", 50), ("PAYMENT", 10),
                    ("RETURN", 10), ("VOID", 5),
                ):
                    c.execute(
                        "INSERT INTO credit_logs(customer_id,type,amount) VALUES(?,?,?)",
                        (cid,kind,amount),
                    )
            result = audit.audit_customer_credit(cid)
            assert result["credit_balance"] == Decimal("25")
            assert result["credit_log_net"] == Decimal("25")
            assert result["findings"] == (), result
            assert result["loyalty_reconciled"] is False
            with database.db() as c:
                c.execute(
                    "UPDATE customers SET credit_balance=30,loyalty_points=-1 WHERE id=?",
                    (cid,),
                )
                c.execute(
                    "INSERT INTO credit_logs(customer_id,type,amount) "
                    "VALUES(?,'UNKNOWN',7)", (cid,)
                )
            codes = {f.code for f in audit.audit_customer_credit(cid)["findings"]}
            assert {"credit_balance_unverified","negative_loyalty_points",
                    "unknown_credit_log_type"}.issubset(codes), codes
            """
        )

    def test_supplier_all_time_liability_excludes_voided_grns_and_separates_advance(self):
        self.isolated(
            """
            from decimal import Decimal
            from velopos import database
            from velopos_qt.ledger_audit import PreviewLedgerAuditor
            database.init_db()
            permission = {"admin": True}
            audit = PreviewLedgerAuditor(
                database, authorize=lambda: permission["admin"]
            )
            with database.db() as c:
                c.execute("INSERT INTO suppliers(name) VALUES('Supplier A')")
                sid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                c.execute("INSERT INTO suppliers(name) VALUES('Supplier B')")
                other = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                c.execute(
                    "INSERT INTO purchases(grn_no,supplier_id,subtotal,discount,total,"
                    "paid,status) VALUES('GRN-1',?,110,10,100,40,'OK')", (sid,)
                )
                purchase = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                c.execute(
                    "INSERT INTO purchases(grn_no,supplier_id,subtotal,discount,total,"
                    "paid,status) VALUES('GRN-VOID',?,100,0,100,0,'VOID')", (sid,)
                )
                c.execute(
                    "INSERT INTO supplier_payments(supplier_id,purchase_id,amount) "
                    "VALUES(?,?,40)", (sid,purchase)
                )
                c.execute(
                    "INSERT INTO supplier_payments(supplier_id,amount) VALUES(?,30)", (sid,)
                )
            result = audit.audit_supplier_balance(sid)
            assert result["valid_grn_total"] == Decimal("100.00"), result
            assert result["payment_total"] == Decimal("70.00"), result
            assert result["balance"] == Decimal("30.00"), result
            assert result["payable"] == Decimal("30.00")
            assert result["advance"] == Decimal("0.00")
            assert result["findings"] == (), result
            with database.db() as c:
                c.execute(
                    "INSERT INTO supplier_payments(supplier_id,amount) VALUES(?,50)",
                    (sid,),
                )
                c.execute(
                    "INSERT INTO purchases(grn_no,supplier_id,subtotal,total,status) "
                    "VALUES('GRN-OTHER',?,10,10,'OK')", (other,)
                )
                wrong = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                c.execute(
                    "INSERT INTO supplier_payments(supplier_id,purchase_id,amount) "
                    "VALUES(?,?,1)", (sid,wrong)
                )
            advance = audit.audit_supplier_balance(sid)
            assert advance["payable"] == Decimal("0.00")
            assert advance["advance"] == Decimal("21.00"), advance
            assert "foreign_purchase_payment" in {f.code for f in advance["findings"]}
            permission["admin"] = False
            for call in (
                lambda: audit.audit_supplier_balance(sid),
                lambda: audit.audit_customer_credit(1),
                lambda: audit.audit_sale_totals("EX-1"),
            ):
                try:
                    call()
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Revoked admin read access")
            """
        )

    def test_bad_identifiers_are_rejected_and_no_mutations_performed(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.ledger_audit import PreviewLedgerAuditor
            database.init_db()
            audit = PreviewLedgerAuditor(database, authorize=lambda: True)
            for invalid in (0,-1,True,"1",None):
                for op in (audit.audit_customer_credit,audit.audit_supplier_balance):
                    try:
                        op(invalid)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("Invalid ID accepted")
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0
                assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
                assert c.execute("SELECT COUNT(*) FROM supplier_payments").fetchone()[0] == 0
            """
        )


if __name__ == "__main__":
    unittest.main()
