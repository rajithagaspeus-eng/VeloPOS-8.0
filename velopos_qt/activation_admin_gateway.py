"""Signed operator command gateway CONTRACT for disposable V8 preview data.

NOT a hosted HTTP API, production authentication gateway or shop-client SDK.
Never expose provision_operator/dispatch as unprotected public endpoints.
The operator public-key roster and license watermark must reside on a trusted
server, not on the cashier PC. All signing private keys here are TEST keys.
No real licenses, transaction posting, renewals or production data are used.
"""
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .activation_chain import _identifier, _utc
from .idempotency_ledger import _REQUEST_ID
from .license_entitlements import _decode, _unique_json_object
from .server_activation_reference import (
    PreviewServerActivationAuthority, _clock, _stamp,
)


_OPERATIONS = {
    "register": frozenset({"license_id", "machine_id", "branch_id", "expires_utc"}),
    "revoke": frozenset({"license_id"}),
    "issue": frozenset({"license_id", "machine_id", "branch_id"}),
}
_ENVELOPE_FIELDS = frozenset({
    "v", "operator_id", "request_id", "operation", "issued_utc",
    "expires_utc", "payload",
})
_MAX_ENVELOPE = 8192


@dataclass(frozen=True)
class PreviewAdminResponse:
    operation: str
    response: dict
    retry: bool
    can_execute: bool = False  # NEVER grants commercial checkout.


