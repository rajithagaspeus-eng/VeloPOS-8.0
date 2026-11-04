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

    def inspect(self, *, action, license_key, machine_id, today=None):
        _guard(self.database)
        if action not in _ACTIONS:
            raise ValueError("Unknown protected financial action")
        if not isinstance(machine_id, str) or not 1 <= len(machine_id) <= 120:
            raise ValueError("Invalid machine identity")
        day = date.today() if today is None else today
        if not isinstance(day, date) or isinstance(day, datetime):
            raise ValueError("Invalid inspection date")
        reasons = ["preview_transactions_disabled"]
        verified, matched, entitled = False, False, False
        data = None
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
            parsed = json.loads(payload.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("License payload must be an object")
            data = parsed
            verified = True
        except (ValueError, TypeError, UnicodeError, binascii.Error,
                InvalidSignature, json.JSONDecodeError):
            reasons.append("invalid_license_signature")
        if verified:
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
                        entitled = matched
        return PreviewEntitlementDecision(
            action, verified, matched, entitled, tuple(reasons),
        )
