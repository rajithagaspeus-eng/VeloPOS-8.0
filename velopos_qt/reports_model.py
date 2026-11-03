"""Audited read-only reporting foundation for VeloPOS 8 preview storage.

Reports do not calculate financial figures from displayed cart state; they
query persisted original sales/expense records. No financial data is cached.
Never use for commercial decisions until voids, refunds and COGS are reconciled.
"""
from datetime import date
from decimal import Decimal
from .product_editor import _guard


def _date(value):
    text = str(value)
    try:
        if date.fromisoformat(text).isoformat() != text:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter a valid date in YYYY-MM-DD format") from exc
    return text


def _currency(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


class PreviewReportsReader:
    def __init__(self, database):
        _guard(database)
        self.database = database

    def snapshot(self, start, end):
        _guard(self.database)
        start, end = _date(start), _date(end)
        if start > end:
            raise ValueError("Start date cannot be later than end date")
        with self.database.db() as connection:
            sales = connection.execute(
                "SELECT COUNT(*) AS count, COALESCE(SUM(total_amount),0) AS total, "
                "COALESCE(SUM(profit),0) AS profit "
                "FROM sales WHERE date BETWEEN ? AND ? AND status='OK'",
                (start, end),
            ).fetchone()
            expenses = connection.execute(
                "SELECT COALESCE(SUM(amount),0) AS total FROM expenses "
                "WHERE date BETWEEN ? AND ?", (start, end),
            ).fetchone()
            recent = connection.execute(
                "SELECT invoice_no, date, total_amount, payment_method "
                "FROM sales WHERE date BETWEEN ? AND ? AND status='OK' "
                "ORDER BY date DESC, time DESC, id DESC LIMIT 30",
                (start, end),
            ).fetchall()
        sales_total = _currency(sales["total"])
        gross = _currency(sales["profit"])
        spent = _currency(expenses["total"])
        return {
            "sale_count": sales["count"],
            "sales_total": sales_total,
            "recorded_gross_profit": gross,
            "expenses": spent,
            "indicative_net": gross - spent,
            "recent_sales": [dict(row) for row in recent],
        }

    def staff_activity(self, limit=30):
        """Admin-only caller required; source remains an unmodified audit log."""
        _guard(self.database)
        limit = max(1, min(int(limit), 100))
        with self.database.db() as connection:
            rows = connection.execute(
                "SELECT ts, user, action FROM audit_log "
                "ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
