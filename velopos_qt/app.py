"""Experimental, isolated PySide6 settings UI.

No production db, printer discovery, payment, or license operations are invoked.
"""
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)
from .settings_model import SettingsAdapter, PRINTER_BRANDS, PRINT_MODES, PAPER_SIZES
from .i18n import LANGUAGES, translate
from .preview_models import InventoryReader, DirectoryReader
from .directory_pages import DirectoryPage
from .core_pages import InventoryPage, BillingPage
from .product_editor import PreviewProductEditor

DARK = """
QWidget { background:#0b1220; color:#e8edf8; font: 10pt 'Segoe UI'; }
QFrame#panel { background:#131f32; border:1px solid #26364c; border-radius:12px; }
QLineEdit, QComboBox { background:#1c2b40; border:1px solid #37506b;
  border-radius:7px; min-height:31px; padding:3px 10px; }
QPushButton { background:#15b8a6; color:#061c24; border:0; border-radius:8px;
  padding:10px 18px; font-weight:600; }
QPushButton:hover { background:#44d4c4; }
QListWidget { border:0; background:#131f32; font-size:11pt; }
QListWidget::item { padding:16px; border-radius:7px; }
QListWidget::item:selected { background:#1b716b; }
QLabel#hint { color:#a6b5ca; }
"""
LIGHT = """
QWidget { background:#f4f7fc; color:#17263a; font: 10pt 'Segoe UI'; }
QFrame#panel { background:#ffffff; border:1px solid #dbe4ef; border-radius:12px; }
QLineEdit, QComboBox { background:white; border:1px solid #c8d4e3;
  border-radius:7px; min-height:31px; padding:3px 10px; }
QPushButton { background:#087f78; color:white; border:0; border-radius:8px;
  padding:10px 18px; font-weight:600; }
QPushButton:hover { background:#076f69; }
QListWidget { border:0; background:#ffffff; font-size:11pt; }
QListWidget::item { padding:16px; border-radius:7px; }
QListWidget::item:selected { background:#c7eae6; color:#06463f; }
QLabel#hint { color:#617087; }
"""


