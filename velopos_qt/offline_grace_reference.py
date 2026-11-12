"""Signed, bounded offline grace PREVIEW for disposable VeloPOS8PreviewData.

A trusted server could issue a short grant tied to its latest activation
receipt. The local inspector verifies signatures and consistency only.
The customer controls the offline PC clock and storage; it can replay old
valid receipts/grants. A verified window NEVER authorizes V8 checkout.
No production keys, hosted service, persistent license or billing changes.
"""
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .activation_chain import _identifier, _utc, _sequence
from .license_entitlements import _decode, _unique_json_object
from .product_editor import _guard
from .server_activation_reference import (
    PreviewServerActivationAuthority, _clock, _encode, _stamp,
)

_MAX_GRACE_HOURS = 24
_MAX_ENVELOPE_CHARS = 8192
_GRANT_FIELDS = frozenset({
    "v", "kind", "license_id", "machine_id", "branch_id", "sequence",
    "receipt_payload_sha256", "issued_utc", "valid_until_utc",
    "license_expires_utc",
})


@dataclass(frozen=True)
class PreviewOfflineGraceDecision:
    signature_valid: bool
    window_consistent: bool
    reasons: tuple[str, ...]
    grant_expires_utc: str | None = None
    can_execute: bool = False


@dataclass(frozen=True)
class PreviewOfflineGrant:
    signed_grant: str
    valid_until_utc: str
    can_execute: bool = False


def _signed_content(token, key):
    if type(token) is not str or len(token) > _MAX_ENVELOPE_CHARS:
        raise ValueError("Signed envelope too large or missing")
    if token.count(".") != 1:
        raise ValueError("Malformed signed envelope")
    encoded, signature_b64 = token.split(".")
    raw = _decode(encoded, limit=_MAX_ENVELOPE_CHARS)
    signature = _decode(signature_b64, limit=128)
    if len(signature) != 64:
        raise ValueError("Invalid signature size")
    key.verify(signature, raw)
    body = json.loads(raw.decode("utf-8"),
                      object_pairs_hook=_unique_json_object)
    if type(body) is not dict:
        raise ValueError("Signed envelope must contain an object")
    return body, hashlib.sha256(raw).hexdigest()


class PreviewOfflineGraceAuthority:
    """Test-only grant signer; caller owns server transaction and its clock."""

    def __init__(self, authority):
        if not isinstance(authority, PreviewServerActivationAuthority):
            raise TypeError("Preview server authority required")
        self.authority = authority
        _guard(authority.database)

    def issue(self, connection, *, signed_activation_receipt, license_id,
              machine_id, branch_id, hours=24, server_now=None):
        self.authority._check(connection)
        if not all(_identifier(v) for v in
                   (license_id, machine_id, branch_id)):
            raise ValueError("Canonical license/device/branch required")
        if type(hours) is not int or not 1 <= hours <= _MAX_GRACE_HOURS:
            raise ValueError("Grace duration must be between 1 and 24 hours")
        now = _clock(server_now)
        decision = self.authority.inspect_current(
            connection, signed_status=signed_activation_receipt,
            license_id=license_id, machine_id=machine_id,
            branch_id=branch_id, server_now=now,
        )
        if not decision.receipt_matches_server_state:
            raise PermissionError("Current active server receipt required")
        row = connection.execute(
            "SELECT expires_utc,last_sequence FROM "
            "v8_preview_server_license_state WHERE license_id=?",
            (license_id,),
        ).fetchone()
        if row is None:
            raise PermissionError("No server license state")
        expires = _utc(row["expires_utc"])
        if expires <= now:
            raise PermissionError("License has expired")
        deadline = min(now + timedelta(hours=hours), expires)
        activation_raw = _decode(
            signed_activation_receipt.split(".")[0], limit=8192,
        )
        payload = {
            "v": 8, "kind": "offline_grace",
            "license_id": license_id, "machine_id": machine_id,
            "branch_id": branch_id, "sequence": row["last_sequence"],
            "receipt_payload_sha256": hashlib.sha256(activation_raw).hexdigest(),
            "issued_utc": _stamp(now), "valid_until_utc": _stamp(deadline),
            "license_expires_utc": row["expires_utc"],
        }
        raw = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        token = _encode(raw) + "." + _encode(self.authority._signer.sign(raw))
        return PreviewOfflineGrant(token, _stamp(deadline))

    def require_checkout(self, *args, **kwargs):
        raise PermissionError("Preview offline grace cannot authorize checkout")


