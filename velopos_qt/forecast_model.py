"""Explainable demand *baseline* for isolated V8 TEST DATA.

Historical units sold, not an ML prediction. Forecasts are deliberately
withheld for sparse products; no automatic orders, no stock changes. Returns,
lost sales, seasonality and branch-specific demand are not modeled.
"""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from .product_editor import _guard


def _positive_days(value, *, name, max_days):
    if isinstance(value, bool):
        raise ValueError(f"Invalid {name}")
    try:
        number = int(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"Invalid {name}") from exc
    if str(number) != str(value).strip() or not 1 <= number <= max_days:
        raise ValueError(f"Invalid {name}")
    return number


def demand_baseline(daily_units, *, horizon=7, stock=0, min_sale_days=5):
    """Calculate a transparent 28d/7d weighted sales *rate*, with no writes.

    A dictionary maps YYYY-MM-DD to nonnegative units sold; its caller must
    provide a completed 28-day window. Insufficient evidence returns no demand
    estimate, rather than an invented AI forecast.
    """
    horizon = _positive_days(horizon, name="forecast horizon", max_days=30)
    try:
        values = [Decimal(str(x)) for x in daily_units]
        available = Decimal(str(stock))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError("Invalid demand history") from exc
    if len(values) != 28 or any(not x.is_finite() or x < 0 for x in values):
        raise ValueError("Exactly 28 nonnegative days are required")
    if not available.is_finite():
        raise ValueError("Invalid stock")
    observed = sum(x > 0 for x in values)
    total28 = sum(values, Decimal(0))
    recent7 = sum(values[-7:], Decimal(0))
    result = {
        "observed_sale_days": observed,
        "units_28d": total28,
        "units_7d": recent7,
        "status": "insufficient" if observed < min_sale_days else "baseline",
        "units_expected": None,
        "stock_coverage_days": None,
    }
    if observed < min_sale_days:
        return result
    rate = (total28 / Decimal(28) + recent7 / Decimal(7)) / Decimal(2)
    result["units_expected"] = (rate * horizon).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP)
    if available >= 0 and rate > 0:
        result["stock_coverage_days"] = (available / rate).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP)
    return result


class DemandForecastReader:
    def __init__(self, database, authorize):
        _guard(database)
        self.database, self.authorize = database, authorize

    def snapshot(self, *, as_of=None, horizon=7, limit=25):
        _guard(self.database)
        if not self.authorize():
            raise PermissionError("Preview Admin sign-in required for demand planning")
        horizon = _positive_days(horizon, name="forecast horizon", max_days=30)
        limit = _positive_days(limit, name="row limit", max_days=100)
        try:
            today = date.today() if as_of is None else date.fromisoformat(str(as_of))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid as-of date") from exc
        # Exclude today's incomplete trading period.
        end_day = today - timedelta(days=1)
        first_day = today - timedelta(days=28)
        with self.database.db() as c:
            products = c.execute(
                "SELECT barcode, name_en, COALESCE(stock_qty,0) stock_qty "
                "FROM products ORDER BY name_en COLLATE NOCASE, barcode LIMIT 100"
            ).fetchall()
            items = c.execute(
                "SELECT i.barcode, s.date day, SUM(i.qty) qty "
                "FROM sale_items i JOIN sales s ON s.invoice_no=i.invoice_no "
                "WHERE s.status='OK' AND s.date BETWEEN ? AND ? "
                "GROUP BY i.barcode, s.date",
                (first_day.isoformat(), end_day.isoformat()),
            ).fetchall()
        by_product = {}
        for row in items:
            by_product.setdefault(row["barcode"], {})[row["day"]] = row["qty"]
        calendar = [(first_day + timedelta(days=day)).isoformat()
                    for day in range(28)]
        output = []
        for p in products:
            history = by_product.get(p["barcode"], {})
            stats = demand_baseline(
                [history.get(day, 0) for day in calendar],
                horizon=horizon, stock=p["stock_qty"],
            )
            output.append({
                "barcode": p["barcode"], "product": p["name_en"],
                "stock": p["stock_qty"], **stats,
            })
        # Sparse products remain visible and explicitly marked; stable order.
        output.sort(key=lambda row: (
            row["status"] != "baseline",
            -(row["units_expected"] or Decimal(0)),
            row["barcode"],
        ))
        return {
            "history_from": first_day.isoformat(),
            "history_to": end_day.isoformat(),
            "horizon": horizon,
            "products": output[:limit],
            "evaluated_products": len(products),
            "ready_products": sum(r["status"] == "baseline" for r in output),
        }
