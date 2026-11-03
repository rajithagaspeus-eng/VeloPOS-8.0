"""Fast keyboard-friendly billing draft UI — NO sale, payment or stock writes.

Barcodes can be scanned into the search field and submitted with Enter.
The cart exists in memory only. Display totals use the existing read-only
bill preview service when the isolated launcher provides it.
"""
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .preview_models import Cart, preview_existing_bill, cash_estimate, money


class BillingPage(QWidget):
    def __init__(self, inventory, text, bill_preview=None, shift_reader=None, identity=None, stock_reader=None):
        super().__init__()
        self.inventory = inventory
        self.text = text
        self.bill_preview = bill_preview
        self.shift_reader = shift_reader
        self.identity = identity or (lambda: None)
        self.stock_reader = stock_reader
        self._last_stock_signature = None
        self.cart = Cart()
        self.products = []
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.heading = QLabel()
        self.heading.setStyleSheet("font-size:19pt; font-weight:650;")
        layout.addWidget(self.heading)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.shift_status = QLabel()
        self.shift_status.setWordWrap(True)
        self.shift_status.setObjectName("hint")
        layout.addWidget(self.shift_status)

        search_row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setClearButtonEnabled(True)
        self.query.setMinimumHeight(44)
        self.query.textChanged.connect(self.refresh_products)
        self.query.returnPressed.connect(self.scan_or_add)
        search_row.addWidget(self.query, 1)
        self.add_button = QPushButton()
        self.add_button.setMinimumHeight(44)
        self.add_button.clicked.connect(self.add_selected)
        search_row.addWidget(self.add_button)
        layout.addLayout(search_row)

        self.results = QTableWidget(0, 3)
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.setMaximumHeight(180)
        self.results.setMinimumHeight(105)
        self.results.verticalHeader().setVisible(False)
        self.results.setAlternatingRowColors(True)
        header = self.results.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.results.itemDoubleClicked.connect(lambda _item: self.add_selected())
        layout.addWidget(self.results)

        self.cart_title = QLabel()
        self.cart_title.setStyleSheet("font-size:12pt; font-weight:650;")
        layout.addWidget(self.cart_title)
        self.cart_table = QTableWidget(0, 4)
        self.cart_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.cart_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.cart_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.setAlternatingRowColors(True)
        cart_header = self.cart_table.horizontalHeader()
        cart_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index in (1, 2, 3):
            cart_header.setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
        self.cart_table.itemDoubleClicked.connect(lambda _item: self.edit_quantity())
        layout.addWidget(self.cart_table, 1)

        controls = QHBoxLayout()
        self.quantity_label = QLabel()
        controls.addWidget(self.quantity_label)
        self.quantity_input = QLineEdit("1")
        self.quantity_input.setMaximumWidth(95)
        self.quantity_input.setToolTip("Positive quantity. Press Enter to update the selected cart line.")
        self.quantity_input.returnPressed.connect(self.edit_quantity)
        controls.addWidget(self.quantity_input)
        self.quantity_button = QPushButton()
        self.quantity_button.setObjectName("secondaryAction")
        self.quantity_button.clicked.connect(self.edit_quantity)
        controls.addWidget(self.quantity_button)
        controls.addStretch(1)
        self.remove_button = QPushButton()
        self.remove_button.setObjectName("secondaryAction")
        self.remove_button.clicked.connect(self.remove_selected)
        controls.addWidget(self.remove_button)
        self.clear_button = QPushButton()
        self.clear_button.setObjectName("secondaryAction")
        self.clear_button.clicked.connect(self.clear_cart)
        controls.addWidget(self.clear_button)
        layout.addLayout(controls)

        # No payment is recorded. These fields are draft-only estimates.
        estimate_row = QHBoxLayout()
        self.discount_label = QLabel()
        estimate_row.addWidget(self.discount_label)
        self.discount_input = QLineEdit("0")
        self.discount_input.setMaximumWidth(90)
        self.discount_input.textChanged.connect(lambda _text: self.refresh_cart())
        estimate_row.addWidget(self.discount_input)
        self.tender_label = QLabel()
        estimate_row.addWidget(self.tender_label)
        self.tender_input = QLineEdit("0")
        self.tender_input.setMaximumWidth(100)
        self.tender_input.textChanged.connect(lambda _text: self.refresh_cart())
        estimate_row.addWidget(self.tender_input)
        estimate_row.addStretch(1)
        layout.addLayout(estimate_row)
        self.cash_status = QLabel()
        self.cash_status.setWordWrap(True)
        layout.addWidget(self.cash_status)
        self.stock_status = QLabel()
        self.stock_status.setWordWrap(True)
        layout.addWidget(self.stock_status)

        self.totals_panel = QFrame()
        self.totals_panel.setObjectName("billingTotals")
        summary = QHBoxLayout(self.totals_panel)
        summary.setContentsMargins(16, 14, 16, 14)
        self.line_count = QLabel()
        summary.addWidget(self.line_count)
        summary.addStretch(1)
        self.total = QLabel()
        self.total.setStyleSheet("font-size:13pt; font-weight:650;")
        summary.addWidget(self.total)
        self.net_total = QLabel()
        self.net_total.setStyleSheet("font-size:14pt; font-weight:750;")
        summary.addWidget(self.net_total)
        layout.addWidget(self.totals_panel)

        self.barcode_shortcut = QShortcut(QKeySequence("F2"), self)
        self.barcode_shortcut.activated.connect(self.query.setFocus)
        self.quantity_shortcut = QShortcut(QKeySequence("F3"), self)
        self.quantity_shortcut.activated.connect(self.quantity_input.setFocus)

        self.retranslate()
        self.refresh_products()
        self.refresh_cart()

    def retranslate(self):
        self.heading.setText(self.text("billing"))
        self.notice.setText(self.text("no_checkout_notice"))
        self.query.setPlaceholderText(self.text("barcode_search_hint"))
        self.add_button.setText(self.text("add_to_cart"))
        self.quantity_label.setText(self.text("quantity"))
        self.quantity_button.setText(self.text("update_quantity"))
        self.remove_button.setText(self.text("remove_line"))
        self.clear_button.setText(self.text("clear_cart"))
        self.cart_title.setText(self.text("draft_items"))
        self.discount_label.setText(self.text("draft_discount"))
        self.tender_label.setText(self.text("draft_cash_tender"))
        self.results.setHorizontalHeaderLabels(
            [self.text(k) for k in ("barcode", "product_name", "price")]
        )
        self.cart_table.setHorizontalHeaderLabels(
            [self.text(k) for k in ("product_name", "quantity", "price", "line_total")]
        )
        self._last_stock_signature = None
        self.refresh_cart()
        self.refresh_shift()

    def refresh_stock(self):
        self._last_stock_signature = None
        self.refresh_cart()

    def refresh_shift(self):
        """Information only; never used to authorize sale operations."""
        if self.shift_reader is None:
            self.shift_status.setText(self.text("shift_preview_unavailable"))
            return
        try:
            shift = self.shift_reader.current()
        except (OSError, RuntimeError) as exc:
            self.shift_status.setText(str(exc))
            return
        user = self.identity()
        actor = user.username if user is not None else self.text("not_signed_in")
        if shift:
            self.shift_status.setText(
                f'{self.text("preview_cashier")}: {actor}  •  '
                f'{self.text("open_shift_label")}: #{shift["id"]} ({shift["cashier"]})'
            )
        else:
            self.shift_status.setText(
                f'{self.text("preview_cashier")}: {actor}  •  {self.text("no_open_shift")}'
            )

    def refresh_products(self, _value=None):
        try:
            self.products = self.inventory.search(self.query.text(), limit=50)
        except (OSError, ValueError, RuntimeError) as exc:
            self.products = []
            self.notice.setText(str(exc))
        else:
            self.notice.setText(self.text("no_checkout_notice"))
        self.results.setRowCount(len(self.products))
        for row, item in enumerate(self.products):
            values = (item["barcode"], item["name_en"],
                      f'{float(item["selling_price"]):,.2f}')
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setToolTip(str(value))
                self.results.setItem(row, col, cell)

    def scan_or_add(self):
        """Exact scan matches only; single-result search can also use Enter."""
        term = self.query.text().strip()
        if not term:
            return
        exact = next((i for i, product in enumerate(self.products)
                      if str(product["barcode"]) == term), None)
        if exact is not None:
            self.results.selectRow(exact)
            self.add_selected()
        elif len(self.products) == 1:
            self.results.selectRow(0)
            self.add_selected()
        # Multiple ambiguous results: require a selection/click, never
        # silently choose the wrong stock item.

    def add_selected(self):
        index = self.results.currentRow()
        if not 0 <= index < len(self.products):
            return
        try:
            self.cart.add(self.products[index])
        except ValueError as exc:
            QMessageBox.warning(self, self.text("failed_title"), str(exc))
            return
        self.refresh_cart()
        self.query.clear()
        self.query.setFocus()

    def edit_quantity(self):
        row = self.cart_table.currentRow()
        if not 0 <= row < len(self.cart.lines):
            return
        barcode = list(self.cart.lines)[row]
        try:
            self.cart.set_quantity(barcode, self.quantity_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, self.text("failed_title"), str(exc))
            return
        self.refresh_cart(selected_barcode=barcode)

    def remove_selected(self):
        row = self.cart_table.currentRow()
        if 0 <= row < len(self.cart.lines):
            self.cart.remove(list(self.cart.lines)[row])
            self.refresh_cart()

    def clear_cart(self):
        self.cart.clear()
        self.refresh_cart()

    def refresh_cart(self, selected_barcode=None):
        lines = list(self.cart.lines.values())
        self.cart_table.setRowCount(len(lines))
        for row, line in enumerate(lines):
            values = (line["name"], f'{line["qty"]:g}', f'{line["price"]:,.2f}',
                      f'{money(line["qty"] * line["price"]):,.2f}')
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.cart_table.setItem(row, col, item)
            if line["barcode"] == selected_barcode:
                self.cart_table.selectRow(row)
        self.line_count.setText(f'{self.text("draft_items")}: {len(lines)}')
        self.total.setText(f'{self.text("subtotal")}: {self.cart.subtotal():,.2f}')
        self.cash_status.setText("")
        if lines:
            try:
                if self.bill_preview is not None:
                    result = preview_existing_bill(
                        self.cart, self.bill_preview, self.discount_input.text()
                    )
                    due = money(result["net"])
                else:
                    from .preview_models import validated_discount
                    due = self.cart.subtotal() - validated_discount(
                        self.discount_input.text(), self.cart.subtotal()
                    )
                self.net_total.setText(f'{self.text("estimated_net")}: {due:,.2f}')
                cash = cash_estimate(due, self.tender_input.text())
                key = "draft_change" if not cash["shortfall"] else "draft_shortfall"
                amount = cash["change"] if not cash["shortfall"] else cash["shortfall"]
                self.cash_status.setText(
                    f'{self.text(key)}: {amount:,.2f}  •  {self.text("draft_only_warning")}'
                )
            except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
                self.net_total.setText(f'{self.text("preview_error")}: {exc}')
        else:
            self.net_total.setText("")
        # Tender/discount typing should not trigger repeated SQLite reads.
        signature = tuple(
            (line["barcode"], line["qty"], line["price"]) for line in lines
        )
        if signature != self._last_stock_signature:
            self._last_stock_signature = signature
            if self.stock_reader is not None and lines:
                try:
                    warnings = self.stock_reader.inspect(self.cart)
                except (ValueError, OSError, RuntimeError) as exc:
                    self.stock_status.setText(f'{self.text("stock_check_error")}: {exc}')
                else:
                    if not warnings:
                        self.stock_status.setText(self.text("draft_stock_looks_ok"))
                    else:
                        names = ", ".join(str(entry["barcode"]) for entry in warnings[:5])
                        self.stock_status.setText(
                            f'{self.text("draft_stock_attention")}: {names}'
                        )
            else:
                self.stock_status.setText("")
