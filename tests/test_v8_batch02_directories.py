"""Batch 02: read-only customer and supplier directory regression tests."""
import sqlite3
import unittest
from contextlib import contextmanager

from velopos_qt.preview_models import DirectoryReader, Cart, preview_existing_bill


class TestDatabase:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, "
            "phone TEXT, address TEXT, credit_balance REAL)"
        )
        self.connection.execute(
            "CREATE TABLE suppliers (id INTEGER PRIMARY KEY, name TEXT, "
            "contact TEXT, phone TEXT, address TEXT, active INTEGER)"
        )
        self.connection.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?)", [
                (1, "කමල්", "0771234567", "Colombo", 150),
                (2, "Sara%Test", None, None, 0),
            ])
        self.connection.executemany(
            "INSERT INTO suppliers VALUES (?, ?, ?, ?, ?, ?)", [
                (1, "Alpha Tools", "Nimal", "0710000000", "Kandy", 1),
                (2, "Beta Supply", "Anu", "0720000000", "", 0),
            ])

    @contextmanager
    def db(self):
        yield self.connection


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.db = TestDatabase()
        self.reader = DirectoryReader(self.db)

    def tearDown(self):
        self.db.connection.close()

    def test_customer_unicode_and_phone_search(self):
        self.assertEqual(self.reader.customers("කමල්")[0]["id"], 1)
        self.assertEqual(self.reader.customers("0771234567")[0]["name"], "කමල්")

    def test_supplier_name_and_contact_search(self):
        self.assertEqual(self.reader.suppliers("Alpha")[0]["contact"], "Nimal")
        self.assertEqual(self.reader.suppliers("Anu")[0]["active"], 0)

    def test_wildcards_are_literal_and_nulls_safe(self):
        self.assertEqual([r["id"] for r in self.reader.customers("%")], [2])
        self.assertEqual(self.reader.customers("not found"), [])
        self.assertEqual(self.reader.customers("Sara%")[0]["phone"], "")

    def test_bounded_and_read_only(self):
        self.assertEqual(len(self.reader.suppliers(limit=1)), 1)
        self.assertEqual(len(self.reader.customers(limit=-5)), 1)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 2)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0], 2)


class BillingPreviewTests(unittest.TestCase):
    def test_original_preview_is_called_without_checkout(self):
        cart = Cart()
        cart.add({"barcode": "DEMO-001", "name_en": "Rice", "selling_price": "245.00"}, quantity=2)
        calls = []
        def calculate(lines, discount, redeem):
            calls.append((lines, discount, redeem))
            return {"sub": 490.0, "net": 490.0, "vat": 0.0}
        totals = preview_existing_bill(cart, calculate)
        self.assertEqual(totals["net"], 490.0)
        self.assertEqual(calls[0][0][0]["barcode"], "DEMO-001")
        self.assertEqual(calls[0][0][0]["qty"], 2.0)
        self.assertEqual((calls[0][1], calls[0][2]), (0.0, 0.0))

    def test_empty_cart_does_not_call_billing_service(self):
        def unsafe(*args):
            raise AssertionError("Do not touch the billing service for empty cart")
        self.assertIsNone(preview_existing_bill(Cart(), unsafe))


if __name__ == "__main__":
    unittest.main()
