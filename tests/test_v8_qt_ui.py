"""Optional offscreen Qt smoke test. Never imports a customer database.

Run separately: python -m unittest tests.test_v8_qt_ui -v
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from velopos_qt.app import SettingsPreview
    from velopos_qt.settings_model import SettingsAdapter
except ModuleNotFoundError as exc:
    # Skip only when Qt itself is genuinely absent. A missing/broken VeloPOS
    # import is a real failure and must never be reported as "PySide6 absent".
    if exc.name == "PySide6" or (exc.name or "").startswith("PySide6."):
        QApplication = None
    else:
        raise


class FakeInventory:
    def search(self, query="", limit=100):
        products = [
            {"barcode": "D001", "name_en": "Sample Rice", "name_local": "සහල්", "stock_qty": 5, "selling_price": 250},
            {"barcode": "D002", "name_en": "Sample Soap", "name_local": "සබන්", "stock_qty": 8, "selling_price": 180},
        ]
        return [p for p in products if query.lower() in
                (p["barcode"] + p["name_en"] + p["name_local"]).lower()][:limit]


class FakeDirectory:
    def customers(self, query="", limit=100):
        records = [{"id": 1, "name": "Demo Customer", "phone": "0771112222",
                    "address": "Demo Town", "credit_balance": 125.50}]
        return [row for row in records if query.lower() in row["name"].lower()][:limit]

    def suppliers(self, query="", limit=100):
        records = [{"id": 1, "name": "Demo Supplier", "contact": "Demo Contact",
                    "phone": "0773334444", "address": "", "active": 1}]
        return [row for row in records if query.lower() in row["name"].lower()][:limit]


class FakeStore:
    def __init__(self):
        self.data = {"shop_name": "Demo", "theme": "light", "font_size": "15"}

    def get(self, key, default=""):
        return self.data.get(key, default)

    def set_many(self, changes):
        self.data.update(changes)


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class PreviewSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory(prefix="velopos8_qt_test_")
        self.preferences = QSettings(os.path.join(self.sandbox.name, "preview.ini"), QSettings.Format.IniFormat)
        self.window = SettingsPreview(SettingsAdapter(FakeStore()), preferences=self.preferences,
                                      inventory=FakeInventory())
        self.window.directory = FakeDirectory()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.sandbox.cleanup()

    def test_dashboard_quick_navigation_and_translation(self):
        self.assertEqual(len(self.window.quick_buttons), 3)
        self.window.quick_buttons[0][0].click()
        self.assertEqual(self.window.nav.currentRow(), 1)
        self.window.nav.setCurrentRow(0)
        self.window.locale_combo.setCurrentIndex(1)
        self.assertEqual(self.window.quick_buttons[0][0].text(), "තොගය බලන්න")
        self.window.quick_buttons[1][0].click()
        self.assertEqual(self.window.nav.currentRow(), 2)

    def test_dashboard_then_shop_settings(self):
        self.assertEqual(self.window.nav.count(), 9)
        self.assertEqual(self.window.nav.currentRow(), 0)
        self.window.nav.setCurrentRow(5)
        self.assertEqual(self.window.controls["shop_name"].text(), "Demo")

    def test_inventory_and_billing_draft_without_checkout(self):
        self.window.nav.setCurrentRow(1)
        inventory = self.window._pages[1]
        self.assertEqual(inventory.table.rowCount(), 2)
        inventory.query.setText("Rice")
        self.assertEqual(inventory.table.rowCount(), 1)

        self.window.nav.setCurrentRow(2)
        billing = self.window._pages[2]
        billing.results.setCurrentCell(0, 0)
        billing.add_selected()
        self.assertEqual(billing.cart_table.rowCount(), 1)
        self.assertEqual(str(billing.cart.subtotal()), "250.00")
        self.assertFalse(hasattr(billing, "checkout_button"))
        self.window.locale_combo.setCurrentIndex(1)
        self.assertEqual(billing.heading.text(), "බිල්පත් කෙටුම්පත")
        billing.clear_cart()
        self.assertEqual(billing.cart_table.rowCount(), 0)

    def test_customer_supplier_directories(self):
        self.window.nav.setCurrentRow(3)
        customers = self.window._pages[3]
        self.assertEqual(customers.table.rowCount(), 1)
        self.assertEqual(customers.table.item(0, 0).text(), "Demo Customer")
        customers.search.setText("nonexistent")
        self.assertEqual(customers.table.rowCount(), 0)

        self.window.nav.setCurrentRow(4)
        suppliers = self.window._pages[4]
        self.assertEqual(suppliers.table.rowCount(), 1)
        self.window.locale_combo.setCurrentIndex(1)
        self.assertEqual(suppliers.heading.text(), "සැපයුම්කරුවන්")

    def test_existing_bill_preview_estimate_uses_read_only_callback(self):
        from velopos_qt.core_pages import BillingPage

        requests = []
        def estimate(cart, discount, redeem):
            requests.append((cart, discount, redeem))
            return {"net": 265.00}

        page = BillingPage(FakeInventory(), self.window.t, bill_preview=estimate)
        try:
            page.results.setCurrentCell(0, 0)
            page.add_selected()
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0][0][0]["barcode"], "D001")
            self.assertEqual(requests[0][1:], (0.0, 0.0))
            self.assertIn("265.00", page.net_total.text())
            page.clear_cart()
            self.assertEqual(page.net_total.text(), "")
        finally:
            page.close()
            page.deleteLater()

    def test_inventory_editor_dialog_and_preview_header(self):
        from velopos_qt.product_dialog import ProductDialog
        from velopos_qt.core_pages import InventoryPage

        class FakeEditor:
            def __init__(self):
                self.saved = []
            def get(self, barcode):
                return {
                    "barcode": barcode, "name_en": "Rice",
                    "name_local": "සහල්", "stock_qty": 5,
                    "selling_price": 250
                }
            def save(self, *args, **kwargs):
                self.saved.append((args, kwargs))

        editor = FakeEditor()
        self.assertIn("TEST MODE", self.window.preview_badge.text())
        inventory_page = InventoryPage(FakeInventory(), self.window.t, editor=editor)
        dialog = ProductDialog(editor, self.window.t, barcode="D001")
        try:
            self.assertFalse(dialog.barcode.isEnabled() and not dialog.barcode.isReadOnly())
            self.assertEqual(dialog.name.text(), "Rice")
            dialog.stock.setText("8")
            dialog.accept()
            self.assertEqual(editor.saved[0][0], ("D001", "Rice"))
            self.assertEqual(editor.saved[0][1]["stock"], "8")
            self.assertEqual(inventory_page.add_product_button.text(), "New product")
        finally:
            dialog.close()
            inventory_page.close()
            dialog.deleteLater()
            inventory_page.deleteLater()

    def test_printer_settings_page_is_lazy_and_safe(self):
        self.assertNotIn(7, self.window._pages)
        self.window.nav.setCurrentRow(7)
        self.assertIn(7, self.window._pages)
        self.assertEqual(self.window.controls["printer_brand"].currentText(), "")
        self.window.controls["printer_brand"].setCurrentText("Xprinter")
        self.window.controls["paper_size"].setCurrentText("80mm")
        self.window.controls["print_mode"].setCurrentText("Browser only")
        self.window.controls["print_copies"].setCurrentText("2")
        self.window.controls["receipt_footer"].setText("Thanks")
        # Test the adapter directly to avoid a modal confirmation blocking smoke tests.
        settings = self.window.adapter.save({
            key: self.window.controls[key].currentText()
                 if hasattr(self.window.controls[key], "currentText")
                 else self.window.controls[key].text()
            for key in ("printer_brand", "paper_size", "print_mode", "print_copies", "receipt_footer")
        })
        self.assertEqual(settings["print_copies"], "2")

    def test_printer_labels_translate_in_sinhala(self):
        self.window.nav.setCurrentRow(7)
        self.window.locale_combo.setCurrentIndex(1)
        self.assertEqual(self.window.nav.item(7).text(), "මුද්‍රණ යන්ත්‍ර සහ රිසිට්පත්")
        self.assertEqual(self.window.printer_notice.text()[:4], "මෙහි")

    def test_sinhala_switch_updates_visible_labels(self):
        self.window.nav.setCurrentRow(5)
        self.window.locale_combo.setCurrentIndex(1)
        self.assertEqual(self.window.nav.item(5).text(), "වෙළඳසැල් තොරතුරු")
        self.assertTrue(any(label.text() == "වෙළඳසැලේ නම"
                            for label, _ in self.window.translatable_labels))

    def test_language_persists_across_preview_windows(self):
        self.window.locale_combo.setCurrentIndex(1)
        self.assertEqual(self.preferences.value("language"), "si")
        other = SettingsPreview(SettingsAdapter(FakeStore()), preferences=self.preferences,
                                inventory=FakeInventory())
        try:
            self.assertEqual(other.locale, "si")
            self.assertEqual(other.locale_combo.currentData(), "si")
            self.assertEqual(other.nav.item(0).text(), "ප්‍රධාන පුවරුව")
        finally:
            other.close()
            other.deleteLater()

    def test_invalid_saved_locale_falls_back_to_english(self):
        self.preferences.setValue("language", "unknown")
        other = SettingsPreview(SettingsAdapter(FakeStore()), preferences=self.preferences)
        try:
            self.assertEqual(other.locale, "en")
        finally:
            other.close()
            other.deleteLater()

    def test_tamil_then_english_does_not_destroy_inputs(self):
        self.window.nav.setCurrentRow(5)
        self.window.controls["shop_name"].setText("Unsaved demo")
        self.window.locale_combo.setCurrentIndex(2)
        self.window.locale_combo.setCurrentIndex(0)
        self.assertEqual(self.window.controls["shop_name"].text(), "Unsaved demo")


if __name__ == "__main__":
    unittest.main()