class PreviewOfflineGraceInspector:
    """Read-only offline consistency check; never grants transactions."""

    def __init__(self, database, *, server_public_key_b64):
        _guard(database)
        pub = _decode(server_public_key_b64, limit=128)
        if len(pub) != 32:
            raise ValueError("Valid Ed25519 server public key required")
        self.database = database
        self._public_key = Ed25519PublicKey.from_public_bytes(pub)

    def inspect(self, *, signed_activation_receipt, signed_grant,
                license_id, machine_id, branch_id, now=None,
                last_observed_utc=None):
        _guard(self.database)
        if not all(_identifier(v) for v in
                   (license_id, machine_id, branch_id)):
            raise ValueError("Canonical license/device/branch required")
        if last_observed_utc is not None:
            # An optional local watermark is useful diagnostically but can
            # be reset by an attacker and is never a trust anchor.
            last_seen = _utc(last_observed_utc)
        else:
            last_seen = None
        clock = _clock(now)  # A local clock is UNTRUSTED offline.
        reasons = ["preview_transactions_disabled"]
        verified = {}
        for label, token in (
            ("receipt", signed_activation_receipt),
            ("grant", signed_grant),
        ):
            try:
                verified[label] = _signed_content(token, self._public_key)
            except (ValueError, TypeError, UnicodeError, binascii.Error,
                    InvalidSignature, OverflowError):
                reasons.append(label + "_signature_invalid")
        if len(verified) != 2:
            return PreviewOfflineGraceDecision(False, False, tuple(reasons))

        receipt, receipt_hash = verified["receipt"]
        grant, _ = verified["grant"]
        if (type(receipt.get("v")) is not int or receipt["v"] != 8
                or type(receipt.get("status")) is not str
                or receipt["status"] != "active"
                or _sequence(receipt.get("sequence")) in (None, 0)):
            reasons.append("receipt_not_active_or_version_invalid")
        if (type(grant.get("v")) is not int or grant["v"] != 8
                or type(grant.get("kind")) is not str
                or grant["kind"] != "offline_grace"
                or grant.keys() != _GRANT_FIELDS):
            reasons.append("grace_schema_invalid")
        for name, expected in (
            ("license_id", license_id), ("machine_id", machine_id),
            ("branch_id", branch_id),
        ):
            if (type(grant.get(name)) is not str or grant[name] != expected
                    or type(receipt.get(name)) is not str
                    or receipt[name] != expected):
                reasons.append(name + "_binding_mismatch")
        if (type(grant.get("sequence")) is not int
                or grant["sequence"] != receipt.get("sequence")):
            reasons.append("grace_sequence_mismatch")
        if (type(grant.get("receipt_payload_sha256")) is not str
                or grant["receipt_payload_sha256"] != receipt_hash):
            reasons.append("grace_receipt_digest_mismatch")
        dates = {}
        for field in ("issued_utc", "valid_until_utc", "license_expires_utc"):
            try:
                dates[field] = _utc(grant.get(field))
            except (TypeError, ValueError, OverflowError):
                dates[field] = None
                reasons.append(field + "_invalid")
        try:
            receipt_issued = _utc(receipt.get("observed_utc"))
            receipt_expiry = _utc(receipt.get("expires_utc"))
        except (ValueError, TypeError, OverflowError):
            receipt_issued = receipt_expiry = None
            reasons.append("receipt_clock_or_expiry_invalid")
        issued, valid_until, expires = (
            dates["issued_utc"], dates["valid_until_utc"],
            dates["license_expires_utc"],
        )
        if expires is not None and (
                type(receipt.get("expires_utc")) is not str
                or receipt["expires_utc"] != grant.get("license_expires_utc")):
            reasons.append("grace_license_expiry_mismatch")
        if all(v is not None for v in (
                issued, valid_until, expires, receipt_issued, receipt_expiry)):
            if (issued < receipt_issued or
                    valid_until <= issued or
                    valid_until > issued + timedelta(hours=_MAX_GRACE_HOURS) or
                    valid_until > expires or
                    valid_until > receipt_expiry):
                reasons.append("grace_duration_or_order_invalid")
            if clock < issued - timedelta(minutes=5):
                reasons.append("grace_clock_before_issue")
            if clock > valid_until:
                reasons.append("grace_window_expired")
            if clock > expires:
                reasons.append("license_signed_expiry_elapsed")
            if last_seen is not None and clock < last_seen:
                reasons.append("local_clock_rollback_observed")
        return PreviewOfflineGraceDecision(
            signature_valid=True, window_consistent=len(reasons) == 1,
            reasons=tuple(reasons),
            grant_expires_utc=(
                grant.get("valid_until_utc")
                if type(grant.get("valid_until_utc")) is str else None
            ),
        )

    def require_checkout(self, **kwargs):
        decision = self.inspect(**kwargs)
        raise PermissionError("; ".join(
            (*decision.reasons, "commercial_offline_grace_not_implemented")
        ))
