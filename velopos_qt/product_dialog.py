"""Focused product form for preview-only inventory edits."""
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
    QVBoxLayout,
)


class ProductDialog(QDialog):
    def __init__(self, editor, text, barcode=None, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.text = text
        self.setMinimumWidth(430)
        self.setWindowTitle(text("edit_product") if barcode else text("new_product"))
        main = QVBoxLayout(self)
        notice = QLabel(text("preview_edit_warning"))
        notice.setWordWrap(True)
        main.addWidget(notice)
        form = QFormLayout()
        self.barcode = QLineEdit()
        self.name = QLineEdit()
        self.local_name = QLineEdit()
        self.price = QLineEdit("0")
        self.stock = QLineEdit("0")
        self.stock.setToolTip(text("stock_absolute_hint"))
        for field, widget in (
            ("barcode", self.barcode),
            ("product_name", self.name),
            ("product_local_name", self.local_name),
            ("price", self.price),
            ("stock", self.stock),
        ):
            form.addRow(text(field), widget)
        main.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        main.addWidget(self.buttons)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color:#d44b4b;")
        main.addWidget(self.error)
        if barcode is not None:
            record = self.editor.get(barcode)
            if record is None:
                raise ValueError("Product no longer exists")
            self.barcode.setText(record["barcode"])
            self.barcode.setReadOnly(True)
            self.name.setText(record["name_en"])
            self.local_name.setText(record["name_local"] or "")
            self.price.setText(str(record["selling_price"]))
            self.stock.setText(str(record["stock_qty"]))

    def accept(self):
        try:
            self.editor.save(
                self.barcode.text(),
                self.name.text(),
                name_local=self.local_name.text(),
                sell=self.price.text(),
                stock=self.stock.text(),
            )
        except (RuntimeError, OSError, ValueError, PermissionError) as exc:
            self.error.setText(str(exc))
            return
        super().accept()
