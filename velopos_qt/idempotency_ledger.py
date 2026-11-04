"""Isolated V8 transactional idempotency ledger contract (NOT checkout).

This helper can be used only within a caller-owned, write-locked SQLite
transaction on VeloPOS8PreviewData. A request reservation and all eventual
business mutations MUST commit or roll back together on the same connection.

No existing V7 sale service or Qt checkout path uses this ledger yet.
Creating a journal record does not grant permission to sell.
"""
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .product_editor import _guard


_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}\Z")
_MAX_REQUEST_BYTES = 256 * 1024
_MAX_REQUEST_NODES = 10000
_SCOPES = frozenset({
    "sale", "return", "purchase", "supplier_payment", "credit_payment",
    "points_redemption", "shift_open", "shift_close",
})


class IdempotencyConflict(ValueError):
    """A request key was already used for another immutable payload."""


@dataclass(frozen=True)
class ClaimResult:
    is_new: bool
    result_ref: str | None


def request_fingerprint(payload):
    """Canonical payload digest. No secret data or full payload is stored."""
    if not isinstance(payload, dict):
        raise ValueError("Request payload must be an object")
    # JSON coerces integer object keys to strings. That would make distinct
    # caller payloads share one idempotency fingerprint (e.g. {1: "a"} and
    # {"1": "a"}). Reject ambiguous keys at every nesting level.
    remaining_nodes = _MAX_REQUEST_NODES

    def validate_keys(value, ancestors, depth=0):
        nonlocal remaining_nodes
        remaining_nodes -= 1
        if remaining_nodes < 0:
            raise ValueError("Request payload has too many nodes")
        if depth > 64:
            raise ValueError("Request payload nesting too deep")
        if isinstance(value, (dict, list, tuple)):
            if id(value) in ancestors:
                raise ValueError("Cyclic request payload")
            ancestors = ancestors | {id(value)}
        if isinstance(value, dict):
            if any(type(key) is not str for key in value):
                raise ValueError("Request payload keys must be strings")
            if any(len(key) > _MAX_REQUEST_BYTES for key in value):
                raise ValueError("Request payload too large")
            for child in value.values():
                validate_keys(child, ancestors, depth + 1)
        elif isinstance(value, (list, tuple)):
            for child in value:
                validate_keys(child, ancestors, depth + 1)
        elif isinstance(value, str) and len(value) > _MAX_REQUEST_BYTES:
            raise ValueError("Request payload too large")

    validate_keys(payload, frozenset())
    try:
        serialized = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Unsupported request payload") from exc
    try:
        encoded = serialized.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Unsupported request payload encoding") from exc
    if len(encoded) > _MAX_REQUEST_BYTES:
        raise ValueError("Request payload too large")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class RecoveryInspection:
    """Journal evidence only; never authorization or proof of business posting."""
    state: str
    result_ref: str | None = None


def _valid_result_ref(value):
    return (
        type(value) is str and 1 <= len(value) <= 128
        and value == value.strip() and value.isprintable()
    )


class PreviewIdempotencyLedger:
    """Transactional storage primitive, never a business-action authorization."""

    def __init__(self, database):
        _guard(database)
        self.database = database

    def _check_connection(self, connection):
        _guard(self.database)
        if not connection.in_transaction:
            raise RuntimeError("Idempotency requires a caller-owned transaction")
        databases = connection.execute("PRAGMA database_list").fetchall()
        actual = next(
            (row[2] for row in databases if row[1] == "main"), None
        )
        if not actual or Path(actual).resolve() != Path(self.database.DB_PATH).resolve():
            raise RuntimeError("Idempotency connection must use isolated preview DB")

    @staticmethod
    def _validate_identity(scope, request_id):
        if scope not in _SCOPES:
            raise ValueError("Unknown idempotency scope")
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            raise ValueError("Invalid idempotency request id")

    def inspect_request(self, connection, scope, request_id, payload):
        """Read-only crash/replay triage in a caller-owned preview transaction.

        PENDING and corrupt rows require human reconciliation against the
        business records; this never deletes/retries them or authorizes commerce.
        A COMPLETED journal row alone is NOT proof that an invoice exists.
        """
        self._check_connection(connection)
        self._validate_identity(scope, request_id)
        fingerprint = request_fingerprint(payload)
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='v8_preview_request_journal'"
        ).fetchone()
        if not exists:
            return RecoveryInspection("not_recorded")
        row = connection.execute(
            "SELECT payload_sha256,status,result_ref "
            "FROM v8_preview_request_journal WHERE scope=? AND request_id=?",
            (scope, request_id),
        ).fetchone()
        if row is None:
            return RecoveryInspection("not_recorded")
        if row["payload_sha256"] != fingerprint:
            raise IdempotencyConflict("Request identifier used with different payload")
        if row["status"] == "PENDING" and row["result_ref"] is None:
            return RecoveryInspection("pending_manual_reconciliation")
        if row["status"] == "COMPLETED" and _valid_result_ref(row["result_ref"]):
            return RecoveryInspection("journal_completed_unverified", row["result_ref"])
        return RecoveryInspection("corrupt_manual_reconciliation")

    def claim(self, connection, scope, request_id, payload):
        """Insert pending claim or return completed ref; caller commits/rolls back.

        Never commit here. A pending row from a prior committed transaction
        means incomplete work and is rejected, not silently retried.
        """
        self._check_connection(connection)
        self._validate_identity(scope, request_id)
        fingerprint = request_fingerprint(payload)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS v8_preview_request_journal ("
            "scope TEXT NOT NULL, request_id TEXT NOT NULL, "
            "payload_sha256 TEXT NOT NULL, status TEXT NOT NULL "
            "CHECK(status IN ('PENDING','COMPLETED')), "
            "result_ref TEXT, "
            "CHECK((status='PENDING' AND result_ref IS NULL) OR "
            "(status='COMPLETED' AND result_ref IS NOT NULL "
            "AND length(result_ref)>0)), "
            "PRIMARY KEY(scope,request_id))"
        )
        row = connection.execute(
            "SELECT payload_sha256,status,result_ref "
            "FROM v8_preview_request_journal WHERE scope=? AND request_id=?",
            (scope, request_id),
        ).fetchone()
        if row:
            if row["payload_sha256"] != fingerprint:
                raise IdempotencyConflict("Request identifier used with different payload")
            if row["status"] != "COMPLETED" or not _valid_result_ref(row["result_ref"]):
                raise RuntimeError("Previous request has no trustworthy committed result")
            return ClaimResult(False, row["result_ref"])
        connection.execute(
            "INSERT INTO v8_preview_request_journal "
            "(scope,request_id,payload_sha256,status) VALUES(?,?,?,'PENDING')",
            (scope, request_id, fingerprint),
        )
        return ClaimResult(True, None)

    def complete(self, connection, scope, request_id, result_ref):
        """Attach the result of work in the SAME uncommitted transaction."""
        self._check_connection(connection)
        if scope not in _SCOPES:
            raise ValueError("Unknown idempotency scope")
        if not _valid_result_ref(result_ref):
            raise ValueError("Invalid result reference")
        updated = connection.execute(
            "UPDATE v8_preview_request_journal SET status='COMPLETED', "
            "result_ref=? WHERE scope=? AND request_id=? AND status='PENDING'",
            (result_ref, scope, request_id),
        )
        if updated.rowcount != 1:
            raise RuntimeError("No pending idempotency claim to complete")
