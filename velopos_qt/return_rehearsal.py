"""Rollback-only partial-return rehearsal for ISOLATED V8 TEST storage.

NOT a refund service, POS return API or production transaction. This internal
test harness deliberately stages a synthetic return, stock restoration and an
idempotency result in a single BEGIN IMMEDIATE transaction and ALWAYS rolls
back on success and failure. It never charges, refunds or prints anything.

Return quantities are validated against persisted sale-item quantities minus
already-recorded returns, including repeated lines within the same request.
Tax, batches, unit conversion, discounts, credit and loyalty reversal remain
unimplemented: this harness cannot be used as a commercial return engine.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256

from .checkout_preflight import _quantity
from .idempotency_ledger import PreviewIdempotencyLedger
from .service_authorization import PreviewServiceAuthorization


@dataclass(frozen=True)
class ReturnRehearsal:
    return_preview: str
    amount: Decimal
    staged_items: int
    persisted: bool = False


class RollbackOnlyReturnRehearsal:
    def __init__(self, database):
        self.database = database
        self.auth = PreviewServiceAuthorization(database)
        self.journal = PreviewIdempotencyLedger(database)

    def simulate(self, *, identity, shift_id, request_id, invoice_no, items,
                 today=None, inject_failure_at=None):
        """Inspect and stage a refund, then ALWAYS roll back every database change."""
        if not isinstance(invoice_no, str) or not 1 <= len(invoice_no) <= 120:
            raise ValueError("Invalid invoice reference")
        if not isinstance(items, (list, tuple)) or not 1 <= len(items) <= 100:
            raise ValueError("Provide 1-100 return items")
        day = date.today() if today is None else date.fromisoformat(str(today))
        if today is not None and day.isoformat() != str(today):
            raise ValueError("Noncanonical date")
        quantities = {}
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Invalid return item")
            item_id = item.get("sale_item_id")
            if isinstance(item_id, bool) or not isinstance(item_id, int) or item_id < 1:
                raise ValueError("Invalid original sale-item ID")
            qty = _quantity(item.get("qty"))
            if not Decimal(0) < qty <= Decimal(1000000):
                raise ValueError("Invalid return quantity")
            quantities[item_id] = quantities.get(item_id, Decimal(0)) + qty

        payload = {
            "actor": getattr(identity, "username", None),
            "shift": shift_id, "invoice": invoice_no,
            "day": day.isoformat(),
            "items": [{"id": i, "qty": str(q)} for i, q in sorted(quantities.items())],
        }
        return_no = "SIM-RET-" + sha256(str(request_id).encode("utf-8")).hexdigest()[:18]
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            authorization = self.auth.inspect(
                connection, action="return", identity=identity, shift_id=shift_id
            )
            # The preview/license blockers are NEVER waived for real commerce.
            # This is ONLY an internal rollback-only consistency exercise.
            problems = set(authorization.reasons) - {
                "preview_transactions_disabled", "commercial_license_unverified"
            }
            if problems or not authorization.actor:
                raise PermissionError("Return rehearsal denied: " + ", ".join(sorted(problems)))
            sale = connection.execute(
                "SELECT invoice_no,status FROM sales WHERE invoice_no=?", (invoice_no,)
            ).fetchone()
            if sale is None or sale["status"] != "OK":
                raise ValueError("Original sale missing, void or ineligible")
            claim = self.journal.claim(connection, "return", request_id, payload)
            if not claim.is_new:
                raise ValueError("Unexpected persisted rehearsal result")

            rows = []
            needed = {}
            amount = Decimal(0)
            for sale_item_id, qty in sorted(quantities.items()):
                original = connection.execute(
                    "SELECT id,barcode,item_name,qty,selling_price "
                    "FROM sale_items WHERE id=? AND invoice_no=?",
                    (sale_item_id, invoice_no),
                ).fetchone()
                if original is None:
                    raise ValueError("Sale item does not belong to invoice")
                already = connection.execute(
                    "SELECT COALESCE(SUM(qty),0) FROM return_items "
                    "WHERE sale_item_id=?", (sale_item_id,),
                ).fetchone()[0]
                sold_qty = _quantity(original["qty"])
                if sold_qty <= 0 or qty + _quantity(already) > sold_qty:
                    raise ValueError("Return exceeds remaining sold quantity")
                price = _quantity(original["selling_price"])
                if price < 0:
                    raise ValueError("Invalid original selling price")
                line_total = (qty * price).quantize(Decimal("0.01"))
                amount += line_total
                rows.append((sale_item_id, original["barcode"], original["item_name"],
                             qty, price, line_total))
                needed[original["barcode"]] = (
                    needed.get(original["barcode"], Decimal(0)) + qty
                )
            for barcode, qty in needed.items():
                changed = connection.execute(
                    "UPDATE products SET stock_qty=stock_qty+? WHERE barcode=?",
                    (float(qty), barcode),
                )
                if changed.rowcount != 1:
                    raise ValueError("Original product not available for restoration")
            if inject_failure_at == "after_stock":
                raise RuntimeError("Injected return failure after stock restoration")
            amount = amount.quantize(Decimal("0.01"))
            connection.execute(
                "INSERT INTO returns(return_no,invoice_no,date,time,amount,"
                "refund_method,reason,cashier,shift_id,profit_adj) "
                "VALUES(?,?,?,'00:00:00',?,'SIMULATED','TEST ONLY',?,?,0)",
                (return_no, invoice_no, day.isoformat(), float(amount),
                 authorization.actor, shift_id),
            )
            for item_id, barcode, name, qty, price, total in rows:
                connection.execute(
                    "INSERT INTO return_items(return_no,sale_item_id,barcode,"
                    "item_name,qty,price,total) VALUES(?,?,?,?,?,?,?)",
                    (return_no, item_id, barcode, name, float(qty),
                     float(price), float(total)),
                )
            if inject_failure_at == "after_return":
                raise RuntimeError("Injected return failure after return records")
            self.journal.complete(connection, "return", request_id, return_no)
            staged = connection.execute(
                "SELECT COUNT(*) FROM return_items WHERE return_no=?", (return_no,)
            ).fetchone()[0]
            return ReturnRehearsal(return_no, amount, staged)
        finally:
            # This unconditional rollback is the key safety property.
            connection.rollback()
            connection.close()
