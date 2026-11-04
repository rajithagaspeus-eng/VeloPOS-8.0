"""Durable V8 SANDBOX ONLY invoice + stock ledger integration experiment.

This component writes exclusively to v8_preview_sandbox_* tables inside the
isolated VeloPOS8PreviewData test database and to the existing V8 TEST request
journal. It NEVER updates the legacy sales, sale_items, payments, shifts,
products, batches or stock_moves tables, and is NOT wired to any UI or checkout.

Preview-signed entitlement and activation-chain observations are not
server-authoritative commercial licensing. This simulation is NOT a sale,
payment, fiscal receipt, or permission to transact; Gate A/B remain BLOCKED.
"""
from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext
from hashlib import sha256

from .auth_model import PreviewIdentity
from .atomic_sale_boundary import PreviewAtomicSaleBoundary
from .atomic_sale_recovery import (
    PreviewAtomicSaleRecovery, canonical_sale_recovery_payload,
)
from .idempotency_ledger import PreviewIdempotencyLedger, request_fingerprint
from .product_editor import _guard
from .sale_plan import canonical_decimal, plan_preview_sale


_CONTEXT = Context(prec=512)


@dataclass(frozen=True)
class SandboxSaleEvidence:
    reference: str
    subtotal_cents: int
    items: int
    replayed: bool
    sandbox_persisted: bool = True
    actual_invoice_posted: bool = False
    payment_captured: bool = False
    can_checkout: bool = False
    can_execute: bool = False


