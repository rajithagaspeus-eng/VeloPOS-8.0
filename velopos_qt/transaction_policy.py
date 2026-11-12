"""Fail-closed transaction permission boundary for the *preview* release.

This is NOT a production session manager. It intentionally rejects all writes:
no Qt element can obtain checkout, purchase, payment, loyalty redemption or
supplier payment permissions by passing a role string or a fake license flag.
A future commercial gateway needs separately verified session, license, shift,
permissions and transactional revalidation before implementation.
"""
from dataclasses import dataclass

from .product_editor import _guard


@dataclass(frozen=True)
class TransactionDecision:
    action: str
    allowed: bool
    reasons: tuple[str, ...]


class PreviewTransactionGate:
    protected = frozenset({
        "sale", "return", "purchase", "supplier_payment", "credit_payment",
        "points_redemption", "shift_open", "shift_close", "receipt_print",
        "sale_void", "purchase_void", "cash_move", "expense_add",
        "expense_delete", "stock_adjustment", "stock_take_finalize",
        "batch_receive",
    })

    def __init__(self, database):
        _guard(database)
        self.database = database

    def evaluate(self, action, identity=None):
        _guard(self.database)
        if action not in self.protected:
            raise ValueError("Unknown protected transaction action")
        reasons = ["V8 preview is non-transactional"]
        if identity is None or getattr(identity, "role", None) not in ("Admin", "Cashier"):
            reasons.append("A verified signed-in cashier session is required")
        # Never trust UI, role strings, fabricated licenses or shift flags to
        # convert this read-only test build into a transactional system.
        return TransactionDecision(action, False, tuple(reasons))

    def require(self, action, identity=None):
        decision = self.evaluate(action, identity)
        if not decision.allowed:
            raise PermissionError("; ".join(decision.reasons))
        raise AssertionError("No preview transactions may ever be authorized")
