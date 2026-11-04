"""Preview-only reference for a SERVER-owned monotonic activation ledger.

This is neither a deployed API nor a working commercial license service.
Every mutating call must run inside a trusted backend transaction (BEGIN
IMMEDIATE). The caller passes a signing key and optional clock for TESTS ONLY.
A desktop-client-controlled key, clock or database provides no authority.
Never expose register/revoke/issue as unauthenticated HTTP methods.
"""
import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .activation_chain import _identifier, _utc, _MAX_SEQUENCE
from .idempotency_ledger import PreviewIdempotencyLedger
from .license_entitlements import _decode, _unique_json_object


@dataclass(frozen=True)
class PreviewServerReceipt:
    signed_status: str
    sequence: int
    status: str
    can_execute: bool = False


@dataclass(frozen=True)
class PreviewServerContinuityDecision:
    receipt_matches_server_state: bool
    reasons: tuple[str, ...]
    can_execute: bool = False


def _clock(server_now):
    # Only a real hosted backend can source and protect the server clock.
    now = datetime.now(timezone.utc) if server_now is None else server_now
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware server clock required")
    return now.astimezone(timezone.utc)


def _stamp(value):
    return value.isoformat().replace("+00:00", "Z")


def _valid_id(value):
    if not _identifier(value):
        raise ValueError("Canonical machine, license and branch IDs required")
    return value


