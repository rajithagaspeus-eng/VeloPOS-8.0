"""Read-only inventory browsing and draft cart widgets.

A draft cart never calls create_sale, prints receipts, or changes stock.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from .preview_models import Cart


class InventoryPage(QWidget):
    def __init__(self, inventory, text):
        super().__init__()
        self.inventory = inventory
        self.text = text
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
        self.status.setText(self.text("read_only_notice"))

    def refresh(self, _value=None):
        try:
            self.products = self.inventory.search(self.query.text(), limit=100)
        except Exception as exc:
            # No crashes on a transient preview database error.
            self.products = []
            self.status.setText(str(exc))
        else:
            self.status.setText(self.text("read_only_notice"))
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
    def __init__(self, inventory, text):
        super().__init__()
        self.inventory = inventory
        self.text = text
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
