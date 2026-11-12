"""Test-only deterministic sale request rehearsal; no database or posting.

The output is a diagnostic preview of canonical lines and a stable fingerprint.
It is NEVER a commercial quote, permission, tax calculation or stock promise.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from .sale_plan import plan_preview_sale

_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}\Z")


@dataclass(frozen=True)
class SaleRequestRehearsal:
    request_id: str
    fingerprint: str
    subtotal_cents: int
    line_count: int
    canonical_lines: tuple[str, ...]
    can_checkout: bool = False
    can_post: bool = False


def rehearse_sale_request(*, request_id, lines):
    """Validate and fingerprint a preview sale request without any side effects.

    Canonical JSON removes ambiguity from dictionary key ordering. The request
    ID is included so two different client intents never share a fingerprint.
    This does not reserve the request ID, verify a cashier or touch stock.
    """
    if type(request_id) is not str or _REQUEST_ID.fullmatch(request_id) is None:
        raise ValueError("Invalid preview sale request id")
    plan = plan_preview_sale(lines)
    canonical = tuple(
        json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        for item in plan.request_items()
    )
    payload = json.dumps(
        {"scope": "sale_rehearsal_v1", "request_id": request_id,
         "lines": [json.loads(item) for item in canonical]},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return SaleRequestRehearsal(
        request_id=request_id, fingerprint=digest,
        subtotal_cents=int(plan.subtotal * 100),
        line_count=plan.line_count, canonical_lines=canonical,
    )


class PreviewSaleRequestService:
    """Service boundary for previews only; no commercial write entry point."""

    def inspect(self, *, request_id, lines):
        return rehearse_sale_request(request_id=request_id, lines=lines)

    def commit(self, *, request_id, lines, **_claims):
        # Deny BEFORE inspecting claims, touching a database, or invoking a
        # delegated financial service. Caller-controlled flags cannot unlock.
        raise PermissionError("V8 sale request rehearsal cannot post transactions")
