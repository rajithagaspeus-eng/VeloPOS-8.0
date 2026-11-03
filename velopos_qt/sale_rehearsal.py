"""Rollback-only atomic sale rehearsal in ISOLATED V8 preview storage.

This is an internal test harness, not a commerce service or Qt checkout:
it stages a synthetic invoice, stock movements and idempotency claim while
holding one BEGIN IMMEDIATE SQLite lock, but ALWAYS ROLLS ALL OF IT BACK.
Even a successful rehearsal cannot persist an invoice, payment or stock change.
Never wire this module into UI or production services. Not all legacy business
rules (units, taxes, credit, returns, batches) are simulated.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256

from .checkout_preflight import _quantity
from .idempotency_ledger import PreviewIdempotencyLedger
from .service_authorization import PreviewServiceAuthorization


@dataclass(frozen=True)
class SaleRehearsal:
    invoice_preview: str
    subtotal: Decimal
    staged_items: int
    persisted: bool = False


class RollbackOnlySaleRehearsal:
    def __init__(self, database):
        self.database = database
        self.auth = PreviewServiceAuthorization(database)
        self.journal = PreviewIdempotencyLedger(database)

    def simulate(self, *, identity, shift_id, request_id, lines, today=None,
                 inject_failure_at=None):
        """Prove core transaction composition without committing anything.

        The only accepted actor must have a live persisted preview identity
        and own an open shift; commercial license remains unverified, and
        staged writes are therefore *always* rolled back, even on success.
        inject_failure_at is test-only ('after_stock' or 'after_invoice').
        """
        if not isinstance(lines, (list, tuple)) or not 1 <= len(lines) <= 100:
            raise ValueError("Provide 1-100 sample lines")
        day = date.today() if today is None else date.fromisoformat(str(today))
        if today is not None and day.isoformat() != str(today):
            raise ValueError("Noncanonical date")
        parsed, needed = [], {}
        total = Decimal(0)
        for item in lines:
            if not isinstance(item, dict):
                raise ValueError("Invalid line")
            barcode = item.get("barcode")
            if not isinstance(barcode, str) or not 1 <= len(barcode) <= 80:
                raise ValueError("Invalid barcode")
            qty, price = _quantity(item.get("qty")), _quantity(item.get("price"))
            if not 0 < qty <= Decimal(1000000) or not 0 <= price <= Decimal(100000000):
                raise ValueError("Invalid quantity/price")
            needed[barcode] = needed.get(barcode, Decimal(0)) + qty
            parsed.append((barcode, qty, price))
            total += qty * price
        total = total.quantize(Decimal("0.01"))
        # Keep fingerprint fully bound to immutable line quantities, dates,
        # identity and shift. This is still only a test-only claim.
        payload = {
            "actor": getattr(identity, "username", None),
            "shift": shift_id,
            "day": day.isoformat(),
            "items": [
                {"barcode": barcode, "qty": str(qty), "price": str(price)}
                for barcode, qty, price in parsed
            ],
        }
        invoice = "SIM-" + sha256(str(request_id).encode("utf-8")).hexdigest()[:20]
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            decision = self.auth.inspect(
                connection, action="sale", identity=identity, shift_id=shift_id
            )
            # The two always-present release blockers are *never bypassed for
            # commerce*; this method simulates only the other local checks.
            remaining = set(decision.reasons) - {
                "preview_transactions_disabled", "commercial_license_unverified"
            }
            if remaining or not decision.actor:
                raise PermissionError("Rehearsal actor/shift denied: " + ", ".join(sorted(remaining)))
            claim = self.journal.claim(connection, "sale", request_id, payload)
            if not claim.is_new:
                raise ValueError("Unexpected persisted rehearsal result")
            for barcode, qty in needed.items():
                row = connection.execute(
                    "SELECT stock_qty, expiry_date FROM products WHERE barcode=?",
                    (barcode,),
                ).fetchone()
                if row is None:
                    raise ValueError("Missing product")
                if _quantity(row["stock_qty"]) < qty:
                    raise ValueError("Insufficient stock")
                if row["expiry_date"] and row["expiry_date"] < day.isoformat():
                    raise ValueError("Expired product")
                changed = connection.execute(
                    "UPDATE products SET stock_qty=stock_qty-? "
                    "WHERE barcode=? AND stock_qty>=?",
                    (float(qty), barcode, float(qty)),
                )
                if changed.rowcount != 1:
                    raise ValueError("Stock changed during rehearsal")
            if inject_failure_at == "after_stock":
                raise RuntimeError("Injected failure after stock changes")
            for barcode, _, price in parsed:
                row = connection.execute(
                    "SELECT selling_price FROM products WHERE barcode=?",
                    (barcode,),
                ).fetchone()
                if row is None or _quantity(row["selling_price"]) != price:
                    raise ValueError("Price changed")
            connection.execute(
                "INSERT INTO sales(invoice_no,date,time,total_amount,cashier,status) "
                "VALUES(?,?,'00:00:00',?,?,'SIMULATED')",
                (invoice, day.isoformat(), float(total), decision.actor),
            )
            for barcode, qty, price in parsed:
                connection.execute(
                    "INSERT INTO sale_items(invoice_no,barcode,qty,selling_price,total) "
                    "VALUES(?,?,?,?,?)",
                    (invoice, barcode, float(qty), float(price), float(qty * price)),
                )
            if inject_failure_at == "after_invoice":
                raise RuntimeError("Injected failure after invoice")
            self.journal.complete(connection, "sale", request_id, invoice)
            staged = connection.execute(
                "SELECT COUNT(*) FROM sale_items WHERE invoice_no=?", (invoice,)
            ).fetchone()[0]
            return SaleRehearsal(invoice, total, staged)
        finally:
            # NEVER COMMIT, under any circumstances. This is the safety
            # guarantee and cannot be overridden with caller arguments.
            connection.rollback()
            connection.close()
