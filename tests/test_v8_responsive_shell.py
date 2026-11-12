"""Windows compact preview shell and sidebar UI regressions.

Purely local Qt offscreen tests, no production DB and no POS posting.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt, QSettings
    from PySide6.QtGui import QKeySequence
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
        self.data = {"shop_name": "Compact Demo", "theme": "dark"}

    def get(self, key, default=""):
        return self.data.get(key, default)

    def set_many(self, values):
        self.data.update(values)


class FakeInventory:
    def search(self, query="", limit=100):
        row = {
            "barcode": "DEMO-001", "name_en": "Sample Rice",
            "name_local": "සහල්", "stock_qty": 12,
            "selling_price": 245.00,
        }
        return [row] if query.lower() in (
            row["barcode"] + row["name_en"]
        ).lower() else []


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class PreviewResponsiveShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory(prefix="v8_responsive_")
        self.prefs = QSettings(
            os.path.join(self.sandbox.name, "prefs.ini"),
            QSettings.Format.IniFormat,
        )
        self.window = SettingsPreview(
            SettingsAdapter(FakeStore()), preferences=self.prefs,
            inventory=FakeInventory(),
        )
        self.window.show()
        QApplication.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QApplication.processEvents()
        self.sandbox.cleanup()

    def narrow(self, width=820):
        self.window.resize(width, 600)
        QApplication.processEvents()

    def test_compact_width_keeps_navigation_available_but_reserves_workspace(self):
        self.narrow()
        self.assertTrue(self.window._compact_mode)
        self.assertTrue(self.window.navpanel.isHidden())
        self.assertTrue(self.window.menu_button.isVisible())
        self.assertEqual(self.window.brand_title.text(), "VeloPOS 8")
        self.assertEqual(self.window.quick_jump_button.text(), "Ctrl+K")
        self.assertEqual(self.window.navpanel.width(), 216)
        self.assertEqual(self.window.outer_layout.contentsMargins().left(), 10)
        self.assertEqual(self.window.workspace_layout.contentsMargins().left(), 12)
        self.assertFalse(self.window.menu_button.isChecked())
        self.assertIn("QPushButton#sidebarToggle", DARK)
        self.assertIn("QPushButton#sidebarToggle", LIGHT)

    def test_menu_and_ctrl_b_toggle_same_sidebar_and_focus(self):
        self.narrow()
        self.window.menu_button.click()
        QApplication.processEvents()
        self.assertFalse(self.window.navpanel.isHidden())
        self.assertTrue(self.window.menu_button.isChecked())
        self.window.sidebar_shortcut.activated.emit()
        QApplication.processEvents()
        self.assertTrue(self.window.navpanel.isHidden())
        self.assertFalse(self.window.menu_button.isChecked())
        self.assertEqual(self.window.sidebar_shortcut.key(), QKeySequence("Ctrl+B"))

    def test_sidebar_selection_closes_compact_menu_and_preserves_draft_only(self):
        self.narrow()
        self.window.menu_button.click()
        self.window.nav.setCurrentRow(2)
        QApplication.processEvents()
        self.assertEqual(self.window.nav.currentRow(), 2)
        self.assertTrue(self.window.navpanel.isHidden())
        self.assertFalse(self.window.menu_button.isChecked())
        billing = self.window._pages[2]
        self.assertFalse(hasattr(billing, "checkout_button"))
        self.assertIsNone(self.window.transaction_gateway)
        self.assertIsNone(self.window.checkout_preflight)
        self.assertEqual(billing.cart_table.rowCount(), 0)

    def test_resize_restores_desktop_nav_and_respects_manual_toggle_within_mode(self):
        self.narrow(1000)
        self.assertTrue(self.window.navpanel.isHidden())
        self.window.menu_button.click()
        self.assertFalse(self.window.navpanel.isHidden())
        self.narrow(900)
        self.assertFalse(self.window.navpanel.isHidden())
        self.window.resize(1220, 780)
        QApplication.processEvents()
        self.assertFalse(self.window._compact_mode)
        self.assertFalse(self.window.navpanel.isHidden())
        self.assertEqual(self.window.navpanel.width(), 244)
        self.assertEqual(self.window.brand_title.text(), "VeloPOS 8.0")
        self.assertEqual(self.window.quick_jump_button.text(),
                         translate("en", "quick_jump_action"))
        self.window.menu_button.click()
        self.assertTrue(self.window.navpanel.isHidden())
        self.window.resize(1150, 700)
        QApplication.processEvents()
        self.assertTrue(self.window.navpanel.isHidden())
        self.narrow(820)
        self.assertTrue(self.window.navpanel.isHidden())

    def test_language_and_theme_changes_keep_compact_actions_readable(self):
        self.narrow()
        self.assertEqual(
            self.window.menu_button.accessibleName(),
            translate("en", "navigation_toggle"),
        )
        for index, code in ((1, "si"), (2, "ta"), (0, "en")):
            self.window.locale_combo.setCurrentIndex(index)
            self.assertEqual(
                self.window.menu_button.accessibleName(),
                translate(code, "navigation_toggle"),
            )
            self.assertEqual(
                self.window.menu_button.toolTip(),
                translate(code, "navigation_toggle_hint"),
            )
            self.assertEqual(
                self.window.quick_jump_button.accessibleName(),
                translate(code, "quick_jump_action"),
            )
            self.assertEqual(self.window.quick_jump_button.text(), "Ctrl+K")
        self.window.nav.setCurrentRow(6)
        self.window.controls["theme"].setCurrentText("light")
        self.window._apply_theme()
        self.assertIn("QPushButton#sidebarToggle", self.window.styleSheet())
        self.assertTrue(self.window.navpanel.isHidden())

    def test_quick_jump_in_compact_mode_preserves_canonical_navigation(self):
        self.narrow()
        def select_inventory(dialog):
            dialog.search.setText("inventory")
            self.assertEqual(
                dialog.results.currentItem().data(Qt.ItemDataRole.UserRole), 1
            )
            dialog.accept_selected()
            return dialog.result()

        with patch.object(PreviewQuickJumpDialog, "exec", select_inventory):
            self.window.quick_jump_button.click()
        self.assertEqual(self.window.nav.currentRow(), 1)
        self.assertTrue(self.window.navpanel.isHidden())
        self.assertEqual(self.window._pages[1].table.rowCount(), 1)
        self.assertIsNone(self.window.transaction_gateway)


if __name__ == "__main__":
    unittest.main()
