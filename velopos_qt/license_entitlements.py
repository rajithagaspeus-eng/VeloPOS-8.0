"""Fail-closed signed-entitlement inspection for V8 TEST DATA ONLY.

This pure diagnostic does not read installed keys, local trial seals, online
activation state or licenses from production, and NEVER grants transaction
permission. It verifies the legacy base64url.payload + Ed25519.signature
envelope with an explicitly supplied public key; unsigned UI claims cannot
satisfy the cryptographic boundary. Real commercial policy is still blocked.
"""
import base64
import binascii
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .product_editor import _guard
from .transaction_policy import PreviewTransactionGate


_MAX_KEY_CHARS = 8192
_ACTIONS = PreviewTransactionGate.protected


@dataclass(frozen=True)
class PreviewEntitlementDecision:
    action: str
    signature_valid: bool
    machine_matches: bool
    entitled: bool
    reasons: tuple[str, ...]
    can_execute: bool = False
    signed_license_id: str | None = None
    signed_branch_id: str | None = None


def _unique_json_object(pairs):
    """Reject ambiguous duplicate signed claims rather than last-key-wins."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate signed JSON claim")
        result[key] = value
    return result


def _decode(encoded, *, limit):
    if not isinstance(encoded, str) or not encoded or len(encoded) > limit:
        raise ValueError("Malformed encoded license field")
    if any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in encoded):
        raise ValueError("Malformed base64url license field")
    raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != encoded:
        raise ValueError("Noncanonical base64url license field")
    return raw


class PreviewSignedEntitlementInspector:
    """Cryptographic diagnostics only. Never call this to authorize posting."""

    def __init__(self, database, *, public_key_b64):
        _guard(database)
        self.database = database
        try:
            pub = _decode(public_key_b64, limit=128)
            if len(pub) != 32:
                raise ValueError("Expected an Ed25519 public key")
            self.public_key = Ed25519PublicKey.from_public_bytes(pub)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Valid Ed25519 public key required") from exc

    def inspect(self, *, action, license_key, machine_id, today=None,
                expected_branch_id=None):
        _guard(self.database)
        if action not in _ACTIONS:
            raise ValueError("Unknown protected financial action")
        if not isinstance(machine_id, str) or not 1 <= len(machine_id) <= 120:
            raise ValueError("Invalid machine identity")
        if expected_branch_id is not None and (type(expected_branch_id) is not str
                or not 1 <= len(expected_branch_id) <= 120
                or not all(c.isascii() and (c.isalnum() or c in '-_')
                           for c in expected_branch_id)):
            raise ValueError('Invalid expected branch identity')
        day = date.today() if today is None else today
        if not isinstance(day, date) or isinstance(day, datetime):
            raise ValueError("Invalid inspection date")
        reasons = ["preview_transactions_disabled"]
        verified, matched, entitled = False, False, False
        data = None
        signed_license_id = None
        signed_branch_id = None
        try:
            if not isinstance(license_key, str) or len(license_key) > _MAX_KEY_CHARS:
                raise ValueError("Malformed license")
            envelope = "".join(license_key.split())
            if envelope.count(".") != 1:
                raise ValueError("Malformed license")
            payload_b64, signature_b64 = envelope.split(".")
            payload = _decode(payload_b64, limit=_MAX_KEY_CHARS)
            signature = _decode(signature_b64, limit=128)
            if len(signature) != 64:
                raise ValueError("Invalid signature length")
            self.public_key.verify(signature, payload)
            parsed = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_json_object)
            if not isinstance(parsed, dict):
                raise ValueError("License payload must be an object")
            data = parsed
            verified = True
        except (ValueError, TypeError, UnicodeError, binascii.Error,
                InvalidSignature, json.JSONDecodeError):
            reasons.append("invalid_license_signature")
        if verified:
            # V8 activation binding requires a versioned, signed identifier.
            # Existing V7 envelopes remain inspectable but never gain one.
            identifier = data.get('license_id')
            if type(data.get('v')) is int and data['v'] == 8 and isinstance(identifier, str) and (
                1 <= len(identifier) <= 120 and identifier == identifier.strip()
                and all(c.isascii() and (c.isalnum() or c in '-_') for c in identifier)
            ):
                signed_license_id = identifier
            branch_claim = data.get("branch_id")
            if (type(data.get("v")) is int and data["v"] == 8
                    and type(branch_claim) is str
                    and 1 <= len(branch_claim) <= 120
                    and all(c.isascii() and (c.isalnum() or c in "-_")
                            for c in branch_claim)):
                signed_branch_id = branch_claim
            if expected_branch_id is not None:
                if signed_branch_id is None:
                    reasons.append("signed_branch_scope_missing")
                elif signed_branch_id != expected_branch_id:
                    reasons.append("signed_branch_scope_mismatch")
            matched = data.get("m") == machine_id
            if not matched:
                reasons.append("license_machine_mismatch")
            # Old V7 licenses may legitimately have no scope/expiry fields.
            # They remain untouched by this preview; do NOT infer a commercial
            # V8 transaction entitlement from a valid legacy signature.
            scopes = data.get("actions")
            if not isinstance(scopes, list) or action not in scopes or any(
                not isinstance(value, str) or value not in _ACTIONS
                for value in scopes
            ):
                reasons.append("signed_action_entitlement_missing")
            else:
                expires = data.get("expires")
                try:
                    expiry = date.fromisoformat(expires)
                    if not isinstance(expires, str) or expiry.isoformat() != expires:
                        raise ValueError
                except (ValueError, TypeError):
                    reasons.append("signed_expiry_missing_or_invalid")
                else:
                    if day > expiry:
                        reasons.append("signed_entitlement_expired")
                    else:
                        entitled = matched and (expected_branch_id is None or signed_branch_id == expected_branch_id)
        return PreviewEntitlementDecision(
            action, verified, matched, entitled, tuple(reasons),
            signed_license_id=signed_license_id,
            signed_branch_id=signed_branch_id,
        )
