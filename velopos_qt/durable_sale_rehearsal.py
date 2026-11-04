"""Durable, test-only SQLite replay ledger for disposable V8 rehearsals.

No production DB connection, real invoice, stock movement, or financial posting.
Only explicitly named databases in the system temporary directory are allowed.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
import tempfile

from .sale_request_service import rehearse_sale_request

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REFERENCE = re.compile(r"REHEARSAL-[0-9]{8,}\Z")


@dataclass(frozen=True)
class DurableRehearsalResult:
    reference: str
    fingerprint: str
    replayed: bool
    can_checkout: bool = False
    can_post: bool = False


class DurablePreviewSaleJournal:
    """SQLite transactionally records only noncommercial replay diagnostics."""

    def __init__(self, path, *, max_requests=10000):
        if type(max_requests) is not int or not 1 <= max_requests <= 100000:
            raise ValueError("Invalid preview journal capacity")
        if type(path) is not str:
            raise ValueError("Use a disposable preview SQLite path")
        candidate = Path(path)
        # Reject symlinks and paths outside the OS temp directory. Require
        # a distinctive preview-only basename; never attach the POS database.
        temp = Path(tempfile.gettempdir()).resolve()
        if (candidate.is_symlink() or candidate.parent.resolve() != temp or
                not re.fullmatch(r"v8-preview-rehearsal-[A-Za-z0-9_-]{1,60}\.sqlite",
                                 candidate.name)):
            raise PermissionError("Only disposable V8 preview databases are allowed")
        self.path = str(candidate)
        self.max_requests = max_requests
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS preview_rehearsals (
                request_id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                reference TEXT NOT NULL UNIQUE
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS preview_sequence (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                next_number INTEGER NOT NULL CHECK(next_number > 0)
            )""")
            conn.execute(
                "INSERT OR IGNORE INTO preview_sequence(singleton,next_number) VALUES (1,1)"
            )

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def inspect(self, *, request_id, lines):
        draft = rehearse_sale_request(request_id=request_id, lines=lines)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT fingerprint,reference FROM preview_rehearsals "
                    "WHERE request_id=?", (request_id,)
                ).fetchone()
                if existing is not None:
                    fingerprint, reference = existing
                    if (type(fingerprint) is not str or
                            _DIGEST.fullmatch(fingerprint) is None or
                            type(reference) is not str or
                            _REFERENCE.fullmatch(reference) is None):
                        raise PermissionError("Corrupt preview replay record")
                    if fingerprint != draft.fingerprint:
                        raise ValueError("Preview request id reused with different payload")
                    result = DurableRehearsalResult(reference, fingerprint, True)
                else:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM preview_rehearsals"
                    ).fetchone()[0]
                    if count >= self.max_requests:
                        raise OverflowError("Preview journal capacity exceeded")
                    number = conn.execute(
                        "SELECT next_number FROM preview_sequence WHERE singleton=1"
                    ).fetchone()
                    if (number is None or type(number[0]) is not int or
                            not 1 <= number[0] <= 99999999):
                        raise PermissionError("Corrupt preview sequence")
                    reference = f"REHEARSAL-{number[0]:08d}"
                    conn.execute(
                        "INSERT INTO preview_rehearsals "
                        "(request_id,fingerprint,reference) VALUES (?,?,?)",
                        (request_id,draft.fingerprint,reference)
                    )
                    conn.execute(
                        "UPDATE preview_sequence SET next_number=? WHERE singleton=1",
                        (number[0]+1,)
                    )
                    result = DurableRehearsalResult(
                        reference, draft.fingerprint, False
                    )
                conn.execute("COMMIT")
                return result
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def commit(self, **_claims):
        raise PermissionError("Preview durable journal cannot post sales")
