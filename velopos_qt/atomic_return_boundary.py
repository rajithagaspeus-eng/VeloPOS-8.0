"""Atomic return readiness diagnostic for isolated V8 TEST DATA ONLY.

One locked snapshot checks session, branch, signed entitlement/activation,
invoice eligibility, and remaining quantities. It never writes, reserves a
request, calls legacy services, commits, or authorizes a refund.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .combined_authorization import PreviewCombinedAuthorization
from .idempotency_ledger import PreviewIdempotencyLedger
from .product_editor import _guard

_CENT = Decimal("0.01")
_MAX_QTY = Decimal("1000000")


@dataclass(frozen=True)
class AtomicReturnReadiness:
    reasons: tuple[str, ...]
    item_count: int
    amount: Decimal
    local_checks_consistent: bool
    session_bound: bool
    branch_verified: bool
    license_bound: bool
    signed_chain_valid: bool
    policy_consistent: bool
    can_execute: bool = False
    can_refund: bool = False


class PreviewAtomicReturnBoundary:
    """Read-only one-snapshot return diagnostic; never a refund service."""

    def __init__(self, database, *, license_public_key_b64):
        _guard(database)
        self.database = database
        self.authorization = PreviewCombinedAuthorization(
            database, public_key_b64=license_public_key_b64
        )
        self._connection_gate = PreviewIdempotencyLedger(database)

    @staticmethod
    def _day(today):
        if today is None:
            return date.today()
        if type(today) is not str:
            raise ValueError("Use canonical YYYY-MM-DD date")
        try:
            day = date.fromisoformat(today)
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid inspection date") from exc
        if day.isoformat() != today:
            raise ValueError("Use canonical YYYY-MM-DD date")
        return day

    @staticmethod
    def _items(items):
        if not isinstance(items, (list, tuple)) or not 1 <= len(items) <= 100:
            raise ValueError("Provide 1-100 return lines")
        quantities = {}
        for item in items:
            if not isinstance(item, dict) or set(item) != {"sale_item_id", "qty"}:
                raise ValueError("Return line must contain sale_item_id and qty")
            item_id = item["sale_item_id"]
            if type(item_id) is not int or item_id <= 0:
                raise ValueError("Invalid original sale-item ID")
            try:
                qty = Decimal(str(item["qty"]))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError("Invalid return quantity") from exc
            if not qty.is_finite() or qty <= 0 or qty > _MAX_QTY:
                raise ValueError("Return quantity out of range")
            total = quantities.get(item_id, Decimal("0")) + qty
            if total > _MAX_QTY:
                raise ValueError("Combined return quantity out of range")
            quantities[item_id] = total
        return quantities

    def inspect_in_transaction(
            self, connection, *, identity, shift_id, request_id, invoice_no,
            items, expected_branch_id, license_id, machine_id, license_key,
            server_public_key_b64, previous_status, current_status,
            today=None, now=None, max_offline_hours=24):
        """Inspect caller-owned BEGIN IMMEDIATE snapshot; never commits or writes."""
        self._connection_gate._check_connection(connection)
        day = self._day(today)
        if (type(request_id) is not str or not 8 <= len(request_id) <= 128 or
                not request_id.isascii() or
                not all(c.isalnum() or c in "_.:-" for c in request_id)):
            raise ValueError("Invalid return request ID")
        if (type(invoice_no) is not str or not 1 <= len(invoice_no) <= 120 or
                invoice_no != invoice_no.strip() or not invoice_no.isprintable()):
            raise ValueError("Invalid invoice reference")
        quantities = self._items(items)

        decision = self.authorization.inspect_with_activation_chain(
            connection, action="return",
            expected_branch_id=expected_branch_id,
            license_id=license_id,
            server_public_key_b64=server_public_key_b64,
            previous_status=previous_status, current_status=current_status,
            identity=identity, shift_id=shift_id, license_key=license_key,
            machine_id=machine_id, today=day, now=now,
            max_offline_hours=max_offline_hours,
        )
        reasons = list(dict.fromkeys((
            *decision.authorization.session_reasons,
            *decision.authorization.license_reasons,
            *decision.branch_reasons, *decision.chain_reasons,
        )))
        amount = Decimal("0.00")
        local_ok = True
        sale = connection.execute(
            "SELECT status FROM sales WHERE invoice_no=?", (invoice_no,)
        ).fetchone()
        if sale is None or sale["status"] != "OK":
            reasons.append("eligible_original_invoice_required")
            local_ok = False
        else:
            for item_id, qty in sorted(quantities.items()):
                original = connection.execute(
                    "SELECT qty,selling_price FROM sale_items "
                    "WHERE id=? AND invoice_no=?", (item_id, invoice_no)
                ).fetchone()
                if original is None:
                    reasons.append(f"sale_item_not_on_invoice:{item_id}")
                    local_ok = False
                    continue
                try:
                    sold = Decimal(str(original["qty"]))
                    price = Decimal(str(original["selling_price"]))
                    already = Decimal(str(connection.execute(
                        "SELECT COALESCE(SUM(qty),0) FROM return_items "
                        "WHERE sale_item_id=?", (item_id,)
                    ).fetchone()[0]))
                except (InvalidOperation, TypeError, ValueError):
                    reasons.append(f"invalid_original_sale_values:{item_id}")
                    local_ok = False
                    continue
                if (not all(v.is_finite() for v in (sold, price, already)) or
                        sold <= 0 or price < 0 or already < 0 or already > sold):
                    reasons.append(f"invalid_original_sale_values:{item_id}")
                    local_ok = False
                    continue
                if already + qty > sold:
                    reasons.append(f"return_exceeds_remaining_quantity:{item_id}")
                    local_ok = False
                    continue
                try:
                    amount += (qty * price).quantize(
                        _CENT, rounding=ROUND_HALF_UP
                    )
                except InvalidOperation:
                    reasons.append(f"return_amount_out_of_range:{item_id}")
                    local_ok = False

        reasons.append("commercial_atomic_return_unimplemented")
        return AtomicReturnReadiness(
            reasons=tuple(dict.fromkeys(reasons)), item_count=len(quantities),
            amount=amount, local_checks_consistent=local_ok,
            session_bound=(
                decision.authorization.actor is not None and
                "verified_session_required" not in
                decision.authorization.session_reasons
            ),
            branch_verified=decision.branch_verified,
            license_bound=decision.identity_bound,
            signed_chain_valid=(
                decision.chain_signatures_valid and decision.chain_consistent
            ),
            policy_consistent=decision.policy_consistent,
        )

    def inspect(self, **kwargs):
        """Take an isolated write lock, diagnose, and always roll back."""
        _guard(self.database)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            return self.inspect_in_transaction(connection, **kwargs)
        finally:
            connection.rollback()
            connection.close()

    def require(self, **kwargs):
        result = self.inspect(**kwargs)
        raise PermissionError("; ".join(result.reasons))
