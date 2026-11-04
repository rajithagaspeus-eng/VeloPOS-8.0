"""Batch 05 billing draft model validations. No real transactions."""
from decimal import Decimal
import unittest

from velopos_qt.preview_models import Cart, money


class DraftQuantityTests(unittest.TestCase):
    def setUp(self):
        self.cart = Cart()
        self.product = {
            "barcode": "0001234567890",
            "name_en": "Sample Notebook",
            "selling_price": "19.95",
        }
        self.cart.add(self.product)

    def test_blank_and_null_barcodes_cannot_enter_draft(self):
        original = dict(self.cart.lines["0001234567890"])
        for barcode in ("", "  ", None):
            with self.subTest(barcode=barcode), self.assertRaises(ValueError):
                self.cart.add(dict(self.product, barcode=barcode))
            self.assertEqual(self.cart.lines["0001234567890"], original)
            self.assertEqual(len(self.cart.lines), 1)

    def test_extreme_catalog_money_is_rejected_without_mutation(self):
        original = dict(self.cart.lines["0001234567890"])
        for value in ("1e999", "999999999999999999999999999999999999"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                money(value)
            with self.assertRaises(ValueError):
                self.cart.add(dict(self.product, selling_price=value))
            self.assertEqual(self.cart.lines["0001234567890"], original)
        self.assertEqual(self.cart.subtotal(), Decimal("19.95"))

    def test_repeated_scan_keeps_draft_price_after_catalog_repricing(self):
        repriced = dict(self.product, selling_price="29.95",
                        name_en="Renamed Notebook")
        self.cart.add(repriced)
        line = self.cart.lines["0001234567890"]
        self.assertEqual(line["qty"], Decimal("2"))
        self.assertEqual(line["price"], Decimal("19.95"))
        self.assertEqual(line["name"], "Sample Notebook")
        self.assertEqual(self.cart.subtotal(), Decimal("39.90"))
        self.assertEqual(len(self.cart.lines), 1)

    def test_invalid_repeated_scan_does_not_change_existing_draft(self):
        original = dict(self.cart.lines["0001234567890"])
        for quantity in ("NaN", "bad", "0", "-2", "Infinity"):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.cart.add(dict(self.product, selling_price="29.95"),
                              quantity=quantity)
            self.assertEqual(self.cart.lines["0001234567890"], original)

    def test_change_quantity_updates_money_without_db_write(self):
        self.cart.set_quantity("0001234567890", "2.5")
        self.assertEqual(self.cart.lines["0001234567890"]["qty"], Decimal("2.5"))
        self.assertEqual(self.cart.subtotal(), Decimal("49.88"))
        self.assertEqual(len(self.cart.lines), 1)

    def test_invalid_quantities_do_not_change_cart(self):
        for value in ("", "nan", "inf", "-inf", "-2", "0", "1000001", "bad"):
            with self.subTest(quantity=value), self.assertRaises(ValueError):
                self.cart.set_quantity("0001234567890", value)
            self.assertEqual(self.cart.lines["0001234567890"]["qty"], Decimal(1))

    def test_missing_product_is_error(self):
        with self.assertRaises(ValueError):
            self.cart.set_quantity("does-not-exist", "3")

    def test_setting_quantity_keeps_original_price(self):
        self.cart.set_quantity("0001234567890", 4)
        self.assertEqual(self.cart.lines["0001234567890"]["price"], Decimal("19.95"))
        self.assertEqual(self.cart.subtotal(), Decimal("79.80"))


if __name__ == "__main__":
    unittest.main()
