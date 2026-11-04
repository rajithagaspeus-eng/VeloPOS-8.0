"""Single-boundary preview authorization and signed entitlement diagnostics.

This is a read-only composition of TWO independent checks performed while
the caller owns an isolated SQLite transaction. It NEVER authorizes a post,
even if both checks appear healthy. Production entitlement installation,
license revocation, device binding and transaction posting remain unresolved.
"""
from dataclasses import dataclass

from .activation_status import PreviewActivationStatusInspector
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
    signed_license_id: str | None = None


@dataclass(frozen=True)
class PreviewActivationCombinedDecision:
    authorization: PreviewCombinedDecision
    activation_reasons: tuple[str, ...]
    activation_signature_valid: bool
    activation_current: bool
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
            signed_license_id=license_decision.signed_license_id,
        )

    def require(self, connection, **kwargs):
        decision = self.inspect(connection, **kwargs)
        raise PermissionError(
            "; ".join(dict.fromkeys(
                (*decision.session_reasons, *decision.license_reasons)
            ))
        )

    def inspect_with_activation(self, connection, *, server_public_key_b64,
                                signed_status, license_id, now=None,
                                last_seen_utc=None, max_offline_hours=24,
                                last_accepted_sequence=None,
                                **authorization_kwargs):
        """Compose three diagnostics; never treat unsigned license_id as proof.

        Only explicitly versioned V8 entitlements with a signed license_id can
        bind to the signed activation status. Legacy licenses remain unbound.
        """
        authorization = self.inspect(connection, **authorization_kwargs)
        status = PreviewActivationStatusInspector(
            self.service.database, server_public_key_b64=server_public_key_b64
        ).inspect(
            signed_status=signed_status,
            machine_id=authorization_kwargs.get("machine_id"),
            license_id=license_id,
            now=now, last_seen_utc=last_seen_utc,
            max_offline_hours=max_offline_hours,
            last_accepted_sequence=last_accepted_sequence,
        )
        bound = (authorization.signature_valid and authorization.entitled
                 and authorization.signed_license_id is not None
                 and authorization.signed_license_id == license_id)
        return PreviewActivationCombinedDecision(
            authorization=authorization,
            activation_reasons=(*status.reasons, *(("signed_license_id_binding_unverified",) if not bound else ())),
            activation_signature_valid=status.signature_valid,
            activation_current=status.current,
        )

    def require_with_activation(self, connection, **kwargs):
        decision = self.inspect_with_activation(connection, **kwargs)
        raise PermissionError("; ".join(dict.fromkeys(
            (*decision.authorization.session_reasons,
             *decision.authorization.license_reasons,
             *decision.activation_reasons)
        )))
