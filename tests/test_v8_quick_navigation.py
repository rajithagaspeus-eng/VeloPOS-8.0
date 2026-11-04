"""V8 premium quick jump UI tests (headless, no customer/production data)."""
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtGui import QKeySequence
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog
    from velopos_qt.app import SettingsPreview, DARK, LIGHT
    from velopos_qt.i18n import translate
    from velopos_qt.quick_navigation import PreviewQuickJumpDialog
    from velopos_qt.settings_model import SettingsAdapter
except ModuleNotFoundError as exc:
    if exc.name == "PySide6" or (exc.name or "").startswith("PySide6."):
        QApplication = None
    else:
        raise


class FakeStore:
    def __init__(self):
        self.settings = {"shop_name": "Quick Jump Demo", "theme": "light"}

    def get(self, key, default=""):
        return self.settings.get(key, default)

    def set_many(self, changes):
        self.settings.update(changes)


class FakeInventory:
    def search(self, query="", limit=100):
        items = [
            {"barcode": "DEMO-001", "name_en": "Sample Rice",
             "name_local": "සහල්", "stock_qty": 36,
             "selling_price": 245},
        ]
        return [item for item in items if query.casefold() in (
            item["name_en"] + item["barcode"]).casefold()][:limit]


@unittest.skipIf(QApplication is None, "PySide6 unavailable")
class PreviewQuickNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory(prefix="v8_quick_jump_")
        prefs = QSettings(
            os.path.join(self.sandbox.name, "quick_jump.ini"),
            QSettings.Format.IniFormat,
        )
        self.window = SettingsPreview(
            SettingsAdapter(FakeStore()), preferences=prefs,
            inventory=FakeInventory(),
        )

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.sandbox.cleanup()

    def dialog(self):
        return PreviewQuickJumpDialog(
            self.window.nav_keys, self.window.t, parent=self.window
        )

    def test_all_fourteen_pages_maintain_canonical_indices(self):
        dialog = self.dialog()
        try:
            self.assertEqual(dialog.results.count(), 14)
            self.assertEqual(
                [dialog.results.item(i).data(Qt.ItemDataRole.UserRole)
                 for i in range(dialog.results.count())],
                list(range(14)),
            )
            self.assertIn("Ctrl+K", self.window.quick_jump_button.text())
            self.assertEqual(
                self.window.quick_jump_shortcut.key(),
                QKeySequence("Ctrl+K"),
            )
            self.assertIn("QPushButton#quickJumpAction", DARK)
            self.assertIn("QPushButton#quickJumpAction", LIGHT)
            self.assertEqual(dialog.search.objectName(), "quickJumpSearch")
            self.assertTrue(dialog.search.accessibleName())
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_search_handles_english_label_on_sinhala_screen(self):
        self.window.locale_combo.setCurrentIndex(1)
        dialog = self.dialog()
        try:
            dialog.search.setText("Inventory")
            # Both "Inventory" and "Smart inventory" are genuine matches.
            # The canonical Inventory page must stay first.
            self.assertEqual(dialog.results.count(), 2)
            self.assertEqual(
                [dialog.results.item(i).data(Qt.ItemDataRole.UserRole)
                 for i in range(dialog.results.count())], [1, 10]
            )
            self.assertEqual(
                dialog.results.currentItem().data(Qt.ItemDataRole.UserRole), 1
            )
            self.assertIn("තොග", dialog.results.currentItem().text())
            dialog.accept_selected()
            self.assertEqual(dialog.selected_index, 1)
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_tamil_label_search_and_no_results_fail_closed(self):
        self.window.locale_combo.setCurrentIndex(2)
        dialog = self.dialog()
        try:
            dialog.search.setText(translate("ta", "customers"))
            self.assertEqual(dialog.results.count(), 1)
            self.assertEqual(
                dialog.results.item(0).data(Qt.ItemDataRole.UserRole), 3
            )
            dialog.search.setText("does-not-exist-anywhere")
            self.assertEqual(dialog.results.count(), 0)
            self.assertFalse(dialog.go_button.isEnabled())
            self.assertEqual(dialog.hint.text(),
                             translate("ta", "quick_jump_no_results"))
            dialog.accept_selected()
            self.assertIsNone(dialog.selected_index)
            self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_keyboard_down_up_and_enter_activate_selected_page(self):
        dialog = self.dialog()
        try:
            dialog.search.setText("report")
            # One matching page should not permit row indices out of range.
            self.assertEqual(dialog.results.count(), 1)
            QTest.keyClick(dialog.search, Qt.Key.Key_Down)
            self.assertEqual(dialog.results.currentRow(), 0)
            QTest.keyClick(dialog.search, Qt.Key.Key_Up)
            self.assertEqual(dialog.results.currentRow(), 0)
            dialog.search.clear()
            QTest.keyClick(dialog.search, Qt.Key.Key_Down)
            self.assertEqual(dialog.results.currentRow(), 1)
            QTest.keyClick(dialog.search, Qt.Key.Key_Up)
            self.assertEqual(dialog.results.currentRow(), 0)
            QTest.keyClick(dialog.search, Qt.Key.Key_Return)
            self.assertEqual(dialog.selected_index, 0)
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_topbar_and_keyboard_share_original_navigation_and_denial(self):
        def choose_billing(dialog):
            dialog.search.setText("billing")
            self.assertEqual(dialog.results.count(), 1)
            dialog.accept_selected()
            return dialog.result()

        with patch.object(PreviewQuickJumpDialog, "exec", choose_billing):
            self.window.quick_jump_button.click()
        self.assertEqual(self.window.nav.currentRow(), 2)
        page = self.window._pages[2]
        self.assertFalse(hasattr(page, "checkout_button"))
        self.assertIsNone(self.window.transaction_gateway)
        self.assertIsNone(self.window.checkout_preflight)

        def choose_inventory(dialog):
            dialog.search.setText("inventory")
            dialog.accept_selected()
            return dialog.result()

        with patch.object(PreviewQuickJumpDialog, "exec", choose_inventory):
            self.window.quick_jump_shortcut.activated.emit()
        self.assertEqual(self.window.nav.currentRow(), 1)
        self.assertEqual(self.window._pages[1].table.rowCount(), 1)

    def test_cancel_stays_on_page_and_localized_action_relabels(self):
        self.window.nav.setCurrentRow(4)
        with patch.object(
            PreviewQuickJumpDialog, "exec",
            lambda dialog: QDialog.DialogCode.Rejected,
        ):
            self.window.open_quick_jump()
        self.assertEqual(self.window.nav.currentRow(), 4)

        for index, code in ((1, "si"), (2, "ta"), (0, "en")):
            self.window.locale_combo.setCurrentIndex(index)
            self.assertEqual(self.window.quick_jump_button.text(),
                             translate(code, "quick_jump_action"))
            self.assertEqual(self.window.quick_jump_button.toolTip(),
                             translate(code, "quick_jump_hint"))

        dialog = self.dialog()
        try:
            dialog.show()
            QApplication.processEvents()
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
            self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        finally:
            dialog.close()
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
