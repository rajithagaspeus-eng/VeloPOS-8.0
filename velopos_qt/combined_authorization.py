"""Single-boundary preview authorization and signed entitlement diagnostics.

This is a read-only composition of TWO independent checks performed while
the caller owns an isolated SQLite transaction. It NEVER authorizes a post,
even if both checks appear healthy. Production entitlement installation,
license revocation, device binding and transaction posting remain unresolved.
"""
from dataclasses import dataclass

from .license_entitlements import PreviewSignedEntitlementInspector
from .service_authorization import PreviewServiceAuthorization


@dataclass(frozen=True)
class PreviewCombinedDecision:
    action: str
    actor: str | None
    role: str | None
    session_reasons: tuple[str, ...]
    license_reasons: tuple[str, ...]
    signature_valid: bool
    entitled: bool
    can_execute: bool = False


class PreviewCombinedAuthorization:
    """Fail-closed, test-DB-only inspection inside a caller-owned transaction."""

    def __init__(self, database, *, public_key_b64):
        self.service = PreviewServiceAuthorization(database)
        self.entitlements = PreviewSignedEntitlementInspector(
            database, public_key_b64=public_key_b64
        )

    def inspect(self, connection, *, action, identity=None, shift_id=None,
                license_key=None, machine_id=None, today=None):
        # Validate the canonical connection / transaction *before* inspecting
        # any supplied license data. No UI-derived identity/role flag is trusted.
        service = self.service.inspect(
            connection, action=action, identity=identity, shift_id=shift_id
        )
        license_decision = self.entitlements.inspect(
            action=action, license_key=license_key,
            machine_id=machine_id, today=today,
        )
        # The service diagnostic intentionally includes a hard commercial
        # license blocker. It cannot be removed by an apparently valid key.
        return PreviewCombinedDecision(
            action=action,
            actor=service.actor,
            role=service.role,
            session_reasons=service.reasons,
            license_reasons=license_decision.reasons,
            signature_valid=license_decision.signature_valid,
            entitled=license_decision.entitled,
        )

    def require(self, connection, **kwargs):
        decision = self.inspect(connection, **kwargs)
        raise PermissionError(
            "; ".join(dict.fromkeys(
                (*decision.session_reasons, *decision.license_reasons)
            ))
        )
