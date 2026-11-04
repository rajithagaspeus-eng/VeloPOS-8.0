"""Fail-closed offline activation-status diagnostic for isolated V8 preview.

The server-status envelope must be independently Ed25519-signed by an explicitly
supplied public key. No network call or local unsigned timestamp can establish
commercial trust. This diagnostic NEVER authorizes financial writes.
"""
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .license_entitlements import _decode, _unique_json_object
from .product_editor import _guard


@dataclass(frozen=True)
class PreviewActivationStatus:
    signature_valid: bool
    current: bool
    reasons: tuple[str, ...]
    can_execute: bool = False


class PreviewActivationStatusInspector:
    """Validate signed server observation; never trust caller's status flag."""

    def __init__(self, database, *, server_public_key_b64):
        _guard(database)
        self.database = database
        try:
            raw = _decode(server_public_key_b64, limit=128)
            if len(raw) != 32:
                raise ValueError("Invalid public key length")
            self.public_key = Ed25519PublicKey.from_public_bytes(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError("Valid server verification key required") from exc

    def inspect(self, *, signed_status, machine_id, license_id, now=None,
                last_seen_utc=None, max_offline_hours=24):
        _guard(self.database)
        if not isinstance(machine_id, str) or not 1 <= len(machine_id) <= 120:
            raise ValueError("Invalid machine identity")
        if (not isinstance(license_id, str) or not 1 <= len(license_id) <= 120
                or any(not (c.isascii() and (c.isalnum() or c in "-_"))
                       for c in license_id)):
            raise ValueError("Invalid license identity")
        if type(max_offline_hours) is not int or not 0 <= max_offline_hours <= 168:
            raise ValueError("Invalid offline limit")
        clock = datetime.now(timezone.utc) if now is None else now
        if not isinstance(clock, datetime) or clock.tzinfo is None:
            raise ValueError("UTC-aware clock required")
        clock = clock.astimezone(timezone.utc)
        reasons = ["preview_transactions_disabled"]
        valid = False
        observed = None
        try:
            if not isinstance(signed_status, str) or len(signed_status) > 8192:
                raise ValueError("Malformed status")
            if signed_status.count(".") != 1:
                raise ValueError("Malformed status envelope")
            payload_b64, sig_b64 = signed_status.split(".")
            payload = _decode(payload_b64, limit=8192)
            signature = _decode(sig_b64, limit=128)
            if len(signature) != 64:
                raise ValueError("Bad signature length")
            self.public_key.verify(signature, payload)
            data = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_json_object)
            if not isinstance(data, dict):
                raise ValueError("Status payload must be an object")
            valid = True
        except (ValueError, TypeError, UnicodeError, InvalidSignature):
            reasons.append("activation_status_signature_invalid")
        if valid:
            # Signed observations must use explicit textual identities. Python
            # treats True == 1; never let JSON booleans stand in for IDs.
            if (type(data.get("machine_id")) is not str
                    or type(data.get("license_id")) is not str
                    or data.get("machine_id") != machine_id
                    or data.get("license_id") != license_id):
                reasons.append("activation_binding_mismatch")
            if type(data.get("status")) is not str or data.get("status") != "active":
                reasons.append("activation_not_active")
            timestamp = data.get("observed_utc")
            try:
                if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
                    raise ValueError
                observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if observed.tzinfo is None or observed.utcoffset() != timedelta(0):
                    raise ValueError
                if observed.isoformat().replace("+00:00", "Z") != timestamp:
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
                reasons.append("activation_timestamp_invalid")
            else:
                if observed > clock + timedelta(minutes=5):
                    reasons.append("activation_timestamp_in_future")
                if clock - observed > timedelta(hours=max_offline_hours):
                    reasons.append("activation_status_stale")
        if last_seen_utc is not None:
            if not isinstance(last_seen_utc, datetime) or last_seen_utc.tzinfo is None:
                raise ValueError("Last seen time must be timezone-aware")
            trusted_previous = last_seen_utc.astimezone(timezone.utc)
            if clock + timedelta(minutes=5) < trusted_previous:
                reasons.append("local_clock_rollback_suspected")
            # A newly presented signed observation older than a previously
            # accepted observation must not silently refresh offline grace.
            # The caller-provided watermark is diagnostic, not tamper-proof.
            if observed is not None and observed < trusted_previous:
                reasons.append("activation_observation_replay_suspected")
        return PreviewActivationStatus(
            signature_valid=valid,
            current=valid and len(reasons) == 1,
            reasons=tuple(reasons),
        )
