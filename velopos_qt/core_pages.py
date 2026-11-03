"""Read-only inventory browsing and draft cart widgets.

A draft cart never calls create_sale, prints receipts, or changes stock.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from .product_dialog import ProductDialog


class InventoryPage(QWidget):
    def __init__(self, inventory, text, editor=None):
        super().__init__()
        self.inventory = inventory
        self.text = text
        self.editor = editor
        self.products = []
        layout = QVBoxLayout(self)
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size:19pt; font-weight:650;")
        layout.addWidget(self.heading)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setClearButtonEnabled(True)
        self.query.textChanged.connect(self.refresh)
        row.addWidget(self.query)
        self.add_product_button = QPushButton()
        self.add_product_button.setObjectName("secondaryAction")
        self.add_product_button.clicked.connect(self.add_product)
        row.addWidget(self.add_product_button)
        self.edit_product_button = QPushButton()
        self.edit_product_button.setObjectName("secondaryAction")
        self.edit_product_button.clicked.connect(self.edit_selected)
        row.addWidget(self.edit_product_button)
        self.add_product_button.setVisible(self.editor is not None)
        self.edit_product_button.setVisible(self.editor is not None)
        layout.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        # Let product names use remaining width instead of truncating after
        # only a few characters, while numeric columns remain compact.
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.retranslate()
        self.refresh()

    def retranslate(self):
        self.heading.setText(self.text("inventory"))
        self.query.setPlaceholderText(self.text("product_search"))
        self.table.setHorizontalHeaderLabels([self.text(k) for k in
                                               ("barcode", "product_name", "stock", "price")])
        self.add_product_button.setText(self.text("new_product"))
        self.edit_product_button.setText(self.text("edit_product"))
        self.status.setText(self.text("preview_edit_warning") if self.editor is not None
                            else self.text("read_only_notice"))

    def _dialog(self, barcode=None):
        if self.editor is None:
            return
        try:
            dialog = ProductDialog(self.editor, self.text, barcode=barcode, parent=self)
        except (RuntimeError, ValueError) as exc:
            QMessageBox.warning(self, self.text("failed_title"), str(exc))
            return
        from PySide6.QtWidgets import QDialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def add_product(self):
        self._dialog()

    def edit_selected(self):
        index = self.table.currentRow()
        if 0 <= index < len(self.products):
            self._dialog(self.products[index]["barcode"])

    def refresh(self, _value=None):
        try:
            self.products = self.inventory.search(self.query.text(), limit=100)
        except Exception as exc:
            # No crashes on a transient preview database error.
            self.products = []
            self.status.setText(str(exc))
        else:
            self.status.setText(self.text("preview_edit_warning") if self.editor is not None
                                else self.text("read_only_notice"))
        self.table.setRowCount(len(self.products))
        for row, product in enumerate(self.products):
            for col, value in enumerate((
                product["barcode"], product["name_en"],
                f'{float(product["stock_qty"]):g}',
                f'{float(product["selling_price"]):,.2f}',
            )):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.table.setItem(row, col, item)


# The billing draft lives in its own module to keep inventory fast and focused.
from .billing_page import BillingPage
