"""Pure, non-authorizing V8 tender allocation plans for TEST/preview data.

A plan reconciles displayed currency amounts only. Card and QR references are
UNVERIFIED strings, not authorizations or evidence of funds. Credit requires
an identifier for *diagnostic* binding but does not verify the customer's
credit limit or ledger. No payment, invoice, checkout or receipt is posted.
NEVER wire this model to a commercial transaction without a trusted service.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .sale_plan import _finite_decimal


_CENT = Decimal("0.01")
_MAX = Decimal("10000000000")
_METHODS = frozenset({"Cash", "Card", "QR", "Credit"})


def _money(value, *, allow_zero=False):
    amount = _finite_decimal(value)
    if amount < 0 or (amount == 0 and not allow_zero) or amount > _MAX:
        raise ValueError("Tender amount out of range")
    try:
        cents = amount.quantize(_CENT)
    except InvalidOperation as exc:
        raise ValueError("Tender amount precision invalid") from exc
    # No silent rounding: e.g. 2.005 in payment entry is an error.
    if amount != cents:
        raise ValueError("Tender amounts must be exact currency cents")
    return cents


@dataclass(frozen=True)
class PreviewTenderLine:
    method: str
    amount: Decimal
    reference: str


@dataclass(frozen=True)
class PreviewTenderPlan:
    amount_due: Decimal
    tenders: tuple[PreviewTenderLine, ...]
    noncash_total: Decimal
    cash_total: Decimal
    credit_due: Decimal
    change_due: Decimal
    has_unverified_external_payments: bool
    credit_limit_unverified: bool
    can_settle: bool = False
    persisted: bool = False


def plan_preview_tender(amount_due, tenders, *, customer_id=None):
    """Validate 1..10 declared tenders against a *draft* amount due.

    Noncash amounts may not exceed the invoice amount, while cash may exceed
    the remaining due with change computed from cash only. Credit demands a
    customer ID but the real balance/limit remains unverified. Every tender
    here is a declaration, NOT proof of payment, even for Cash.
    """
    due = _money(amount_due)
    if not isinstance(tenders, (tuple, list)) or not 1 <= len(tenders) <= 10:
        raise ValueError("Provide 1-10 tender entries")
    parsed = []
    cash = Decimal("0.00")
    noncash = Decimal("0.00")
    credit = Decimal("0.00")
    external = False
    for entry in tenders:
        if not isinstance(entry, dict):
            raise ValueError("Tender entry must be an object")
        method = entry.get("method")
        if type(method) is not str or method not in _METHODS:
            raise ValueError("Unknown tender method")
        amount = _money(entry.get("amount"))
        ref = entry.get("reference", "")
        if type(ref) is not str or len(ref) > 80 or ref != ref.strip():
            raise ValueError("Invalid payment reference")
        if any(ord(c) < 32 or ord(c) == 127 for c in ref):
            raise ValueError("Invalid payment reference")
        if method in ("Card", "QR"):
            if len(ref) < 4:
                raise ValueError("Unverified external tender needs a reference")
            external = True
        elif ref:
            raise ValueError("Only Card/QR preview tenders may have references")
        if method == "Credit":
            if type(customer_id) is not int or customer_id <= 0:
                raise ValueError("Credit needs a selected customer")
            credit += amount
        if method == "Cash":
            cash += amount
        else:
            noncash += amount
        parsed.append(PreviewTenderLine(method, amount, ref))
    if noncash > due:
        raise ValueError("Noncash tenders exceed amount due")
    if cash + noncash < due:
        raise ValueError("Draft tender allocation is insufficient")
    change = cash + noncash - due
    if change > cash:
        raise ValueError("Only cash may produce change")
    return PreviewTenderPlan(
        amount_due=due, tenders=tuple(parsed), noncash_total=noncash,
        cash_total=cash, credit_due=credit, change_due=change,
        has_unverified_external_payments=external,
        credit_limit_unverified=credit > 0,
    )
