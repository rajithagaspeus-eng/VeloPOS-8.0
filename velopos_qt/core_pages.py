"""Read-only inventory browsing and draft cart widgets.

A draft cart never calls create_sale, prints receipts, or changes stock.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from .preview_models import Cart, preview_existing_bill
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
        self.table.horizontalHeader().setStretchLastSection(True)
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
                self.table.setItem(row, col, item)


class BillingPage(QWidget):
    def __init__(self, inventory, text, bill_preview=None):
        super().__init__()
        self.inventory = inventory
        self.text = text
        self.bill_preview = bill_preview
        self.cart = Cart()
        self.products = []
        layout = QVBoxLayout(self)
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size:19pt; font-weight:650;")
        layout.addWidget(self.heading)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        search_row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.textChanged.connect(self.refresh_products)
        search_row.addWidget(self.query)
        self.add_button = QPushButton()
        self.add_button.clicked.connect(self.add_selected)
        search_row.addWidget(self.add_button)
        layout.addLayout(search_row)
        self.results = QTableWidget(0, 3)
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.setMaximumHeight(190)
        self.results.verticalHeader().setVisible(False)
        layout.addWidget(self.results)
        self.cart_table = QTableWidget(0, 4)
        self.cart_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cart_table.verticalHeader().setVisible(False)
        layout.addWidget(self.cart_table)
        bottom = QHBoxLayout()
        self.total = QLabel()
        bottom.addWidget(self.total)
        self.net_total = QLabel()
        bottom.addWidget(self.net_total)
        bottom.addStretch()
        self.remove_button = QPushButton()
        self.remove_button.clicked.connect(self.remove_selected)
        bottom.addWidget(self.remove_button)
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(self.clear_cart)
        bottom.addWidget(self.clear_button)
        layout.addLayout(bottom)
        self.retranslate()
        self.refresh_products()
        self.refresh_cart()

    def retranslate(self):
        self.heading.setText(self.text("billing"))
        self.notice.setText(self.text("no_checkout_notice"))
        self.query.setPlaceholderText(self.text("product_search"))
        self.add_button.setText(self.text("add_to_cart"))
        self.remove_button.setText(self.text("remove_line"))
        self.clear_button.setText(self.text("clear_cart"))
        self.results.setHorizontalHeaderLabels([self.text(k) for k in
                                                ("barcode", "product_name", "price")])
        self.cart_table.setHorizontalHeaderLabels([self.text(k) for k in
                                                   ("product_name", "quantity", "price", "line_total")])
        self.refresh_cart()

    def refresh_products(self, _value=None):
        try:
            self.products = self.inventory.search(self.query.text(), limit=50)
        except Exception as exc:
            self.products = []
            self.notice.setText(str(exc))
        self.results.setRowCount(len(self.products))
        for row, p in enumerate(self.products):
            for col, value in enumerate((p["barcode"], p["name_en"], f'{float(p["selling_price"]):,.2f}')):
                self.results.setItem(row, col, QTableWidgetItem(str(value)))

    def add_selected(self):
        index = self.results.currentRow()
        if index < 0 or index >= len(self.products):
            return
        try:
            self.cart.add(self.products[index])
        except ValueError as exc:
            QMessageBox.warning(self, self.text("failed_title"), str(exc))
            return
        self.refresh_cart()

    def remove_selected(self):
        row = self.cart_table.currentRow()
        if 0 <= row < len(self.cart.lines):
            barcode = list(self.cart.lines)[row]
            self.cart.remove(barcode)
            self.refresh_cart()

    def clear_cart(self):
        self.cart.clear()
        self.refresh_cart()

    def refresh_cart(self):
        lines = list(self.cart.lines.values())
        self.cart_table.setRowCount(len(lines))
        for row, line in enumerate(lines):
            for col, value in enumerate((
                line["name"], f'{line["qty"]:g}', f'{line["price"]:,.2f}',
                f'{line["qty"] * line["price"]:,.2f}',
            )):
                self.cart_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.total.setText(f'{self.text("subtotal")}: {self.cart.subtotal():,.2f}')
        if self.bill_preview is not None and lines:
            try:
                result = preview_existing_bill(self.cart, self.bill_preview)
                self.net_total.setText(f'{self.text("estimated_net")}: {float(result["net"]):,.2f}')
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self.net_total.setText(f'{self.text("preview_error")}: {exc}')
        else:
            self.net_total.setText("")
