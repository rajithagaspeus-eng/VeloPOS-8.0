"""Test-only product writes through the original audited VeloPOS stock service.

NEVER construct this adapter for production data or expose its operations in
commercial mode before proper login, permissions and QA are implemented.
"""
from pathlib import Path
from decimal import Decimal, InvalidOperation


def _guard(database):
    expected = Path(database.DATA_DIR).resolve()
    actual_db = Path(database.DB_PATH).resolve()
    if expected.name.casefold() != "velopos8previewdata" or actual_db != expected / "velopos.db":
        raise RuntimeError("Product editing is disabled outside isolated VeloPOS8PreviewData")
    # The original service uses the module-global database settings/connection.
    # Reject lookalike database objects backed by another directory.
    from velopos import database as canonical
    if Path(canonical.DB_PATH).resolve() != actual_db:
        raise RuntimeError("Preview database and original service do not match")


def _number(value, field, *, max_value):
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field}: enter a valid number") from exc
    if not result.is_finite() or result < 0 or result > Decimal(str(max_value)):
        raise ValueError(f"{field}: must be between 0 and {max_value}")
    return float(result)


class PreviewProductEditor:
    """Create/update products in TEST storage using services.save_product."""

    def __init__(self, database, save_fn=None):
        _guard(database)
        self.database = database
        if save_fn is None:
            from velopos.services import save_product
            save_fn = save_product
        self._save = save_fn

    def get(self, barcode):
        _guard(self.database)
        with self.database.db() as connection:
            row = connection.execute(
                "SELECT barcode, name_en, name_local, selling_price, stock_qty "
                "FROM products WHERE barcode=?", (barcode,)
            ).fetchone()
        return dict(row) if row else None

    def save(self, barcode, name_en, *, name_local="", sell="0", stock="0"):
        _guard(self.database)
        barcode = str(barcode).strip()
        name_en = " ".join(str(name_en).split())
        if not barcode or len(barcode) > 80:
            raise ValueError("Barcode must be 1 to 80 characters")
        if not name_en or len(name_en) > 120:
            raise ValueError("Product name must be 1 to 120 characters")
        if len(str(name_local)) > 120:
            raise ValueError("Local name is too long")
        selling = _number(sell, "Price", max_value=100000000)
        quantity = _number(stock, "Stock", max_value=1000000)
        # save_product upserts all product metadata, so omitted fields would
        # otherwise be silently reset. Carry them through when editing.
        with self.database.db() as connection:
            existing = connection.execute(
                "SELECT keywords, wholesale_price, expiry_date, warranty "
                "FROM products WHERE barcode=?", (barcode,)
            ).fetchone()
        metadata = {} if existing is None else {
            "keywords": existing["keywords"] or "",
            "wholesale": existing["wholesale_price"] or 0,
            "expiry": existing["expiry_date"] or "",
            "warranty": existing["warranty"] or "",
        }
        # Original audited service preserves cost, category, taxation, image
        # and stock ledger. Other existing metadata is forwarded explicitly.
        return self._save(
            barcode, name_en, "v8-preview",
            name_local=str(name_local).strip(),
            sell=selling, stock=quantity, add=0,
            reason="V8 preview inventory edit", **metadata,
        )
