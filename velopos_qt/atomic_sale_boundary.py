"""Atomic sale readiness *diagnostic* for dedicated V8 TEST DATA ONLY.

This composes, within ONE caller-owned SQLite transaction:
  - current persisted cashier session and assigned open shift,
  - canonical branch registry and user/shift membership,
  - signed license and two signed server activation observations,
  - duplicate-line stock, expiry, signed-in actor and price preflight.

No financial service is invoked. There are no invoices, stock updates,
payments, idempotency reservations or online activation in this module.
Every self-owned transaction is rolled back, including successful checks.

IMPORTANT: policy_consistent / local_checks_consistent are diagnostic labels,
NOT authorization. A true value cannot turn on checkout; can_execute and
can_checkout are unconditionally False, and require() always rejects.
The trusted commercial server, idempotent write path, recovery from crashes,
tax and partial refund accounting remain missing (Gate A is BLOCKED).
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .checkout_preflight import PreviewCheckoutPreflight
from .combined_authorization import PreviewCombinedAuthorization
from .idempotency_ledger import PreviewIdempotencyLedger
from .product_editor import _guard


_EXPECTED_PREVIEW_BLOCKERS = frozenset({
    "preview_checkout_disabled",
    "idempotency_not_implemented",
    "license_not_verified",
})


@dataclass(frozen=True)
class AtomicSaleReadiness:
    """One-snapshot evidence, never a sale permission or license token."""
    reasons: tuple[str, ...]
    line_count: int
    subtotal: Decimal
    local_checks_consistent: bool
    session_bound: bool
    branch_verified: bool
    license_bound: bool
    signed_chain_valid: bool
    policy_consistent: bool
    can_execute: bool = False
    can_checkout: bool = False


class PreviewAtomicSaleBoundary:
    """One-transaction diagnostic using V8 isolated preview test storage."""

    def __init__(self, database, *, license_public_key_b64):
        _guard(database)
        self.database = database
        self.preflight = PreviewCheckoutPreflight(database)
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

    def inspect_in_transaction(
            self, connection, *, identity, shift_id, request_id, lines,
            expected_branch_id, license_id, machine_id, license_key,
            server_public_key_b64, previous_status, current_status,
            today=None, now=None, max_offline_hours=24):
        """Read one canonical SQLite snapshot; caller owns ALL transaction state.

        The caller must first BEGIN IMMEDIATE on the isolated preview DB.
        This method performs no write and never commits or rolls back.
        Rejects foreign connections and an absent transaction.
        """
        self._connection_gate._check_connection(connection)
        day = self._day(today)
        draft = self.preflight.inspect(
            connection=connection, identity=identity, shift_id=shift_id,
            request_id=request_id, lines=lines, today=day.isoformat(),
        )
        decision = self.authorization.inspect_with_activation_chain(
            connection, action="sale",
            expected_branch_id=expected_branch_id,
            license_id=license_id,
            server_public_key_b64=server_public_key_b64,
            previous_status=previous_status,
            current_status=current_status,
            identity=identity, shift_id=shift_id,
            license_key=license_key, machine_id=machine_id,
            today=day, now=now, max_offline_hours=max_offline_hours,
        )
        reasons = tuple(dict.fromkeys((
            *draft.reasons,
            *decision.authorization.session_reasons,
            *decision.authorization.license_reasons,
            *decision.branch_reasons,
            *decision.chain_reasons,
            "commercial_atomic_sale_unimplemented",
        )))
        local_ok = not set(draft.reasons).difference(_EXPECTED_PREVIEW_BLOCKERS)
        authorized = decision.authorization
        return AtomicSaleReadiness(
            reasons=reasons, line_count=draft.line_count,
            subtotal=draft.subtotal,
            local_checks_consistent=local_ok,
            session_bound=(
                authorized.actor is not None and
                "verified_session_required" not in authorized.session_reasons
            ),
            branch_verified=decision.branch_verified,
            license_bound=decision.identity_bound,
            signed_chain_valid=(
                decision.chain_signatures_valid and decision.chain_consistent
            ),
            policy_consistent=decision.policy_consistent,
        )

    def inspect(self, **kwargs):
        """Acquire an isolated BEGIN IMMEDIATE lock, diagnose, ALWAYS roll back."""
        _guard(self.database)
        conn = self.database.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            return self.inspect_in_transaction(conn, **kwargs)
        finally:
            # Deliberately no commit path; this cannot persist commerce.
            conn.rollback()
            conn.close()

    def require(self, **kwargs):
        """Mandatory-deny entry point, even with every diagnostic healthy."""
        result = self.inspect(**kwargs)
        raise PermissionError("; ".join(result.reasons))
