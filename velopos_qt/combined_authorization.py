"""Single-boundary preview authorization and signed entitlement diagnostics.

This is a read-only composition of TWO independent checks performed while
the caller owns an isolated SQLite transaction. It NEVER authorizes a post,
even if both checks appear healthy. Production entitlement installation,
license revocation, device binding and transaction posting remain unresolved.
"""
from dataclasses import dataclass

from .activation_status import PreviewActivationStatusInspector
from .activation_chain import PreviewSignedActivationChainInspector
from .branch_authorization import PreviewBranchAuthorization
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
    signed_branch_id: str | None = None


@dataclass(frozen=True)
class PreviewActivationCombinedDecision:
    authorization: PreviewCombinedDecision
    activation_reasons: tuple[str, ...]
    activation_signature_valid: bool
    activation_current: bool
    can_execute: bool = False


@dataclass(frozen=True)
class PreviewActivationChainCombinedDecision:
    """Read-only composition; policy_consistent is NEVER permission to post."""
    authorization: PreviewCombinedDecision
    branch_reasons: tuple[str, ...]
    chain_reasons: tuple[str, ...]
    branch_verified: bool
    chain_signatures_valid: bool
    chain_consistent: bool
    identity_bound: bool
    policy_consistent: bool
    can_execute: bool = False


@dataclass(frozen=True)
class PreviewCanonicalBranchDecision:
    authorization: PreviewCombinedDecision
    branch_reasons: tuple[str, ...]
    branch_verified: bool
    can_execute: bool = False


class PreviewCombinedAuthorization:
    """Fail-closed, test-DB-only inspection inside a caller-owned transaction."""

    def __init__(self, database, *, public_key_b64):
        self.service = PreviewServiceAuthorization(database)
        self.branches = PreviewBranchAuthorization(database)
        self.entitlements = PreviewSignedEntitlementInspector(
            database, public_key_b64=public_key_b64
        )

    def inspect(self, connection, *, action, identity=None, shift_id=None,
                license_key=None, machine_id=None, today=None,
                expected_branch_id=None):
        # Validate the canonical connection / transaction *before* inspecting
        # any supplied license data. No UI-derived identity/role flag is trusted.
        service = self.service.inspect(
            connection, action=action, identity=identity, shift_id=shift_id
        )
        license_decision = self.entitlements.inspect(
            action=action, license_key=license_key,
            machine_id=machine_id, today=today,
            expected_branch_id=expected_branch_id,
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
            signed_branch_id=license_decision.signed_branch_id,
        )

    def require(self, connection, **kwargs):
        decision = self.inspect(connection, **kwargs)
        raise PermissionError(
            "; ".join(dict.fromkeys(
                (*decision.session_reasons, *decision.license_reasons)
            ))
        )


    def inspect_with_branch_registry(self, connection, *, action,
                                     expected_branch_id, identity=None,
                                     shift_id=None, license_key=None,
                                     machine_id=None, today=None):
        """Inspect signed scope AND persisted branch bindings in one TX.

        expected_branch_id is untrusted client input. Matching a signed
        claim alone does not establish canonical actor or shift membership.
        This method is diagnostic-only and can_execute always remains False.
        """
        authorization = self.inspect(
            connection, action=action, identity=identity, shift_id=shift_id,
            license_key=license_key, machine_id=machine_id, today=today,
            expected_branch_id=expected_branch_id,
        )
        branch = self.branches.inspect(
            connection, action=action, identity=identity,
            branch_id=expected_branch_id, shift_id=shift_id,
        )
        return PreviewCanonicalBranchDecision(
            authorization=authorization,
            branch_reasons=branch.reasons,
            branch_verified=branch.branch_verified,
        )

    def require_with_branch_registry(self, connection, **kwargs):
        decision = self.inspect_with_branch_registry(connection, **kwargs)
        raise PermissionError("; ".join(dict.fromkeys(
            (*decision.authorization.session_reasons,
             *decision.authorization.license_reasons,
             *decision.branch_reasons)
        )))


    def inspect_with_activation_chain(
            self, connection, *, action, expected_branch_id, license_id,
            server_public_key_b64, previous_status, current_status,
            identity=None, shift_id=None, license_key=None, machine_id=None,
            today=None, now=None, max_offline_hours=24):
        """Compose service/shift, canonical branch, signed license and history.

        The claimed branch and license IDs are *inputs*, not authorities.
        The signed V8 license must bind both identifiers, and canonical
        branch membership is independently checked within the caller's
        SQLite transaction. A consistent chain is NOT trusted offline
        continuity and never unlocks a protected financial operation.
        """
        bound = self.inspect_with_branch_registry(
            connection, action=action, expected_branch_id=expected_branch_id,
            identity=identity, shift_id=shift_id, license_key=license_key,
            machine_id=machine_id, today=today,
        )
        chain = PreviewSignedActivationChainInspector(
            self.service.database, server_public_key_b64=server_public_key_b64
        ).inspect(
            previous_status=previous_status, current_status=current_status,
            machine_id=machine_id, license_id=license_id,
            expected_branch_id=expected_branch_id, now=now,
            max_offline_hours=max_offline_hours,
        )
        authorization = bound.authorization
        identity_bound = (
            authorization.signature_valid and authorization.entitled
            and authorization.signed_license_id is not None
            and authorization.signed_license_id == license_id
            and authorization.signed_branch_id is not None
            and authorization.signed_branch_id == expected_branch_id
        )
        chain_reasons = (
            *chain.reasons,
            *(("signed_license_activation_binding_unverified",)
              if not identity_bound else ()),
        )
        # A valid signature/branch diagnosis is *never* commercial access.
        consistent = (
            identity_bound and bound.branch_verified and chain.chain_consistent
            and chain.signatures_valid
            and all(reason in (
                "preview_transactions_disabled", "commercial_license_unverified"
            ) for reason in authorization.session_reasons)
            and all(reason == "preview_transactions_disabled"
                    for reason in authorization.license_reasons)
        )
        return PreviewActivationChainCombinedDecision(
            authorization=authorization,
            branch_reasons=bound.branch_reasons,
            chain_reasons=chain_reasons,
            branch_verified=bound.branch_verified,
            chain_signatures_valid=chain.signatures_valid,
            chain_consistent=chain.chain_consistent,
            identity_bound=identity_bound,
            policy_consistent=consistent,
        )

    def require_with_activation_chain(self, connection, **kwargs):
        decision = self.inspect_with_activation_chain(connection, **kwargs)
        raise PermissionError("; ".join(dict.fromkeys((
            *decision.authorization.session_reasons,
            *decision.authorization.license_reasons,
            *decision.branch_reasons,
            *decision.chain_reasons,
            "commercial_activation_not_implemented",
        ))))

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
