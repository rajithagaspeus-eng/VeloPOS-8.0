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
    def validate_keys(value, ancestors, depth=0):
        if depth > 64:
            raise ValueError("Request payload nesting too deep")
        if isinstance(value, (dict, list, tuple)):
            if id(value) in ancestors:
                raise ValueError("Cyclic request payload")
            ancestors = ancestors | {id(value)}
        if isinstance(value, dict):
            if any(type(key) is not str for key in value):
                raise ValueError("Request payload keys must be strings")
            for child in value.values():
                validate_keys(child, ancestors, depth + 1)
        elif isinstance(value, (list, tuple)):
            for child in value:
                validate_keys(child, ancestors, depth + 1)

    validate_keys(payload, frozenset())
    try:
        serialized = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Unsupported request payload") from exc
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


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

    def claim(self, connection, scope, request_id, payload):
        """Insert pending claim or return completed ref; caller commits/rolls back.

        Never commit here. A pending row from a prior committed transaction
        means incomplete work and is rejected, not silently retried.
        """
        self._check_connection(connection)
        if scope not in _SCOPES:
            raise ValueError("Unknown idempotency scope")
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            raise ValueError("Invalid idempotency request id")
        fingerprint = request_fingerprint(payload)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS v8_preview_request_journal ("
            "scope TEXT NOT NULL, request_id TEXT NOT NULL, "
            "payload_sha256 TEXT NOT NULL, status TEXT NOT NULL "
            "CHECK(status IN ('PENDING','COMPLETED')), "
            "result_ref TEXT, PRIMARY KEY(scope,request_id))"
        )
        row = connection.execute(
            "SELECT payload_sha256,status,result_ref "
            "FROM v8_preview_request_journal WHERE scope=? AND request_id=?",
            (scope, request_id),
        ).fetchone()
        if row:
            if row["payload_sha256"] != fingerprint:
                raise IdempotencyConflict("Request identifier used with different payload")
            if row["status"] != "COMPLETED":
                raise RuntimeError("Previous request has no committed result")
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
        if not isinstance(result_ref, str) or not 1 <= len(result_ref) <= 128:
            raise ValueError("Invalid result reference")
        updated = connection.execute(
            "UPDATE v8_preview_request_journal SET status='COMPLETED', "
            "result_ref=? WHERE scope=? AND request_id=? AND status='PENDING'",
            (result_ref, scope, request_id),
        )
        if updated.rowcount != 1:
            raise RuntimeError("No pending idempotency claim to complete")
