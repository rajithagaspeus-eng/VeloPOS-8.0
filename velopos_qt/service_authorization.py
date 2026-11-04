"""Transaction-bound authorization diagnostic for isolated V8 preview data.

This is a policy *foundation*, never an approval or executable entitlement.
Even a valid persisted session with an open shift has license_verified=False,
and can_execute=False. Original V7 services are not covered by this checker.

All user and shift lookups explicitly target main.*, never TEMP shadow tables.
Call only inside the caller's own BEGIN IMMEDIATE transaction, and repeat the
checks inside any eventual commercial mutation before writing any financial
row. No external role/license booleans can turn the preview into checkout.
"""
from dataclasses import dataclass

from .idempotency_ledger import PreviewIdempotencyLedger
from .transaction_policy import PreviewTransactionGate
from .auth_model import verify_preview_session


@dataclass(frozen=True)
class ServiceAuthorization:
    action: str
    actor: str | None
    role: str | None
    reasons: tuple[str, ...]
    can_execute: bool = False


# Conservative future service contract: even managerial actions should not
# depend on a client-supplied role; all role decisions are read from storage.
_ACTION_ROLES = {
    "sale": ("Admin", "Cashier"),
    "return": ("Admin", "Cashier"),
    "purchase": ("Admin",),
    "supplier_payment": ("Admin",),
    "credit_payment": ("Admin", "Cashier"),
    "points_redemption": ("Admin", "Cashier"),
    "shift_open": ("Admin", "Cashier"),
    "shift_close": ("Admin", "Cashier"),
    "receipt_print": ("Admin", "Cashier"),
    "sale_void": ("Admin",),
    "purchase_void": ("Admin",),
    "cash_move": ("Admin", "Cashier"),
    "expense_add": ("Admin",),
    "expense_delete": ("Admin",),
    "stock_adjustment": ("Admin",),
    "stock_take_finalize": ("Admin",),
    "batch_receive": ("Admin",),
}
_SHIFT_ACTIONS = frozenset({
    "sale", "return", "supplier_payment", "credit_payment", "points_redemption",
    "shift_close", "sale_void", "cash_move", "expense_add", "expense_delete",
})


class PreviewServiceAuthorization:
    def __init__(self, database):
        self.database = database
        self._connection_gate = PreviewIdempotencyLedger(database)
        self._transaction_gate = PreviewTransactionGate(database)

    def inspect(self, connection, *, action, identity=None, shift_id=None):
        """Inspect current persisted actor and shift without granting access.

        Requires an already-open caller transaction on canonical isolated DB.
        Does no writes, and will never call legacy V7 transaction services.
        """
        self._connection_gate._check_connection(connection)
        if action not in _ACTION_ROLES:
            raise ValueError("Unknown financial action")

        reasons = ["preview_transactions_disabled", "commercial_license_unverified"]
        username = getattr(identity, "username", None)
        row = None
        if isinstance(username, str):
            row = connection.execute(
                "SELECT role,pw_hash FROM main.users WHERE username=?", (username,)
            ).fetchone()
        actor, role = None, None
        if verify_preview_session(self.database, identity, row):
            actor, role = username, row["role"]

        if actor is None:
            reasons.append("verified_session_required")
        elif role not in _ACTION_ROLES[action]:
            reasons.append("role_not_permitted")

        if action in _SHIFT_ACTIONS:
            if isinstance(shift_id, bool) or not isinstance(shift_id, int) or shift_id <= 0:
                reasons.append("open_assigned_shift_required")
            else:
                row = connection.execute(
                    "SELECT status,cashier FROM main.shifts WHERE id=?", (shift_id,)
                ).fetchone()
                if row is None or row["status"] != "OPEN":
                    reasons.append("shift_not_open")
                elif actor is None or row["cashier"] != actor:
                    reasons.append("shift_actor_mismatch")
        return ServiceAuthorization(action, actor, role, tuple(reasons))

    def require(self, connection, *, action, identity=None, shift_id=None):
        """Fails closed even for a valid Admin and open shift."""
        decision = self.inspect(
            connection, action=action, identity=identity, shift_id=shift_id
        )
        raise PermissionError("; ".join(decision.reasons))
