"""Headless tests for the UI-independent VeloPOS 8 Settings adapter."""
import unittest
from velopos_qt.settings_model import SettingsAdapter


class FakeSettings:
    def __init__(self):
        self.data = {"shop_name": "Test shop", "theme": "light", "font_size": "15"}
        self.calls = []

    def get(self, key):
        return self.data.get(key, "")

    def set_many(self, changes):
        self.calls.append(dict(changes))
        self.data.update(changes)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeSettings()
        self.adapter = SettingsAdapter(self.store)

    def test_reads_existing_values(self):
        self.assertEqual(self.adapter.read()["shop_name"], "Test shop")

    def test_saves_only_whitelisted_fields(self):
        self.adapter.save({"shop_name": "New shop", "theme": "dark"})
        self.assertEqual(self.store.data["shop_name"], "New shop")
        self.assertEqual(len(self.store.calls), 1)

    def test_refuses_unexpected_fields(self):
        with self.assertRaises(ValueError):
            self.adapter.save({"smtp_pass_enc": "secret"})
        self.assertEqual(self.store.calls, [])

    def test_refuses_blank_shop_name(self):
        with self.assertRaises(ValueError):
            self.adapter.save({"shop_name": " "})

    def test_refuses_invalid_theme(self):
        with self.assertRaises(ValueError):
            self.adapter.save({"theme": "broken"})

    def test_saves_valid_receipt_preferences(self):
        self.adapter.save({
            "printer_brand": "Xprinter", "print_mode": "Browser only",
            "paper_size": "80mm", "print_copies": "2",
            "receipt_footer": "Thanks for visiting",
        })
        self.assertEqual(self.store.data["print_copies"], "2")

    def test_rejects_invalid_printer_brand_without_write(self):
        with self.assertRaises(ValueError):
            self.adapter.save({"printer_brand": "UnexpectedDevice"})
        self.assertEqual(self.store.calls, [])

    def test_rejects_invalid_copies_without_write(self):
        for copies in ("0", "6", "2.5", "xyz"):
            with self.subTest(copies=copies), self.assertRaises(ValueError):
                self.adapter.save({"print_copies": copies})
        self.assertEqual(self.store.calls, [])

    def test_rejects_overlong_receipt_footer(self):
        with self.assertRaises(ValueError):
            self.adapter.save({"receipt_footer": "x" * 251})
        self.assertEqual(self.store.calls, [])

    def test_refuses_invalid_font_size(self):
        with self.assertRaises(ValueError):
            self.adapter.save({"font_size": "999"})


if __name__ == "__main__":
    unittest.main()
