"""Read-only preview dashboard snapshot.

Counts are calculated from isolated preview data. No fabricated sales figures
or live customer data are shown. There is no caching of stock/financial truth.
"""
from pathlib import Path


class DashboardReader:
    def __init__(self, database):
        if database is None:
            raise ValueError("Dashboard requires an isolated preview database")
        self.database = database

    def snapshot(self, *, low_stock_limit=5):
        db = self.database
        expected = Path(db.DATA_DIR).resolve()
        actual = Path(db.DB_PATH).resolve()
        if expected.name.casefold() != "velopos8previewdata" or actual != expected / "velopos.db":
            raise RuntimeError("Dashboard is disabled outside the isolated preview database")
        low_stock_limit = max(0, min(int(low_stock_limit), 100))
        with db.db() as connection:
            # A single read-only connection keeps numbers internally consistent.
            products = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            customers = connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
            suppliers = connection.execute("SELECT COUNT(*) FROM suppliers WHERE active=1").fetchone()[0]
            low_stock = connection.execute(
                "SELECT COUNT(*) FROM products WHERE stock_qty <= ?", (low_stock_limit,)
            ).fetchone()[0]
            alerts = connection.execute(
                "SELECT barcode, name_en, stock_qty FROM products "
                "WHERE stock_qty <= ? ORDER BY stock_qty, name_en LIMIT 6",
                (low_stock_limit,)
            ).fetchall()
        return {
            "products": products,
            "customers": customers,
            "suppliers": suppliers,
            "low_stock": low_stock,
            "alerts": [dict(record) for record in alerts],
        }
