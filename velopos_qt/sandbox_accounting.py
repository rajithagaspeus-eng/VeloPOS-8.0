"""Independent, immutable TEST-SANDBOX revenue/return close-out.

NO production accounting, credit collection, profit, payments or real refunds.
All amounts are INTEGER CENTS; declarations do not prove payment capture.
A single owned BEGIN IMMEDIATE snapshot validates the complete sandbox
invoice/return/journal/stock/settlement chain and ALWAYS rolls back.
"""
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext

from .idempotency_ledger import PreviewIdempotencyLedger
from .product_editor import _guard

_CONTEXT = Context(prec=512, rounding=ROUND_HALF_UP)
_CENT = Decimal("0.01")
_SALE_TABLES = frozenset({
    "v8_preview_sandbox_sales", "v8_preview_sandbox_sale_lines",
    "v8_preview_sandbox_stock", "v8_preview_sandbox_stock_moves",
    "v8_preview_sandbox_settlements", "v8_preview_sandbox_tenders",
    "v8_preview_request_journal",
})
_RETURN_TABLES = frozenset({
    "v8_preview_sandbox_returns", "v8_preview_sandbox_return_lines",
})


@dataclass(frozen=True)
class SandboxCloseout:
    balanced: bool
    reasons: tuple[str, ...]
    invoice_count: int
    return_count: int
    gross_cents: int
    declared_returns_cents: int
    net_after_declared_returns_cents: int
    declared_cash_cents: int
    declared_external_cents: int
    declared_change_cents: int
    captured_payment_cents: int = 0
    actual_refunds_cents: int = 0
    certified_profit_cents: int | None = None
    can_checkout: bool = False


