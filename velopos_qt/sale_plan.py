"""Deterministic, read-only V8 draft sale arithmetic for isolated TEST DATA.

Quantities and unit prices use Decimal and each displayed sale-item amount
is rounded HALF_UP to cents before computing a receipt subtotal. This is a
preview plan, not a tax, discount, payment, stock or posting implementation.
The legacy service's floating-point and tax rules still require an explicit
commercial reconciliation; do NOT use this plan to authorize checkout.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


_CENT = Decimal("0.01")
_MAX_QTY = Decimal("1000000")
_MAX_PRICE = Decimal("100000000")


def _finite_decimal(value):
    """Never silently accept float NaN/Inf, booleans or malformed numbers."""
    if value is None or type(value) is bool:
        raise ValueError("Invalid draft quantity or price")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid draft quantity or price") from exc
    if not number.is_finite():
        raise ValueError("Draft quantity or price must be finite")
    return number


def canonical_decimal(value):
    """Normalize equivalent representations without floating point notation."""
    number = _finite_decimal(value)
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


@dataclass(frozen=True)
class PreviewSaleLine:
    barcode: str
    qty: Decimal
    price: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class PreviewSalePlan:
    lines: tuple[PreviewSaleLine, ...]
    quantities: tuple[tuple[str, Decimal], ...]
    subtotal: Decimal

    @property
    def line_count(self):
        return len(self.lines)

    def request_items(self):
        """Canonical immutable-price payload for test-only idempotency claims."""
        return [
            {"barcode": line.barcode,
             "qty": canonical_decimal(line.qty),
             "price": canonical_decimal(line.price),
             "line_total": f"{line.line_total:.2f}"}
            for line in self.lines
        ]


def plan_preview_sale(lines):
    """Build a draft plan using per-line, HALF_UP cent rounding.

    - 1..100 lines, canonical nonblank printable 1..80-character barcode
    - positive finite qty <=1,000,000, nonnegative finite price <=100m
    - repeated barcodes are accumulated for stock checks; the combined
      requested quantity cannot silently exceed the line-level ceiling
    - each *line* is rounded independently, then summed. Never round an
      unrounded sum and pretend it matches the item rows on a receipt.

    This function does not query the database or authorize financial posting.
    """
    if lines is None or isinstance(lines, (str, bytes, dict)):
        raise ValueError("Provide a list of draft lines")
    try:
        draft = tuple(lines)
    except TypeError as exc:
        raise ValueError("Provide a list of draft lines") from exc
    if not 1 <= len(draft) <= 100:
        raise ValueError("Draft must contain 1-100 lines")

    planned = []
    quantities = {}
    subtotal = Decimal("0.00")
    for item in draft:
        if not isinstance(item, dict):
            raise ValueError("Each draft line must be a dictionary")
        barcode = item.get("barcode")
        if type(barcode) is not str or not 1 <= len(barcode) <= 80:
            raise ValueError("Invalid barcode")
        if (not barcode.strip() or barcode != barcode.strip() or
                not barcode.isprintable()):
            raise ValueError("Invalid barcode")
        qty = _finite_decimal(item.get("qty"))
        price = _finite_decimal(item.get("price"))
        if qty <= 0 or qty > _MAX_QTY:
            raise ValueError("Quantity out of range")
        if price < 0 or price > _MAX_PRICE:
            raise ValueError("Price out of range")
        aggregate = quantities.get(barcode, Decimal("0")) + qty
        if aggregate > _MAX_QTY:
            raise ValueError("Combined quantity out of range")
        quantities[barcode] = aggregate
        try:
            line_total = (qty * price).quantize(_CENT, rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise ValueError("Draft line amount is too large") from exc
        planned.append(PreviewSaleLine(barcode, qty, price, line_total))
        subtotal += line_total

    return PreviewSalePlan(
        tuple(planned), tuple(quantities.items()), subtotal
    )
