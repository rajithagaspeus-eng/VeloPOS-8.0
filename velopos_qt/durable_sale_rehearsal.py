"""Durable, test-only SQLite replay ledger for disposable V8 rehearsals.

No production DB connection, real invoice, stock movement, or financial posting.
Only explicitly named databases in the system temporary directory are allowed.
"""
from contextlib import contextmanager
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
        if candidate.exists() and (not candidate.is_file() or candidate.stat().st_nlink != 1):
            raise PermissionError("Shared or nonregular preview database refused")
        self.path = str(candidate)
        self._file_identity = None
        self.max_requests = max_requests
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._initialize(conn)
                # Validate the file before committing, while the write lock
                # is still held; never attempt ROLLBACK after COMMIT.
                identity = self._identity()
                conn.execute("COMMIT")
                self._file_identity = identity
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    def _initialize(self, conn):
            # Refuse pre-existing triggers/views before any initialization SQL.
            preexisting = conn.execute(
                "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
            allowed = {
                ("table", "preview_rehearsals"),
                ("table", "preview_sequence"),
            }
            if not set(preexisting).issubset(allowed):
                raise PermissionError("Unexpected preview database objects")
            expected_existing = {
                "preview_rehearsals": ("request_id", "fingerprint", "reference"),
                "preview_sequence": ("singleton", "next_number"),
            }
            for kind, name in preexisting:
                columns = conn.execute(f"PRAGMA table_info({name})").fetchall()
                if tuple(column[1] for column in columns) != expected_existing[name]:
                    raise PermissionError("Unexpected preview database schema")
            conn.execute("""CREATE TABLE IF NOT EXISTS preview_rehearsals (
                request_id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                reference TEXT NOT NULL UNIQUE
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS preview_sequence (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                next_number INTEGER NOT NULL CHECK(next_number > 0)
            )""")
            # Do not silently heal a missing sequence in an existing ledger.
            previous_count = conn.execute(
                "SELECT COUNT(*) FROM preview_rehearsals"
            ).fetchone()[0]
            sequence_count = conn.execute(
                "SELECT COUNT(*) FROM preview_sequence"
            ).fetchone()[0]
            if previous_count and not sequence_count:
                raise PermissionError("Missing sequence in existing preview journal")
            if not sequence_count:
                if preexisting:
                    raise PermissionError("Missing sequence in existing preview journal")
                conn.execute(
                    "INSERT INTO preview_sequence(singleton,next_number) VALUES (1,1)"
                )
            # An existing preview file is untrusted: refuse extra triggers,
            # tables or views instead of executing attacker-supplied SQL.
            objects = conn.execute(
                "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if set(objects) != {
                ("table", "preview_rehearsals"),
                ("table", "preview_sequence"),
            }:
                raise PermissionError("Unexpected preview database objects")
            expected_columns = {
                "preview_rehearsals": ("request_id", "fingerprint", "reference"),
                "preview_sequence": ("singleton", "next_number"),
            }
            for table, names in expected_columns.items():
                columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
                if tuple(col[1] for col in columns) != names:
                    raise PermissionError("Unexpected preview database schema")
            self._check_constraints(conn)

    @staticmethod
    def _check_constraints(conn):
        for table, key in (
            ("preview_rehearsals", "request_id"),
            ("preview_sequence", "singleton"),
        ):
            columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
            if tuple(col[1] for col in columns if col[5] > 0) != (key,):
                raise PermissionError("Missing preview primary key")
        # SQLite's quick_check does not establish application-level NOT NULL
        # or CHECK constraints; verify the required declared column flags.
        for table, required in (
            ("preview_rehearsals", ("fingerprint", "reference")),
            ("preview_sequence", ("next_number",)),
        ):
            columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
            for col in columns:
                if col[1] in required and col[3] != 1:
                    raise PermissionError("Missing preview NOT NULL constraint")
        indexes = conn.execute(
            "PRAGMA index_list(preview_rehearsals)"
        ).fetchall()
        if not any(
            index[2] == 1 and
            tuple(col[2] for col in conn.execute(
                f"PRAGMA index_info({index[1]})"
            ).fetchall()) == ("reference",)
            for index in indexes
        ):
            raise PermissionError("Missing unique preview reference constraint")

    def _identity(self):
        candidate = Path(self.path)
        if candidate.is_symlink() or not candidate.is_file():
            raise PermissionError("Preview database file replaced")
        stat = candidate.stat()
        if stat.st_nlink != 1:
            raise PermissionError("Preview database hard link refused")
        return (stat.st_dev, stat.st_ino)

    @contextmanager
    def _connect(self):
        if self._file_identity is not None and self._identity() != self._file_identity:
            raise PermissionError("Preview database file replaced")
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            if self._file_identity is not None and self._identity() != self._file_identity:
                raise PermissionError("Preview database changed during open")
            if self._file_identity is not None:
                # Reject a swapped path even when SQLite opened an old inode.
                db_file = conn.execute("PRAGMA database_list").fetchone()[2]
                if Path(db_file).resolve() != Path(self.path).resolve():
                    raise PermissionError("Unexpected SQLite database attachment")
            # An untrusted preview file must not be able to attach external
            # databases or invoke trusted schema functions via SQL objects.
            conn.execute("PRAGMA trusted_schema=OFF")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=10000")
            yield conn
        finally:
            conn.close()

    def inspect(self, *, request_id, lines):
        draft = rehearse_sale_request(request_id=request_id, lines=lines)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                objects = conn.execute(
                    "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                ).fetchall()
                if set(objects) != {
                    ("table", "preview_rehearsals"),
                    ("table", "preview_sequence"),
                }:
                    raise PermissionError("Unexpected preview database objects")
                for table, names in {
                    "preview_rehearsals": ("request_id", "fingerprint", "reference"),
                    "preview_sequence": ("singleton", "next_number"),
                }.items():
                    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
                    if tuple(col[1] for col in columns) != names:
                        raise PermissionError("Unexpected preview database schema")
                self._check_constraints(conn)
                integrity = conn.execute("PRAGMA quick_check").fetchall()
                if integrity != [("ok",)]:
                    raise PermissionError("Preview SQLite integrity check failed")
                # Verify the complete disposable journal before returning any
                # replay, including entries unrelated to the current request.
                rows = conn.execute(
                    "SELECT fingerprint,reference FROM preview_rehearsals"
                ).fetchall()
                for stored_fingerprint, stored_reference in rows:
                    if (type(stored_fingerprint) is not str or
                            _DIGEST.fullmatch(stored_fingerprint) is None or
                            type(stored_reference) is not str or
                            _REFERENCE.fullmatch(stored_reference) is None):
                        raise PermissionError("Corrupt preview replay record")
                sequence_rows = conn.execute(
                    "SELECT singleton,next_number FROM preview_sequence"
                ).fetchall()
                if (len(sequence_rows) != 1 or
                        type(sequence_rows[0][0]) is not int or
                        sequence_rows[0][0] != 1 or
                        type(sequence_rows[0][1]) is not int or
                        not 1 <= sequence_rows[0][1] <= 100000000):
                    raise PermissionError("Corrupt preview sequence")
                seen_refs = set()
                for index, (stored_fingerprint, stored_reference) in enumerate(rows, 1):
                    if stored_reference in seen_refs:
                        raise PermissionError("Duplicate preview reference")
                    seen_refs.add(stored_reference)
                expected_refs = {
                    f"REHEARSAL-{index:08d}"
                    for index in range(1, len(rows) + 1)
                }
                if (seen_refs != expected_refs or
                        sequence_rows[0][1] != len(rows) + 1):
                    raise PermissionError("Preview sequence or reference chain corrupted")
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
                    number = sequence_rows[0][1]
                    if number > 99999999:
                        raise OverflowError("Preview sequence exhausted")
                    reference = f"REHEARSAL-{number:08d}"
                    conn.execute(
                        "INSERT INTO preview_rehearsals "
                        "(request_id,fingerprint,reference) VALUES (?,?,?)",
                        (request_id,draft.fingerprint,reference)
                    )
                    conn.execute(
                        "UPDATE preview_sequence SET next_number=? WHERE singleton=1",
                        (number+1,)
                    )
                    result = DurableRehearsalResult(
                        reference, draft.fingerprint, False
                    )
                conn.execute("COMMIT")
                return result
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    def commit(self, **_claims):
        raise PermissionError("Preview durable journal cannot post sales")
