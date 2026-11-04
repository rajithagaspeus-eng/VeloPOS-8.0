"""Read-only checkout safety preflight on isolated V8 preview storage.

This is a *diagnostic*, NOT permission to sell. A BEGIN IMMEDIATE transaction
gives a consistent snapshot against concurrent SQLite writers; it is ALWAYS
rolled back and the connection closed. No invoices, sales, stock, payment or
idempotency entries are created. Actual checkout must rerun all decisions
inside its own authenticated atomic write transaction.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from .product_editor import _guard
from .auth_model import verify_preview_session
from .idempotency_ledger import PreviewIdempotencyLedger
from .sale_plan import plan_preview_sale


def _quantity(value):
    try:
        num = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError("Invalid quantity or price") from exc
    if not num.is_finite():
        raise ValueError("Invalid quantity or price")
    return num


@dataclass(frozen=True)
class CheckoutPreflight:
    """Diagnostic result, intentionally never an authorization token."""
    can_checkout: bool
    reasons: tuple[str, ...]
    line_count: int
    subtotal: Decimal


class PreviewCheckoutPreflight:
    def __init__(self, database):
        _guard(database)
        self.database = database
        self._connection_gate = PreviewIdempotencyLedger(database)

    def inspect(self, *, identity=None, shift_id=None, lines=(), request_id="",
                today=None, connection=None):
        """Inspect with own rollback-only lock or a caller-owned preview TX.

        When connection is passed, it MUST already be inside a transaction
        on the canonical preview database. This method never commits or
        rolls back a caller's transaction, allowing independent authorization,
        stock and price checks on precisely the same SQLite snapshot.
        A returned diagnostic is NEVER permission to post a sale.
        """
        """Check only. No service calls and no write or payment side effects."""
        _guard(self.database)
        plan = plan_preview_sale(lines)
        # Prevent subtle receipt discrepancies on fractional units: each
        # planned line is rounded to cents before the subtotal is summed.
        parsed = [(row.barcode, row.qty, row.price) for row in plan.lines]
        needed = dict(plan.quantities)
        subtotal = plan.subtotal
        try:
            day = date.today() if today is None else date.fromisoformat(str(today))
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid inspection date") from exc
        if day.isoformat() != (str(today) if today is not None else day.isoformat()):
            raise ValueError("Invalid inspection date")

        reasons = ["preview_checkout_disabled"]
        # No real idempotency reservation or verified license/shift gateway
        # exists yet; a valid-looking request ID is NOT evidence of uniqueness.
        # The preview journal uses a stricter canonical request-id format
        # than a length check. Deny malformed IDs here, before the recovery
        # diagnostic can inspect or expose journal information.
        try:
            PreviewIdempotencyLedger._validate_identity("sale", request_id)
        except ValueError:
            reasons.append("invalid_request_id")
        reasons.append("idempotency_not_implemented")
        reasons.append("license_not_verified")
        if isinstance(shift_id, bool) or not isinstance(shift_id, int) or shift_id <= 0:
            reasons.append("valid_open_shift_required")

        owns_connection = connection is None
        if owns_connection:
            connection = self.database.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
            except BaseException:
                connection.close()
                raise
        else:
            self._connection_gate._check_connection(connection)
        try:
            username = getattr(identity, "username", None)
            user = None
            if isinstance(username, str):
                user = connection.execute(
                    "SELECT role, pw_hash FROM users WHERE username=?", (username,)
                ).fetchone()
            verified = verify_preview_session(self.database, identity, user)
            if not verified:
                reasons.append("verified_cashier_required")

            if isinstance(shift_id, int) and not isinstance(shift_id, bool) and shift_id > 0:
                shift = connection.execute(
                    "SELECT status, cashier FROM shifts WHERE id=?", (shift_id,)
                ).fetchone()
                if shift is None or shift["status"] != "OPEN":
                    reasons.append("shift_not_open")
                elif not verified or shift["cashier"] != username:
                    reasons.append("shift_cashier_mismatch")

            for barcode, qty in needed.items():
                row = connection.execute(
                    "SELECT stock_qty, selling_price, expiry_date FROM products "
                    "WHERE barcode=?", (barcode,)
                ).fetchone()
                if row is None:
                    reasons.append(f"missing_product:{barcode}")
                    continue
                stock = _quantity(row["stock_qty"])
                if not stock.is_finite() or stock < qty:
                    reasons.append(f"insufficient_stock:{barcode}")
                if row["expiry_date"] and row["expiry_date"] < day.isoformat():
                    reasons.append(f"expired_product:{barcode}")
                if connection.execute(
                    "SELECT 1 FROM batches WHERE barcode=? AND qty_remaining>0 "
                    "AND expiry_date<>'' AND expiry_date<? LIMIT 1",
                    (barcode, day.isoformat()),
                ).fetchone():
                    reasons.append(f"expired_batch_review:{barcode}")

            for barcode, _, price in parsed:
                row = connection.execute(
                    "SELECT selling_price FROM products WHERE barcode=?", (barcode,)
                ).fetchone()
                if row and _quantity(row["selling_price"]) != price:
                    reasons.append(f"price_changed:{barcode}")
        finally:
            # Caller-managed transactions remain untouched. The original
            # inspect() path owns its lock and always rolls it back.
            if owns_connection:
                connection.rollback()
                connection.close()
        return CheckoutPreflight(
            can_checkout=False, reasons=tuple(dict.fromkeys(reasons)),
            line_count=plan.line_count, subtotal=subtotal,
        )
