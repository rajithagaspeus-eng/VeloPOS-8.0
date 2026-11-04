"""Signed activation observation-chain diagnostic for isolated V8 test data.

A pair of correctly signed observations can prove cryptographic consistency,
NOT trustworthy continuity across app restarts. Both envelopes can be rolled
back together unless a future authenticated service holds an independent,
monotonic per-license state. The local clock is NOT a trusted time source.
No financial permission, production licensing or persistence is implemented.
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .license_entitlements import _decode, _unique_json_object
from .product_editor import _guard


_MAX_SEQUENCE = 9223372036854775807


@dataclass(frozen=True)
class PreviewActivationChainDecision:
    signatures_valid: bool
    chain_consistent: bool
    reasons: tuple[str, ...]
    previous_sequence: int | None = None
    current_sequence: int | None = None
    can_execute: bool = False


def _identifier(value):
    return (type(value) is str and 1 <= len(value) <= 120
            and all(c.isascii() and (c.isalnum() or c in "-_")
                    for c in value))


def _utc(value):
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError("Expected UTC timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("Expected UTC timezone")
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise ValueError("Noncanonical UTC timestamp")
    return parsed


def _sequence(value):
    return value if type(value) is int and 0 <= value <= _MAX_SEQUENCE else None


class PreviewSignedActivationChainInspector:
    """Fail-closed comparison of two signed server observations (preview only)."""

    def __init__(self, database, *, server_public_key_b64):
        _guard(database)
        self.database = database
        raw = _decode(server_public_key_b64, limit=128)
        if len(raw) != 32:
            raise ValueError("Valid Ed25519 public key required")
        self._key = Ed25519PublicKey.from_public_bytes(raw)

    def _verify(self, envelope):
        if type(envelope) is not str or len(envelope) > 8192 or envelope.count(".") != 1:
            raise ValueError("Malformed activation envelope")
        encoded_payload, encoded_signature = envelope.split(".")
        payload = _decode(encoded_payload, limit=8192)
        signature = _decode(encoded_signature, limit=128)
        if len(signature) != 64:
            raise ValueError("Wrong Ed25519 signature length")
        self._key.verify(signature, payload)
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_json_object)
        if type(data) is not dict:
            raise ValueError("Signed activation status must be an object")
        return data, hashlib.sha256(payload).hexdigest()

    def inspect(self, *, previous_status, current_status, machine_id,
                license_id, expected_branch_id, now=None, max_offline_hours=24):
        _guard(self.database)
        if not all(_identifier(value) for value in (
                machine_id, license_id, expected_branch_id)):
            raise ValueError("Canonical machine, license and branch IDs required")
        if type(max_offline_hours) is not int or not 0 <= max_offline_hours <= 168:
            raise ValueError("Invalid offline freshness window")
        clock = datetime.now(timezone.utc) if now is None else now
        if not isinstance(clock, datetime) or clock.tzinfo is None:
            raise ValueError("Timezone-aware clock required")
        clock = clock.astimezone(timezone.utc)

        reasons = ["preview_transactions_disabled"]
        verified = {}
        for label, token in (("previous", previous_status), ("current", current_status)):
            try:
                verified[label] = self._verify(token)
            except (ValueError, TypeError, UnicodeError, InvalidSignature):
                reasons.append(label + "_status_signature_invalid")

        if len(verified) != 2:
            return PreviewActivationChainDecision(False, False, tuple(reasons))

        previous, previous_hash = verified["previous"]
        current, _ = verified["current"]
        values = {}
        for label, data in (("previous", previous), ("current", current)):
            if type(data.get("v")) is not int or data["v"] != 8:
                reasons.append(label + "_activation_version_invalid")
            if (type(data.get("machine_id")) is not str
                    or data["machine_id"] != machine_id
                    or type(data.get("license_id")) is not str
                    or data["license_id"] != license_id
                    or type(data.get("branch_id")) is not str
                    or data["branch_id"] != expected_branch_id):
                reasons.append(label + "_activation_binding_mismatch")
            if type(data.get("status")) is not str or data["status"] != "active":
                reasons.append(label + "_activation_not_active")

            seq = _sequence(data.get("sequence"))
            if seq is None:
                reasons.append(label + "_sequence_invalid")
            values[label + "_sequence"] = seq

            for field in ("observed_utc", "expires_utc"):
                try:
                    values[label + "_" + field] = _utc(data.get(field))
                except (TypeError, ValueError, OverflowError):
                    values[label + "_" + field] = None
                    reasons.append(label + "_" + field + "_invalid")
            observed = values[label + "_observed_utc"]
            expires = values[label + "_expires_utc"]
            if observed is not None and expires is not None and expires < observed:
                reasons.append(label + "_expiry_precedes_observation")

        old_seq, new_seq = values["previous_sequence"], values["current_sequence"]
        if old_seq is not None and new_seq is not None and new_seq <= old_seq:
            reasons.append("signed_sequence_not_increasing")
        old_time, new_time = values["previous_observed_utc"], values["current_observed_utc"]
        if old_time is not None and new_time is not None and new_time < old_time:
            reasons.append("signed_observation_time_rollback")
        if (type(current.get("previous_payload_sha256")) is not str
                or current["previous_payload_sha256"] != previous_hash):
            reasons.append("signed_previous_digest_mismatch")
        if new_time is not None:
            if new_time > clock + timedelta(minutes=5):
                reasons.append("activation_observation_in_future")
            if clock - new_time > timedelta(hours=max_offline_hours):
                reasons.append("activation_observation_stale")
        if (values["current_expires_utc"] is not None
                and clock > values["current_expires_utc"]):
            reasons.append("activation_signed_expiry_elapsed")

        return PreviewActivationChainDecision(
            signatures_valid=True,
            chain_consistent=len(reasons) == 1,
            reasons=tuple(reasons),
            previous_sequence=old_seq,
            current_sequence=new_seq,
        )

    def require(self, **kwargs):
        decision = self.inspect(**kwargs)
        raise PermissionError("; ".join((*decision.reasons,
                                        "commercial_activation_not_implemented")))
