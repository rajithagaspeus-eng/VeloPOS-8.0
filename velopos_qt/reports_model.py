"""Audited read-only reporting foundation for VeloPOS 8 preview storage.

Reports do not calculate financial figures from displayed cart state; they
query persisted original sales/expense records. No financial data is cached.
Returns and tax adjustments follow the legacy report rules; this remains\nan indicative rather than independently audited business P&L.
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
            refunds = connection.execute(
                "SELECT COUNT(*) AS count, COALESCE(SUM(amount),0) AS total, "
                "COALESCE(SUM(profit_adj),0) AS profit_adj, "
                "COALESCE(SUM(vat_adj),0) AS vat_adj, "
                "COALESCE(SUM(service_adj),0) AS service_adj "
                "FROM returns WHERE date BETWEEN ? AND ?", (start, end),
            ).fetchone()
            taxes = connection.execute(
                "SELECT COALESCE(SUM(vat_amount),0) AS vat, "
                "COALESCE(SUM(service_amount),0) AS service "
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
        refunded = _currency(refunds["total"])
        # Original report_data uses profit + returns.profit_adj - expenses.
        adjusted_profit = gross + _currency(refunds["profit_adj"])
        return {
            "sale_count": sales["count"],
            "sales_total": sales_total,
            "return_count": refunds["count"],
            "returns_total": refunded,
            "net_revenue": sales_total - refunded,
            "recorded_gross_profit": gross,
            "adjusted_gross_profit": adjusted_profit,
            "vat_net": _currency(taxes["vat"]) - _currency(refunds["vat_adj"]),
            "service_net": _currency(taxes["service"]) - _currency(refunds["service_adj"]),
            "expenses": spent,
            "indicative_net": adjusted_profit - spent,
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
