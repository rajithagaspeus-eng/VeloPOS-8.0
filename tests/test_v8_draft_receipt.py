"""Read-only Billing Draft receipt preview: no invoice or payment creation."""
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from velopos_qt.draft_receipt import draft_receipt_text
from velopos_qt.preview_models import Cart
from velopos_qt.i18n import translate, LANGUAGES


def sample_cart():
    cart = Cart()
    cart.add({
        "barcode": "RICE", "name_en": "Rice - 1kg",
        "selling_price": "45.00",
    }, quantity=2)
    cart.add({
        "barcode": "SOAP", "name_en": "Soap Bar",
        "selling_price": "25.00",
    })
    return cart


class DraftReceiptTextTests(unittest.TestCase):
    def test_receipt_matches_draft_cart_discount_and_cash_estimate(self):
        cart = sample_cart()
        before = dict((key, dict(value)) for key, value in cart.lines.items())
        text = draft_receipt_text(cart, discount="5", tendered="120")
        self.assertIn("DRAFT RECEIPT", text)
        self.assertIn("NOT A TAX INVOICE", text)
        self.assertIn("NO SALE / PAYMENT / STOCK POSTING", text)
        self.assertIn("Rice - 1kg", text)
        self.assertIn("2 × 45.00", text)
        self.assertIn("Soap Bar", text)
        self.assertIn("Subtotal:           115.00", text)
        self.assertIn("Discount (draft):   5.00", text)
        self.assertIn("Estimated payable:  110.00", text)
        self.assertIn("Cash entered:       120.00", text)
        self.assertIn("Estimated change:   10.00", text)
        self.assertIn("Estimated shortfall:0.00", text)
        self.assertEqual(cart.lines, before)

    def test_shortfall_and_invalid_discount(self):
        text = draft_receipt_text(
            sample_cart(), discount="5", tendered="70"
        )
        self.assertIn("Estimated change:   0.00", text)
        self.assertIn("Estimated shortfall:40.00", text)
        with self.assertRaises(ValueError):
            draft_receipt_text(sample_cart(), discount="116")
        with self.assertRaises(ValueError):
            draft_receipt_text(sample_cart(), tendered="-5")
        with self.assertRaisesRegex(ValueError, "Add a draft item"):
            draft_receipt_text(Cart())

    def test_uses_same_read_only_legacy_net_estimate_as_billing_page(self):
        calls = []
        def read_only_calculator(items, discount, _other):
            calls.append((items, discount))
            return {"net": Decimal("112.00")}
        text = draft_receipt_text(
            sample_cart(), discount="5", tendered="120",
            bill_preview=read_only_calculator,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 5.0)
        self.assertIn("Estimated payable:  112.00", text)
        self.assertIn("Estimated change:   8.00", text)
        self.assertNotIn("invoice_no", text)

    def test_item_control_characters_never_reach_receipt(self):
        cart = sample_cart()
        cart.lines["RICE"]["name"] = "Rice\nFAKE PAID RECEIPT"
        with self.assertRaisesRegex(ValueError, "description"):
            draft_receipt_text(cart)
        cart.lines["RICE"]["name"] = "Rice"
        cart.lines["RICE"]["barcode"] = "RICE\rPAID"
        with self.assertRaisesRegex(ValueError, "description"):
            draft_receipt_text(cart)

    def test_three_language_ui_controls_available(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                for key in (
                    "draft_receipt_preview", "draft_receipt_title",
                    "draft_receipt_copy", "draft_receipt_close",
                ):
                    value = translate(language, key)
                    self.assertTrue(value and value != key, (language, key))


class DraftReceiptBillingUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_billing_preview_opens_read_only_dialog_without_checkout(self):
        from PySide6.QtWidgets import QDialog, QPlainTextEdit
        from velopos_qt.billing_page import BillingPage

        class EmptyInventory:
            def search(self, _query="", limit=50):
                return []

        page = BillingPage(EmptyInventory(), lambda key: key)
        try:
            self.assertFalse(page.receipt_button.isEnabled())
            page.cart = sample_cart()
            page.discount_input.setText("5")
            page.tender_input.setText("120")
            page.refresh_cart()
            self.assertTrue(page.receipt_button.isEnabled())
            shown = []

            def capture(dialog):
                self.assertEqual(
                    dialog.objectName(), "draftReceiptPreviewDialog"
                )
                preview = dialog.findChild(
                    QPlainTextEdit, "draftReceiptPreviewText"
                )
                self.assertIsNotNone(preview)
                self.assertTrue(preview.isReadOnly())
                shown.append(preview.toPlainText())
                return 0

            with patch.object(QDialog, "exec", capture):
                page.show_draft_receipt()
            self.assertEqual(len(shown), 1)
            self.assertIn("NOT A TAX INVOICE", shown[0])
            self.assertIn("Estimated payable:  110.00", shown[0])
            self.assertEqual(len(page.cart.lines), 2)
        finally:
            page.close()


if __name__ == "__main__":
    unittest.main()