class PreviewSandboxSaleLedger:
    """Own a single BEGIN IMMEDIATE transaction for sandbox-only posting."""

    _FAILPOINTS = frozenset({
        "after_claim", "after_stock", "after_invoice", "after_complete",
    })

    def __init__(self, database, *, license_public_key_b64):
        _guard(database)
        self.database = database
        self.recovery = PreviewAtomicSaleRecovery(
            database, license_public_key_b64=license_public_key_b64
        )
        self.journal = PreviewIdempotencyLedger(database)

    @staticmethod
    def _create_sandbox_tables(connection):
        connection.executescript if False else None  # Never executescript: it commits!
        connection.execute(
            "CREATE TABLE IF NOT EXISTS main.v8_preview_sandbox_stock ("
            "barcode TEXT PRIMARY KEY, opening_qty TEXT NOT NULL, "
            "remaining_qty TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS main.v8_preview_sandbox_sales ("
            "reference TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, "
            "actor TEXT NOT NULL, branch_id TEXT NOT NULL, shift_id INTEGER NOT NULL, "
            "subtotal_cents INTEGER NOT NULL CHECK(subtotal_cents >= 0))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS main.v8_preview_sandbox_sale_lines ("
            "reference TEXT NOT NULL, line_no INTEGER NOT NULL, "
            "barcode TEXT NOT NULL, quantity TEXT NOT NULL, "
            "price TEXT NOT NULL, line_cents INTEGER NOT NULL, "
            "PRIMARY KEY(reference,line_no))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS main.v8_preview_sandbox_stock_moves ("
            "reference TEXT NOT NULL, barcode TEXT NOT NULL, "
            "before_qty TEXT NOT NULL, sold_qty TEXT NOT NULL, "
            "after_qty TEXT NOT NULL, PRIMARY KEY(reference,barcode))"
        )

    @staticmethod
    def _read_exact_sale(connection, reference, request_id, plan):
        row = connection.execute(
            "SELECT request_id, subtotal_cents FROM main.v8_preview_sandbox_sales "
            "WHERE reference=?", (reference,)
        ).fetchone()
        if row is None or row["request_id"] != request_id:
            raise RuntimeError("Journal result has no matching sandbox sale")
        expected_cents = int(plan.subtotal * 100)
        if row["subtotal_cents"] != expected_cents:
            raise RuntimeError("Journal/sandbox invoice reconciliation failed")
        count = connection.execute(
            "SELECT COUNT(*) FROM main.v8_preview_sandbox_sale_lines "
            "WHERE reference=?", (reference,)
        ).fetchone()[0]
        if count != len(plan.lines):
            raise RuntimeError("Sandbox invoice line count mismatch")
        return SandboxSaleEvidence(reference, expected_cents, count, replayed=True)

    def simulate_commit(self, *, inject_failure_at=None, **sale_kwargs):
        """Commit a *disposable sandbox* sale/stock/journal together, never commerce.

        Signed, persisted session/branch/shift and stock/price/expiry checks
        execute under the very same SQLite lock. A completed request is
        reconciled against sandbox rows; a missing/corrupt/pending journal is
        never silently retried. The caller cannot supply a result reference.
        """
        if inject_failure_at is not None and inject_failure_at not in self._FAILPOINTS:
            raise ValueError("Unknown sandbox failure injection point")
        _guard(self.database)
        plan = plan_preview_sale(sale_kwargs["lines"])
        frozen_lines = tuple(
            {"barcode": line.barcode, "qty": canonical_decimal(line.qty),
             "price": canonical_decimal(line.price)}
            for line in plan.lines
        )
        actor = sale_kwargs["identity"]
        frozen_actor = (
            PreviewIdentity(
                getattr(actor, "username", None),
                getattr(actor, "role", None),
                getattr(actor, "credential_tag", None),
            ) if actor is not None else None
        )
        day = PreviewAtomicSaleBoundary._day(sale_kwargs.get("today")).isoformat()
        stable = dict(
            sale_kwargs, lines=frozen_lines, today=day, identity=frozen_actor
        )
        request_id = stable["request_id"]
        self.journal._validate_identity("sale", request_id)
        payload = canonical_sale_recovery_payload(
            identity=frozen_actor, shift_id=stable["shift_id"],
            lines=frozen_lines, expected_branch_id=stable["expected_branch_id"],
            license_id=stable["license_id"], machine_id=stable["machine_id"],
            today=day,
        )
        fingerprint = request_fingerprint(payload)
        reference = "SBX-" + sha256(
            (request_id + ":" + fingerprint).encode("utf-8")
        ).hexdigest()[:24]
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            checked = self.recovery.inspect_in_transaction(connection, **stable)
            readiness = checked.readiness
            healthy = (
                readiness.session_bound and readiness.branch_verified
                and readiness.license_bound and readiness.signed_chain_valid
                and readiness.local_checks_consistent
                and readiness.policy_consistent
            )
            if not healthy:
                raise PermissionError("Sandbox-only transaction checks denied")
            if checked.journal.state == "journal_completed_unverified":
                evidence = self._read_exact_sale(
                    connection, checked.journal.result_ref, request_id, plan
                )
                # No write on replay. A complete journal is not sufficient by
                # itself; only a matching sandbox sale can be returned.
                connection.rollback()
                return evidence
            if checked.journal.state != "not_recorded":
                raise PermissionError("Sandbox journal requires manual reconciliation")

            self._create_sandbox_tables(connection)
            claim = self.journal.claim(connection, "sale", request_id, payload)
            if not claim.is_new:
                raise RuntimeError("Unexpected claimed sandbox request")
            if inject_failure_at == "after_claim":
                raise RuntimeError("Injected sandbox failure after claim")

            # Original product stock is a READ-ONLY opening snapshot. Subsequent
            # sandbox requests deduct only from the sandbox stock table.
            with localcontext(_CONTEXT):
                for barcode, sold in plan.quantities:
                    row = connection.execute(
                        "SELECT remaining_qty FROM main.v8_preview_sandbox_stock "
                        "WHERE barcode=?", (barcode,)
                    ).fetchone()
                    if row is None:
                        original = connection.execute(
                            "SELECT stock_qty FROM main.products WHERE barcode=?",
                            (barcode,)
                        ).fetchone()
                        if original is None:
                            raise PermissionError("Sandbox product no longer exists")
                        opening = Decimal(str(original["stock_qty"]))
                        if not opening.is_finite() or opening < 0:
                            raise PermissionError("Invalid sandbox opening quantity")
                        opening_text = canonical_decimal(opening)
                        connection.execute(
                            "INSERT INTO main.v8_preview_sandbox_stock "
                            "(barcode,opening_qty,remaining_qty) VALUES (?,?,?)",
                            (barcode,opening_text,opening_text)
                        )
                        remaining = opening
                    else:
                        remaining = Decimal(row["remaining_qty"])
                    if sold > remaining:
                        raise PermissionError("Sandbox available stock insufficient")
                    after = remaining - sold
                    connection.execute(
                        "UPDATE main.v8_preview_sandbox_stock SET remaining_qty=? "
                        "WHERE barcode=?", (canonical_decimal(after), barcode)
                    )
                    connection.execute(
                        "INSERT INTO main.v8_preview_sandbox_stock_moves "
                        "(reference,barcode,before_qty,sold_qty,after_qty) "
                        "VALUES (?,?,?,?,?)",
                        (reference,barcode,canonical_decimal(remaining),
                         canonical_decimal(sold),canonical_decimal(after))
                    )
            if inject_failure_at == "after_stock":
                raise RuntimeError("Injected sandbox failure after stock")

            cents = int(plan.subtotal * 100)
            connection.execute(
                "INSERT INTO main.v8_preview_sandbox_sales "
                "(reference,request_id,actor,branch_id,shift_id,subtotal_cents) "
                "VALUES (?,?,?,?,?,?)",
                (reference,request_id,frozen_actor.username,
                 stable["expected_branch_id"],stable["shift_id"],cents)
            )
            for n, line in enumerate(plan.lines, 1):
                connection.execute(
                    "INSERT INTO main.v8_preview_sandbox_sale_lines "
                    "(reference,line_no,barcode,quantity,price,line_cents) "
                    "VALUES (?,?,?,?,?,?)",
                    (reference,n,line.barcode,canonical_decimal(line.qty),
                     canonical_decimal(line.price),int(line.line_total * 100))
                )
            if inject_failure_at == "after_invoice":
                raise RuntimeError("Injected sandbox failure after invoice")
            self.journal.complete(connection, "sale", request_id, reference)
            if inject_failure_at == "after_complete":
                raise RuntimeError("Injected sandbox failure after complete")
            connection.commit()
            return SandboxSaleEvidence(reference,cents,len(plan.lines),replayed=False)
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def require_commercial_sale(self, **_kwargs):
        raise PermissionError("Sandbox-only; V8 commercial checkout is disabled")