class PreviewSignedActivationGateway:
    """Reference for a future server-enforced signed admin/issuer boundary.

    Public keys are provisioned by a *trusted server operator*, never a shop
    client. The demo provision_operator method intentionally has NO real
    authenticated bootstrap, so it MUST NOT be wired to network transport.
    """

    def __init__(self, database, *, authority):
        if not isinstance(authority, PreviewServerActivationAuthority):
            raise TypeError("Preview server activation authority required")
        self.database = database
        self.authority = authority
        if self.authority.database is not database:
            raise ValueError("Gateway and authority must share canonical DB")

    def _check(self, connection):
        self.authority._check(connection)

    def initialize(self, connection):
        """Test fixture only. Caller must hold isolated preview transaction."""
        self._check(connection)
        self.authority.initialize(connection)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS v8_preview_activation_operators ("
            "operator_id TEXT PRIMARY KEY, public_key_b64 TEXT NOT NULL,"
            "role TEXT NOT NULL CHECK(role IN ('Admin','Issuer')),"
            "active INTEGER NOT NULL CHECK(active IN (0,1)))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS v8_preview_activation_commands ("
            "operator_id TEXT NOT NULL, request_id TEXT NOT NULL,"
            "operation TEXT NOT NULL, signed_body_sha256 TEXT NOT NULL,"
            "response_json TEXT NOT NULL, created_utc TEXT NOT NULL,"
            "PRIMARY KEY(operator_id,request_id))"
        )

    def provision_operator(self, connection, *, operator_id,
                           public_key_b64, role="Issuer"):
        """Privileged test bootstrap; unsafe without real server admin auth."""
        self._check(connection)
        if not _identifier(operator_id) or role not in ("Admin", "Issuer"):
            raise ValueError("Valid operator ID and role required")
        key_bytes = _decode(public_key_b64, limit=128)
        if len(key_bytes) != 32:
            raise ValueError("Ed25519 operator public key required")
        Ed25519PublicKey.from_public_bytes(key_bytes)
        # Duplicate registration cannot silently change a trusted operator.
        connection.execute(
            "INSERT INTO v8_preview_activation_operators "
            "(operator_id,public_key_b64,role,active) VALUES(?,?,?,1)",
            (operator_id, public_key_b64, role),
        )

    def disable_operator(self, connection, *, operator_id):
        """Privileged test fixture only; real API needs separate admin gate."""
        self._check(connection)
        if not _identifier(operator_id):
            raise ValueError("Valid operator identity required")
        updated = connection.execute(
            "UPDATE v8_preview_activation_operators SET active=0 "
            "WHERE operator_id=? AND active=1", (operator_id,),
        )
        if updated.rowcount != 1:
            raise ValueError("Operator missing or already disabled")

    @staticmethod
    def _parse_signed(signed_request):
        if (type(signed_request) is not str or len(signed_request) > _MAX_ENVELOPE
                or signed_request.count(".") != 1):
            raise PermissionError("Invalid operator command envelope")
        try:
            payload_b64, signature_b64 = signed_request.split(".")
            raw = _decode(payload_b64, limit=_MAX_ENVELOPE)
            sig = _decode(signature_b64, limit=128)
            if len(sig) != 64:
                raise ValueError("Bad signature size")
            body = json.loads(raw.decode("utf-8"),
                              object_pairs_hook=_unique_json_object)
            if type(body) is not dict or body.keys() != _ENVELOPE_FIELDS:
                raise ValueError("Unexpected operator command fields")
            return raw, sig, body
        except (ValueError, TypeError, UnicodeError, binascii.Error) as exc:
            raise PermissionError("Invalid operator command envelope") from exc

    def dispatch(self, connection, *, signed_request, server_now=None):
        """Preview-only signed operator command processing in a caller's TX.

        On the real server, commit the license transition and idempotent result
        BEFORE returning the response over transport. An in-process return
        here is not proof that the caller has committed the transaction.
        """
        self._check(connection)
        clock = _clock(server_now)  # A trusted server clock in a real backend.
        raw, signature, body = self._parse_signed(signed_request)
        operator_id = body.get("operator_id")
        operation = body.get("operation")
        request_id = body.get("request_id")
        if (type(body.get("v")) is not int or body["v"] != 8
                or not _identifier(operator_id)
                or type(operation) is not str or operation not in _OPERATIONS
                or type(request_id) is not str or not _REQUEST_ID.fullmatch(request_id)):
            raise PermissionError("Invalid operator command")
        roster = connection.execute(
            "SELECT role, active, public_key_b64 FROM "
            "v8_preview_activation_operators WHERE operator_id=?",
            (operator_id,),
        ).fetchone()
        if not roster or roster["active"] != 1:
            raise PermissionError("Operator not active on server")
        if operation in ("register", "revoke") and roster["role"] != "Admin":
            raise PermissionError("Server administrator role required")
        if roster["role"] not in ("Admin", "Issuer"):
            raise PermissionError("Operator role denied")
        try:
            public_key = _decode(roster["public_key_b64"], limit=128)
            Ed25519PublicKey.from_public_bytes(public_key).verify(signature, raw)
        except (ValueError, TypeError, binascii.Error, InvalidSignature) as exc:
            raise PermissionError("Operator command signature invalid") from exc

        payload = body.get("payload")
        if type(payload) is not dict or payload.keys() != _OPERATIONS[operation]:
            raise PermissionError("Invalid operation payload")
        try:
            issued = _utc(body.get("issued_utc"))
            expires = _utc(body.get("expires_utc"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise PermissionError("Invalid command freshness") from exc
        if (expires <= issued or expires - issued > timedelta(minutes=10)
                or issued > clock + timedelta(minutes=1) or clock > expires):
            raise PermissionError("Signed operator command expired or future-dated")
        # Never use a client-supplied role, clock, authorization flag or
        # license status. All actor roles/entitlement states come from the DB.
        fingerprint = hashlib.sha256(raw).hexdigest()
        previous = connection.execute(
            "SELECT operation,signed_body_sha256,response_json "
            "FROM v8_preview_activation_commands "
            "WHERE operator_id=? AND request_id=?",
            (operator_id, request_id),
        ).fetchone()
        if previous is not None:
            if (previous["operation"] != operation
                    or previous["signed_body_sha256"] != fingerprint):
                raise ValueError("Operator request ID reused with different command")
            result = json.loads(previous["response_json"])
            # Do not hand out a formerly active receipt after revocation,
            # expiry or superseding issuance, even for a signed retry.
            if operation == "issue":
                decision = self.authority.inspect_current(
                    connection, signed_status=result["signed_status"],
                    license_id=payload["license_id"],
                    machine_id=payload["machine_id"],
                    branch_id=payload["branch_id"], server_now=clock,
                )
                if not decision.receipt_matches_server_state:
                    raise PermissionError("Previously issued receipt is no longer current")
            return PreviewAdminResponse(operation, result, retry=True)

        if operation == "register":
            self.authority.register(connection, server_now=clock, **payload)
            result = {"status": "registered", "license_id": payload["license_id"]}
        elif operation == "revoke":
            self.authority.revoke(connection, **payload)
            result = {"status": "revoked", "license_id": payload["license_id"]}
        else:
            receipt = self.authority.issue(
                connection, server_now=clock, **payload)
            result = {
                "signed_status": receipt.signed_status,
                "sequence": receipt.sequence,
                "status": receipt.status,
            }
        connection.execute(
            "INSERT INTO v8_preview_activation_commands "
            "(operator_id,request_id,operation,signed_body_sha256,"
            "response_json,created_utc) VALUES(?,?,?,?,?,?)",
            (operator_id, request_id, operation, fingerprint,
             json.dumps(result, sort_keys=True, separators=(",", ":")),
             _stamp(clock)),
        )
        return PreviewAdminResponse(operation, result, retry=False)

    def require_checkout(self, *args, **kwargs):
        raise PermissionError("Preview gateway never authorizes POS checkout")
