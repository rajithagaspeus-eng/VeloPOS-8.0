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
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from hashlib import sha256
import re

from .auth_model import PreviewIdentity
from .atomic_sale_boundary import PreviewAtomicSaleBoundary
from .atomic_sale_recovery import (
    PreviewAtomicSaleRecovery, canonical_sale_recovery_payload,
)
from .idempotency_ledger import PreviewIdempotencyLedger, request_fingerprint
from .product_editor import _guard
from .sale_plan import canonical_decimal, plan_preview_sale
from .tender_plan import plan_preview_tender


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
    tender_declared: bool = False
    change_cents: int = 0


@dataclass(frozen=True)
class SandboxReconciliation:
    balanced: bool
    reasons: tuple[str, ...]
    invoice_count: int
    subtotal_cents: int
    can_checkout: bool = False


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
        # Never use executescript here: SQLite implicitly commits before it.
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
        connection.execute(
            "CREATE TABLE IF NOT EXISTS main.v8_preview_sandbox_tenders ("
            "reference TEXT NOT NULL, line_no INTEGER NOT NULL, "
            "method TEXT NOT NULL, amount_cents INTEGER NOT NULL "
            "CHECK(amount_cents>0), reference_hint TEXT NOT NULL, "
            "PRIMARY KEY(reference,line_no))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS main.v8_preview_sandbox_settlements ("
            "reference TEXT PRIMARY KEY, declared INTEGER NOT NULL "
            "CHECK(declared IN (0,1)), due_cents INTEGER NOT NULL, "
            "cash_cents INTEGER NOT NULL, noncash_cents INTEGER NOT NULL, "
            "change_cents INTEGER NOT NULL)"
        )

    @staticmethod
    def _read_exact_sale(connection, reference, request_id, plan, tender_plan,
                         expected_actor, expected_branch, expected_shift):
        row = connection.execute(
            "SELECT request_id,actor,branch_id,shift_id,subtotal_cents "
            "FROM main.v8_preview_sandbox_sales "
            "WHERE reference=?", (reference,)
        ).fetchone()
        if row is None or row["request_id"] != request_id:
            raise RuntimeError("Journal result has no matching sandbox sale")
        if (row["actor"] != expected_actor
                or row["branch_id"] != expected_branch
                or type(row["shift_id"]) is not int
                or row["shift_id"] != expected_shift):
            raise RuntimeError("Sandbox invoice identity does not match replay")
        expected_cents = int(plan.subtotal * 100)
        if row["subtotal_cents"] != expected_cents:
            raise RuntimeError("Journal/sandbox invoice reconciliation failed")
        # Replays must verify the actual immutable lines, not merely their
        # count and invoice subtotal: equal-total substitutions are possible.
        recorded_lines = [
            (row["line_no"], row["barcode"], row["quantity"], row["price"], row["line_cents"])
            for row in connection.execute(
                "SELECT line_no,barcode,quantity,price,line_cents FROM "
                "main.v8_preview_sandbox_sale_lines WHERE reference=? "
                "ORDER BY line_no", (reference,)
            )
        ]
        expected_lines = [
            (n, line.barcode, canonical_decimal(line.qty),
             canonical_decimal(line.price), int(line.line_total * 100))
            for n, line in enumerate(plan.lines, 1)
        ]
        if recorded_lines != expected_lines:
            raise RuntimeError("Sandbox invoice lines do not match replay")
        count = len(recorded_lines)
        recorded_moves = {
            row["barcode"]: row
            for row in connection.execute(
                "SELECT barcode,before_qty,sold_qty,after_qty "
                "FROM main.v8_preview_sandbox_stock_moves "
                "WHERE reference=?", (reference,)
            )
        }
        expected_moves = {
            barcode: canonical_decimal(qty) for barcode, qty in plan.quantities
        }
        if set(recorded_moves) != set(expected_moves):
            raise RuntimeError("Sandbox stock movements do not match replay")
        with localcontext(_CONTEXT):
            for barcode, expected_qty in expected_moves.items():
                move = recorded_moves[barcode]
                try:
                    raw_values = (
                        move["before_qty"], move["sold_qty"],
                        move["after_qty"],
                    )
                    if any(
                        type(value) is not str or len(value) > 128
                        for value in raw_values
                    ):
                        raise ValueError("Invalid replay stock decimal encoding")
                    before, sold, after = map(Decimal, raw_values)
                    if any(
                        value.is_finite() and value != 0
                        and not -18 <= value.adjusted() <= 18
                        for value in (before, sold, after)
                    ):
                        raise ValueError("Invalid replay stock decimal exponent")
                except (InvalidOperation, TypeError, ValueError) as exc:
                    raise RuntimeError("Invalid sandbox stock movement") from exc
                if (not all(v.is_finite() for v in (before, sold, after))
                        or before < 0 or sold <= 0 or after < 0
                        or sold != Decimal(expected_qty)
                        or before - sold != after
                        or any(
                            raw != canonical_decimal(value)
                            for raw, value in zip(raw_values, (before, sold, after))
                        )):
                    raise RuntimeError("Sandbox stock movements do not match replay")
        # An older sandbox database may predate tender tables. Never
        # silently treat its completed journal as a settled invoice.
        required = {"v8_preview_sandbox_settlements",
                    "v8_preview_sandbox_tenders"}
        present = {
            row[0] for row in connection.execute(
                "SELECT name FROM main.sqlite_master WHERE type='table' "
                "AND name IN (?,?)", tuple(sorted(required))
            )
        }
        if present != required:
            raise RuntimeError("Sandbox tender schema needs manual reconciliation")
        settlement = connection.execute(
            "SELECT declared,due_cents,cash_cents,noncash_cents,change_cents "
            "FROM main.v8_preview_sandbox_settlements WHERE reference=?",
            (reference,)
        ).fetchone()
        if settlement is None or settlement["due_cents"] != expected_cents:
            raise RuntimeError("Sandbox settlement reconciliation failed")
        declared = tender_plan is not None
        if settlement["declared"] != int(declared):
            raise RuntimeError("Sandbox settlement declaration mismatch")
        expected_tenders = (
            [(n, line.method, int(line.amount * 100), line.reference)
             for n, line in enumerate(tender_plan.tenders, 1)] if declared else []
        )
        recorded = [
            (row["line_no"], row["method"], row["amount_cents"], row["reference_hint"])
            for row in connection.execute(
                "SELECT line_no,method,amount_cents,reference_hint "
                "FROM main.v8_preview_sandbox_tenders "
                "WHERE reference=? ORDER BY line_no", (reference,)
            )
        ]
        if recorded != expected_tenders:
            raise RuntimeError("Sandbox declared tender mismatch")
        if (settlement["cash_cents"] != (
                int(tender_plan.cash_total * 100) if declared else 0)
                or settlement["noncash_cents"] != (
                    int(tender_plan.noncash_total * 100) if declared else 0)
                or settlement["change_cents"] != (
                    int(tender_plan.change_due * 100) if declared else 0)):
            raise RuntimeError("Sandbox settlement totals mismatch")
        return SandboxSaleEvidence(
            reference, expected_cents, count, replayed=True,
            tender_declared=declared,
            change_cents=settlement["change_cents"],
        )

    def simulate_commit(self, *, inject_failure_at=None, tenders=None, **sale_kwargs):
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
        # Declare allocation only. No card processor, customer credit ledger
        # or payment capture exists here; credit cannot be simulated safely.
        # Credit must be rejected explicitly: there is no verified
        # customer balance/limit ledger in this disposable sandbox yet.
        if tenders is not None and isinstance(tenders, (list, tuple)):
            if any(isinstance(row, dict) and row.get("method") == "Credit"
                   for row in tenders):
                raise PermissionError("Sandbox credit requires an audited customer ledger")
        tender_plan = (
            plan_preview_tender(plan.subtotal, tenders)
            if tenders is not None else None
        )
        if tender_plan is not None and tender_plan.credit_due:
            raise PermissionError("Sandbox credit requires an audited customer ledger")
        payload = canonical_sale_recovery_payload(
            identity=frozen_actor, shift_id=stable["shift_id"],
            lines=frozen_lines, expected_branch_id=stable["expected_branch_id"],
            license_id=stable["license_id"], machine_id=stable["machine_id"],
            today=day,
        )
        if tender_plan is not None:
            payload["sandbox_tender_declarations"] = [
                {"method": line.method, "amount_cents": int(line.amount * 100),
                 "reference": line.reference}
                for line in tender_plan.tenders
            ]
            payload["sandbox_change_cents"] = int(tender_plan.change_due * 100)
        fingerprint = request_fingerprint(payload)
        reference = "SBX-" + sha256(
            (request_id + ":" + fingerprint).encode("utf-8")
        ).hexdigest()[:24]
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            # The recovery diagnostic hashes sale-only inputs. For this
            # richer sandbox tender payload, authorize through its identical
            # locked boundary but inspect the journal with the FULL payload.
            readiness = self.recovery.boundary.inspect_in_transaction(
                connection, **stable
            )
            healthy = (
                readiness.session_bound and readiness.branch_verified
                and readiness.license_bound and readiness.signed_chain_valid
                and readiness.local_checks_consistent
                and readiness.policy_consistent
            )
            if not healthy:
                raise PermissionError("Sandbox-only transaction checks denied")
            journal = self.journal.inspect_request(
                connection, "sale", request_id, payload
            )
            if journal.state == "journal_completed_unverified":
                evidence = self._read_exact_sale(
                    connection, journal.result_ref, request_id,
                    plan, tender_plan, frozen_actor.username,
                    stable["expected_branch_id"], stable["shift_id"]
                )
                # No write on replay. A complete journal is not sufficient by
                # itself; only a matching sandbox sale can be returned.
                connection.rollback()
                return evidence
            if journal.state != "not_recorded":
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
            declaration = tender_plan is not None
            cash_cents = int(tender_plan.cash_total * 100) if declaration else 0
            noncash_cents = (
                int(tender_plan.noncash_total * 100) if declaration else 0
            )
            change_cents = (
                int(tender_plan.change_due * 100) if declaration else 0
            )
            connection.execute(
                "INSERT INTO main.v8_preview_sandbox_settlements "
                "(reference,declared,due_cents,cash_cents,noncash_cents,"
                "change_cents) VALUES (?,?,?,?,?,?)",
                (reference,int(declaration),cents,cash_cents,
                 noncash_cents,change_cents)
            )
            if declaration:
                for n, line in enumerate(tender_plan.tenders, 1):
                    connection.execute(
                        "INSERT INTO main.v8_preview_sandbox_tenders "
                        "(reference,line_no,method,amount_cents,reference_hint) "
                        "VALUES (?,?,?,?,?)",
                        (reference,n,line.method,int(line.amount*100),
                         line.reference)
                    )
            self.journal.complete(connection, "sale", request_id, reference)
            if inject_failure_at == "after_complete":
                raise RuntimeError("Injected sandbox failure after complete")
            connection.commit()
            return SandboxSaleEvidence(
                reference,cents,len(plan.lines),replayed=False,
                tender_declared=declaration,change_cents=change_cents
            )
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def reconcile_sandbox(self):
        """Independently audit sandbox invoice totals, stock and journal links.

        This is a read-only evidence check. It does not repair missing rows
        or modify V7 products, sales or real payment records.
        """
        _guard(self.database)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            required = (
                "v8_preview_sandbox_sales",
                "v8_preview_sandbox_sale_lines",
                "v8_preview_sandbox_stock",
                "v8_preview_sandbox_stock_moves",
                "v8_preview_request_journal",
                "v8_preview_sandbox_tenders",
                "v8_preview_sandbox_settlements",
            )
            found = {
                row[0] for row in connection.execute(
                    "SELECT name FROM main.sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if not set(required).issubset(found):
                return SandboxReconciliation(False, ("sandbox_tables_missing",), 0, 0)

            reasons = []
            invoices = connection.execute(
                "SELECT reference,request_id,actor,branch_id,shift_id,subtotal_cents "
                "FROM main.v8_preview_sandbox_sales ORDER BY reference"
            ).fetchall()
            all_lines = connection.execute(
                "SELECT reference,line_no,barcode,quantity,price,line_cents "
                "FROM main.v8_preview_sandbox_sale_lines "
                "ORDER BY reference,line_no"
            ).fetchall()
            expected_lines = {}
            line_numbers = {}
            invoice_refs_seen = {sale["reference"] for sale in invoices}
            line_quantities = {}
            with localcontext(_CONTEXT):
                for line in all_lines:
                    line_numbers.setdefault(line["reference"], []).append(
                        line["line_no"]
                    )
                    if line["reference"] not in invoice_refs_seen:
                        reasons.append("orphan_invoice_line")
                    if (type(line["line_cents"]) is not int
                            or line["line_cents"] < 0):
                        reasons.append("invalid_invoice_line_amount")
                    else:
                        expected_lines[line["reference"]] = (
                            expected_lines.get(line["reference"], 0)
                            + line["line_cents"]
                        )
                    barcode = line["barcode"]
                    if (type(barcode) is not str or not 1 <= len(barcode) <= 80
                            or barcode != barcode.strip()
                            or not barcode.isprintable()):
                        reasons.append("invalid_invoice_line_barcode")
                    key = (line["reference"], barcode)
                    try:
                        raw_qty = line["quantity"]
                        if type(raw_qty) is not str or len(raw_qty) > 128:
                            raise ValueError("invalid quantity encoding")
                        qty = Decimal(raw_qty)
                        if (not qty.is_finite() or qty <= 0
                                or qty > Decimal("1000000")
                                or qty.adjusted() < -18):
                            raise ValueError("invalid quantity")
                    except (InvalidOperation, TypeError, ValueError):
                        reasons.append("invalid_invoice_line_quantity")
                        continue
                    if raw_qty != canonical_decimal(qty):
                        reasons.append("noncanonical_invoice_line_quantity")
                    line_quantities[key] = (
                        line_quantities.get(key, Decimal("0")) + qty
                    )
                    # Recompute each persisted line from its immutable draft
                    # price. Equal-total price/amount substitutions must not
                    # pass an independent invoice subtotal audit.
                    try:
                        raw_price = line["price"]
                        if type(raw_price) is not str or len(raw_price) > 128:
                            raise ValueError("Invalid sandbox price encoding")
                        price = Decimal(raw_price)
                        if (not price.is_finite() or price < 0
                                or price > Decimal("100000000")
                                or (price != 0 and price.adjusted() < -18)):
                            raise ValueError("Invalid sandbox line price/quantity")
                        if raw_price != canonical_decimal(price):
                            reasons.append("noncanonical_invoice_line_price")
                        with localcontext(Context(prec=512, rounding=ROUND_HALF_UP)):
                            expected_cents = int(
                                (qty * price).quantize(Decimal("0.01")) * 100
                            )
                        if expected_cents != line["line_cents"]:
                            reasons.append("invoice_line_arithmetic_mismatch")
                    except (InvalidOperation, TypeError, ValueError, OverflowError):
                        reasons.append("invalid_invoice_line_price")
            invoice_refs = {sale["reference"] for sale in invoices}
            # A completed sale journal without its durable sandbox invoice is
            # a broken exactly-once record, even if no invoice row remains.
            completed_journals = connection.execute(
                "SELECT request_id,result_ref FROM main.v8_preview_request_journal "
                "WHERE scope='sale' AND status='COMPLETED'"
            ).fetchall()
            if any(row["result_ref"] not in invoice_refs
                   for row in completed_journals):
                reasons.append("orphan_completed_sale_journal")
            # The journal must be a one-to-one mapping to committed invoices.
            # A forged second completed request pointing to an existing
            # invoice must not pass merely because its result_ref exists.
            completed_pairs = {
                (row["request_id"], row["result_ref"])
                for row in completed_journals
            }
            invoice_pairs = {
                (sale["request_id"], sale["reference"]) for sale in invoices
            }
            if (completed_pairs != invoice_pairs
                    or len(completed_journals) != len(invoices)):
                reasons.append("completed_sale_journal_coverage_mismatch")
            # Atomic sandbox posting cannot legitimately leave a PENDING
            # sale request after commit. Never treat it as a fresh request.
            pending = connection.execute(
                "SELECT 1 FROM main.v8_preview_request_journal "
                "WHERE scope='sale' AND status='PENDING' LIMIT 1"
            ).fetchone()
            if pending is not None:
                reasons.append("pending_sale_journal_requires_reconciliation")
            for ref, numbers in line_numbers.items():
                if any(type(number) is not int or number <= 0 for number in numbers):
                    reasons.append("invalid_invoice_line_number:" + ref)
                if len(numbers) > 100:
                    reasons.append("invoice_line_count_exceeded:" + ref)
                if numbers != list(range(1, len(numbers) + 1)):
                    reasons.append("invoice_line_sequence_mismatch:" + ref)
            for sale in invoices:
                ref = sale["reference"]
                if (type(ref) is not str or not ref.startswith("SBX-")
                        or len(ref) != 28
                        or any(char not in "0123456789abcdef" for char in ref[4:])):
                    reasons.append("invalid_sandbox_invoice_reference")
                if (type(sale["request_id"]) is not str
                        or re.fullmatch(
                            r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}",
                            sale["request_id"],
                        ) is None):
                    reasons.append("invalid_sandbox_invoice_request_id")
                if (type(sale["actor"]) is not str
                        or not sale["actor"].strip()
                        or sale["actor"] != sale["actor"].strip()
                        or len(sale["actor"]) > 128
                        or not sale["actor"].isprintable()):
                    reasons.append("invalid_sandbox_invoice_actor:" + ref)
                if (type(sale["branch_id"]) is not str
                        or not sale["branch_id"].strip()
                        or sale["branch_id"] != sale["branch_id"].strip()
                        or len(sale["branch_id"]) > 128
                        or not sale["branch_id"].isprintable()):
                    reasons.append("invalid_sandbox_invoice_branch:" + ref)
                if (type(sale["shift_id"]) is not int
                        or sale["shift_id"] <= 0):
                    reasons.append("invalid_sandbox_invoice_shift:" + ref)
                if (type(sale["subtotal_cents"]) is not int
                        or sale["subtotal_cents"] < 0):
                    reasons.append("invalid_invoice_subtotal:" + ref)
                if ref not in line_numbers:
                    reasons.append("invoice_has_no_lines:" + ref)
                if expected_lines.get(ref) != sale["subtotal_cents"]:
                    reasons.append("invoice_line_total_mismatch:" + ref)
                journal = connection.execute(
                    "SELECT status,result_ref FROM main.v8_preview_request_journal "
                    "WHERE scope='sale' AND request_id=?",
                    (sale["request_id"],)
                ).fetchone()
                if (journal is None or journal["status"] != "COMPLETED"
                        or journal["result_ref"] != ref):
                    reasons.append("invoice_journal_mismatch:" + ref)

            # Every persisted sandbox invoice must have exactly one
            # allocation record. A declared tender is a TEST declaration
            # only, NEVER evidence that funds were captured.
            all_tenders = connection.execute(
                "SELECT reference,line_no,method,amount_cents,reference_hint "
                "FROM main.v8_preview_sandbox_tenders ORDER BY reference,line_no"
            ).fetchall()
            tender_by_ref = {}
            for row in all_tenders:
                tender_by_ref.setdefault(row["reference"], []).append(row)
                if row["reference"] not in invoice_refs:
                    reasons.append("orphan_tender_allocation")
                if (row["method"] not in ("Cash","Card","QR")
                        or type(row["amount_cents"]) is not int
                        or row["amount_cents"] <= 0):
                    reasons.append("invalid_tender_declaration")
                if type(row["line_no"]) is not int or row["line_no"] <= 0:
                    reasons.append("invalid_tender_line_number")
                hint = row["reference_hint"]
                if (type(hint) is not str or len(hint) > 80
                        or hint != hint.strip()
                        or any(ord(char) < 32 or ord(char) == 127
                               for char in hint)
                        or (row["method"] in ("Card", "QR") and len(hint) < 4)
                        or (row["method"] == "Cash" and hint)):
                    reasons.append("invalid_tender_reference")
            settlements = connection.execute(
                "SELECT reference,declared,due_cents,cash_cents,noncash_cents,"
                "change_cents FROM main.v8_preview_sandbox_settlements"
            ).fetchall()
            settlement_by_ref = {row["reference"]: row for row in settlements}
            if len(settlement_by_ref) != len(settlements):
                reasons.append("duplicate_settlement_record")
            if set(settlement_by_ref) != invoice_refs:
                reasons.append("settlement_coverage_mismatch")
            for sale in invoices:
                ref = sale["reference"]
                settled = settlement_by_ref.get(ref)
                if settled is None:
                    continue
                if settled["due_cents"] != sale["subtotal_cents"]:
                    reasons.append("settlement_invoice_mismatch:" + ref)
                tenders = tender_by_ref.get(ref, ())
                if len(tenders) > 10:
                    reasons.append("settlement_tender_count_exceeded:" + ref)
                if [row["line_no"] for row in tenders] != list(range(1, len(tenders) + 1)):
                    reasons.append("settlement_tender_line_sequence_mismatch:" + ref)
                declared = settled["declared"]
                if any(
                    type(settled[field]) is not int or settled[field] < 0
                    for field in ("due_cents", "cash_cents",
                                  "noncash_cents", "change_cents")
                ):
                    reasons.append("invalid_settlement_amount:" + ref)
                if declared not in (0,1) or bool(tenders) != bool(declared):
                    reasons.append("settlement_declaration_mismatch:" + ref)
                # Do not classify an unknown method as a legitimate
                # noncash payment. Invalid stored cents must fail closed
                # without raising TypeError during aggregation.
                valid_tenders = [
                    row for row in tenders
                    if type(row["amount_cents"]) is int
                    and row["amount_cents"] > 0
                    and row["method"] in ("Cash", "Card", "QR")
                ]
                cash = sum(
                    row["amount_cents"] for row in valid_tenders
                    if row["method"] == "Cash"
                )
                noncash = sum(
                    row["amount_cents"] for row in valid_tenders
                    if row["method"] in ("Card", "QR")
                )
                if (cash != settled["cash_cents"] or
                        noncash != settled["noncash_cents"]):
                    reasons.append("settlement_tender_total_mismatch:" + ref)
                subtotal = sale["subtotal_cents"]
                if type(subtotal) is not int or subtotal < 0:
                    # The invoice has already been marked invalid above.
                    # Do not subtract a corrupted SQLite TEXT/BLOB value.
                    reasons.append("settlement_invoice_amount_invalid:" + ref)
                    continue
                change = cash + noncash - subtotal
                if declared:
                    if (change < 0 or change > cash or
                            change != settled["change_cents"] or
                            noncash > sale["subtotal_cents"]):
                        reasons.append("settlement_allocation_mismatch:" + ref)
                elif any(
                    settled[field] != 0 for field in (
                        "cash_cents", "noncash_cents", "change_cents"
                    )
                ):
                    reasons.append("unallocated_settlement_nonzero:" + ref)

            stock_rows = connection.execute(
                "SELECT barcode,opening_qty,remaining_qty "
                "FROM main.v8_preview_sandbox_stock"
            ).fetchall()
            moves = connection.execute(
                "SELECT reference,barcode,before_qty,sold_qty,after_qty "
                "FROM main.v8_preview_sandbox_stock_moves ORDER BY rowid"
            ).fetchall()
            moves_by_barcode = {}
            movement_keys = set()
            for move in moves:
                moves_by_barcode.setdefault(move["barcode"], []).append(move)
                key = (move["reference"], move["barcode"])
                movement_keys.add(key)
                if move["reference"] not in invoice_refs:
                    reasons.append("orphan_stock_move")
                if (type(move["reference"]) is not str
                        or not move["reference"].startswith("SBX-")
                        or len(move["reference"]) != 28
                        or any(
                            char not in "0123456789abcdef"
                            for char in move["reference"][4:]
                        )):
                    reasons.append("invalid_stock_move_reference")
                move_barcode = move["barcode"]
                if (type(move_barcode) is not str
                        or not 1 <= len(move_barcode) <= 80
                        or move_barcode != move_barcode.strip()
                        or not move_barcode.isprintable()):
                    reasons.append("invalid_stock_move_barcode")
                try:
                    raw_sold = move["sold_qty"]
                    if type(raw_sold) is not str or len(raw_sold) > 128:
                        raise ValueError("invalid stock movement encoding")
                    sold_qty = Decimal(raw_sold)
                    if (not sold_qty.is_finite() or sold_qty <= 0
                            or sold_qty > Decimal("100000000")
                            or sold_qty.adjusted() < -18):
                        raise ValueError("invalid stock movement")
                except (InvalidOperation, TypeError, ValueError):
                    reasons.append("invalid_stock_move_quantity")
                    continue
                if sold_qty != line_quantities.get(key):
                    reasons.append("stock_line_quantity_mismatch")
            if set(line_quantities) != movement_keys:
                reasons.append("stock_line_coverage_mismatch")
            listed = {row["barcode"] for row in stock_rows}
            if set(moves_by_barcode) - listed:
                reasons.append("untracked_stock_move")
            with localcontext(_CONTEXT):
                for row in stock_rows:
                    barcode = row["barcode"]
                    if (type(barcode) is not str
                            or not 1 <= len(barcode) <= 80
                            or barcode != barcode.strip()
                            or not barcode.isprintable()):
                        reasons.append("invalid_stock_barcode")
                    try:
                        raw_balances = (
                            row["opening_qty"], row["remaining_qty"],
                        )
                        if any(
                            type(value) is not str or len(value) > 128
                            for value in raw_balances
                        ):
                            raise ValueError("invalid stock balance encoding")
                        start, remaining = map(Decimal, raw_balances)
                        if (not start.is_finite() or not remaining.is_finite()
                                or start < 0 or remaining < 0
                                or any(
                                    value != 0 and not -18 <= value.adjusted() <= 18
                                    for value in (start, remaining)
                                )):
                            raise ValueError("invalid stock balance")
                        if any(
                            raw != canonical_decimal(value)
                            for raw, value in zip(raw_balances, (start, remaining))
                        ):
                            reasons.append("noncanonical_stock_balance:" + barcode)
                        current = start
                        for move in moves_by_barcode.get(barcode, ()):
                            raw_values = (
                                move["before_qty"], move["sold_qty"],
                                move["after_qty"],
                            )
                            if any(
                                type(value) is not str or len(value) > 128
                                for value in raw_values
                            ):
                                raise ValueError("invalid stock decimal encoding")
                            before, sold, after = map(Decimal, raw_values)
                            if (not all(v.is_finite() for v in (before, sold, after))
                                    or any(
                                        value != 0 and not -18 <= value.adjusted() <= 18
                                        for value in (before, sold, after)
                                    )):
                                reasons.append("invalid_stock_decimal:" + barcode)
                                continue
                            if any(
                                raw != canonical_decimal(value)
                                for raw, value in zip(raw_values, (before, sold, after))
                            ):
                                reasons.append("noncanonical_stock_move:" + barcode)
                            if (before != current or sold <= 0
                                    or after != before - sold or after < 0):
                                reasons.append("stock_chain_mismatch:" + barcode)
                            current = after
                        if current != remaining:
                            reasons.append("stock_balance_mismatch:" + barcode)
                    except (InvalidOperation, TypeError, ValueError):
                        reasons.append("invalid_stock_decimal:" + barcode)
            # Corrupted SQLite values can have unexpected storage classes.
            # Never let an audit crash or report a trusted monetary total.
            valid_subtotals = [
                sale["subtotal_cents"] for sale in invoices
                if type(sale["subtotal_cents"]) is int
                and sale["subtotal_cents"] >= 0
            ]
            if len(valid_subtotals) != len(invoices):
                reasons.append("invalid_invoice_subtotal_encoding")
            total_cents = sum(valid_subtotals)
            return SandboxReconciliation(
                balanced=not reasons,
                reasons=tuple(dict.fromkeys(reasons)),
                invoice_count=len(invoices),
                subtotal_cents=total_cents,
            )
        finally:
            connection.rollback()
            connection.close()

    def require_commercial_sale(self, **_kwargs):
        raise PermissionError("Sandbox-only; V8 commercial checkout is disabled")
