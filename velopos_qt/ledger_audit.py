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
