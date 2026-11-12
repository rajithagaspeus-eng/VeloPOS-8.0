"""Safe, read-only smart inventory insights from the existing VeloPOS ledger.

No supplier purchase, stock movement or sale is created here. Alerts are
informational; batch tracking and expiry rules at checkout still belong to the
original services. Admin gate is enforced again at the reader boundary.
"""
from datetime import date, timedelta

from .product_editor import _guard


class InventoryInsightsReader:
    def __init__(self, database, authorize=None):
        _guard(database)
        self.database = database
        self.authorize = authorize

    def snapshot(self, low_level=5, expiry_days=30, limit=30, today=None):
        _guard(self.database)
        if self.authorize is not None and not self.authorize():
            raise PermissionError("Preview Admin sign-in required for stock insights")
        # Reject fractional, boolean and non-finite filters instead of
        # silently truncating them into misleading stock/expiry results.
        def bounded_integer(value, name):
            if isinstance(value, bool):
                raise ValueError("Invalid " + name)
            try:
                parsed = int(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Invalid " + name) from exc
            if str(value).strip() != str(parsed):
                raise ValueError("Invalid " + name)
            return parsed

        low_level = bounded_integer(low_level, "stock threshold")
        expiry_days = bounded_integer(expiry_days, "expiry window")
        limit = bounded_integer(limit, "result limit")
        if not 0 <= low_level <= 100000 or not 0 <= expiry_days <= 365:
            raise ValueError("Invalid stock threshold or expiry window")
        limit = max(1, min(limit, 100))
        current_date = date.today() if today is None else date.fromisoformat(str(today))
        start = current_date.isoformat()
        until = (current_date + timedelta(days=expiry_days)).isoformat()
        with self.database.db() as connection:
            low_count = connection.execute(
                "SELECT COUNT(*) FROM products WHERE COALESCE(stock_qty,0)<=?",
                (low_level,),
            ).fetchone()[0]
            low_rows = connection.execute(
                "SELECT barcode, name_en, COALESCE(stock_qty,0) stock_qty "
                "FROM products WHERE COALESCE(stock_qty,0)<=? "
                "ORDER BY stock_qty, name_en, barcode LIMIT ?",
                (low_level, limit),
            ).fetchall()
            # Both product-level expiry and active batches count, but a product
            # is counted only once, even when several batches are expiring.
            expiry_sql = (
                "SELECT p.barcode, p.name_en, "
                "MIN(COALESCE(NULLIF(p.expiry_date,''),'9999-12-31'), "
                "COALESCE((SELECT MIN(b.expiry_date) FROM batches b "
                "WHERE b.barcode=p.barcode AND b.qty_remaining>0 "
                "AND b.expiry_date<>''),'9999-12-31')) expiry_date "
                "FROM products p WHERE COALESCE(p.stock_qty,0)>0 "
                "AND ((p.expiry_date<>'' AND p.expiry_date<=?) "
                "OR EXISTS (SELECT 1 FROM batches b "
                "WHERE b.barcode=p.barcode AND b.qty_remaining>0 "
                "AND b.expiry_date<>'' AND b.expiry_date<=?))"
            )
            expiring = [dict(row) for row in connection.execute(
                expiry_sql + " ORDER BY expiry_date, name_en, barcode LIMIT ?",
                (until, until, limit),
            ).fetchall()]
            expired_count = connection.execute(
                "SELECT COUNT(*) FROM products p "
                "WHERE COALESCE(p.stock_qty,0)>0 AND "
                "((p.expiry_date<>'' AND p.expiry_date<?) "
                "OR EXISTS (SELECT 1 FROM batches b WHERE b.barcode=p.barcode "
                "AND b.qty_remaining>0 AND b.expiry_date<>'' AND b.expiry_date<?))",
                (start, start),
            ).fetchone()[0]
            expiring_count = connection.execute(
                "SELECT COUNT(*) FROM products p "
                "WHERE COALESCE(p.stock_qty,0)>0 AND "
                "((p.expiry_date<>'' AND p.expiry_date BETWEEN ? AND ?) "
                "OR EXISTS (SELECT 1 FROM batches b WHERE b.barcode=p.barcode "
                "AND b.qty_remaining>0 AND b.expiry_date BETWEEN ? AND ?))",
                (start, until, start, until),
            ).fetchone()[0]
            movements = [dict(row) for row in connection.execute(
                "SELECT m.ts, m.barcode, COALESCE(p.name_en,'') name_en, "
                "m.qty_change, m.qty_after, m.reason, m.user "
                "FROM stock_moves m LEFT JOIN products p ON p.barcode=m.barcode "
                "ORDER BY m.id DESC LIMIT ?", (limit,),
            ).fetchall()]
        return {
            "low_count": low_count,
            # Reorder hint is deliberately simple: raise stock ABOVE the
            # chosen alert threshold. It is not a forecast or purchase order.
            "low_rows": [
                {
                    **dict(row),
                    "suggested_topup": round(
                        max(0.0, low_level + 1 - float(row["stock_qty"])), 3
                    ),
                }
                for row in low_rows
            ],
            "expired_count": expired_count,
            "expiring_count": expiring_count,
            "expiry_rows": expiring,
            "movements": movements,
            "checked_on": start,
            "expiry_through": until,
        }
