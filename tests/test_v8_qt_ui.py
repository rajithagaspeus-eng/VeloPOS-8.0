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
except ImportError:
    QApplication = None


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
        self.window = SettingsPreview(SettingsAdapter(FakeStore()), preferences=self.preferences)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.sandbox.cleanup()

    def test_dashboard_then_shop_settings(self):
        self.assertEqual(self.window.nav.count(), 4)
        self.assertEqual(self.window.nav.currentRow(), 0)
        self.window.nav.setCurrentRow(1)
        self.assertEqual(self.window.controls["shop_name"].text(), "Demo")

    def test_sinhala_switch_updates_visible_labels(self):
        self.window.nav.setCurrentRow(1)
        self.window.locale_combo.setCurrentIndex(1)
        self.assertEqual(self.window.nav.item(1).text(), "වෙළඳසැල් තොරතුරු")
        self.assertTrue(any(label.text() == "වෙළඳසැලේ නම"
                            for label, _ in self.window.translatable_labels))

    def test_language_persists_across_preview_windows(self):
        self.window.locale_combo.setCurrentIndex(1)
        self.assertEqual(self.preferences.value("language"), "si")
        other = SettingsPreview(SettingsAdapter(FakeStore()), preferences=self.preferences)
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
        self.window.nav.setCurrentRow(1)
        self.window.controls["shop_name"].setText("Unsaved demo")
        self.window.locale_combo.setCurrentIndex(2)
        self.window.locale_combo.setCurrentIndex(0)
        self.assertEqual(self.window.controls["shop_name"].text(), "Unsaved demo")


if __name__ == "__main__":
    unittest.main()