def _encode(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


class PreviewServerActivationAuthority:
    """Atomic, reference-only receipt signer; never authorizes a POS action.

    This is intentionally isolated to disposable VeloPOS8PreviewData. The
    signing_key is supplied by TEST fixtures, not generated or persisted.
    For production an authenticated backend and protected key custody are
    mandatory; this class must NOT be exposed directly to shop clients.
    """

    def __init__(self, database, *, signing_key):
        self.database = database
        self._gate = PreviewIdempotencyLedger(database)
        if not isinstance(signing_key, Ed25519PrivateKey):
            raise ValueError("Explicit in-memory Ed25519 test signing key required")
        self._signer = signing_key

    def _check(self, connection):
        self._gate._check_connection(connection)

    def initialize(self, connection):
        """Create disposable reference schema within caller transaction."""
        self._check(connection)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS v8_preview_server_license_state ("
            "license_id TEXT PRIMARY KEY, machine_id TEXT NOT NULL,"
            "branch_id TEXT NOT NULL, expires_utc TEXT NOT NULL,"
            "status TEXT NOT NULL CHECK(status IN ('active','revoked')),"
            "last_sequence INTEGER NOT NULL CHECK(last_sequence>=0),"
            "last_observed_utc TEXT, last_payload_sha256 TEXT)"
        )

    def register(self, connection, *, license_id, machine_id, branch_id,
                 expires_utc, server_now=None):
        """Trusted-operator test fixture only; duplicate IDs cannot reset."""
        self._check(connection)
        for identifier in (license_id, machine_id, branch_id):
            _valid_id(identifier)
        expiry = _utc(expires_utc)
        if expiry <= _clock(server_now):
            raise ValueError("License expiry must be in the future")
        # INSERT (never REPLACE/UPSERT): registering an existing ID cannot
        # reset its sequence, binding or revoked state.
        connection.execute(
            "INSERT INTO v8_preview_server_license_state "
            "(license_id,machine_id,branch_id,expires_utc,status,last_sequence) "
            "VALUES(?,?,?,?,'active',0)",
            (license_id, machine_id, branch_id, expires_utc),
        )

    def revoke(self, connection, *, license_id):
        """Trusted-operator test fixture; no local client revoke endpoint."""
        self._check(connection)
        _valid_id(license_id)
        updated = connection.execute(
            "UPDATE v8_preview_server_license_state SET status='revoked' "
            "WHERE license_id=? AND status='active'", (license_id,),
        )
        if updated.rowcount != 1:
            raise ValueError("Unknown or previously revoked license")

    def issue(self, connection, *, license_id, machine_id, branch_id,
              server_now=None):
        """Sign the next observation, atomically recording the new watermark.

        The caller MUST commit the watermark and signed receipt delivery
        semantics together at its backend boundary; a rolled-back transaction
        cannot establish a durable activation history.
        """
        self._check(connection)
        for identifier in (license_id, machine_id, branch_id):
            _valid_id(identifier)
        clock = _clock(server_now)
        row = connection.execute(
            "SELECT * FROM v8_preview_server_license_state WHERE license_id=?",
            (license_id,),
        ).fetchone()
        if row is None:
            raise PermissionError("Unknown license")
        if row["machine_id"] != machine_id or row["branch_id"] != branch_id:
            raise PermissionError("License device or branch mismatch")
        if row["last_sequence"] >= _MAX_SEQUENCE:
            raise OverflowError("Server sequence exhausted")
        if row["last_observed_utc"] is not None and (
                clock < _utc(row["last_observed_utc"])):
            raise ValueError("Server observation clock rollback")
        if row["status"] == "active" and clock > _utc(row["expires_utc"]):
            raise PermissionError("License expired")
        next_sequence = row["last_sequence"] + 1
        payload = dict(
            v=8, machine_id=machine_id, license_id=license_id,
            branch_id=branch_id, status=row["status"], sequence=next_sequence,
            observed_utc=_stamp(clock), expires_utc=row["expires_utc"],
        )
        if row["last_payload_sha256"] is not None:
            payload["previous_payload_sha256"] = row["last_payload_sha256"]
        signed_bytes = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        receipt = _encode(signed_bytes) + "." + _encode(
            self._signer.sign(signed_bytes)
        )
        digest = hashlib.sha256(signed_bytes).hexdigest()
        updated = connection.execute(
            "UPDATE v8_preview_server_license_state "
            "SET last_sequence=?,last_observed_utc=?,last_payload_sha256=? "
            "WHERE license_id=? AND last_sequence=? AND status=?",
            (next_sequence, _stamp(clock), digest, license_id,
             row["last_sequence"], row["status"]),
        )
        if updated.rowcount != 1:
            raise RuntimeError("Concurrent server activation state change")
        return PreviewServerReceipt(receipt, next_sequence, row["status"])

    def inspect_current(self, connection, *, signed_status,
                        license_id, machine_id, branch_id, server_now=None):
        """Compare a signed receipt to the SERVER'S last committed state.

        Unlike comparing two client-held receipts, the latest committed
        server digest/sequence can detect replay of an earlier receipt.
        This is a test-only reference; it does NOT grant a checkout license.
        """
        self._check(connection)
        for identifier in (license_id, machine_id, branch_id):
            _valid_id(identifier)
        clock = _clock(server_now)
        reasons = ["preview_transactions_disabled"]
        row = connection.execute(
            "SELECT * FROM v8_preview_server_license_state WHERE license_id=?",
            (license_id,),
        ).fetchone()
        if row is None:
            reasons.append("server_license_missing")
        elif row["machine_id"] != machine_id or row["branch_id"] != branch_id:
            reasons.append("server_license_binding_mismatch")
        elif row["status"] != "active":
            reasons.append("server_license_revoked")
        if row is not None and clock > _utc(row["expires_utc"]):
            reasons.append("server_license_expired")
        try:
            if (type(signed_status) is not str or len(signed_status) > 8192
                    or signed_status.count(".") != 1):
                raise ValueError("Malformed signed receipt")
            encoded, sig = signed_status.split(".")
            raw = _decode(encoded, limit=8192)
            signature = _decode(sig, limit=128)
            if len(signature) != 64:
                raise ValueError("Malformed signature length")
            self._signer.public_key().verify(signature, raw)
            payload = json.loads(
                raw.decode("utf-8"), object_pairs_hook=_unique_json_object,
            )
            if type(payload) is not dict:
                raise ValueError("Signed receipt must be object")
        except (ValueError, TypeError, UnicodeError, binascii.Error,
                InvalidSignature):
            reasons.append("server_receipt_signature_invalid")
        else:
            if row is None:
                reasons.append("server_receipt_has_no_authority")
            else:
                if (type(payload.get("v")) is not int or payload["v"] != 8
                        or type(payload.get("machine_id")) is not str
                        or payload["machine_id"] != row["machine_id"]
                        or type(payload.get("license_id")) is not str
                        or payload["license_id"] != row["license_id"]
                        or type(payload.get("branch_id")) is not str
                        or payload["branch_id"] != row["branch_id"]
                        or type(payload.get("status")) is not str
                        or payload["status"] != row["status"]
                        or type(payload.get("expires_utc")) is not str
                        or payload["expires_utc"] != row["expires_utc"]):
                    reasons.append("server_receipt_binding_mismatch")
                if (type(payload.get("sequence")) is not int
                        or payload["sequence"] != row["last_sequence"]
                        or hashlib.sha256(raw).hexdigest()
                        != row["last_payload_sha256"]
                        or type(payload.get("observed_utc")) is not str
                        or payload["observed_utc"] != row["last_observed_utc"]):
                    reasons.append("server_receipt_sequence_or_digest_replay")
        return PreviewServerContinuityDecision(
            receipt_matches_server_state=len(reasons) == 1,
            reasons=tuple(reasons),
        )

    def require(self, connection, **kwargs):
        decision = self.inspect_current(connection, **kwargs)
        raise PermissionError("; ".join(
            (*decision.reasons, "commercial_activation_not_implemented")
        ))