class PreviewSandboxAccounting:
    """Read-only cross-ledger reconciliation on canonical isolated SQLite."""

    def __init__(self, database):
        _guard(database)
        self.database = database
        self._gate = PreviewIdempotencyLedger(database)

    def closeout(self):
        """Cross-check all invoices and returns in ONE locked snapshot.

        A missing, damaged, or altered journal/line/settlement/stock table
        returns an unbalanced report, never a guessed financial result.
        """
        _guard(self.database)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._gate._check_connection(connection)
            found = {
                row[0] for row in connection.execute(
                    "SELECT name FROM main.sqlite_master WHERE type='table'"
                )
            }
            if not _SALE_TABLES.issubset(found):
                return SandboxCloseout(
                    False, ("sandbox_accounting_tables_missing",),
                    0, 0, 0, 0, 0, 0, 0, 0,
                )
            if bool(_RETURN_TABLES & found) != _RETURN_TABLES.issubset(found):
                return SandboxCloseout(
                    False, ("sandbox_return_schema_partial",),
                    0, 0, 0, 0, 0, 0, 0, 0,
                )
            has_returns = _RETURN_TABLES.issubset(found)
            reasons = []
            sales = connection.execute(
                "SELECT reference,request_id,branch_id,subtotal_cents "
                "FROM main.v8_preview_sandbox_sales"
            ).fetchall()
            sale_by_ref = {row["reference"]: row for row in sales}
            sale_lines = connection.execute(
                "SELECT reference,line_no,barcode,quantity,price,line_cents "
                "FROM main.v8_preview_sandbox_sale_lines"
            ).fetchall()
            line_map = {(row["reference"], row["line_no"]): row
                        for row in sale_lines}
            if len(line_map) != len(sale_lines):
                reasons.append("duplicate_sale_line_identity")
            sale_amounts = {}
            sold_quantities = {}
            with localcontext(_CONTEXT):
                for line in sale_lines:
                    ref = line["reference"]
                    sale_amounts[ref] = sale_amounts.get(ref, 0) + line["line_cents"]
                    key = (ref, line["barcode"])
                    try:
                        qty = Decimal(line["quantity"])
                        price = Decimal(line["price"])
                    except Exception:
                        reasons.append("invalid_sale_line_decimal")
                        continue
                    if (not qty.is_finite() or not price.is_finite()
                            or qty <= 0 or price < 0 or line["line_cents"] < 0):
                        reasons.append("invalid_sale_line_amount")
                    else:
                        expected_line_cents = int(
                            (qty * price).quantize(
                                _CENT, rounding=ROUND_HALF_UP
                            ) * 100
                        )
                        if line["line_cents"] != expected_line_cents:
                            reasons.append("sale_price_quantity_mismatch")
                    sold_quantities[key] = sold_quantities.get(
                        key, Decimal("0")
                    ) + qty
            if set(sale_amounts) - set(sale_by_ref):
                reasons.append("orphan_sale_line")
            settlements = connection.execute(
                "SELECT reference,declared,due_cents,cash_cents,"
                "noncash_cents,change_cents FROM "
                "main.v8_preview_sandbox_settlements"
            ).fetchall()
            settlement_map = {row["reference"]: row for row in settlements}
            if set(settlement_map) != set(sale_by_ref):
                reasons.append("settlement_invoice_coverage")
            tenders = connection.execute(
                "SELECT reference,method,amount_cents FROM "
                "main.v8_preview_sandbox_tenders"
            ).fetchall()
            allocations = {}
            for row in tenders:
                ref = row["reference"]
                if ref not in sale_by_ref:
                    reasons.append("orphan_tender_allocation")
                if row["method"] not in ("Cash", "Card", "QR") or row["amount_cents"] <= 0:
                    reasons.append("invalid_tender_declaration")
                amounts = allocations.setdefault(ref, [0, 0])
                amounts[0 if row["method"] == "Cash" else 1] += row["amount_cents"]

            journal_sales = connection.execute(
                "SELECT request_id,status,result_ref FROM "
                "main.v8_preview_request_journal WHERE scope='sale'"
            ).fetchall()
            matched_sale_journals = set()
            for journal in journal_sales:
                ref = journal["result_ref"]
                if journal["status"] != "COMPLETED" or ref not in sale_by_ref:
                    reasons.append("unmatched_sale_journal")
                else:
                    if sale_by_ref[ref]["request_id"] != journal["request_id"]:
                        reasons.append("sale_request_journal_mismatch")
                    matched_sale_journals.add(ref)

            for sale in sales:
                ref = sale["reference"]
                if (sale_amounts.get(ref) != sale["subtotal_cents"]
                        or sale["subtotal_cents"] < 0):
                    reasons.append("sale_line_total_mismatch")
                if ref not in matched_sale_journals:
                    reasons.append("missing_completed_sale_journal")
                settled = settlement_map.get(ref)
                if settled is None:
                    continue
                if settled["due_cents"] != sale["subtotal_cents"]:
                    reasons.append("invoice_settlement_mismatch")
                cash, noncash = allocations.get(ref, (0, 0))
                if (cash != settled["cash_cents"] or
                        noncash != settled["noncash_cents"]):
                    reasons.append("tender_settlement_mismatch")
                if settled["declared"] == 1:
                    change = cash + noncash - sale["subtotal_cents"]
                    if (change < 0 or change > cash
                            or change != settled["change_cents"]
                            or noncash > sale["subtotal_cents"]):
                        reasons.append("invalid_declared_change")
                elif (settled["declared"] != 0 or cash or noncash
                      or settled["cash_cents"] or settled["noncash_cents"]
                      or settled["change_cents"]):
                    reasons.append("invalid_undeclared_settlement")

            stocks = connection.execute(
                "SELECT barcode,opening_qty,remaining_qty FROM "
                "main.v8_preview_sandbox_stock"
            ).fetchall()
            moves = connection.execute(
                "SELECT reference,barcode,before_qty,sold_qty,after_qty "
                "FROM main.v8_preview_sandbox_stock_moves ORDER BY rowid"
            ).fetchall()
            movement_keys = set()
            move_map = {}
            with localcontext(_CONTEXT):
                for move in moves:
                    key = (move["reference"], move["barcode"])
                    movement_keys.add(key)
                    move_map.setdefault(move["barcode"], []).append(move)
                    try:
                        sold = Decimal(move["sold_qty"])
                    except Exception:
                        reasons.append("invalid_stock_move_decimal")
                        continue
                    if sold_quantities.get(key) != sold:
                        reasons.append("sale_stock_quantity_mismatch")
                if movement_keys != set(sold_quantities):
                    reasons.append("sale_stock_coverage_mismatch")
                if set(move_map) != {row["barcode"] for row in stocks}:
                    reasons.append("stock_coverage_mismatch")
                for row in stocks:
                    barcode = row["barcode"]
                    try:
                        running = Decimal(row["opening_qty"])
                        remaining = Decimal(row["remaining_qty"])
                        for move in move_map.get(barcode, ()):
                            before = Decimal(move["before_qty"])
                            sold = Decimal(move["sold_qty"])
                            after = Decimal(move["after_qty"])
                            if before != running or sold <= 0 or after != before - sold:
                                reasons.append("stock_movement_chain_mismatch")
                            running = after
                        if (not running.is_finite() or not remaining.is_finite()
                                or remaining < 0 or running != remaining):
                            reasons.append("stock_balance_mismatch")
                    except Exception:
                        reasons.append("invalid_stock_balance")

            ret_headers = (connection.execute(
                "SELECT reference,request_id,original_ref,branch_id,"
                "refund_cents,refund_mode FROM main.v8_preview_sandbox_returns"
            ).fetchall() if has_returns else [])
            ret_lines = (connection.execute(
                "SELECT reference,sale_line_no,barcode,quantity,refund_cents,"
                "disposition,restocked FROM main.v8_preview_sandbox_return_lines"
            ).fetchall() if has_returns else [])
            ret_by_ref = {row["reference"]: row for row in ret_headers}
            refunded_per_sale_line = {}
            refunds_per_header = {}
            with localcontext(_CONTEXT):
                for row in ret_lines:
                    header = ret_by_ref.get(row["reference"])
                    if header is None:
                        reasons.append("orphan_return_line")
                        continue
                    key = (header["original_ref"], row["sale_line_no"])
                    original_line = line_map.get(key)
                    if original_line is None or original_line["barcode"] != row["barcode"]:
                        reasons.append("return_line_not_in_original_sale")
                        continue
                    try:
                        qty = Decimal(row["quantity"])
                    except Exception:
                        reasons.append("invalid_return_quantity")
                        continue
                    if (row["disposition"] not in ("DAMAGED","DISCARDED")
                            or row["restocked"] != 0):
                        reasons.append("return_disposition_not_nonrestocking")
                    refunded_per_sale_line.setdefault(key, []).append((qty, row["refund_cents"]))
                    refunds_per_header[row["reference"]] = (
                        refunds_per_header.get(row["reference"], 0)
                        + row["refund_cents"]
                    )
                    if qty <= 0 or not qty.is_finite() or row["refund_cents"] < 0:
                        reasons.append("invalid_return_line_amount")
                for key, lines in refunded_per_sale_line.items():
                    sold_line = line_map[key]
                    used = sum((q for q, _ in lines), Decimal("0"))
                    refunded_cents = sum(value for _, value in lines)
                    if used > Decimal(sold_line["quantity"]):
                        reasons.append("overreturned_original_quantity")
                    expected_cents = min(
                        sold_line["line_cents"],
                        int((used * Decimal(sold_line["price"]))
                            .quantize(_CENT, rounding=ROUND_HALF_UP) * 100),
                    )
                    if refunded_cents != expected_cents:
                        reasons.append("return_amount_allocation_mismatch")
            journal_returns = connection.execute(
                "SELECT request_id,status,result_ref FROM "
                "main.v8_preview_request_journal WHERE scope='return'"
            ).fetchall()
            matched_return_journals = set()
            for journal in journal_returns:
                ref = journal["result_ref"]
                if journal["status"] != "COMPLETED" or ref not in ret_by_ref:
                    reasons.append("unmatched_return_journal")
                else:
                    if ret_by_ref[ref]["request_id"] != journal["request_id"]:
                        reasons.append("return_request_journal_mismatch")
                    matched_return_journals.add(ref)
            for row in ret_headers:
                ref = row["reference"]
                original = sale_by_ref.get(row["original_ref"])
                if (original is None or row["branch_id"] != original["branch_id"]):
                    reasons.append("return_branch_mismatch")
                if row["refund_mode"] not in ("Cash", "Card", "QR"):
                    reasons.append("invalid_refund_declaration")
                if (ref not in matched_return_journals or
                        refunds_per_header.get(ref) != row["refund_cents"]
                        or row["refund_cents"] <= 0):
                    reasons.append("return_header_reconciliation_mismatch")
            gross = sum(row["subtotal_cents"] for row in sales)
            returned = sum(row["refund_cents"] for row in ret_headers)
            if returned > gross:
                reasons.append("returns_exceed_gross")
            return SandboxCloseout(
                balanced=not reasons,
                reasons=tuple(dict.fromkeys(reasons)),
                invoice_count=len(sales),
                return_count=len(ret_headers),
                gross_cents=gross,
                declared_returns_cents=returned,
                net_after_declared_returns_cents=gross - returned,
                declared_cash_cents=sum(
                    row["cash_cents"] for row in settlements
                ),
                declared_external_cents=sum(
                    row["noncash_cents"] for row in settlements
                ),
                declared_change_cents=sum(
                    row["change_cents"] for row in settlements
                ),
            )
        finally:
            connection.rollback()
            connection.close()

    def require_certified_accounting(self):
        raise PermissionError(
            "Sandbox declarations are not real settlements or certified accounting"
        )
