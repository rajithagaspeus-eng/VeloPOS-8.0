"""Read-only financial and stock integrity checks for the isolated V8 preview.

This audits individual persisted legacy invoices and product stock movements.
It is NOT certified accounting, a repair/migration tool, or an endorsement of
live transactions. An explicit Admin authorization callback is required;
the reader never writes, fixes or guesses missing financial records.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .product_editor import _guard


_CENT = Decimal("0.01")
_TOL = Decimal("0.02")


def _decimal(value, name):
    try:
        result = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError(f"Invalid recorded {name}") from exc
    if not result.is_finite():
        raise ValueError(f"Non-finite recorded {name}")
    return result


@dataclass(frozen=True)
class AuditFinding:
    code: str
    reference: str
    detail: str


@dataclass(frozen=True)
class InvoiceAudit:
    invoice_no: str
    sale_status: str
    sale_subtotal: Decimal
    recorded_line_total: Decimal
    refund_count: int
    findings: tuple[AuditFinding, ...]
    certified: bool = False


@dataclass(frozen=True)
class StockAudit:
    barcode: str
    current_qty: Decimal
    latest_ledger_qty: Decimal | None
    findings: tuple[AuditFinding, ...]
    certified: bool = False


class PreviewLedgerAuditor:
    """Read-only per-record diagnostics; no production DB or public access."""

    def __init__(self, database, authorize=None):
        _guard(database)
        self.database = database
        self.authorize = authorize

    def _check(self):
        _guard(self.database)
        if self.authorize is None or not self.authorize():
            raise PermissionError("Current preview Admin session is required for audit")

    @staticmethod
    def _key(value, what, max_length):
        if not isinstance(value, str) or not 1 <= len(value) <= max_length:
            raise ValueError(f"Invalid {what}")
        if value != value.strip() or any(ord(ch) < 32 for ch in value):
            raise ValueError(f"Invalid {what}")
        return value

    def audit_invoice(self, invoice_no):
        """Cross-check sale-item subtotals, return links and return quantities.

        A refund may legitimately include tax/discount allocations, so refund
        amount vs raw return-item prices is NOT deemed a corruption finding.
        """
        self._check()
        invoice_no = self._key(invoice_no, "invoice", 120)
        findings = []
        with self.database.db() as c:
            sale = c.execute(
                "SELECT invoice_no,status,subtotal FROM sales WHERE invoice_no=?",
                (invoice_no,),
            ).fetchone()
            if sale is None:
                raise ValueError("Invoice not found")
            lines = c.execute(
                "SELECT id,barcode,qty,total FROM sale_items WHERE invoice_no=? "
                "ORDER BY id", (invoice_no,),
            ).fetchall()
            if not lines:
                findings.append(AuditFinding(
                    "sale_lines_missing", invoice_no, "No original sale items recorded"
                ))
            recorded_total = Decimal(0)
            for line in lines:
                key = str(line["id"])
                sold = _decimal(line["qty"], "sold quantity")
                line_total = _decimal(line["total"], "line amount")
                recorded_total += line_total
                if sold <= 0 or line_total < 0:
                    findings.append(AuditFinding(
                        "invalid_sale_line", key, "Nonpositive quantity or negative amount"
                    ))
                returned_rows = c.execute(
                    "SELECT ri.qty,ri.barcode,ri.return_no,r.invoice_no "
                    "FROM return_items ri LEFT JOIN returns r "
                    "ON r.return_no=ri.return_no WHERE ri.sale_item_id=?",
                    (line["id"],),
                ).fetchall()
                returned = Decimal(0)
                for rr in returned_rows:
                    if rr["invoice_no"] != invoice_no:
                        findings.append(AuditFinding(
                            "return_invoice_mismatch", key,
                            "Return record not linked to the original invoice"
                        ))
                    if rr["barcode"] != line["barcode"]:
                        findings.append(AuditFinding(
                            "return_barcode_mismatch", key,
                            "Return barcode differs from the original item"
                        ))
                    quantity = _decimal(rr["qty"], "return quantity")
                    if quantity <= 0:
                        findings.append(AuditFinding(
                            "invalid_return_quantity", key, "Nonpositive return quantity"
                        ))
                    returned += quantity
                if returned > sold:
                    findings.append(AuditFinding(
                        "over_returned", key, "Returned quantity exceeds original sale"
                    ))
            # Check return rows referring to absent or other-invoice items.
            orphan_rows = c.execute(
                "SELECT ri.sale_item_id,ri.return_no FROM return_items ri "
                "JOIN returns r ON r.return_no=ri.return_no "
                "LEFT JOIN sale_items si ON si.id=ri.sale_item_id "
                "WHERE r.invoice_no=? AND (si.id IS NULL OR si.invoice_no<>?)",
                (invoice_no, invoice_no),
            ).fetchall()
            for rr in orphan_rows:
                findings.append(AuditFinding(
                    "foreign_return_item", str(rr["return_no"]),
                    "Return line references a missing or foreign sale item"
                ))
            refund_count = c.execute(
                "SELECT COUNT(*) FROM returns WHERE invoice_no=?", (invoice_no,),
            ).fetchone()[0]
        subtotal = _decimal(sale["subtotal"], "invoice subtotal")
        if abs(subtotal - recorded_total) > _TOL:
            findings.append(AuditFinding(
                "sale_subtotal_mismatch", invoice_no,
                "Original line amounts do not reconcile to recorded subtotal"
            ))
        return InvoiceAudit(
            invoice_no, str(sale["status"]), subtotal,
            recorded_total.quantize(_CENT), refund_count, tuple(findings),
        )

    def audit_stock(self, barcode):
        """Compare current product balance to latest persisted stock ledger row.

        This is an endpoint check, NOT a full historical movement reconciliation.
        """
        self._check()
        barcode = self._key(barcode, "barcode", 80)
        with self.database.db() as c:
            item = c.execute(
                "SELECT stock_qty FROM products WHERE barcode=?", (barcode,),
            ).fetchone()
            if item is None:
                raise ValueError("Product not found")
            move = c.execute(
                "SELECT qty_after FROM stock_moves WHERE barcode=? "
                "ORDER BY id DESC LIMIT 1", (barcode,),
            ).fetchone()
        current = _decimal(item["stock_qty"], "stock")
        latest = _decimal(move["qty_after"], "stock movement") if move else None
        findings = []
        if latest is None:
            findings.append(AuditFinding(
                "stock_ledger_missing", barcode, "No stock movement available"
            ))
        elif abs(current - latest) > Decimal("0.000001"):
            findings.append(AuditFinding(
                "stock_balance_mismatch", barcode,
                "Current stock does not match latest recorded movement"
            ))
        return StockAudit(barcode, current, latest, tuple(findings))

    def audit_sale_totals(self, invoice_no):
        """Verify persisted invoice-level arithmetic, not original tax rates.

        Inclusive VAT is already in subtotal. Exact taxable allocation cannot
        be reconstructed from invoice totals alone; this does not certify tax.
        """
        self._check()
        invoice_no = self._key(invoice_no, "invoice", 120)
        with self.database.db() as c:
            row = c.execute(
                "SELECT subtotal,discount,redeemed,total_amount,paid_amount,"
                "balance,vat_amount,service_amount,vat_mode,payment_method "
                "FROM sales WHERE invoice_no=?", (invoice_no,),
            ).fetchone()
        if row is None:
            raise ValueError("Invoice not found")
        amounts = {k: _decimal(row[k], k) for k in (
            "subtotal", "discount", "redeemed", "total_amount",
            "paid_amount", "balance", "vat_amount", "service_amount"
        )}
        errors = []
        for key, val in amounts.items():
            if val < 0:
                errors.append(AuditFinding(
                    "negative_invoice_amount", invoice_no, f"Negative {key}"
                ))
        sub = amounts["subtotal"]
        discount = amounts["discount"]
        redeem = amounts["redeemed"]
        if discount + redeem > sub + _TOL:
            errors.append(AuditFinding(
                "discount_over_subtotal", invoice_no,
                "Discount and redeemed points exceed subtotal"
            ))
        mode = row["vat_mode"] or ""
        if mode not in ("", "Inclusive", "Exclusive"):
            errors.append(AuditFinding(
                "invalid_vat_mode", invoice_no, "Unknown VAT mode"
            ))
        expected = sub - discount - redeem + amounts["service_amount"]
        if mode == "Exclusive":
            expected += amounts["vat_amount"]
        if abs(expected - amounts["total_amount"]) > _TOL:
            errors.append(AuditFinding(
                "invoice_total_mismatch", invoice_no,
                "Persisted net does not reconcile to discount/service/VAT fields"
            ))
        if row["payment_method"] != "Credit" and (
            amounts["paid_amount"] + _TOL < amounts["total_amount"]
        ):
            errors.append(AuditFinding(
                "underpaid_noncredit", invoice_no,
                "Noncredit sale paid amount is below the recorded net"
            ))
        if row["payment_method"] != "Credit" and abs(
            amounts["balance"] - max(
                Decimal(0), amounts["paid_amount"] - amounts["total_amount"]
            )
        ) > _TOL:
            errors.append(AuditFinding(
                "change_mismatch", invoice_no,
                "Recorded change does not match paid minus net"
            ))
        return tuple(errors)

    def audit_customer_credit(self, customer_id):
        """Compare credit book with its CREDIT_SALE/PAYMENT/RETURN/VOID log.

        A difference may be a legitimate opening balance or migration; report
        it as an unverified gap rather than silently rewriting the customer.
        Loyalty points have no complete standalone movement journal, so no
        invented loyalty reconciliation is attempted.
        """
        self._check()
        if isinstance(customer_id, bool) or not isinstance(customer_id, int) or customer_id < 1:
            raise ValueError("Invalid customer id")
        with self.database.db() as c:
            customer = c.execute(
                "SELECT credit_balance,loyalty_points FROM customers WHERE id=?",
                (customer_id,),
            ).fetchone()
            if customer is None:
                raise ValueError("Customer not found")
            logs = c.execute(
                "SELECT type,amount FROM credit_logs WHERE customer_id=? ORDER BY id",
                (customer_id,),
            ).fetchall()
        actual = _decimal(customer["credit_balance"], "customer credit")
        points = _decimal(customer["loyalty_points"], "loyalty points")
        expected = Decimal(0)
        findings = []
        signs = {"CREDIT_SALE": 1, "PAYMENT": -1, "RETURN": -1, "VOID": -1}
        for item in logs:
            kind = item["type"]
            amount = _decimal(item["amount"], "credit log amount")
            if amount < 0:
                findings.append(AuditFinding(
                    "negative_credit_log", str(customer_id), "Negative credit log amount"
                ))
            if kind not in signs:
                findings.append(AuditFinding(
                    "unknown_credit_log_type", str(customer_id),
                    "Unrecognized credit log entry"
                ))
            else:
                expected += signs[kind] * amount
        if abs(expected - actual) > _TOL:
            findings.append(AuditFinding(
                "credit_balance_unverified", str(customer_id),
                "Current credit balance differs from known credit-log movements"
            ))
        if points < 0:
            findings.append(AuditFinding(
                "negative_loyalty_points", str(customer_id),
                "Persisted loyalty points cannot be negative"
            ))
        return {
            "customer_id": customer_id,
            "credit_balance": actual,
            "credit_log_net": expected,
            "loyalty_points": points,
            "loyalty_reconciled": False,
            "findings": tuple(findings),
            "certified": False,
        }

    def audit_supplier_balance(self, supplier_id):
        """Recompute all-time valid GRNs minus all recorded payments.

        Initial GRN paid amounts are already also in supplier_payments; do not
        subtract purchases.paid again. Advances are kept separately.
        """
        self._check()
        if isinstance(supplier_id, bool) or not isinstance(supplier_id, int) or supplier_id < 1:
            raise ValueError("Invalid supplier id")
        with self.database.db() as c:
            sup = c.execute(
                "SELECT id FROM suppliers WHERE id=?", (supplier_id,),
            ).fetchone()
            if sup is None:
                raise ValueError("Supplier not found")
            purchases = c.execute(
                "SELECT status,total,subtotal,discount FROM purchases "
                "WHERE supplier_id=?", (supplier_id,),
            ).fetchall()
            payments = c.execute(
                "SELECT amount,purchase_id FROM supplier_payments "
                "WHERE supplier_id=?", (supplier_id,),
            ).fetchall()
            bad_refs = c.execute(
                "SELECT COUNT(*) FROM supplier_payments sp "
                "LEFT JOIN purchases p ON p.id=sp.purchase_id "
                "WHERE sp.supplier_id=? AND sp.purchase_id IS NOT NULL "
                "AND (p.id IS NULL OR p.supplier_id<>sp.supplier_id)",
                (supplier_id,),
            ).fetchone()[0]
        findings = []
        bought = Decimal(0)
        for p in purchases:
            value = _decimal(p["total"], "purchase total")
            if value < 0:
                findings.append(AuditFinding(
                    "negative_purchase_total", str(supplier_id),
                    "Purchase has negative recorded total"
                ))
            if p["status"] == "OK":
                bought += value
                subtotal = _decimal(p["subtotal"], "purchase subtotal")
                discount = _decimal(p["discount"], "purchase discount")
                if abs(subtotal - discount - value) > _TOL:
                    findings.append(AuditFinding(
                        "purchase_total_mismatch", str(supplier_id),
                        "Valid GRN does not reconcile to subtotal minus discount"
                    ))
        paid = Decimal(0)
        for p in payments:
            amount = _decimal(p["amount"], "supplier payment")
            if amount <= 0:
                findings.append(AuditFinding(
                    "invalid_supplier_payment", str(supplier_id),
                    "Supplier payment is not positive"
                ))
            paid += amount
        if bad_refs:
            findings.append(AuditFinding(
                "foreign_purchase_payment", str(supplier_id),
                "Payment references a missing or different supplier's purchase"
            ))
        balance = bought - paid
        return {
            "supplier_id": supplier_id,
            "valid_grn_total": bought.quantize(_CENT),
            "payment_total": paid.quantize(_CENT),
            "balance": balance.quantize(_CENT),
            "payable": max(balance, Decimal(0)).quantize(_CENT),
            "advance": max(-balance, Decimal(0)).quantize(_CENT),
            "findings": tuple(findings),
            "certified": False,
        }
