"""Batch-01 headless tests: read-only catalogue + draft cart + guarded demo seed."""
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from velopos_qt.preview_models import InventoryReader, Cart, money
from velopos_qt.demo_data import ensure_preview_products


class InMemoryStore:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE products (barcode TEXT PRIMARY KEY, name_en TEXT, "
            "name_local TEXT, stock_qty REAL, selling_price REAL)"
        )
        self.conn.executemany(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?)",
            [
                ("1001", "Rice", "සහල්", 10, 250.50),
                ("2002", "Milk", "பால்", 5, 430),
                ("3%4", "Special", "", 2, 50),
            ],
        )

    @contextmanager
    def db(self):
        yield self.conn


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStore()
        self.reader = InventoryReader(self.store)

    def tearDown(self):
        self.store.conn.close()

    def test_search_local_and_english(self):
        self.assertEqual(self.reader.search("සහල්")[0]["barcode"], "1001")
        self.assertEqual(self.reader.search("Milk")[0]["barcode"], "2002")

    def test_search_escapes_sql_wildcards(self):
        self.assertEqual([p["barcode"] for p in self.reader.search("%")], ["3%4"])
        self.assertEqual(self.reader.search("does not exist"), [])

    def test_query_is_read_only(self):
        self.reader.search("Rice")
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM products").fetchone()[0], 3)

    def test_limit_is_bounded(self):
        self.assertEqual(len(self.reader.search(limit=1)), 1)
        self.assertEqual(len(self.reader.search(limit=-1)), 1)


class CartTests(unittest.TestCase):
    def setUp(self):
        self.cart = Cart()
        self.product = {"barcode": "1001", "name_en": "Rice", "selling_price": 250.50}

    def test_add_merge_remove_and_clear(self):
        self.cart.add(self.product)
        self.cart.add(self.product, quantity=2)
        self.assertEqual(self.cart.subtotal(), Decimal("751.50"))
        self.assertEqual(self.cart.lines["1001"]["qty"], Decimal(3))
        self.cart.remove("1001")
        self.assertEqual(self.cart.subtotal(), Decimal("0.00"))
        self.cart.add(self.product)
        self.cart.clear()
        self.assertEqual(len(self.cart.lines), 0)

    def test_rejects_invalid_amounts_and_quantity(self):
        for invalid in ("nan", "inf", -1, 0):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.cart.add(self.product, invalid)
        with self.assertRaises(ValueError):
            money("nan")
        with self.assertRaises(ValueError):
            self.cart.add({**self.product, "selling_price": "-5"})

    def test_decimal_rounding(self):
        self.assertEqual(money("1.005"), Decimal("1.01"))


class GuardTests(unittest.TestCase):
    def test_demo_seed_refuses_unexpected_path(self):
        with tempfile.TemporaryDirectory() as base:
            class Fake:
                DATA_DIR = str(Path(base) / "VeloPOS")
            with self.assertRaises(RuntimeError):
                ensure_preview_products(Fake())


if __name__ == "__main__":
    unittest.main()
