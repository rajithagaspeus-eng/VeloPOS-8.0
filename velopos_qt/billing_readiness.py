"""Read-only stock and price readiness signals for a draft bill.

A green preview is NOT a permission to commit: original create_sale must
re-check units, batches, oversell settings, prices, stock and open shift
inside its own transaction. This module intentionally performs no writes.
"""
from datetime import date
from decimal import Decimal
from .product_editor import _guard


class DraftStockReader:
    def __init__(self, database):
        _guard(database)
        self.database = database

    def inspect(self, cart, today=None):
        _guard(self.database)
        current_day = date.today().isoformat() if today is None else date.fromisoformat(str(today)).isoformat()
        results = []
        with self.database.db() as connection:
            for item in cart.lines.values():
                row = connection.execute(
                    "SELECT name_en, stock_qty, selling_price, expiry_date FROM products WHERE barcode=?",
                    (item["barcode"],),
                ).fetchone()
                if row is None:
                    results.append({"barcode": item["barcode"], "status": "missing"})
                elif Decimal(str(row["stock_qty"] or 0)) < item["qty"]:
                    results.append({
                        "barcode": item["barcode"],
                        "status": "insufficient",
                        "available": str(row["stock_qty"] or 0),
                    })
                elif row["expiry_date"] and row["expiry_date"] < current_day:
                    results.append({"barcode": item["barcode"], "status": "expired"})
                elif connection.execute(
                    "SELECT 1 FROM batches WHERE barcode=? AND qty_remaining>0 "
                    "AND expiry_date<>'' AND expiry_date<? LIMIT 1",
                    (item["barcode"], current_day),
                ).fetchone():
                    results.append({"barcode": item["barcode"], "status": "expired_batch"})
                elif Decimal(str(row["selling_price"] or 0)) != item["price"]:
                    results.append({"barcode": item["barcode"], "status": "price_changed"})
        return results
