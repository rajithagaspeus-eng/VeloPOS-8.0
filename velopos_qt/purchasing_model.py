"""Read-only purchasing dashboard on original VeloPOS tables.

This module does not create purchase orders, GRNs, supplier payments or stock.
It is an information/validation foundation, not production purchasing.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from .product_editor import _guard


def preview_purchase_line(qty, unit_cost):
    """Estimate one GRN line without silently rounding quantity."""
    try:
        q, cost = Decimal(str(qty).strip()), Decimal(str(unit_cost).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Invalid quantity or cost") from exc
    if not q.is_finite() or not cost.is_finite() or q <= 0 or q > 1000000:
        raise ValueError("Invalid quantity")
    if not cost.is_finite() or cost < 0 or cost > 100000000:
        raise ValueError("Invalid unit cost")
    return (q * cost).quantize(Decimal("0.01"))


class PurchaseOverviewReader:
    def __init__(self, database, authorize):
        _guard(database)
        self.database = database
        self.authorize = authorize

    def snapshot(self, *, limit=30, start=None, end=None):
        _guard(self.database)
        if not self.authorize():
            raise PermissionError("Preview Admin sign-in required for purchasing overview")
        limit = max(1, min(int(limit), 100))
        start = str(start) if start is not None else "0001-01-01"
        end = str(end) if end is not None else "9999-12-31"
        for day in (start, end):
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError("Invalid date")
        if start > end:
            raise ValueError("Invalid date range")
        with self.database.db() as c:
            totals = c.execute(
                "SELECT COUNT(*) purchase_count, COALESCE(SUM(total),0) total, "
                "COALESCE(SUM(paid),0) paid "
                "FROM purchases WHERE status='OK' AND date BETWEEN ? AND ?",
                (start, end),
            ).fetchone()
            rows = c.execute(
                "SELECT p.grn_no, p.date, s.name supplier, p.total, p.paid, "
                "p.status FROM purchases p "
                "LEFT JOIN suppliers s ON s.id=p.supplier_id "
                "WHERE p.date BETWEEN ? AND ? "
                "ORDER BY p.date DESC, p.id DESC LIMIT ?",
                (start, end, limit),
            ).fetchall()
            # The original service calculates supplier balance as ALL valid
            # GRNs minus ALL supplier_payments, including later settlements.
            # Group each side first: joining payments directly to purchases
            # would multiply rows and overstate totals.
            balances = c.execute(
                "SELECT s.id, s.name, "
                "COALESCE(p.bought,0) bought, COALESCE(sp.paid,0) paid "
                "FROM suppliers s "
                "LEFT JOIN (SELECT supplier_id, SUM(total) bought "
                "FROM purchases WHERE status='OK' GROUP BY supplier_id) p "
                "ON p.supplier_id=s.id "
                "LEFT JOIN (SELECT supplier_id, SUM(amount) paid "
                "FROM supplier_payments GROUP BY supplier_id) sp "
                "ON sp.supplier_id=s.id "
                "ORDER BY s.name COLLATE NOCASE, s.id"
            ).fetchall()
            suppliers = c.execute(
                "SELECT id, name FROM suppliers WHERE active=1 "
                "ORDER BY name COLLATE NOCASE, id LIMIT ?",
                (limit,),
            ).fetchall()
        total, paid = Decimal(str(totals["total"])), Decimal(str(totals["paid"]))
        all_balances = [
            dict(id=int(row["id"]), name=row["name"],
                 bought=Decimal(str(row["bought"])),
                 paid=Decimal(str(row["paid"])),
                 balance=Decimal(str(row["bought"])) - Decimal(str(row["paid"])))
            for row in balances
        ]
        return {
            "purchase_count": int(totals["purchase_count"]),
            "total": total,
            "paid": paid,
            "unpaid_estimate": total - paid,
            # These are current *all-time* liabilities; a date-filtered
            # purchase subtotal cannot be reconciled with later payments.
            "supplier_payables": sum(
                (max(Decimal("0"), row["balance"]) for row in all_balances),
                Decimal("0"),
            ),
            "supplier_advances": sum(
                (max(Decimal("0"), -row["balance"]) for row in all_balances),
                Decimal("0"),
            ),
            "recent": [dict(row) for row in rows],
            "suppliers": [dict(row) for row in suppliers],
            "balances": sorted(
                all_balances, key=lambda row: (-row["balance"], row["name"])
            )[:limit],
        }
