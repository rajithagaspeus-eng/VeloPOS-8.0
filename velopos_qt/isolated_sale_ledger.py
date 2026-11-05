"""In-memory-only atomic sale/stock/ledger rehearsal; NEVER commercial posting."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import sqlite3
from threading import RLock

from .sale_request_service import rehearse_sale_request
from .sale_plan import plan_preview_sale


@dataclass(frozen=True)
class RehearsalPosting:
    reference: str
    fingerprint: str
    subtotal_cents: int
    replayed: bool
    can_checkout: bool = False
    can_post: bool = False


class IsolatedSaleLedger:
    """Disposable RAM-only simulation; cannot open or mutate POS database."""

    def __init__(self, initial_stock):
        if type(initial_stock) is not dict or not initial_stock:
            raise ValueError("Explicit nonempty test stock required")
        self._lock = RLock()
        self._db = sqlite3.connect(":memory:", isolation_level=None,
                                   check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript("""
            CREATE TABLE stock(barcode TEXT PRIMARY KEY, qty TEXT NOT NULL);
            CREATE TABLE requests(request_id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL, reference TEXT NOT NULL UNIQUE,
                subtotal_cents INTEGER NOT NULL);
            CREATE TABLE items(reference TEXT NOT NULL, barcode TEXT NOT NULL,
                qty TEXT NOT NULL, line_cents INTEGER NOT NULL,
                FOREIGN KEY(reference) REFERENCES requests(reference));
            CREATE TABLE journal(reference TEXT NOT NULL, account TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                FOREIGN KEY(reference) REFERENCES requests(reference));
        """)
        for barcode, qty in initial_stock.items():
            if (type(barcode) is not str or not 1 <= len(barcode) <= 80 or
                    barcode != barcode.strip() or not barcode.isprintable()):
                raise ValueError("Invalid test barcode")
            try:
                amount = Decimal(str(qty))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError("Invalid test quantity") from exc
            if type(qty) is bool or not amount.is_finite() or amount < 0 or amount > 1000000:
                raise ValueError("Invalid test quantity")
            self._db.execute("INSERT INTO stock VALUES (?,?)", (barcode, str(amount)))

    def inspect(self, *, request_id, lines, inject_failure=False):
        """Atomic RAM rehearsal with replay and rollback; no sale authorization."""
        draft = rehearse_sale_request(request_id=request_id, lines=lines)
        plan = plan_preview_sale([json.loads(item) for item in draft.canonical_lines])
        with self._lock:
            db = self._db
            db.execute("BEGIN IMMEDIATE")
            try:
                prior = db.execute(
                    "SELECT fingerprint,reference,subtotal_cents FROM requests WHERE request_id=?",
                    (request_id,)).fetchone()
                if prior:
                    if prior[0] != draft.fingerprint:
                        raise ValueError("Request ID reused with changed sale")
                    result = RehearsalPosting(prior[1], prior[0], prior[2], True)
                    db.execute("COMMIT")
                    return result
                for barcode, qty in plan.quantities:
                    row = db.execute("SELECT qty FROM stock WHERE barcode=?", (barcode,)).fetchone()
                    if row is None or Decimal(row[0]) < qty:
                        raise ValueError("Insufficient test stock")
                number = db.execute("SELECT COUNT(*) FROM requests").fetchone()[0] + 1
                reference = f"RAM-REHEARSAL-{number:08d}"
                db.execute("INSERT INTO requests VALUES (?,?,?,?)",
                           (request_id, draft.fingerprint, reference, draft.subtotal_cents))
                for line in plan.lines:
                    db.execute("INSERT INTO items VALUES (?,?,?,?)",
                               (reference, line.barcode, str(line.qty), int(line.line_total * 100)))
                for barcode, qty in plan.quantities:
                    row = db.execute("SELECT qty FROM stock WHERE barcode=?", (barcode,)).fetchone()
                    db.execute("UPDATE stock SET qty=? WHERE barcode=?",
                               (str(Decimal(row[0]) - qty), barcode))
                db.execute("INSERT INTO journal VALUES (?,?,?)",
                           (reference, "demo_receivable", draft.subtotal_cents))
                if inject_failure:
                    raise RuntimeError("Injected RAM-only rollback")
                db.execute("INSERT INTO journal VALUES (?,?,?)",
                           (reference, "demo_sales", -draft.subtotal_cents))
                db.execute("COMMIT")
                return RehearsalPosting(reference, draft.fingerprint, draft.subtotal_cents, False)
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def snapshot(self):
        with self._lock:
            return {
                "stock": tuple(self._db.execute("SELECT barcode,qty FROM stock ORDER BY barcode")),
                "requests": tuple(self._db.execute("SELECT * FROM requests ORDER BY reference")),
                "items": tuple(self._db.execute("SELECT * FROM items ORDER BY reference,barcode")),
                "journal": tuple(self._db.execute("SELECT * FROM journal ORDER BY reference,account")),
            }

    def reconcile(self):
        """Independently verify demo stock and balanced posting totals.

        Read-only check, not certified accounting or production authorization.
        """
        with self._lock:
            db = self._db
            requests = db.execute(
                "SELECT reference,subtotal_cents FROM requests ORDER BY reference"
            ).fetchall()
            for reference, expected in requests:
                line_total = db.execute(
                    "SELECT COALESCE(SUM(line_cents),0) FROM items WHERE reference=?",
                    (reference,),
                ).fetchone()[0]
                entries = db.execute(
                    "SELECT account,amount_cents FROM journal WHERE reference=?",
                    (reference,),
                ).fetchall()
                if (line_total != expected or len(entries) != 2 or
                        dict(entries) != {"demo_receivable": expected,
                                          "demo_sales": -expected}):
                    raise ValueError("RAM rehearsal accounting mismatch")
            for barcode, raw in db.execute("SELECT barcode,qty FROM stock"):
                amount = Decimal(raw)
                if not amount.is_finite() or amount < 0:
                    raise ValueError("Invalid RAM rehearsal stock")
            return {"reconciled_requests": len(requests),
                    "total_cents": sum(value for _, value in requests),
                    "balanced": True}

    def commit(self, **_claims):
        raise PermissionError("RAM rehearsal cannot post commercial transactions")
