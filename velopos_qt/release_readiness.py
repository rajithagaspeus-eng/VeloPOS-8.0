"""Fail-closed, machine-readable V8 commercial release readiness snapshot.

This reports engineering evidence requirements; it does not infer that a
commercial gate has passed merely because a test or preview component exists.
No production database, license, payment gateway, or Qt object is accessed.
"""
from dataclasses import asdict, dataclass
import json


@dataclass(frozen=True)
class ReleaseGate:
    key: str
    title: str
    status: str
    outstanding: tuple[str, ...]


# Keep these blockers aligned with docs/V8_COMMERCIAL_RELEASE_GATES.md.
_GATES = (
    ReleaseGate("A", "Transaction integrity", "BLOCKED", (
        "Verified commercial session and signed entitlement at every service entry",
        "Atomic sales, returns, tenders, stock, tax and crash-safe replay",
        "End-to-end concurrent and rollback acceptance on disposable databases",
    )),
    ReleaseGate("B", "Financial and inventory acceptance", "BLOCKED", (
        "Certified invoice-level COGS, tax, loyalty and inventory reconciliation",
        "Migration and accounting acceptance against representative test fixtures",
    )),
    ReleaseGate("C", "Multi-branch and mobile sync", "NOT_READY", (
        "Authenticated offline-first tenant and branch-scoped synchronization",
        "Conflict resolution and secure owner dashboard API",
    )),
    ReleaseGate("D", "Commercial licensing and distribution", "NOT_READY", (
        "Server-authoritative signed activation, recovery and offline grace",
        "Installer, upgrades, rollback and secret-handling acceptance",
    )),
    ReleaseGate("E", "Windows release quality", "NOT_READY", (
        "Complete Windows GUI, device, multilingual and accessibility QA",
        "Verified CI, installer and signed release acceptance",
    )),
)


def release_readiness():
    """Return immutable gates; never authorize commerce based on this report."""
    return _GATES


def release_readiness_report():
    gates = release_readiness()
    return {
        "product": "VeloPOS 8.0",
        "branch": "develop-v8",
        "preview_only": True,
        "can_checkout": False,
        "production_ready": False,
        "gate_counts": {
            "total": len(gates),
            "passed": sum(g.status == "PASSED" for g in gates),
            "blocked": sum(g.status == "BLOCKED" for g in gates),
            "not_ready": sum(g.status == "NOT_READY" for g in gates),
        },
        "gates": [asdict(g) for g in gates],
    }


def main():
    print(json.dumps(release_readiness_report(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
