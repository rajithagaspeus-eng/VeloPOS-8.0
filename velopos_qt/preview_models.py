"""Read-only catalogue and non-transactional cart for the VeloPOS 8 UI preview.

No product, sale, inventory or stock writes are allowed in these classes.
Checkout is intentionally unavailable until auth, stock and transaction tests pass.
"""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid money amount") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("Money amount must be finite and nonnegative")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class InventoryReader:
    """A bounded, parameterized read-only query using the existing SQLite schema."""
    def __init__(self, database):
        self.database = database

    def search(self, query="", limit=100):
        if isinstance(limit, bool):
            raise ValueError("Invalid lookup limit")
        try:
            parsed_limit = int(limit)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Invalid lookup limit") from exc
        if str(limit).strip() != str(parsed_limit):
            raise ValueError("Invalid lookup limit")
        limit = max(1, min(parsed_limit, 200))
        search = "%" + str(query).strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with self.database.db() as connection:
            rows = connection.execute(
                "SELECT barcode, name_en, name_local, stock_qty, selling_price "
                "FROM products WHERE barcode LIKE ? ESCAPE '\\' "
                "OR name_en LIKE ? ESCAPE '\\' OR name_local LIKE ? ESCAPE '\\' "
                "ORDER BY name_en, barcode LIMIT ?",
                (search, search, search, limit),
            ).fetchall()
        return [dict(row) for row in rows]


@dataclass
class Cart:
    """Preview cart only; no persistence and no call to create_sale."""
    lines: dict = field(default_factory=dict)

    def add(self, product, quantity=1):
        barcode = str(product["barcode"])
        if not barcode:
            raise ValueError("A product barcode is required")
        try:
            qty = Decimal(str(quantity).strip())
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Enter a valid quantity") from exc
        if not qty.is_finite() or qty <= 0:
            raise ValueError("Quantity must be positive")
        price = money(product["selling_price"])
        old = self.lines.get(barcode)
        next_qty = qty + (old["qty"] if old else 0)
        if next_qty > Decimal("1000000"):
            raise ValueError("Quantity is too large")
        self.lines[barcode] = {
            "barcode": barcode,
            "name": str(product["name_en"]),
            "qty": next_qty,
            "price": price,
        }

    def set_quantity(self, barcode, quantity):
        """Change a draft line without writing stock or creating an invoice."""
        barcode = str(barcode)
        if barcode not in self.lines:
            raise ValueError("Product is not in the draft cart")
        try:
            qty = Decimal(str(quantity).strip())
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Enter a valid quantity") from exc
        if not qty.is_finite() or qty <= 0 or qty > Decimal("1000000"):
            raise ValueError("Quantity must be greater than zero and at most 1,000,000")
        self.lines[barcode]["qty"] = qty

    def remove(self, barcode):
        self.lines.pop(str(barcode), None)

    def clear(self):
        self.lines.clear()

    def subtotal(self):
        return sum((money(line["price"] * line["qty"]) for line in self.lines.values()), Decimal("0.00"))


class DirectoryReader:
    """Bounded customer and supplier lookup. Uses parameterized, read-only SQL."""

    def __init__(self, database):
        self.database = database

    @staticmethod
    def _pattern(query):
        value = str(query).strip()
        return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"

    def customers(self, query="", limit=100):
        if isinstance(limit, bool):
            raise ValueError("Invalid lookup limit")
        try:
            parsed_limit = int(limit)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Invalid lookup limit") from exc
        if str(limit).strip() != str(parsed_limit):
            raise ValueError("Invalid lookup limit")
        limit = max(1, min(parsed_limit, 200))
        search = self._pattern(query)
        with self.database.db() as connection:
            records = connection.execute(
                "SELECT id, name, COALESCE(phone, '') AS phone, "
                "COALESCE(address, '') AS address, "
                "COALESCE(credit_balance, 0) AS credit_balance "
                "FROM customers WHERE name LIKE ? ESCAPE '\\' "
                "OR phone LIKE ? ESCAPE '\\' "
                "ORDER BY name COLLATE NOCASE, id LIMIT ?",
                (search, search, limit),
            ).fetchall()
        return [dict(row) for row in records]

    def suppliers(self, query="", limit=100):
        if isinstance(limit, bool):
            raise ValueError("Invalid lookup limit")
        try:
            parsed_limit = int(limit)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Invalid lookup limit") from exc
        if str(limit).strip() != str(parsed_limit):
            raise ValueError("Invalid lookup limit")
        limit = max(1, min(parsed_limit, 200))
        search = self._pattern(query)
        with self.database.db() as connection:
            records = connection.execute(
                "SELECT id, name, COALESCE(contact, '') AS contact, "
                "COALESCE(phone, '') AS phone, "
                "COALESCE(address, '') AS address, COALESCE(active, 1) AS active "
                "FROM suppliers WHERE name LIKE ? ESCAPE '\\' "
                "OR contact LIKE ? ESCAPE '\\' OR phone LIKE ? ESCAPE '\\' "
                "ORDER BY name COLLATE NOCASE, id LIMIT ?",
                (search, search, search, limit),
            ).fetchall()
        return [dict(row) for row in records]


def validated_discount(value, subtotal):
    """Exact, nonnegative currency discount for a draft bill only."""
    amount = money(value)
    if amount > subtotal:
        raise ValueError("Discount cannot exceed draft subtotal")
    return amount


def cash_estimate(payable, tendered):
    """Preview change/shortfall only. Never accepts or records payment."""
    due, tender = money(payable), money(tendered)
    return {"due": due, "tendered": tender,
            "change": max(Decimal("0.00"), tender - due),
            "shortfall": max(Decimal("0.00"), due - tender)}


def preview_existing_bill(cart, calculate, discount=0):
    """Call original *read-only* preview_bill service, never create_sale.

    Actual checkout must revalidate permissions, customer, stock, VAT,
    discounts, payment and shift *inside* the original transaction service.
    """
    subtotal = cart.subtotal()
    deduction = validated_discount(discount, subtotal)
    items = [
        {"barcode": line["barcode"], "qty": float(line["qty"]),
         "price": float(line["price"]), "name": line["name"]}
        for line in cart.lines.values()
    ]
    if not items:
        return None
    return calculate(items, float(deduction), 0.0)
