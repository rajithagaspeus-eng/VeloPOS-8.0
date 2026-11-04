"""Read-only commercial transaction acceptance planning for V8.

This module describes missing proofs for a future service boundary. It never
grants checkout access, even when all supplied test evidence appears true.
"""
from dataclasses import dataclass


_REQUIRED = {
    "sale": (
        "authenticated_session", "action_permission", "signed_entitlement",
        "open_shift", "branch_scope", "price_revalidation", "stock_revalidation",
        "tax_and_rounding", "atomic_commit", "idempotent_recovery",
    ),
    "return": (
        "authenticated_session", "action_permission", "signed_entitlement",
        "open_shift", "branch_scope", "original_invoice", "refund_reconciliation",
        "atomic_commit", "idempotent_recovery",
    ),
    "purchase": (
        "authenticated_session", "action_permission", "signed_entitlement",
        "branch_scope", "supplier_revalidation", "stock_revalidation",
        "atomic_commit", "idempotent_recovery",
    ),
}


@dataclass(frozen=True)
class CommercialBoundaryAssessment:
    action: str
    required_proofs: tuple[str, ...]
    missing_proofs: tuple[str, ...]
    unverified_proofs: tuple[str, ...]
    can_execute: bool = False
    production_ready: bool = False


def assess_commercial_boundary(action, evidence=None):
    """Inventory supplied *test* proofs, never authenticate them.

    Unknown keys, booleans, arbitrary objects and even apparently complete
    proof dictionaries are not a verified session or commercial license.
    """
    if type(action) is not str or action not in _REQUIRED:
        raise ValueError("Unknown commercial boundary action")
    if evidence is None:
        evidence = {}
    if type(evidence) is not dict:
        raise ValueError("Commercial evidence must be a dictionary")
    if any(type(key) is not str or key not in _REQUIRED[action]
           for key in evidence):
        raise ValueError("Unknown commercial evidence key")
    required = _REQUIRED[action]
    missing = tuple(key for key in required if key not in evidence)
    # No self-attested evidence is trusted as a service-side verification.
    unverified = tuple(key for key in required if key in evidence)
    return CommercialBoundaryAssessment(
        action=action, required_proofs=required,
        missing_proofs=missing, unverified_proofs=unverified,
    )
