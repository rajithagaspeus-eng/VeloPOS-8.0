"""Financial integrity diagnostics are read-only, Admin-gated and isolated."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class LedgerAuditIntegrationTests(unittest.TestCase):
    def isolated(self, code, directory="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_ledger_audit_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / directory)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(code)],
                env=env, text=True, capture_output=True, timeout=50,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_invoice_partial_returns_and_cross_invoice_anomalies(self):
        self.isolated(
            """
            from decimal import Decimal
            from velopos import database
            from velopos_qt.ledger_audit import PreviewLedgerAuditor
            database.init_db()
            allowed = {"ok": True}
            auditor = PreviewLedgerAuditor(database, authorize=lambda: allowed["ok"])
            with database.db() as c:
                c.execute(
                    "INSERT INTO sales(invoice_no,date,subtotal,total_amount,status) "
                    "VALUES('INV-A','2026-11-01',80,80,'OK')"
                )
                c.execute(
                    "INSERT INTO sales(invoice_no,date,subtotal,total_amount,status) "
                    "VALUES('INV-B','2026-11-01',50,50,'OK')"
                )
                c.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,selling_price,total) "
                    "VALUES('INV-A','RICE','Rice',3,20,60)"
                )
                rice = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                c.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,selling_price,total) "
                    "VALUES('INV-A','SOAP','Soap',2,10,20)"
                )
                c.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,item_name,qty,selling_price,total) "
                    "VALUES('INV-B','TEA','Tea',1,50,50)"
                )
                foreign = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                c.execute(
                    "INSERT INTO returns(return_no,invoice_no,date,amount) "
                    "VALUES('RET-1','INV-A','2026-11-02',20)"
                )
                c.execute(
                    "INSERT INTO return_items(return_no,sale_item_id,barcode,qty,price,total) "
                    "VALUES('RET-1',?,'RICE',1,20,20)", (rice,)
                )
            clean = auditor.audit_invoice("INV-A")
            assert clean.certified is False
            assert clean.sale_subtotal == Decimal("80")
            assert clean.recorded_line_total == Decimal("80.00")
            assert clean.refund_count == 1
            assert clean.findings == (), clean
            with database.db() as c:
                c.execute("UPDATE sales SET subtotal=79 WHERE invoice_no='INV-A'")
                c.execute(
                    "INSERT INTO returns(return_no,invoice_no,date,amount) "
                    "VALUES('RET-2','INV-A','2026-11-03',100)"
                )
                c.execute(
                    "INSERT INTO return_items(return_no,sale_item_id,barcode,qty,price,total) "
                    "VALUES('RET-2',?,'RICE',3,20,60)", (rice,)
                )
                c.execute(
                    "INSERT INTO return_items(return_no,sale_item_id,barcode,qty,price,total) "
                    "VALUES('RET-2',?,'TEA',1,50,50)", (foreign,)
                )
                c.execute(
                    "INSERT INTO return_items(return_no,sale_item_id,barcode,qty,price,total) "
                    "VALUES('RET-2',99999,'MISSING',1,1,1)"
                )
            audited = auditor.audit_invoice("INV-A")
            codes = {f.code for f in audited.findings}
            assert {"sale_subtotal_mismatch","over_returned",
                    "foreign_return_item"}.issubset(codes), codes
            assert audited.refund_count == 2
            # Verify zero audit writes or repair side effects.
            with database.db() as c:
                assert c.execute("SELECT subtotal FROM sales WHERE invoice_no='INV-A'").fetchone()[0] == 79
                assert c.execute("SELECT COUNT(*) FROM return_items").fetchone()[0] == 4
            allowed["ok"] = False
            try:
                auditor.audit_invoice("INV-A")
            except PermissionError:
                pass
            else:
                raise AssertionError("Revoked Admin retained financial read access")
            """
        )

    def test_stock_endpoint_matches_latest_movement_and_detects_drift(self):
        self.isolated(
            """
            from velopos import database, services
            from velopos_qt.ledger_audit import PreviewLedgerAuditor
            database.init_db()
            services.save_product("SOAP","Soap","setup",sell=10,stock=6)
            auditor = PreviewLedgerAuditor(database, authorize=lambda: True)
            good = auditor.audit_stock("SOAP")
            assert good.certified is False
            assert good.current_qty == 6
            assert good.latest_ledger_qty == 6
            assert good.findings == (), good
            with database.db() as c:
                c.execute("UPDATE products SET stock_qty=4 WHERE barcode='SOAP'")
            bad = auditor.audit_stock("SOAP")
            assert [f.code for f in bad.findings] == ["stock_balance_mismatch"]
            assert bad.current_qty == 4
            with database.db() as c:
                c.execute(
                    "INSERT INTO products(barcode,name_en,stock_qty) "
                    "VALUES('NO-MOVE','No move',0)"
                )
            missing = auditor.audit_stock("NO-MOVE")
            assert [f.code for f in missing.findings] == ["stock_ledger_missing"]
            for key in ("unknown", "NO-MOVE\\n", ""):
                try:
                    auditor.audit_stock(key)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Invalid/missing product accepted")
            with database.db() as c:
                assert c.execute("SELECT stock_qty FROM products WHERE barcode='SOAP'").fetchone()[0] == 4
            """
        )

    def test_requires_explicit_authorization_and_nonproduction_db(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.ledger_audit import PreviewLedgerAuditor
            database.init_db()
            auditor = PreviewLedgerAuditor(database)
            for op in (
                lambda: auditor.audit_invoice("INV-A"),
                lambda: auditor.audit_stock("RICE"),
            ):
                try:
                    op()
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Unauthenticated financial reader")
            """
        )
        self.isolated(
            """
            from velopos import database
            from velopos_qt.ledger_audit import PreviewLedgerAuditor
            database.init_db()
            try:
                PreviewLedgerAuditor(database, authorize=lambda: True)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Production DB permitted")
            """, directory="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
