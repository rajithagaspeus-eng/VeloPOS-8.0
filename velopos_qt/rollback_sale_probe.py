"""Service-owned, rollback-only sale journal probe for V8 PREVIEW TEST DATA.

This is a fail-closed laboratory primitive, NOT a checkout service. It never
touches V7 transaction services, invoices, payments, stock or shifts. It owns
BEGIN IMMEDIATE, revalidates the saved actor/branch/shift and signed entitlement
diagnostics inside that lock, stages a journal claim/completion/replay, and
ALWAYS rolls back the transaction (including on success or injected failure).

A healthy preview diagnosis does not imply Gate A/B readiness. Callers cannot
request an actual commit, supply a result reference or inject arbitrary writes.
"""
from dataclasses import dataclass
from hashlib import sha256

from .atomic_sale_boundary import PreviewAtomicSaleBoundary
from .atomic_sale_recovery import (
    PreviewAtomicSaleRecovery, canonical_sale_recovery_payload,
)
from .auth_model import PreviewIdentity
from .idempotency_ledger import PreviewIdempotencyLedger, request_fingerprint
from .product_editor import _guard
from .sale_plan import canonical_decimal, plan_preview_sale


@dataclass(frozen=True)
class PreviewRollbackSaleEvidence:
    """Never a token, invoice, receipt, posting permission or durable result."""
    simulated_result_ref: str
    stage: str = "journal_only_rolled_back"
    journal_replayed_in_transaction: bool = True
    persisted: bool = False
    can_execute: bool = False
    can_checkout: bool = False


class PreviewRollbackOnlySaleProbe:
    """A service-owned single SQLite transaction that cannot commit."""

    _FAILPOINTS = frozenset({
        "after_claim", "after_complete", "after_replay",
    })

    def __init__(self, database, *, license_public_key_b64):
        _guard(database)
        self.database = database
        self.recovery = PreviewAtomicSaleRecovery(
            database, license_public_key_b64=license_public_key_b64
        )
        self.journal = PreviewIdempotencyLedger(database)

    def simulate(self, *, inject_failure_at=None, **sale_kwargs):
        """Exercise signed/persisted checks and staged journal under one lock.

        Even an apparently valid state returns ONLY the fact that a synthetic
        journal cycle was rolled back. This never attempts any financial write.
        Old completed or pending claims require reconciliation, not replay.
        """
        if inject_failure_at is not None and inject_failure_at not in self._FAILPOINTS:
            raise ValueError("Unknown preview failure injection point")
        _guard(self.database)
        # Capture caller-owned mutable data once, before any authorization
        # and journal checks. A one-shot lines generator must not be read twice.
        plan = plan_preview_sale(sale_kwargs["lines"])
        stable_lines = tuple(
            {"barcode": line.barcode,
             "qty": canonical_decimal(line.qty),
             "price": canonical_decimal(line.price)}
            for line in plan.lines
        )
        day = PreviewAtomicSaleBoundary._day(sale_kwargs.get("today")).isoformat()
        identity = sale_kwargs["identity"]
        frozen_identity = (
            PreviewIdentity(
                username=getattr(identity, "username", None),
                role=getattr(identity, "role", None),
                credential_tag=getattr(identity, "credential_tag", None),
            ) if identity is not None else None
        )
        stable = dict(
            sale_kwargs, lines=stable_lines, today=day, identity=frozen_identity,
        )
        payload = canonical_sale_recovery_payload(
            identity=frozen_identity, shift_id=stable["shift_id"],
            lines=stable_lines, expected_branch_id=stable["expected_branch_id"],
            license_id=stable["license_id"], machine_id=stable["machine_id"],
            today=day,
        )
        # Fully materialize immutable request identity before opening a write
        # transaction; no invalid hashable values reach the journal.
        digest = request_fingerprint(payload)
        request_id = stable["request_id"]
        self.journal._validate_identity("sale", request_id)
        simulated_ref = "SIM-" + sha256(
            (request_id + ":" + digest).encode("utf-8")
        ).hexdigest()[:24]

        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            checked = self.recovery.inspect_in_transaction(connection, **stable)
            # Never treat preview-only can_checkout as true. The explicit
            # local policy evidence is used solely for a rollback rehearsal.
            healthy = (
                checked.readiness.session_bound
                and checked.readiness.branch_verified
                and checked.readiness.license_bound
                and checked.readiness.signed_chain_valid
                and checked.readiness.local_checks_consistent
                and checked.readiness.policy_consistent
            )
            if not healthy or checked.journal.state != "not_recorded":
                raise PermissionError("Rollback sale probe denied; check authorization or reconcile journal")
            claim = self.journal.claim(connection, "sale", request_id, payload)
            if not claim.is_new:
                raise RuntimeError("Unexpected previously completed preview claim")
            if inject_failure_at == "after_claim":
                raise RuntimeError("Injected failure after journal claim")
            self.journal.complete(connection, "sale", request_id, simulated_ref)
            if inject_failure_at == "after_complete":
                raise RuntimeError("Injected failure after journal completion")
            replay = self.journal.claim(connection, "sale", request_id, payload)
            if replay.is_new or replay.result_ref != simulated_ref:
                raise RuntimeError("Preview journal replay integrity mismatch")
            if inject_failure_at == "after_replay":
                raise RuntimeError("Injected failure after replay")
            return PreviewRollbackSaleEvidence(simulated_result_ref=simulated_ref)
        finally:
            # No code path, successful or failed, may commit any journal entry.
            connection.rollback()
            connection.close()

    def require(self, **_kwargs):
        """Hard commercial denial: a dry run is never permission to sell."""
        raise PermissionError("V8 preview transaction posting remains disabled")
