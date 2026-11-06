"""In-memory-only atomic sale/stock/ledger rehearsal; NEVER commercial posting."""
from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext
import json
import re
import sqlite3
from threading import RLock

from .sale_request_service import rehearse_sale_request
from .sale_plan import plan_preview_sale

_RECONCILE_CONTEXT = Context(prec=512)
_PERSISTED_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}\\Z")


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
        self._initial_stock = {}
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
                raw_qty = str(qty)
                if len(raw_qty) > 128:
                    raise ValueError("Test quantity representation too long")
                amount = Decimal(raw_qty)
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError("Invalid test quantity") from exc
            if (type(qty) is bool or not amount.is_finite() or
                    amount < 0 or amount > 1000000 or
                    (amount != 0 and not -18 <= amount.adjusted() <= 18)):
                raise ValueError("Invalid test quantity")
            self._db.execute("INSERT INTO stock VALUES (?,?)", (barcode, str(amount)))
            self._initial_stock[barcode] = amount

    def inspect(self, *, request_id, lines, inject_failure=False):
        """Atomic RAM rehearsal with replay and rollback; no sale authorization."""
        draft = rehearse_sale_request(request_id=request_id, lines=lines)
        plan = plan_preview_sale([json.loads(item) for item in draft.canonical_lines])
        with self._lock:
            # Refuse to append to a corrupted rehearsal history, including
            # replay attempts. This is a disposable diagnostic, not recovery.
            self.reconcile()
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
                    with localcontext(_RECONCILE_CONTEXT):
                        remaining = Decimal(row[0]) - qty
                    db.execute("UPDATE stock SET qty=? WHERE barcode=?",
                               (str(remaining), barcode))
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
            if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("RAM rehearsal SQLite integrity mismatch")
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("RAM rehearsal foreign key mismatch")
            requests = db.execute(
                "SELECT reference,subtotal_cents FROM requests ORDER BY reference"
            ).fetchall()
            metadata = db.execute(
                "SELECT request_id,fingerprint,reference FROM requests ORDER BY reference"
            ).fetchall()
            for number, (request_id, fingerprint, reference) in enumerate(metadata, 1):
                if (type(request_id) is not str or
                        _PERSISTED_REQUEST_ID.fullmatch(request_id) is None or
                        type(fingerprint) is not str or len(fingerprint) != 64 or
                        any(ch not in "0123456789abcdef" for ch in fingerprint) or
                        reference != f"RAM-REHEARSAL-{number:08d}"):
                    raise ValueError("RAM rehearsal request metadata mismatch")
            for reference, expected in requests:
                # SQLite INTEGER affinity does not prevent a corrupted row
                # from containing TEXT/REAL; refuse it before arithmetic.
                if type(expected) is not int or expected < 0:
                    raise ValueError("RAM rehearsal subtotal mismatch")
                line_amounts = db.execute(
                    "SELECT line_cents FROM items WHERE reference=?",
                    (reference,),
                ).fetchall()
                if (not line_amounts or any(
                        type(row[0]) is not int or row[0] < 0
                        for row in line_amounts)):
                    raise ValueError("RAM rehearsal item amount mismatch")
                line_total = sum(row[0] for row in line_amounts)
                entries = db.execute(
                    "SELECT account,amount_cents FROM journal WHERE reference=?",
                    (reference,),
                ).fetchall()
                if (line_total != expected or len(entries) != 2 or
                        any(type(account) is not str or type(amount) is not int
                            for account, amount in entries) or
                        dict(entries) != {"demo_receivable": expected,
                                          "demo_sales": -expected}):
                    raise ValueError("RAM rehearsal accounting mismatch")
            stock = dict(db.execute("SELECT barcode,qty FROM stock"))
            if set(stock) != set(self._initial_stock):
                raise ValueError("RAM rehearsal stock catalog mismatch")
            consumed = {barcode: Decimal("0") for barcode in self._initial_stock}
            for reference, barcode, raw_qty in db.execute(
                    "SELECT reference,barcode,qty FROM items"):
                if barcode not in consumed:
                    raise ValueError("Unknown RAM rehearsal item")
                if type(raw_qty) is not str or len(raw_qty) > 128:
                    raise ValueError("Invalid RAM rehearsal item quantity")
                try:
                    qty = Decimal(raw_qty)
                except InvalidOperation as exc:
                    raise ValueError("Invalid RAM rehearsal item quantity") from exc
                if (not qty.is_finite() or qty <= 0 or qty > 1000000 or
                        not -18 <= qty.adjusted() <= 18):
                    raise ValueError("Invalid RAM rehearsal item quantity")
                with localcontext(_RECONCILE_CONTEXT):
                    consumed[barcode] += qty
            with localcontext(_RECONCILE_CONTEXT):
                for barcode, raw in stock.items():
                    if type(raw) is not str or len(raw) > 128:
                        raise ValueError("Invalid RAM rehearsal stock")
                    try:
                        amount = Decimal(raw)
                    except InvalidOperation as exc:
                        raise ValueError("Invalid RAM rehearsal stock") from exc
                    if (not amount.is_finite() or amount < 0 or amount > 1000000 or
                            (amount != 0 and not -18 <= amount.adjusted() <= 18) or
                            amount != self._initial_stock[barcode] - consumed[barcode]):
                        raise ValueError("RAM rehearsal stock movement mismatch")
            for table in ("items", "journal"):
                orphan = db.execute(
                    f"SELECT 1 FROM {table} AS detail LEFT JOIN requests AS r "
                    "ON detail.reference=r.reference "
                    "WHERE r.reference IS NULL LIMIT 1"
                ).fetchone()
                if orphan:
                    raise ValueError("Orphan RAM rehearsal entry")
            return {"reconciled_requests": len(requests),
                    "total_cents": sum(value for _, value in requests),
                    "balanced": True}

    def commit(self, **_claims):
        raise PermissionError("RAM rehearsal cannot post commercial transactions")
