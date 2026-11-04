"""Printable-looking DRAFT receipt text; strictly no sale, invoice or payment.

This is a pure view of the current in-memory BillingPage cart. No DB reads,
printer interaction, receipt numbering, persisted sales or customer PII.
The banner makes the preview impossible to mistake for a fiscal receipt.
"""
from decimal import Decimal

from .preview_models import (
    cash_estimate, money, preview_existing_bill, validated_discount,
)


def draft_receipt_text(cart, *, discount="0", tendered="0", bill_preview=None):
    """Build receipt-style text consistent with BillingPage's draft totals.

    If a legacy *read-only* bill preview callback was supplied by the app,
    use the same estimated net figure as BillingPage.refresh_cart(). This
    cannot be printed or promoted to a sale by this module.
    """
    if not cart.lines:
        raise ValueError("Add a draft item before previewing a receipt")
    if len(cart.lines) > 100:
        raise ValueError("Draft receipt has too many items")

    subtotal = cart.subtotal()
    deduction = validated_discount(discount, subtotal)
    if bill_preview is None:
        due = money(subtotal - deduction)
    else:
        estimated = preview_existing_bill(cart, bill_preview, discount)
        if estimated is None:
            raise ValueError("Draft preview is unavailable")
        due = money(estimated["net"])
    cash = cash_estimate(due, tendered)

    rows = [
        "VELOPOS 8   •   DRAFT RECEIPT",
        "TEST DATA ONLY — NOT A TAX INVOICE",
        "NO SALE / PAYMENT / STOCK POSTING",
        "-" * 43,
    ]
    for line in cart.lines.values():
        name = str(line["name"])
        barcode = str(line["barcode"])
        if not name or not name.isprintable() or not barcode or not barcode.isprintable():
            raise ValueError("Draft item description is invalid")
        if len(name) > 160 or len(barcode) > 80:
            raise ValueError("Draft item description is too long")
        qty = Decimal(str(line["qty"]))
        price = money(line["price"])
        total = money(qty * price)
        rows.extend([
            name[:80],
            f"  {barcode[:80]}  |  {format(qty, 'f')} × {price:,.2f}",
            f"  Estimated line: {total:,.2f}",
        ])
    rows.extend([
        "-" * 43,
        f"Subtotal:           {subtotal:,.2f}",
        f"Discount (draft):   {deduction:,.2f}",
        f"Estimated payable:  {due:,.2f}",
        f"Cash entered:       {cash['tendered']:,.2f}",
        f"Estimated change:   {cash['change']:,.2f}",
        f"Estimated shortfall:{cash['shortfall']:,.2f}",
        "-" * 43,
        "PREVIEW ONLY — amounts may change at checkout.",
        "Not valid for payment, returns or proof of sale.",
    ])
    return "\n".join(rows)