class SettingsPreview(QMainWindow):
    def __init__(self, adapter: SettingsAdapter, preferences=None, inventory=None):
        super().__init__()
        self.preferences = preferences if preferences is not None else QSettings("VeloPOS", "VeloPOS8Preview")
        self.adapter = adapter
        self.inventory = inventory
        db = getattr(inventory, "database", None)
        self.directory = DirectoryReader(db) if db is not None else None
        # The guarded editor refuses production DB paths. No authentication
        # or production product mutations are enabled in V8 yet.
        self.product_editor = PreviewProductEditor(db) if db is not None else None
        self.saved = adapter.read()
        self.controls = {}
        stored_locale = str(self.preferences.value("language", "en"))
        self.locale = stored_locale if stored_locale in LANGUAGES else "en"
        self.translatable_labels = []
        self.save_buttons = []
        self.setWindowTitle("VeloPOS 8.0 | Modern Preview — TEST DATA")
        self.resize(1020, 680)
        self.setMinimumSize(760, 520)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 20, 22, 20)
        title = QLabel("VeloPOS 8.0")
        title.setStyleSheet("font-size:24pt; font-weight:700;")
        outer.addWidget(title)
        self.subtitle = QLabel(self.t("subtitle"))
        self.subtitle.setObjectName("hint")
        self.subtitle.setWordWrap(True)
        outer.addWidget(self.subtitle)

        locale_row = QHBoxLayout()
        locale_row.addStretch()
        self.locale_label = QLabel(self.t("language"))
        locale_row.addWidget(self.locale_label)
        self.locale_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.locale_combo.addItem(name, code)
        self.locale_combo.setCurrentIndex(list(LANGUAGES).index(self.locale))
        self.locale_combo.currentIndexChanged.connect(self.change_language)
        locale_row.addWidget(self.locale_combo)
        outer.addLayout(locale_row)

        body = QHBoxLayout()
        outer.addLayout(body, 1)
        navpanel = QFrame()
        navpanel.setObjectName("panel")
        navlayout = QVBoxLayout(navpanel)
        self.nav = QListWidget()
        self.nav.addItems([self.t(key) for key in self.nav_keys])
        navlayout.addWidget(self.nav)
        navpanel.setFixedWidth(230)
        body.addWidget(navpanel)
        content = QFrame()
        content.setObjectName("panel")
        contentlayout = QVBoxLayout(content)
        contentlayout.setContentsMargins(26, 26, 26, 22)
        self.pages = QStackedWidget()
        contentlayout.addWidget(self.pages)
        body.addWidget(content, 1)

        # Lazy-create each page on first navigation; never repaint a giant form.
        self._pages = {}
        self.nav.currentRowChanged.connect(self.open_page)
        self.nav.setCurrentRow(0)
        self._apply_theme()

    nav_keys = ("dashboard", "inventory", "billing", "customers", "suppliers", "shop_profile", "appearance", "printer_receipts", "about")

    def t(self, key):
        return translate(self.locale, key)

    def change_language(self, _index):
        self.locale = self.locale_combo.currentData() or "en"
        self.preferences.setValue("language", self.locale)
        self.subtitle.setText(self.t("subtitle"))
        self.locale_label.setText(self.t("language"))
        for index, key in enumerate(self.nav_keys):
            self.nav.item(index).setText(self.t(key))
        for label, key in self.translatable_labels:
            label.setText(self.t(key))
        for button in self.save_buttons:
            button.setText(self.t("save"))
        if hasattr(self, "dashboard_intro"):
            self.dashboard_intro.setText(self.t("dashboard_intro"))
            self.dashboard_hint.setText(self.t("dashboard_hint"))
        if hasattr(self, "about_notice"):
            self.about_notice.setText(self.t("about_text"))
        if hasattr(self, "printer_notice"):
            self.printer_notice.setText(self.t("printer_notice"))
        for page in self._pages.values():
            if isinstance(page, (InventoryPage, BillingPage, DirectoryPage)):
                page.retranslate()

    def add_field(self, form, key, widget):
        label = QLabel(self.t(key))
        label.setMinimumWidth(155)
        form.addRow(label, widget)
        self.translatable_labels.append((label, key))

    def _line(self, key):
        widget = QLineEdit(self.saved.get(key, ""))
        self.controls[key] = widget
        return widget

    def _choice(self, key, values):
        widget = QComboBox()
        widget.addItems(values)
        original = self.saved.get(key, "")
        if original not in values:
            widget.addItem(original)
        widget.setCurrentText(original)
        self.controls[key] = widget
        return widget

    def _create_page(self, index):
        if index == 1 and self.inventory is not None:
            return InventoryPage(self.inventory, self.t, editor=self.product_editor)
        if index == 2 and self.inventory is not None:
            # Only use the original billing preview engine in our test-only DB.
            preview_fn = None
            db = getattr(self.inventory, "database", None)
            if db is not None:
                from pathlib import Path
                if Path(db.DATA_DIR).resolve().name.casefold() == "velopos8previewdata":
                    from velopos import services
                    preview_fn = services.preview_bill
            return BillingPage(self.inventory, self.t, bill_preview=preview_fn)
        if index in (3, 4) and self.directory is not None:
            return DirectoryPage(self.directory, self.nav_keys[index], self.t)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        heading = QLabel(self.t(self.nav_keys[index]))
        self.translatable_labels.append((heading, self.nav_keys[index]))
        heading.setStyleSheet("font-size:19pt; font-weight:650;")
        layout.addWidget(heading)
        form = QFormLayout()
        form.setVerticalSpacing(15)
        if index == 0:
            self.dashboard_intro = QLabel(self.t("dashboard_intro"))
            self.dashboard_intro.setWordWrap(True)
            self.dashboard_hint = QLabel(self.t("dashboard_hint"))
            self.dashboard_hint.setWordWrap(True)
            layout.addWidget(self.dashboard_intro)
            layout.addWidget(self.dashboard_hint)
        elif index == 5:
            fields = [
                ("shop_name", "shop_name"), ("phone", "phone"),
                ("address", "address"), ("currency", "currency"),
                ("bank_name", "bank_name"), ("bank_branch", "bank_branch"),
                ("bank_acc", "bank_acc"), ("bank_holder", "bank_holder"),
            ]
            for label, key in fields:
                self.add_field(form, key, self._line(key))
        elif index == 6:
            self.add_field(form, "theme", self._choice("theme", ["light", "dark", "system"]))
            self.add_field(form, "accent", self._choice("accent", ["Blue", "Green", "Purple", "Orange", "Red"]))
            self.add_field(form, "font_family", self._choice("font_family", ["Segoe UI", "Arial", "Nirmala UI", "Calibri"]))
            self.add_field(form, "font_size", self._choice("font_size", ["13", "14", "15", "16", "18", "20", "22"]))
        elif index == 7:
            self.printer_notice = QLabel(self.t("printer_notice"))
            self.printer_notice.setWordWrap(True)
            layout.addWidget(self.printer_notice)
            self.add_field(form, "printer_brand", self._choice("printer_brand", PRINTER_BRANDS))
            self.add_field(form, "print_mode", self._choice("print_mode", PRINT_MODES))
            self.add_field(form, "paper_size", self._choice("paper_size", PAPER_SIZES))
            self.add_field(form, "print_copies", self._choice("print_copies", [str(i) for i in range(1, 6)]))
            self.add_field(form, "receipt_footer", self._line("receipt_footer"))
        else:
            self.about_notice = QLabel(self.t("about_text"))
            self.about_notice.setWordWrap(True)
            layout.addWidget(self.about_notice)
        if index in (5, 6, 7):
            layout.addLayout(form)
            save = QPushButton(self.t("save"))
            save.clicked.connect(self.save_settings)
            self.save_buttons.append(save)
            layout.addWidget(save, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addStretch()
        return page

    def open_page(self, index):
        if index < 0:
            return
        if index not in self._pages:
            page = self._create_page(index)
            self._pages[index] = page
            self.pages.addWidget(page)
        self.pages.setCurrentWidget(self._pages[index])

    def save_settings(self):
        try:
            # Save only the visible page's values, avoiding stale values from other pages.
            page_fields = {
                5: ("shop_name", "phone", "address", "currency", "bank_name", "bank_branch", "bank_acc", "bank_holder"),
                6: ("theme", "accent", "font_family", "font_size"),
                7: ("printer_brand", "print_mode", "paper_size", "print_copies", "receipt_footer"),
            }
            keys = page_fields.get(self.nav.currentRow(), ())
            changes = {
                key: (self.controls[key].currentText()
                      if isinstance(self.controls[key], QComboBox)
                      else self.controls[key].text())
                for key in keys if key in self.controls
            }
            self.adapter.save(changes)
        except (ValueError, OSError, RuntimeError) as exc:
            QMessageBox.warning(self, self.t("failed_title"), str(exc))
            return
        self.saved.update(changes)
        if "theme" in changes:
            self._apply_theme()
        QMessageBox.information(self, self.t("saved_title"), self.t("saved"))

    def _apply_theme(self):
        theme_widget = self.controls.get("theme")
        selected = theme_widget.currentText() if theme_widget else self.saved.get("theme", "light")
        if selected == "system":
            selected = "light"
        self.setStyleSheet(DARK if selected == "dark" else LIGHT)


def run(settings, database=None):
    app = QApplication.instance() or QApplication([])
    window = SettingsPreview(SettingsAdapter(settings),
                             inventory=InventoryReader(database) if database is not None else None)
    window.show()
    return app.exec()
