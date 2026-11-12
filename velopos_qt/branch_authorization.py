"""Read-only, fail-closed branch-binding diagnostic for isolated V8 preview.

The branch registry and user/shift bindings are persisted in the disposable
VeloPOS8PreviewData SQLite database by test fixtures. This inspector NEVER
creates or edits those tables, changes V7 data, or authorizes a transaction.
It requires the caller's canonical preview connection inside a transaction.
A branch string supplied by a UI/client is not proof of branch membership.
All registry, membership and shift lookups bind main.*, not TEMP shadows.
"""
from dataclasses import dataclass
import sqlite3

from .idempotency_ledger import PreviewIdempotencyLedger
from .service_authorization import PreviewServiceAuthorization, _ACTION_ROLES, _SHIFT_ACTIONS


_TABLES = frozenset({
    "v8_preview_branch_registry",
    "v8_preview_branch_memberships",
    "v8_preview_branch_shifts",
})


@dataclass(frozen=True)
class PreviewBranchDecision:
    action: str
    branch_id: str | None
    actor: str | None
    reasons: tuple[str, ...]
    branch_verified: bool
    can_execute: bool = False


class PreviewBranchAuthorization:
    """Inspect canonical persisted branch/actor/shift bindings; never grant."""

    def __init__(self, database):
        self.database = database
        self._connection_gate = PreviewIdempotencyLedger(database)
        self._service = PreviewServiceAuthorization(database)

    def inspect(self, connection, *, action, identity=None, branch_id, shift_id=None):
        self._connection_gate._check_connection(connection)
        if action not in _ACTION_ROLES:
            raise ValueError("Unknown protected financial action")
        # Revalidate the signed-in identity against canonical persisted user
        # and shift state. A client-provided username is never trusted.
        service = self._service.inspect(
            connection, action=action, identity=identity, shift_id=shift_id
        )
        actor = service.actor
        # Persisted role and shift denials must also deny branch verification.
        reasons = [
            reason for reason in service.reasons
            if reason not in (
                "preview_transactions_disabled", "commercial_license_unverified"
            )
        ]
        valid_branch = (
            type(branch_id) is str
            and 1 <= len(branch_id) <= 120
            and all(c.isascii() and (c.isalnum() or c in "-_")
                    for c in branch_id)
        )
        if not valid_branch:
            reasons.append("canonical_branch_id_required")
        if not isinstance(actor, str) or not actor:
            reasons.append("verified_branch_actor_required")

        present = {
            row[0] for row in connection.execute(
                "SELECT name FROM main.sqlite_master WHERE type='table' "
                "AND name IN (?,?,?)", tuple(sorted(_TABLES))
            ).fetchall()
        }
        if present != _TABLES:
            reasons.append("canonical_branch_registry_missing")
            return PreviewBranchDecision(
                action, branch_id if valid_branch else None,
                actor if isinstance(actor, str) else None,
                tuple(reasons), False,
            )

        if valid_branch:
            try:
                branches = connection.execute(
                "SELECT active FROM main.v8_preview_branch_registry WHERE branch_id=?",
                (branch_id,),
                ).fetchall()
            except sqlite3.DatabaseError:
                branches = []
            if len(branches) != 1 or branches[0]["active"] != 1:
                reasons.append("branch_not_active")

        if valid_branch and isinstance(actor, str) and actor:
            try:
                memberships = connection.execute(
                "SELECT active FROM main.v8_preview_branch_memberships "
                "WHERE username=? AND branch_id=?",
                (actor, branch_id),
                ).fetchall()
            except sqlite3.DatabaseError:
                memberships = []
            if len(memberships) != 1 or memberships[0]["active"] != 1:
                reasons.append("actor_branch_membership_required")

        if action in _SHIFT_ACTIONS:
            if type(shift_id) is not int or shift_id <= 0:
                reasons.append("branch_shift_binding_required")
            else:
                try:
                    shifts = connection.execute(
                    "SELECT s.cashier, s.status, b.branch_id "
                    "FROM main.shifts AS s LEFT JOIN main.v8_preview_branch_shifts AS b "
                    "ON b.shift_id=s.id WHERE s.id=?",
                    (shift_id,),
                    ).fetchall()
                except sqlite3.DatabaseError:
                    shifts = []
                # Reject ambiguous duplicate shift bindings, even if one matches.
                if len(shifts) != 1 or shifts[0]["status"] != "OPEN":
                    reasons.append("branch_shift_not_open")
                else:
                    shift = shifts[0]
                    if not isinstance(actor, str) or shift["cashier"] != actor:
                        reasons.append("branch_shift_actor_mismatch")
                    if not valid_branch or shift["branch_id"] != branch_id:
                        reasons.append("shift_branch_mismatch")

        # Even an empty reasons tuple is ONLY a read-only diagnostic.
        return PreviewBranchDecision(
            action, branch_id if valid_branch else None,
            actor if isinstance(actor, str) else None,
            tuple(reasons), not reasons,
        )

    def require(self, connection, **kwargs):
        decision = self.inspect(connection, **kwargs)
        raise PermissionError("; ".join(
            (*decision.reasons, "preview_transactions_disabled")
        ))
