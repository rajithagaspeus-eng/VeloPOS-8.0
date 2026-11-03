"""Read-only stock and price readiness signals for a draft bill.

A green preview is NOT a permission to commit: original create_sale must
re-check units, batches, oversell settings, prices, stock and open shift
inside its own transaction. This module intentionally performs no writes.
"""
from decimal import Decimal
from .product_editor import _guard


class DraftStockReader:
    def __init__(self, database):
        _guard(database)
        self.database = database

    def inspect(self, cart):
        _guard(self.database)
        results = []
        with self.database.db() as connection:
            for item in cart.lines.values():
                row = connection.execute(
                    "SELECT name_en, stock_qty, selling_price FROM products WHERE barcode=?",
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
                elif Decimal(str(row["selling_price"] or 0)) != item["price"]:
                    results.append({"barcode": item["barcode"], "status": "price_changed"})
        return results
