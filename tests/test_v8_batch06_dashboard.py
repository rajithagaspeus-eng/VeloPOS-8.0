"""Batch 06 dashboard tests, using an isolated SQLite database only."""
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from velopos_qt.dashboard_model import DashboardReader


class FakePreviewDatabase:
    def __init__(self, root):
        self.DATA_DIR = str(Path(root) / "VeloPOS8PreviewData")
        self.DB_PATH = str(Path(self.DATA_DIR) / "velopos.db")
        Path(self.DATA_DIR).mkdir(parents=True)
        self.connection = sqlite3.connect(self.DB_PATH)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            "CREATE TABLE products (barcode TEXT, name_en TEXT, stock_qty REAL);"
            "CREATE TABLE customers (id INTEGER PRIMARY KEY);"
            "CREATE TABLE suppliers (id INTEGER PRIMARY KEY, active INTEGER);"
        )
        self.connection.executemany(
            "INSERT INTO products VALUES (?,?,?)", [
                ("A1", "Rice", 0), ("A2", "Milk", 3),
                ("A3", "Notebook", 10), ("A4", "Soap", 5),
            ],
        )
        self.connection.executemany(
            "INSERT INTO customers VALUES (?)", [(1,), (2,)]
        )
        self.connection.executemany(
            "INSERT INTO suppliers VALUES (?,?)", [(1, 1), (2, 0), (3, 1)]
        )
        self.connection.commit()

    @contextmanager
    def db(self):
        yield self.connection

    def close(self):
        self.connection.close()


class DashboardStatsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = FakePreviewDatabase(self.temp.name)
        self.reader = DashboardReader(self.database)

    def tearDown(self):
        self.database.close()
        self.temp.cleanup()

    def test_aggregates_and_low_stock_preview_rows(self):
        metrics = self.reader.snapshot()
        self.assertEqual(
            (metrics["products"], metrics["customers"],
             metrics["suppliers"], metrics["low_stock"]),
            (4, 2, 2, 3),
        )
        self.assertEqual([p["barcode"] for p in metrics["alerts"]],
                         ["A1", "A2", "A4"])

    def test_refresh_does_not_cache_mutated_stock(self):
        self.database.connection.execute(
            "UPDATE products SET stock_qty=15 WHERE barcode='A1'"
        )
        self.database.connection.commit()
        self.assertEqual(self.reader.snapshot()["low_stock"], 2)
        self.assertEqual(self.reader.snapshot()["products"], 4)

    def test_low_stock_limit_is_bounded(self):
        self.assertEqual(self.reader.snapshot(low_stock_limit=-20)["low_stock"], 1)
        self.assertEqual(self.reader.snapshot(low_stock_limit=2)["low_stock"], 1)

    def test_refuses_production_like_directory(self):
        self.database.DATA_DIR = str(Path(self.temp.name) / "VeloPOS")
        with self.assertRaises(RuntimeError):
            self.reader.snapshot()

    def test_does_not_write_during_snapshot(self):
        before = self.database.connection.total_changes
        self.reader.snapshot()
        self.assertEqual(self.database.connection.total_changes, before)


if __name__ == "__main__":
    unittest.main()
