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
    declared_credit_charges_cents: int = 0
    declared_credit_repayments_cents: int = 0
    outstanding_credit_cents: int = 0
    declared_credit_notes_cents: int = 0


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
                    # One sale/barcode must produce exactly one aggregated
                    # stock movement. A set-based coverage check alone loses
                    # duplicate rows and can hide a forged movement.
                    if key in movement_keys:
                        reasons.append("duplicate_sale_stock_movement")
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
            credit_charged = 0
            credit_repaid = 0
            credit_notes = 0
            credit_tables = {
                "v8_preview_sandbox_credit_accounts",
                "v8_preview_sandbox_credit_charges",
                "v8_preview_sandbox_credit_repayments",
                "v8_preview_sandbox_credit_notes",
                "v8_preview_sandbox_credit_allocations",
            }
            if credit_tables & found and not credit_tables.issubset(found):
                reasons.append("sandbox_credit_schema_partial")
            elif credit_tables.issubset(found):
                accounts = {
                    row["customer_id"]: row for row in connection.execute(
                        "SELECT customer_id,branch_id,limit_cents FROM "
                        "main.v8_preview_sandbox_credit_accounts"
                    )
                }
                balances = {cid: [0, 0, 0] for cid in accounts}
                credit_charge_refs = set()
                credit_repayment_refs = set()
                credit_note_refs = set()
                charge_by_ref = {row["reference"]: row for row in connection.execute(
                    "SELECT reference,invoice_ref,customer_id,branch_id "
                    "FROM main.v8_preview_sandbox_credit_charges"
                )}
                for charge in connection.execute(
                    "SELECT reference,request_id,invoice_ref,customer_id,"
                    "branch_id,amount_cents FROM "
                    "main.v8_preview_sandbox_credit_charges"
                ):
                    credit_charge_refs.add(charge["reference"])
                    credit_charged += charge["amount_cents"]
                    balances.setdefault(charge["customer_id"], [0, 0, 0])[0] += charge["amount_cents"]
                    invoice = sale_by_ref.get(charge["invoice_ref"])
                    settlement = settlement_map.get(charge["invoice_ref"])
                    account = accounts.get(charge["customer_id"])
                    journal = connection.execute(
                        "SELECT status,result_ref FROM main.v8_preview_request_journal "
                        "WHERE scope='credit_charge' AND request_id=?",
                        (charge["request_id"],)
                    ).fetchone()
                    if (invoice is None or
                            invoice["branch_id"] != charge["branch_id"] or
                            invoice["subtotal_cents"] != charge["amount_cents"] or
                            settlement is None or settlement["declared"] != 0 or
                            settlement["cash_cents"] or settlement["noncash_cents"] or
                            settlement["change_cents"] or
                            account is None or account["branch_id"] != charge["branch_id"] or
                            journal is None or journal["status"] != "COMPLETED" or
                            journal["result_ref"] != charge["reference"]):
                        reasons.append("sandbox_credit_charge_reconciliation")
                for repayment in connection.execute(
                    "SELECT reference,request_id,customer_id,branch_id,"
                    "amount_cents,method FROM "
                    "main.v8_preview_sandbox_credit_repayments"
                ):
                    credit_repayment_refs.add(repayment["reference"])
                    credit_repaid += repayment["amount_cents"]
                    balances.setdefault(repayment["customer_id"], [0, 0, 0])[1] += repayment["amount_cents"]
                    account = accounts.get(repayment["customer_id"])
                    journal = connection.execute(
                        "SELECT status,result_ref FROM main.v8_preview_request_journal "
                        "WHERE scope='credit_payment' AND request_id=?",
                        (repayment["request_id"],)
                    ).fetchone()
                    if (account is None or account["branch_id"] != repayment["branch_id"]
                            or repayment["method"] != "Cash" or journal is None
                            or journal["status"] != "COMPLETED" or
                            journal["result_ref"] != repayment["reference"]):
                        reasons.append("sandbox_credit_repayment_reconciliation")
                allocated_by_charge = {}
                allocated_payment_refs = set()
                customers_with_allocations = set()
                for allocation in connection.execute(
                    "SELECT repayment_ref,charge_ref,customer_id,branch_id,amount_cents "
                    "FROM main.v8_preview_sandbox_credit_allocations"
                ):
                    allocated_payment_refs.add(allocation["repayment_ref"])
                    customers_with_allocations.add(allocation["customer_id"])
                    repayment = connection.execute(
                        "SELECT customer_id,branch_id,amount_cents FROM "
                        "main.v8_preview_sandbox_credit_repayments WHERE reference=?",
                        (allocation["repayment_ref"],)
                    ).fetchone()
                    charge = charge_by_ref.get(allocation["charge_ref"])
                    if (repayment is None or charge is None or
                            repayment["customer_id"] != allocation["customer_id"] or
                            repayment["branch_id"] != allocation["branch_id"] or
                            repayment["amount_cents"] != allocation["amount_cents"] or
                            charge["customer_id"] != allocation["customer_id"] or
                            charge["branch_id"] != allocation["branch_id"]):
                        reasons.append("sandbox_credit_allocation_mismatch")
                    allocated_by_charge[allocation["charge_ref"]] = (
                        allocated_by_charge.get(allocation["charge_ref"],0)
                        + allocation["amount_cents"]
                    )
                if customers_with_allocations:
                    for repayment in connection.execute(
                        "SELECT reference,customer_id FROM "
                        "main.v8_preview_sandbox_credit_repayments"
                    ):
                        if (repayment["customer_id"] in customers_with_allocations
                                and repayment["reference"] not in allocated_payment_refs):
                            reasons.append("sandbox_credit_mixed_repayment_modes")
                note_totals_by_charge = {}
                note_lines = {}
                for note in connection.execute(
                    "SELECT reference,request_id,charge_ref,invoice_ref,customer_id,"
                    "branch_id,sale_line_no,quantity,disposition,restocked,"
                    "amount_cents FROM main.v8_preview_sandbox_credit_notes"
                ):
                    credit_note_refs.add(note["reference"])
                    credit_notes += note["amount_cents"]
                    note_totals_by_charge[note["charge_ref"]] = (
                        note_totals_by_charge.get(note["charge_ref"],0)
                        + note["amount_cents"]
                    )
                    balances.setdefault(note["customer_id"],[0,0,0])[2] += note["amount_cents"]
                    charge = charge_by_ref.get(note["charge_ref"])
                    line = line_map.get((note["invoice_ref"],note["sale_line_no"]))
                    journal = connection.execute(
                        "SELECT status,result_ref FROM main.v8_preview_request_journal "
                        "WHERE scope='credit_note' AND request_id=?",
                        (note["request_id"],)
                    ).fetchone()
                    if (charge is None or charge["invoice_ref"] != note["invoice_ref"]
                            or charge["customer_id"] != note["customer_id"]
                            or charge["branch_id"] != note["branch_id"]
                            or note["disposition"] not in ("DAMAGED","DISCARDED")
                            or note["restocked"] != 0 or note["amount_cents"] <= 0
                            or line is None or journal is None
                            or journal["status"] != "COMPLETED"
                            or journal["result_ref"] != note["reference"]):
                        reasons.append("sandbox_credit_note_reconciliation")
                    if line is not None and charge is not None:
                        note_lines.setdefault((note["invoice_ref"],note["sale_line_no"]),[]).append(note)
                with localcontext(_CONTEXT):
                    for key, credited_lines in note_lines.items():
                        original = line_map[key]
                        try:
                            used = sum((Decimal(row["quantity"]) for row in credited_lines),Decimal("0"))
                            cents = sum(row["amount_cents"] for row in credited_lines)
                            expected = min(original["line_cents"],int(
                                (used*Decimal(original["price"]))
                                .quantize(_CENT,rounding=ROUND_HALF_UP)*100
                            ))
                            if (used <= 0 or used > Decimal(original["quantity"])
                                    or cents != expected):
                                reasons.append("sandbox_credit_note_quantity_mismatch")
                        except Exception:
                            reasons.append("sandbox_credit_note_invalid_quantity")
                for charge_ref, charge in charge_by_ref.items():
                    if (allocated_by_charge.get(charge_ref,0)
                            + note_totals_by_charge.get(charge_ref,0)
                            > connection.execute(
                                "SELECT amount_cents FROM "
                                "main.v8_preview_sandbox_credit_charges WHERE reference=?",
                                (charge_ref,)
                            ).fetchone()[0]):
                        reasons.append("sandbox_credit_invoice_overallocated")
                for cid, (charges, repayments, credited) in balances.items():
                    account = accounts.get(cid)
                    if (account is None or charges < 0 or repayments < 0
                            or repayments + credited > charges or
                            charges - repayments - credited > account["limit_cents"]):
                        reasons.append("sandbox_credit_balance_or_limit_mismatch")
                for scope, refs in (
                    ("credit_charge", credit_charge_refs),
                    ("credit_payment", credit_repayment_refs),
                    ("credit_note", credit_note_refs),
                ):
                    for row in connection.execute(
                        "SELECT status,result_ref FROM main.v8_preview_request_journal "
                        "WHERE scope=?", (scope,)
                    ):
                        if row["status"] != "COMPLETED" or row["result_ref"] not in refs:
                            reasons.append("sandbox_credit_orphan_journal")
            gross = sum(row["subtotal_cents"] for row in sales)
            returned = sum(row["refund_cents"] for row in ret_headers)
            if returned + credit_notes > gross:
                reasons.append("returns_exceed_gross")
            return SandboxCloseout(
                balanced=not reasons,
                reasons=tuple(dict.fromkeys(reasons)),
                invoice_count=len(sales),
                return_count=len(ret_headers),
                gross_cents=gross,
                declared_returns_cents=returned,
                net_after_declared_returns_cents=gross - returned - credit_notes,
                declared_cash_cents=sum(
                    row["cash_cents"] for row in settlements
                ),
                declared_external_cents=sum(
                    row["noncash_cents"] for row in settlements
                ),
                declared_change_cents=sum(
                    row["change_cents"] for row in settlements
                ),
                declared_credit_charges_cents=credit_charged,
                declared_credit_repayments_cents=credit_repaid,
                outstanding_credit_cents=credit_charged-credit_repaid-credit_notes,
                declared_credit_notes_cents=credit_notes,
            )
        finally:
            connection.rollback()
            connection.close()

    def require_certified_accounting(self):
        raise PermissionError(
            "Sandbox declarations are not real settlements or certified accounting"
        )
