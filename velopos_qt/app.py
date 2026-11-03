"""Experimental, isolated PySide6 settings UI.

No production db, printer discovery, payment, or license operations are invoked.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)
from .settings_model import SettingsAdapter

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
    def __init__(self, adapter: SettingsAdapter):
        super().__init__()
        self.adapter = adapter
        self.saved = adapter.read()
        self.controls = {}
        self.setWindowTitle("VeloPOS 8.0 | Settings Preview — TEST DATA")
        self.resize(1020, 680)
        self.setMinimumSize(760, 520)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 20, 22, 20)
        title = QLabel("VeloPOS 8.0")
        title.setStyleSheet("font-size:24pt; font-weight:700;")
        outer.addWidget(title)
        sub = QLabel("Modern Settings Preview  •  Isolated test data  •  Not for shop use")
        sub.setObjectName("hint")
        outer.addWidget(sub)

        body = QHBoxLayout()
        outer.addLayout(body, 1)
        navpanel = QFrame()
        navpanel.setObjectName("panel")
        navlayout = QVBoxLayout(navpanel)
        self.nav = QListWidget()
        self.nav.addItems(["Shop profile", "Appearance", "About preview"])
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
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        heading = QLabel(["Shop profile", "Appearance", "About this preview"][index])
        heading.setStyleSheet("font-size:19pt; font-weight:650;")
        layout.addWidget(heading)
        form = QFormLayout()
        form.setVerticalSpacing(15)
        if index == 0:
            fields = [
                ("Shop name", "shop_name"), ("Telephone", "phone"),
                ("Address", "address"), ("Currency symbol", "currency"),
                ("Bank name", "bank_name"), ("Bank branch", "bank_branch"),
                ("Bank account", "bank_acc"), ("Account holder", "bank_holder"),
            ]
            for label, key in fields:
                form.addRow(label, self._line(key))
        elif index == 1:
            form.addRow("Theme", self._choice("theme", ["light", "dark", "system"]))
            form.addRow("Accent", self._choice("accent", ["Blue", "Green", "Purple", "Orange", "Red"]))
            form.addRow("Font", self._choice("font_family", ["Segoe UI", "Arial", "Nirmala UI", "Calibri"]))
            form.addRow("Font size", self._choice("font_size", ["13", "14", "15", "16", "18", "20", "22"]))
        else:
            notice = QLabel(
                "This is an isolated interface proof of concept.\n\n"
                "Existing billing, inventory, reports, licensing, and production "
                "settings remain in the original application.\n\n"
                "This preview does not read or write real shop data."
            )
            notice.setWordWrap(True)
            layout.addWidget(notice)
        if index in (0, 1):
            layout.addLayout(form)
            save = QPushButton("Save settings to test database")
            save.clicked.connect(self.save_settings)
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
            changes = {
                key: (widget.currentText() if isinstance(widget, QComboBox)
                      else widget.text())
                for key, widget in self.controls.items()
            }
            self.adapter.save(changes)
        except (ValueError, OSError, RuntimeError) as exc:
            QMessageBox.warning(self, "Unable to save", str(exc))
            return
        self.saved.update(changes)
        self._apply_theme()
        QMessageBox.information(self, "Saved", "Saved to isolated preview test database.")

    def _apply_theme(self):
        theme_widget = self.controls.get("theme")
        selected = theme_widget.currentText() if theme_widget else self.saved.get("theme", "light")
        if selected == "system":
            selected = "light"
        self.setStyleSheet(DARK if selected == "dark" else LIGHT)


def run(settings):
    app = QApplication.instance() or QApplication([])
    window = SettingsPreview(SettingsAdapter(settings))
    window.show()
    return app.exec()
