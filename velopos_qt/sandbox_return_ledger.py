"""Persistent V8 TEST-SANDBOX non-restocking returns; NEVER real refunds.

Requires a separately signed 'return' action, matching cashier/shift/branch
and activation-chain observations under one BEGIN IMMEDIATE transaction.
Refunds are declarations only: NO cash disbursement, no card reversal and NO
restocking (damaged/unusable goods policy). Never edits legacy V7 data.
"""
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from hashlib import sha256

from .atomic_sale_boundary import PreviewAtomicSaleBoundary
from .auth_model import PreviewIdentity
from .combined_authorization import PreviewCombinedAuthorization
from .idempotency_ledger import PreviewIdempotencyLedger, request_fingerprint
from .product_editor import _guard
from .sale_plan import _finite_decimal, canonical_decimal

_CENT = Decimal("0.01")
_CONTEXT = Context(prec=512, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class SandboxReturnEvidence:
    reference: str
    original_reference: str
    refund_cents: int
    items: int
    replayed: bool
    sandbox_persisted: bool = True
    actual_refund_posted: bool = False
    stock_restocked: bool = False
    can_checkout: bool = False


@dataclass(frozen=True)
class SandboxReturnAudit:
    balanced: bool
    reasons: tuple[str, ...]
    return_count: int
    total_refund_cents: int
    actual_refund_posted: bool = False


class PreviewSandboxReturnLedger:
    """Service-owned return journal + refund declarations (no cash/stock writes)."""

    _FAILPOINTS = frozenset({"after_claim", "after_lines", "after_complete"})

    def __init__(self, database, *, license_public_key_b64):
        _guard(database)
        self.database = database
        self.authorization = PreviewCombinedAuthorization(
            database, public_key_b64=license_public_key_b64
        )
        self.journal = PreviewIdempotencyLedger(database)

    @staticmethod
    def _tables(connection):
        # Do not use executescript; that implicitly commits SQLite transactions.
        connection.execute(
            "CREATE TABLE IF NOT EXISTS main.v8_preview_sandbox_returns ("
            "reference TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, "
            "original_ref TEXT NOT NULL, actor TEXT NOT NULL, "
            "branch_id TEXT NOT NULL, shift_id INTEGER NOT NULL, "
            "refund_cents INTEGER NOT NULL CHECK(refund_cents>0), "
            "refund_mode TEXT NOT NULL CHECK(refund_mode IN ('Cash','Card','QR')))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS main.v8_preview_sandbox_return_lines ("
            "reference TEXT NOT NULL, line_no INTEGER NOT NULL, "
            "sale_line_no INTEGER NOT NULL, barcode TEXT NOT NULL, "
            "quantity TEXT NOT NULL, refund_cents INTEGER NOT NULL "
            "CHECK(refund_cents>=0), disposition TEXT NOT NULL "
            "CHECK(disposition IN ('DAMAGED','DISCARDED')), "
            "restocked INTEGER NOT NULL DEFAULT 0 CHECK(restocked=0), "
            "PRIMARY KEY(reference,line_no), "
            "UNIQUE(reference,sale_line_no))"
        )

    def simulate_return(self, *, identity, shift_id, request_id, original_ref,
                        returns, refund_mode="Cash", disposition="DAMAGED",
                        expected_branch_id,
                        license_id, machine_id, license_key,
                        server_public_key_b64, previous_status, current_status,
                        today=None, now=None, max_offline_hours=24,
                        inject_failure_at=None):
        """Durably declare a non-restocking refund on disposable sandbox data."""
        if inject_failure_at is not None and inject_failure_at not in self._FAILPOINTS:
            raise ValueError("Unknown return failpoint")
        _guard(self.database)
        self.journal._validate_identity("return", request_id)
        if type(original_ref) is not str or not original_ref.startswith("SBX-") or len(original_ref) != 28:
            raise ValueError("Canonical original sandbox reference required")
        if refund_mode not in ("Cash", "Card", "QR") or type(refund_mode) is not str:
            raise ValueError("Unsupported sandbox refund declaration")
        if type(disposition) is not str or disposition not in ("DAMAGED", "DISCARDED"):
            raise ValueError("Only explicitly non-restocking disposition is supported")
        if not isinstance(returns, (list, tuple)) or not 1 <= len(returns) <= 100:
            raise ValueError("Provide 1-100 return line requests")
        frozen = []
        seen = set()
        for row in returns:
            if type(row) is not dict:
                raise ValueError("Return line must be an object")
            line_no = row.get("line_no")
            if type(line_no) is not int or line_no <= 0 or line_no in seen:
                raise ValueError("Unique positive original sale line required")
            seen.add(line_no)
            qty = _finite_decimal(row.get("qty"))
            if qty <= 0 or qty > Decimal("1000000"):
                raise ValueError("Invalid return quantity")
            frozen.append((line_no, canonical_decimal(qty)))
        day = PreviewAtomicSaleBoundary._day(today).isoformat()
        original_actor = identity
        actor = (
            PreviewIdentity(
                getattr(original_actor, "username", None),
                getattr(original_actor, "role", None),
                getattr(original_actor, "credential_tag", None)
            ) if original_actor is not None else None
        )
        payload = {
            "v": 1, "action": "return", "original_ref": original_ref,
            "actor_hint": getattr(actor, "username", None),
            "shift_id": shift_id, "branch_id": expected_branch_id,
            "license_id": license_id, "machine_id": machine_id,
            "day": day, "refund_mode": refund_mode,
            "disposition": disposition, "non_restock": True,
            "lines": [{"line_no": n, "qty": q} for n, q in frozen],
        }
        digest = request_fingerprint(payload)
        ref = "SRF-" + sha256(
            (request_id + ":" + digest).encode("utf-8")
        ).hexdigest()[:24]
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            signed = self.authorization.inspect_with_activation_chain(
                connection, action="return",
                identity=actor, shift_id=shift_id,
                expected_branch_id=expected_branch_id, license_id=license_id,
                machine_id=machine_id, license_key=license_key,
                server_public_key_b64=server_public_key_b64,
                previous_status=previous_status, current_status=current_status,
                today=PreviewAtomicSaleBoundary._day(day), now=now,
                max_offline_hours=max_offline_hours,
            )
            if not signed.policy_consistent:
                raise PermissionError("Sandbox return signed/session/shift policy denied")
            needed = {"v8_preview_sandbox_sales", "v8_preview_sandbox_sale_lines",
                      "v8_preview_sandbox_settlements"}
            known = {
                row[0] for row in connection.execute(
                    "SELECT name FROM main.sqlite_master WHERE type='table'"
                )
            }
            if not needed.issubset(known):
                raise PermissionError("Original sandbox invoice schema unavailable")
            sale = connection.execute(
                "SELECT request_id,branch_id,subtotal_cents FROM "
                "main.v8_preview_sandbox_sales WHERE reference=?",
                (original_ref,)
            ).fetchone()
            if sale is None or sale["branch_id"] != expected_branch_id:
                raise PermissionError("Original sandbox invoice not in branch")
            # A sandbox invoice must have its original completed journal.
            sale_journal = connection.execute(
                "SELECT status,result_ref FROM main.v8_preview_request_journal "
                "WHERE scope='sale' AND request_id=?", (sale["request_id"],)
            ).fetchone()
            if (sale_journal is None or sale_journal["status"] != "COMPLETED"
                    or sale_journal["result_ref"] != original_ref):
                raise PermissionError("Original sandbox invoice journal not verified")
            if connection.execute(
                "SELECT declared FROM main.v8_preview_sandbox_settlements "
                "WHERE reference=?", (original_ref,)
            ).fetchone() is None:
                raise PermissionError("Original sandbox settlement unavailable")
            # No credit-note / receivable reduction policy exists yet.
            # A return on a sandbox invoice already assigned to customer
            # credit would otherwise leave the credit outstanding overstated.
            if "v8_preview_sandbox_credit_charges" in known:
                if connection.execute(
                    "SELECT 1 FROM main.v8_preview_sandbox_credit_charges "
                    "WHERE invoice_ref=?", (original_ref,)
                ).fetchone() is not None:
                    raise PermissionError(
                        "Credit-backed return needs approved credit-note policy"
                    )
            # Check this key first, while authorization and original invoice
            # are current. Conflict blocks changed quantities/mode.
            journal = self.journal.inspect_request(
                connection, "return", request_id, payload
            )
            self._tables(connection)
            if journal.state == "journal_completed_unverified":
                saved = connection.execute(
                    "SELECT original_ref,refund_cents,refund_mode,actor,branch_id,"
                    "shift_id FROM main.v8_preview_sandbox_returns "
                    "WHERE reference=? AND request_id=?",
                    (journal.result_ref, request_id)
                ).fetchone()
                recorded = connection.execute(
                    "SELECT sale_line_no,quantity,refund_cents,disposition,"
                    "restocked FROM main.v8_preview_sandbox_return_lines "
                    "WHERE reference=? ORDER BY line_no",
                    (journal.result_ref,)
                ).fetchall()
                if (journal.result_ref != ref or saved is None
                        or saved["original_ref"] != original_ref
                        or saved["refund_mode"] != refund_mode
                        or saved["actor"] != actor.username
                        or saved["branch_id"] != expected_branch_id
                        or saved["shift_id"] != shift_id
                        or [(row["sale_line_no"], row["quantity"])
                            for row in recorded] != frozen
                        or any(row["disposition"] != disposition or
                               row["restocked"] != 0 for row in recorded)
                        or sum(row["refund_cents"] for row in recorded)
                            != saved["refund_cents"]
                        or saved["refund_cents"] <= 0):
                    raise RuntimeError("Sandbox return journal requires reconciliation")
                connection.rollback()
                return SandboxReturnEvidence(
                    ref, original_ref, saved["refund_cents"], len(recorded), True
                )
            if journal.state != "not_recorded":
                raise PermissionError("Prior return journal needs reconciliation")
            # A subsequent return is limited by cumulative returned quantities
            # AND cumulative line cents, all inside this same SQLite lock.
            processed = []
            total_refund = 0
            with localcontext(_CONTEXT):
                for line_no, quantity_text in frozen:
                    original = connection.execute(
                        "SELECT barcode,quantity,price,line_cents FROM "
                        "main.v8_preview_sandbox_sale_lines "
                        "WHERE reference=? AND line_no=?", (original_ref,line_no)
                    ).fetchone()
                    if original is None:
                        raise ValueError("Original invoice line not found")
                    original_qty = Decimal(original["quantity"])
                    qty = Decimal(quantity_text)
                    prior = connection.execute(
                        "SELECT r.quantity,r.refund_cents FROM "
                        "main.v8_preview_sandbox_return_lines AS r "
                        "JOIN main.v8_preview_sandbox_returns AS h "
                        "ON h.reference=r.reference "
                        "WHERE h.original_ref=? AND r.sale_line_no=?",
                        (original_ref,line_no)
                    ).fetchall()
                    used = sum((Decimal(x["quantity"]) for x in prior), Decimal(0))
                    used_cents = sum(x["refund_cents"] for x in prior)
                    if used + qty > original_qty:
                        raise PermissionError("Return exceeds original sold quantity")
                    # Cumulative rounding allocates residual cents to the
                    # final fraction without exceeding the original line.
                    new_total_cents = int(
                        (Decimal(original["price"]) * (used + qty))
                        .quantize(_CENT, rounding=ROUND_HALF_UP) * 100
                    )
                    new_total_cents = min(original["line_cents"], new_total_cents)
                    refund_cents = new_total_cents - used_cents
                    if refund_cents < 0:
                        raise RuntimeError("Corrupt original refund allocation")
                    processed.append((
                        line_no, original["barcode"], quantity_text, refund_cents
                    ))
                    total_refund += refund_cents
            if total_refund <= 0:
                raise ValueError("Return has no refundable cents")
            claim = self.journal.claim(
                connection, "return", request_id, payload
            )
            if not claim.is_new:
                raise RuntimeError("Unexpected return journal claim")
            if inject_failure_at == "after_claim":
                raise RuntimeError("Injected return failure after claim")
            connection.execute(
                "INSERT INTO main.v8_preview_sandbox_returns "
                "(reference,request_id,original_ref,actor,branch_id,shift_id,"
                "refund_cents,refund_mode) VALUES(?,?,?,?,?,?,?,?)",
                (ref,request_id,original_ref,actor.username,
                 expected_branch_id,shift_id,total_refund,refund_mode)
            )
            for n, (sale_line_no, barcode, qty, cents) in enumerate(processed,1):
                connection.execute(
                    "INSERT INTO main.v8_preview_sandbox_return_lines "
                    "(reference,line_no,sale_line_no,barcode,quantity,"
                    "refund_cents,disposition,restocked) "
                    "VALUES(?,?,?,?,?,?,?,0)",
                    (ref,n,sale_line_no,barcode,qty,cents,disposition)
                )
            if inject_failure_at == "after_lines":
                raise RuntimeError("Injected return failure after lines")
            self.journal.complete(connection,"return",request_id,ref)
            if inject_failure_at == "after_complete":
                raise RuntimeError("Injected return failure after complete")
            connection.commit()
            return SandboxReturnEvidence(ref,original_ref,total_refund,len(frozen),False)
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def reconcile_returns(self):
        """Read-only independent audit of sandbox returns against sale lines.

        Does not issue payments, restock goods or repair corrupt records.
        """
        _guard(self.database)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            required = {
                "v8_preview_sandbox_sales", "v8_preview_sandbox_sale_lines",
                "v8_preview_sandbox_returns",
                "v8_preview_sandbox_return_lines", "v8_preview_request_journal",
            }
            existing = {
                row[0] for row in connection.execute(
                    "SELECT name FROM main.sqlite_master WHERE type='table'"
                )
            }
            if not required.issubset(existing):
                return SandboxReturnAudit(
                    False, ("sandbox_return_tables_missing",), 0, 0
                )
            reasons = []
            headers = connection.execute(
                "SELECT reference,request_id,original_ref,branch_id,"
                "refund_mode,refund_cents FROM "
                "main.v8_preview_sandbox_returns"
            ).fetchall()
            lines = connection.execute(
                "SELECT reference,sale_line_no,barcode,quantity,refund_cents,"
                "disposition,restocked "
                "FROM main.v8_preview_sandbox_return_lines"
            ).fetchall()
            invoice_map = {
                row["reference"]: row for row in connection.execute(
                    "SELECT reference,branch_id FROM "
                    "main.v8_preview_sandbox_sales"
                )
            }
            header_map = {row["reference"]: row for row in headers}
            refunds_by_ref = {}
            refunds_by_sale_line = {}
            with localcontext(_CONTEXT):
                for row in lines:
                    refunds_by_ref.setdefault(row["reference"], []).append(row)
                    header = header_map.get(row["reference"])
                    if header is None:
                        reasons.append("orphan_return_line")
                        continue
                    key = (header["original_ref"], row["sale_line_no"])
                    try:
                        quantity = Decimal(row["quantity"])
                        if not quantity.is_finite() or quantity <= 0:
                            raise ValueError("Invalid return quantity")
                    except (ValueError, TypeError, ArithmeticError):
                        reasons.append("invalid_return_line")
                        continue
                    refunds_by_sale_line.setdefault(key, []).append(row)
                    original = connection.execute(
                        "SELECT barcode FROM "
                        "main.v8_preview_sandbox_sale_lines "
                        "WHERE reference=? AND line_no=?", key
                    ).fetchone()
                    if original is None or original["barcode"] != row["barcode"]:
                        reasons.append("return_original_line_mismatch")
                    if row["refund_cents"] < 0:
                        reasons.append("invalid_return_line")
                    if (row["disposition"] not in ("DAMAGED","DISCARDED")
                            or row["restocked"] != 0):
                        reasons.append("invalid_nonrestock_disposition")
                for (original_ref,line_no), entries in refunds_by_sale_line.items():
                    original = connection.execute(
                        "SELECT quantity,price,line_cents FROM "
                        "main.v8_preview_sandbox_sale_lines "
                        "WHERE reference=? AND line_no=?",
                        (original_ref,line_no)
                    ).fetchone()
                    if original is None:
                        continue
                    quantity = sum(
                        (Decimal(item["quantity"]) for item in entries),
                        Decimal(0)
                    )
                    total = sum(item["refund_cents"] for item in entries)
                    if quantity > Decimal(original["quantity"]):
                        reasons.append("overreturned_sale_line")
                    expected = int(
                        (Decimal(original["price"]) * quantity)
                        .quantize(_CENT,rounding=ROUND_HALF_UP) * 100
                    )
                    if total != min(original["line_cents"],expected):
                        reasons.append("return_line_amount_mismatch")
            for header in headers:
                ref = header["reference"]
                original = invoice_map.get(header["original_ref"])
                if (original is None or
                        original["branch_id"] != header["branch_id"]):
                    reasons.append("return_invoice_branch_mismatch")
                rows = refunds_by_ref.get(ref, ())
                if not rows or sum(
                    row["refund_cents"] for row in rows
                ) != header["refund_cents"]:
                    reasons.append("return_header_total_mismatch")
                if header["refund_mode"] not in ("Cash","Card","QR"):
                    reasons.append("return_method_invalid")
                journal = connection.execute(
                    "SELECT status,result_ref FROM "
                    "main.v8_preview_request_journal "
                    "WHERE scope='return' AND request_id=?",
                    (header["request_id"],)
                ).fetchone()
                if (journal is None or journal["status"] != "COMPLETED"
                        or journal["result_ref"] != ref):
                    reasons.append("return_journal_mismatch")
            for journal in connection.execute(
                "SELECT result_ref FROM main.v8_preview_request_journal "
                "WHERE scope='return' AND status='COMPLETED'"
            ):
                if journal["result_ref"] not in header_map:
                    reasons.append("orphan_completed_return_journal")
            return SandboxReturnAudit(
                not reasons, tuple(dict.fromkeys(reasons)),
                len(headers), sum(h["refund_cents"] for h in headers)
            )
        finally:
            connection.rollback()
            connection.close()

    def require_real_refund(self, **_kwargs):
        raise PermissionError("Commercial refunds are disabled; sandbox only")
