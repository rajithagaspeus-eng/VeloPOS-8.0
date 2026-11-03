"""Explainable, read-only business intelligence over original POS records.

This is historical descriptive analytics, NOT an AI forecast or certified P&L.
Original sales.profit incorporates original sale-time costs, discounts and taxes.
Returns are counted by return date (as in legacy report_data), and inventory
COGS changes/partial returns still need final accounting reconciliation.
"""
from datetime import date
from decimal import Decimal
from .reports_model import _date, _currency
from .product_editor import _guard


class BusinessIntelligenceReader:
    def __init__(self, database, authorize):
        _guard(database)
        self.database, self.authorize = database, authorize

    def snapshot(self, start, end, limit=10):
        _guard(self.database)
        if not self.authorize():
            raise PermissionError("Preview Admin sign-in required for business intelligence")
        start, end = _date(start), _date(end)
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        if not 0 <= days <= 366:
            raise ValueError("Select a date range of 367 days or less")
        limit = max(1, min(int(limit), 50))
        with self.database.db() as c:
            # Group each source by its own event date to avoid duplicate joins.
            sale_daily = c.execute(
                "SELECT date day, COUNT(*) bills, COALESCE(SUM(total_amount),0) sales, "
                "COALESCE(SUM(profit),0) gross "
                "FROM sales WHERE status='OK' AND date BETWEEN ? AND ? "
                "GROUP BY date ORDER BY date", (start, end),
            ).fetchall()
            return_daily = c.execute(
                "SELECT date day, COALESCE(SUM(amount),0) refunds, "
                "COALESCE(SUM(profit_adj),0) profit_adj "
                "FROM returns WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date",
                (start, end),
            ).fetchall()
            expense_daily = c.execute(
                "SELECT date day, COALESCE(SUM(amount),0) spent "
                "FROM expenses WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date",
                (start, end),
            ).fetchall()
            categories = c.execute(
                "SELECT COALESCE(NULLIF(TRIM(category),''),'Uncategorized') category, "
                "COUNT(*) entries, COALESCE(SUM(amount),0) total "
                "FROM expenses WHERE date BETWEEN ? AND ? "
                "GROUP BY COALESCE(NULLIF(TRIM(category),''),'Uncategorized') "
                "ORDER BY total DESC, category LIMIT ?", (start, end, limit),
            ).fetchall()
            # Sale items are included once per valid parent invoice.
            # These figures are sales BEFORE refunds and represent no
            # per-product net-return or margin estimate.
            products = c.execute(
                "SELECT i.barcode, MAX(i.item_name) product, "
                "COALESCE(SUM(i.qty),0) qty, COALESCE(SUM(i.total),0) revenue "
                "FROM sale_items i JOIN sales s ON s.invoice_no=i.invoice_no "
                "WHERE s.status='OK' AND s.date BETWEEN ? AND ? "
                "GROUP BY i.barcode ORDER BY revenue DESC, i.barcode LIMIT ?",
                (start, end, limit),
            ).fetchall()
        all_days = {}
        def day_record(key):
            return all_days.setdefault(
                key, {"date": key, "bills": 0, "sales": Decimal("0.00"),
                      "refunds": Decimal("0.00"), "net_revenue": Decimal("0.00"),
                      "gross": Decimal("0.00"), "expenses": Decimal("0.00"),
                      "indicative_net": Decimal("0.00")}
            )
        for row in sale_daily:
            target = day_record(row["day"])
            target["bills"] = row["bills"]
            target["sales"] = _currency(row["sales"])
            target["gross"] = _currency(row["gross"])
        for row in return_daily:
            target = day_record(row["day"])
            target["refunds"] = _currency(row["refunds"])
            target["gross"] += _currency(row["profit_adj"])
        for row in expense_daily:
            day_record(row["day"])["expenses"] = _currency(row["spent"])
        for rec in all_days.values():
            rec["net_revenue"] = rec["sales"] - rec["refunds"]
            rec["indicative_net"] = rec["gross"] - rec["expenses"]
        daily = [all_days[day] for day in sorted(all_days)]
        return {
            "start": start, "end": end, "daily": daily,
            "sales_total": sum((r["sales"] for r in daily), Decimal("0.00")),
            "refunds_total": sum((r["refunds"] for r in daily), Decimal("0.00")),
            "net_revenue": sum((r["net_revenue"] for r in daily), Decimal("0.00")),
            "indicative_net": sum((r["indicative_net"] for r in daily), Decimal("0.00")),
            "expenses_by_category": [
                {"category": row["category"], "entries": row["entries"],
                 "total": _currency(row["total"])} for row in categories
            ],
            "top_products": [
                {"barcode": row["barcode"], "product": row["product"],
                 "qty": row["qty"], "revenue": _currency(row["revenue"])}
                for row in products
            ],
        }
