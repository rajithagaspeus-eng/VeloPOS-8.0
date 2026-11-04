"""V8 draft-only barcode keyboard navigation regression tests.

Uses synthetic offscreen widgets. Never opens customer data or executes sales.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from velopos_qt.billing_page import BillingPage
    from velopos_qt.i18n import translate
    from velopos_qt.app import DARK, LIGHT
except ModuleNotFoundError as exc:
    if exc.name == "PySide6" or (exc.name or "").startswith("PySide6."):
        QApplication = None
    else:
        raise


class SyntheticInventory:
    def __init__(self):
        self.records = [
            dict(barcode="RICE-A", name_en="Sample Rice A",
                 name_local="සහල් A", stock_qty=20, selling_price=245),
            dict(barcode="RICE-B", name_en="Sample Rice B",
                 name_local="சாதம் B", stock_qty=15, selling_price=250),
            dict(barcode="MIX-3", name_en="RICE-A accessory set",
                 name_local="Accessory", stock_qty=5, selling_price=500),
        ]
        self.reads = 0

    def search(self, query="", limit=50):
        self.reads += 1
        q = query.casefold()
        return [
            r for r in self.records
            if q in (r["barcode"] + r["name_en"] + r["name_local"]).casefold()
        ][:limit]


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class DraftBillingKeyboardSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.locale = "en"
        self.inventory = SyntheticInventory()
        self.page = BillingPage(
            self.inventory, lambda key: translate(self.locale, key)
        )
        self.page.show()
        QApplication.processEvents()

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        QApplication.processEvents()

    def test_ambiguous_enter_requires_explicit_keyboard_selection(self):
        self.page.query.setText("Rice")
        self.assertEqual(self.page.results.rowCount(), 3)
        self.assertIsNone(self.page._explicit_search_row)
        QTest.keyClick(self.page.query, Qt.Key.Key_Return)
        self.assertEqual(self.page.cart.lines, {})
        QTest.keyClick(self.page.query, Qt.Key.Key_Down)
        self.assertEqual(self.page._explicit_search_row, 0)
        self.assertEqual(self.page.results.currentRow(), 0)
        QTest.keyClick(self.page.query, Qt.Key.Key_Down)
        self.assertEqual(self.page.results.currentRow(), 1)
        QTest.keyClick(self.page.query, Qt.Key.Key_Return)
        self.assertEqual(list(self.page.cart.lines), ["RICE-B"])
        self.assertEqual(str(self.page.cart.subtotal()), "250.00")
        self.assertIsNone(self.page._explicit_search_row)
        self.assertEqual(self.page.query.text(), "")

    def test_new_query_forgets_old_selected_row_and_blocks_wrong_product(self):
        self.page.query.setText("Rice")
        QTest.keyClick(self.page.query, Qt.Key.Key_Down)
        QTest.keyClick(self.page.query, Qt.Key.Key_Down)
        self.assertEqual(self.page.results.currentRow(), 1)
        self.page.query.setText("Accessory")
        self.assertIsNone(self.page._explicit_search_row)
        self.assertEqual(self.page.results.rowCount(), 1)
        self.page.query.setText("Rice")
        self.assertEqual(self.page.results.rowCount(), 3)
        self.assertIsNone(self.page._explicit_search_row)
        QTest.keyClick(self.page.query, Qt.Key.Key_Return)
        self.assertEqual(self.page.cart.lines, {})
        QTest.keyClick(self.page.query, Qt.Key.Key_Up)
        self.assertEqual(self.page.results.currentRow(), 2)
        QTest.keyClick(self.page.query, Qt.Key.Key_Return)
        self.assertEqual(list(self.page.cart.lines), ["MIX-3"])

    def test_exact_scanned_barcode_overrides_other_name_matches(self):
        # "RICE-A" also appears in MIX-3's name; an exact scan wins.
        self.page.query.setText("RICE-A")
        self.assertEqual(self.page.results.rowCount(), 2)
        self.page.scan_or_add()
        self.assertEqual(list(self.page.cart.lines), ["RICE-A"])
        self.assertEqual(str(self.page.cart.subtotal()), "245.00")

    def test_mouse_selected_ambiguous_result_and_search_reset(self):
        self.page.query.setText("Rice")
        self.page.results.setCurrentCell(2, 0)
        self.page.results.itemClicked.emit(self.page.results.item(2, 0))
        self.assertEqual(self.page._explicit_search_row, 2)
        self.page.scan_or_add()
        self.assertEqual(list(self.page.cart.lines), ["MIX-3"])
        self.assertIsNone(self.page._explicit_search_row)
        self.page.query.setText("Rice")
        self.page.scan_or_add()
        self.assertEqual(list(self.page.cart.lines), ["MIX-3"])

    def test_localized_accessible_help_and_zero_matches(self):
        for language in ("en", "si", "ta"):
            self.locale = language
            self.page.retranslate()
            self.page.query.setText("Rice")
            self.assertEqual(
                self.page.search_help.text(),
                translate(language, "billing_search_many").format(count=3)
            )
            self.assertEqual(
                self.page.query.accessibleName(),
                translate(language, "billing_product_lookup")
            )
            self.assertEqual(
                self.page.results.accessibleName(),
                translate(language, "billing_search_results")
            )
            self.page.query.setText("not-a-real-barcode")
            self.assertEqual(self.page.results.rowCount(), 0)
            self.assertEqual(
                self.page.search_help.text(),
                translate(language, "billing_search_none")
            )
            QTest.keyClick(self.page.query, Qt.Key.Key_Return)
            self.assertEqual(self.page.cart.lines, {})
        self.assertIn("QLabel#billingSearchHelp", DARK)
        self.assertIn("QLabel#billingSearchHelp", LIGHT)

    def test_draft_cart_rejects_malformed_quantity_without_mutation(self):
        self.page.query.setText("RICE-B")
        self.page.scan_or_add()
        before = dict(self.page.cart.lines["RICE-B"])
        for invalid in ("bad", "", "NaN", "Infinity", "-Infinity", "0", "-1"):
            with self.assertRaises(ValueError, msg=invalid):
                self.page.cart.add(self.inventory.records[1], quantity=invalid)
            self.assertEqual(self.page.cart.lines["RICE-B"], before)
        self.assertEqual(str(self.page.cart.subtotal()), "250.00")
        self.assertFalse(hasattr(self.page, "checkout_button"))

    def test_only_one_match_and_no_checkout_or_financial_writes(self):
        self.page.query.setText("RICE-B")
        self.assertEqual(self.page.results.rowCount(), 1)
        self.assertEqual(
            self.page.search_help.text(),
            translate("en", "billing_search_one")
        )
        self.page.scan_or_add()
        self.assertEqual(list(self.page.cart.lines), ["RICE-B"])
        self.assertEqual(str(self.page.cart.subtotal()), "250.00")
        self.assertFalse(hasattr(self.page, "checkout_button"))
        self.assertIsNone(self.page.bill_preview)
        self.assertFalse(hasattr(self.inventory, "database"))
        self.page.clear_session_draft()
        self.assertEqual(self.page.cart.lines, {})
        self.assertIsNone(self.page._explicit_search_row)


if __name__ == "__main__":
    unittest.main()
