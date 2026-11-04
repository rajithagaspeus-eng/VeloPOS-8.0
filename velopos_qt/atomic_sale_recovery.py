"""Single-snapshot sale request recovery diagnostic (V8 TEST DATA ONLY).

Inspect a canonical sale draft alongside persisted cashier/shift/branch policy,
signed license + activation-chain diagnostics, and an immutable idempotency
journal observation under ONE caller-owned SQLite transaction. This is never
a commercial authorization or proof that a sale was posted.

Own-connection reads always BEGIN IMMEDIATE and ROLLBACK. Caller-owned reads
never commit, roll back or reserve a journal row. No V7 service is invoked.
"""
from dataclasses import dataclass

from .auth_model import PreviewIdentity
from .atomic_sale_boundary import PreviewAtomicSaleBoundary
from .idempotency_ledger import (
    PreviewIdempotencyLedger, RecoveryInspection,
)
from .product_editor import _guard
from .sale_plan import canonical_decimal, plan_preview_sale


def canonical_sale_recovery_payload(
        *, identity, shift_id, lines, expected_branch_id, license_id,
        machine_id, today=None):
    """Build *untrusted request identity* for preview journal comparison.

    These are claims bound into a fingerprint, not verified authorities.
    Any later change of branch, actor, shift, license, device or invoice draft
    must conflict when the same request id is reused. No tender is accepted.
    """
    day = PreviewAtomicSaleBoundary._day(today)
    plan = plan_preview_sale(lines)
    username = getattr(identity, "username", None)
    if type(username) is not str:
        username = None
    return {
        "v": 1, "action": "sale",
        "actor_hint": username,
        "branch_id": expected_branch_id,
        "license_id": license_id,
        "machine_id": machine_id,
        "shift_id": shift_id,
        "day": day.isoformat(),
        "lines": plan.request_items(),
    }


@dataclass(frozen=True)
class SaleRequestRecoveryReadiness:
    """One locked snapshot; NEVER a transaction capability or a receipt."""
    readiness: object
    journal: RecoveryInspection
    reasons: tuple[str, ...]
    can_execute: bool = False
    can_checkout: bool = False


class PreviewAtomicSaleRecovery:
    """Compose existing sale policy and journal triage without posting."""

    def __init__(self, database, *, license_public_key_b64):
        _guard(database)
        self.database = database
        self.boundary = PreviewAtomicSaleBoundary(
            database, license_public_key_b64=license_public_key_b64
        )
        self.journal = PreviewIdempotencyLedger(database)

    def inspect_in_transaction(self, connection, **sale_kwargs):
        """Observe current policy AND durable request state in one snapshot."""
        self.journal._check_connection(connection)
        # A generator can be consumed by the preflight, and a caller-owned
        # mutable list can change between preflight and journal hashing.
        # Freeze validated decimal values ONCE so both inspections see the
        # identical draft even if the caller mutates its original input.
        plan = plan_preview_sale(sale_kwargs["lines"])
        frozen_lines = tuple(
            {"barcode": line.barcode, "qty": canonical_decimal(line.qty),
             "price": canonical_decimal(line.price)}
            for line in plan.lines
        )
        # Resolve an omitted date once; midnight must not make the draft
        # preflight and the durable request identity disagree.
        frozen_day = PreviewAtomicSaleBoundary._day(
            sale_kwargs.get("today")
        ).isoformat()
        # Freeze the caller-provided (and potentially mutable) identity once.
        # Persisted user/role/password hash and the active HMAC session token
        # are STILL revalidated inside the same SQLite transaction. This
        # snapshot itself cannot grant permission or revive a revoked session.
        original_identity = sale_kwargs["identity"]
        frozen_identity = None
        if original_identity is not None:
            frozen_identity = PreviewIdentity(
                username=getattr(original_identity, "username", None),
                role=getattr(original_identity, "role", None),
                credential_tag=getattr(original_identity, "credential_tag", None),
            )
        stable_kwargs = dict(
            sale_kwargs, lines=frozen_lines, today=frozen_day,
            identity=frozen_identity,
        )
        readiness = self.boundary.inspect_in_transaction(
            connection, **stable_kwargs
        )
        payload = canonical_sale_recovery_payload(
            identity=stable_kwargs["identity"],
            shift_id=stable_kwargs["shift_id"],
            lines=stable_kwargs["lines"],
            expected_branch_id=stable_kwargs["expected_branch_id"],
            license_id=stable_kwargs["license_id"],
            machine_id=stable_kwargs["machine_id"],
            today=stable_kwargs.get("today"),
        )
        journal = self.journal.inspect_request(
            connection, "sale", sale_kwargs["request_id"], payload
        )
        reasons = tuple(dict.fromkeys((
            *readiness.reasons,
            *(() if journal.state == "not_recorded" else
              ("journal_" + journal.state,)),
            "sale_recovery_diagnostic_only",
        )))
        return SaleRequestRecoveryReadiness(readiness, journal, reasons)

    def inspect(self, **sale_kwargs):
        """Own the lock and always roll back, even when inspection raises."""
        _guard(self.database)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            return self.inspect_in_transaction(connection, **sale_kwargs)
        finally:
            connection.rollback()
            connection.close()

    def require(self, **sale_kwargs):
        """No preview journal or valid signature can grant checkout."""
        result = self.inspect(**sale_kwargs)
        raise PermissionError("; ".join(result.reasons))
