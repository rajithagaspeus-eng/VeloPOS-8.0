"""Fast keyboard-friendly billing draft UI — NO sale, payment or stock writes.

Barcodes can be scanned into the search field and submitted with Enter.
The cart exists in memory only. Display totals use the existing read-only
bill preview service when the isolated launcher provides it.
"""
from copy import deepcopy
from decimal import Decimal

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .preview_models import Cart, preview_existing_bill, cash_estimate, money
from .customer_loyalty import projected_points_for_paid_bill
from .draft_receipt import draft_receipt_text


class BillingPage(QWidget):
    def __init__(self, inventory, text, bill_preview=None, shift_reader=None, identity=None, stock_reader=None, customer_reader=None, authorize_customer=None):
        super().__init__()
        self.inventory = inventory
        self.text = text
        self.bill_preview = bill_preview
        self.shift_reader = shift_reader
        self.identity = identity or (lambda: None)
        self.stock_reader = stock_reader
        self.customer_reader = customer_reader
        # A real preview window passes its persisted-session verifier here.
        # Component-only tests may fall back to their synthetic identity.
        self.authorize_customer = authorize_customer or (
            lambda: bool(
                self.identity() and
                getattr(self.identity(), "role", None) in ("Admin", "Cashier")
            )
        )
        self.customer_id = None
        self._last_stock_signature = None
        self.cart = Cart()
        self._held_draft = None
        self.products = []
        # Explicit row selection is ephemeral. Never carry a highlighted
        # product from one search result list into a different search.
        self._explicit_search_row = None
        # Billing grows vertically as customer/loyalty/hold controls are added.
        # A scrollable inner canvas preserves table heights at smaller Windows
        # display scales instead of squeezing the "Draft items" heading onto
        # the product result rows.
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("billingScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        root_layout.addWidget(self.scroll_area)
        canvas = QWidget()
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(15)
        self.scroll_area.setWidget(canvas)

        self.eyebrow = QLabel("02  /  CHECKOUT WORKSPACE")
        self.eyebrow.setObjectName("pageEyebrow")
        layout.addWidget(self.eyebrow)
        self.heading = QLabel()
        self.heading.setObjectName("screenTitle")
        layout.addWidget(self.heading)
        self.notice = QLabel()
        self.notice.setObjectName("previewSafetyNotice")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.shift_status = QLabel()
        self.shift_status.setWordWrap(True)
        self.shift_status.setObjectName("hint")
        layout.addWidget(self.shift_status)

        # Customer lookup is opt-in and gated by a signed-in cashier identity.
        # No name or phone is kept in a held draft; only a stable customer ID.
        customer_row = QHBoxLayout()
        self.customer_search_label = QLabel()
        customer_row.addWidget(self.customer_search_label)
        self.customer_search = QLineEdit()
        self.customer_search.setMaximumWidth(230)
        self.customer_search.returnPressed.connect(self.refresh_customers)
        customer_row.addWidget(self.customer_search)
        self.customer_search_button = QPushButton()
        self.customer_search_button.setObjectName("secondaryAction")
        self.customer_search_button.clicked.connect(self.refresh_customers)
        customer_row.addWidget(self.customer_search_button)
        self.customer_choice = QComboBox()
        self.customer_choice.setMinimumWidth(180)
        self.customer_choice.currentIndexChanged.connect(self.choose_customer)
        customer_row.addWidget(self.customer_choice, 1)
        self.customer_clear_button = QPushButton()
        self.customer_clear_button.setObjectName("secondaryAction")
        self.customer_clear_button.clicked.connect(self.clear_customer)
        customer_row.addWidget(self.customer_clear_button)
        layout.addLayout(customer_row)
        self.customer_summary = QLabel()
        self.customer_summary.setObjectName("hint")
        self.customer_summary.setWordWrap(True)
        layout.addWidget(self.customer_summary)
        self.loyalty_projection = QLabel()
        self.loyalty_projection.setObjectName("hint")
        self.loyalty_projection.setWordWrap(True)
        layout.addWidget(self.loyalty_projection)

        self.scan_panel = QFrame()
        self.scan_panel.setObjectName("searchPanel")
        scan_layout = QVBoxLayout(self.scan_panel)
        scan_layout.setContentsMargins(17, 16, 17, 16)
        scan_layout.setSpacing(11)
        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        self.query = QLineEdit()
        self.query.setObjectName("barcodeSearch")
        self.query.installEventFilter(self)
        self.query.setClearButtonEnabled(True)
        self.query.setMinimumHeight(44)
        self.query.textChanged.connect(self.refresh_products)
        self.query.returnPressed.connect(self.scan_or_add)
        search_row.addWidget(self.query, 1)
        self.add_button = QPushButton()
        self.add_button.setMinimumHeight(44)
        self.add_button.clicked.connect(self.add_selected)
        search_row.addWidget(self.add_button)
        scan_layout.addLayout(search_row)

        self.results = QTableWidget(0, 3)
        self.results.setObjectName("searchResults")
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.setMaximumHeight(205)
        self.results.setMinimumHeight(155)
        self.results.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        self.results.verticalHeader().setVisible(False)
        self.results.setAlternatingRowColors(True)
        header = self.results.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.results.itemDoubleClicked.connect(lambda _item: self.add_selected())
        self.results.itemClicked.connect(self._search_result_clicked)
        scan_layout.addWidget(self.results)
        self.search_help = QLabel()
        self.search_help.setObjectName("billingSearchHelp")
        self.search_help.setWordWrap(True)
        scan_layout.addWidget(self.search_help)
        layout.addWidget(self.scan_panel)

        self.cart_title = QLabel()
        self.cart_title.setObjectName("sectionTitle")
        layout.addWidget(self.cart_title)
        self.cart_table = QTableWidget(0, 4)
        self.cart_table.setObjectName("draftCartTable")
        self.cart_table.setMinimumHeight(135)
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

        hold_row = QHBoxLayout()
        self.hold_button = QPushButton()
        self.hold_button.setObjectName("secondaryAction")
        self.hold_button.clicked.connect(self.hold_draft)
        hold_row.addWidget(self.hold_button)
        self.resume_button = QPushButton()
        self.resume_button.setObjectName("secondaryAction")
        self.resume_button.clicked.connect(self.resume_draft)
        hold_row.addWidget(self.resume_button)
        self.receipt_button = QPushButton()
        self.receipt_button.setObjectName("draftReceiptPreviewButton")
        self.receipt_button.clicked.connect(self.show_draft_receipt)
        hold_row.addWidget(self.receipt_button)
        self.hold_note = QLabel()
        self.hold_note.setObjectName("hint")
        self.hold_note.setWordWrap(True)
        hold_row.addWidget(self.hold_note, 1)
        layout.addLayout(hold_row)

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
        summary.setContentsMargins(20, 18, 20, 18)
        summary.setSpacing(16)
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
        self.discount_shortcut = QShortcut(QKeySequence("F4"), self)
        self.discount_shortcut.activated.connect(self.discount_input.setFocus)
        self.tender_shortcut = QShortcut(QKeySequence("F5"), self)
        self.tender_shortcut.activated.connect(self.tender_input.setFocus)
        self.hold_shortcut = QShortcut(QKeySequence("F6"), self)
        self.hold_shortcut.activated.connect(self.hold_draft)
        self.resume_shortcut = QShortcut(QKeySequence("F7"), self)
        self.resume_shortcut.activated.connect(self.resume_draft)

        self.retranslate()
        self.refresh_products()
        self.refresh_cart()

    def retranslate(self):
        self.heading.setText(self.text("billing"))
        self.notice.setText(self.text("no_checkout_notice"))
        self.query.setPlaceholderText(self.text("barcode_search_hint"))
        self.query.setAccessibleName(self.text("billing_product_lookup"))
        self.results.setAccessibleName(self.text("billing_search_results"))
        self._refresh_search_help()
        self.add_button.setText(self.text("add_to_cart"))
        self.quantity_label.setText(self.text("quantity"))
        self.quantity_button.setText(self.text("update_quantity"))
        self.remove_button.setText(self.text("remove_line"))
        self.clear_button.setText(self.text("clear_cart"))
        self.cart_title.setText(self.text("draft_items"))
        self.customer_search_label.setText(self.text("billing_customer"))
        self.customer_search.setPlaceholderText(self.text("billing_customer_lookup"))
        self.customer_search_button.setText(self.text("billing_find_customer"))
        self.customer_clear_button.setText(self.text("billing_walk_in"))
        self.refresh_customer_summary()
        self.hold_button.setText(self.text("hold_draft"))
        self.resume_button.setText(self.text("resume_draft"))
        self.receipt_button.setText(self.text("draft_receipt_preview"))
        self.hold_button.setToolTip("F6")
        self.resume_button.setToolTip("F7")
        self._refresh_hold_controls()
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

    def refresh_customers(self):
        if self.customer_reader is None or not self.authorize_customer():
            self.refresh_customer_summary()
            return
        try:
            matches = self.customer_reader.search(self.customer_search.text())
        except (ValueError, RuntimeError, OSError, PermissionError) as exc:
            # On a revoked session or a failed sensitive lookup, never retain
            # the previous customer's name, phone, points, or held ID in UI.
            self.customer_choice.blockSignals(True)
            self.customer_choice.clear()
            self.customer_choice.blockSignals(False)
            self.customer_id = None
            self.loyalty_projection.setText("")
            self.customer_summary.setText(str(exc))
            return
        previous = self.customer_id
        self.customer_choice.blockSignals(True)
        self.customer_choice.clear()
        self.customer_choice.addItem(self.text("billing_walk_in"), None)
        for row in matches:
            self.customer_choice.addItem(
                f'{row["name"]} ({row["phone"]})' if row["phone"] else row["name"],
                row["id"],
            )
        restored = self.customer_choice.findData(previous)
        self.customer_choice.setCurrentIndex(max(0, restored))
        self.customer_choice.blockSignals(False)
        if restored == -1 and previous is not None:
            self.customer_id = None
        self.refresh_customer_summary()
        self.refresh_cart()

    def choose_customer(self, _index):
        self.customer_id = self.customer_choice.currentData()
        self.refresh_customer_summary()
        self.refresh_cart()

    def clear_customer(self):
        self.customer_id = None
        self.customer_choice.blockSignals(True)
        self.customer_choice.setCurrentIndex(0 if self.customer_choice.count() else -1)
        self.customer_choice.blockSignals(False)
        self.refresh_customer_summary()
        self.refresh_cart()

    def refresh_customer_summary(self):
        # Never expose balances/points unless authenticated at read time.
        allowed = bool(self.authorize_customer())
        self.customer_search.setEnabled(allowed and self.customer_reader is not None)
        self.customer_search_button.setEnabled(allowed and self.customer_reader is not None)
        self.customer_choice.setEnabled(allowed and self.customer_reader is not None)
        self.customer_clear_button.setEnabled(allowed and self.customer_reader is not None)
        if not allowed or self.customer_reader is None:
            # Do not leave customer names/phone numbers visible in a disabled
            # selector when a session expires or role access is revoked.
            self.customer_choice.blockSignals(True)
            self.customer_choice.clear()
            self.customer_choice.blockSignals(False)
            self.customer_search.clear()
            self.customer_id = None
            self.customer_summary.setText(self.text("billing_customer_login_needed"))
            self.loyalty_projection.setText("")
            return
        if self.customer_id is None:
            self.customer_summary.setText(self.text("billing_walk_in_note"))
            self.loyalty_projection.setText("")
            return
        try:
            customer = self.customer_reader.get(self.customer_id)
        except (ValueError, RuntimeError, OSError, PermissionError):
            customer = None
        if customer is None:
            self.customer_id = None
            self.customer_choice.blockSignals(True)
            self.customer_choice.setCurrentIndex(0 if self.customer_choice.count() else -1)
            self.customer_choice.blockSignals(False)
            self.customer_summary.setText(self.text("billing_customer_unavailable"))
            self.loyalty_projection.setText("")
            return
        self.customer_summary.setText(
            f'{customer["name"]}  •  {self.text("billing_points")}: '
            f'{customer["loyalty_points"]:,.2f}  •  '
            f'{self.text("billing_credit_balance")}: {customer["credit_balance"]:,.2f}'
            f'  •  {self.text("billing_credit_limit")}: {customer["credit_limit"]:,.2f}'
            f'  •  {self.text("billing_points_readonly")}'
        )

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

    def _refresh_search_help(self):
        if not hasattr(self, "search_help"):
            return
        if not self.products:
            self.search_help.setText(self.text("billing_search_none"))
        elif len(self.products) == 1:
            self.search_help.setText(self.text("billing_search_one"))
        else:
            self.search_help.setText(
                self.text("billing_search_many").format(count=len(self.products))
            )

    def _search_result_clicked(self, item):
        """A deliberate product click permits Enter on an ambiguous search."""
        self._explicit_search_row = item.row() if item is not None else None

    def eventFilter(self, watched, event):
        """Up/Down in scan field selects a deliberate result without focus loss."""
        if (watched is self.query and event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up)
                and self.products):
            current = self._explicit_search_row
            if current is None:
                row = 0 if event.key() == Qt.Key.Key_Down else len(self.products) - 1
            else:
                delta = 1 if event.key() == Qt.Key.Key_Down else -1
                row = max(0, min(len(self.products) - 1, current + delta))
            self._explicit_search_row = row
            self.results.setCurrentCell(row, 0)
            self.results.scrollToItem(self.results.item(row, 0))
            return True
        return super().eventFilter(watched, event)

    def refresh_products(self, _value=None):
        # QTableWidget can retain a current-row index while data changes.
        # Reset that selection BEFORE repopulating the result table.
        self._explicit_search_row = None
        self.results.clearSelection()
        self.results.setCurrentCell(-1, -1)
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
        self._refresh_search_help()

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
        elif (self._explicit_search_row is not None
              and self.results.currentRow() == self._explicit_search_row
              and 0 <= self._explicit_search_row < len(self.products)):
            # Multiple matches: Enter is safe only after an explicit
            # arrow-key or mouse choice in THIS particular result list.
            self.add_selected()
        # Otherwise do nothing: never silently choose ambiguous stock.

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

    def clear_session_draft(self):
        """Discard ALL active and held data at sign-out; no DB calls."""
        self._held_draft = None
        self.customer_id = None
        self.customer_choice.clear()
        self.customer_search.clear()
        self.cart.clear()
        self.discount_input.setText("0")
        self.tender_input.setText("0")
        self.quantity_input.setText("1")
        self.query.clear()
        self._explicit_search_row = None
        self.results.clearSelection()
        self.results.setCurrentCell(-1, -1)
        self.refresh_cart()
        self._refresh_hold_controls()

    def _refresh_hold_controls(self):
        if not hasattr(self, "hold_button"):
            return
        held = self._held_draft is not None
        self.hold_button.setEnabled(bool(self.cart.lines) and not held)
        self.resume_button.setEnabled(held and not bool(self.cart.lines))
        self.hold_note.setText(
            self.text("draft_held_note") if held else self.text("draft_hold_hint")
        )

    def hold_draft(self):
        """Hold one unsaved draft in memory; never create a transaction."""
        if not self.cart.lines or self._held_draft is not None:
            return
        self._held_draft = (
            deepcopy(self.cart.lines),
            self.discount_input.text(),
            self.tender_input.text(),
            self.customer_id,
        )
        self.customer_id = None
        self.clear_customer()
        self.cart.clear()
        self.discount_input.setText("0")
        self.tender_input.setText("0")
        self.query.clear()
        self.refresh_cart()
        self._refresh_hold_controls()

    def resume_draft(self):
        """Prevent silently replacing a second active draft."""
        if self._held_draft is None or self.cart.lines:
            return
        held_lines, discount, tender, held_customer_id = self._held_draft
        self.cart.lines = deepcopy(held_lines)
        self._held_draft = None
        self.discount_input.setText(discount)
        self.tender_input.setText(tender)
        self.customer_id = held_customer_id
        # Revalidate the saved ID and restore the visible choice, without
        # trusting a stale customer name/phone from the held draft.
        if held_customer_id is not None and self.customer_reader is not None:
            self.refresh_customers()
        else:
            self.refresh_customer_summary()
        self.refresh_cart()
        self._refresh_hold_controls()

    def show_draft_receipt(self):
        """Display an in-memory receipt-style DRAFT, never print or checkout."""
        if not self.cart.lines:
            return
        try:
            preview = draft_receipt_text(
                self.cart, discount=self.discount_input.text(),
                tendered=self.tender_input.text(), bill_preview=self.bill_preview,
            )
        except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
            QMessageBox.warning(self, self.text("draft_receipt_title"), str(exc))
            return

        dialog = QDialog(self)
        dialog.setObjectName("draftReceiptPreviewDialog")
        dialog.setWindowTitle(self.text("draft_receipt_title"))
        dialog.resize(540, 550)
        layout = QVBoxLayout(dialog)
        warning = QLabel(self.text("draft_only_warning"))
        warning.setWordWrap(True)
        layout.addWidget(warning)
        body = QPlainTextEdit(dialog)
        body.setObjectName("draftReceiptPreviewText")
        body.setReadOnly(True)
        body.setPlainText(preview)
        layout.addWidget(body)
        actions = QHBoxLayout()
        copy_button = QPushButton(self.text("draft_receipt_copy"))
        copy_button.clicked.connect(
            lambda: QApplication.clipboard().setText(body.toPlainText())
        )
        actions.addWidget(copy_button)
        actions.addStretch(1)
        close_button = QPushButton(self.text("draft_receipt_close"))
        close_button.setObjectName("secondaryAction")
        close_button.clicked.connect(dialog.accept)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        dialog.exec()

    def refresh_cart(self, selected_barcode=None):
        lines = list(self.cart.lines.values())
        self._refresh_hold_controls()
        self.receipt_button.setEnabled(bool(lines))
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
        self.loyalty_projection.setText("")
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
                if (self.customer_id is not None and self.customer_reader is not None
                        and self.authorize_customer()):
                    points = projected_points_for_paid_bill(due)
                    self.loyalty_projection.setText(
                        f'{self.text("loyalty_earn_estimate")}: {points:,.2f}'
                        f'  •  {self.text("loyalty_no_redemption")}'
                    )
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
                        messages = []
                        for entry in warnings[:5]:
                            reason_key = {
                                "missing": "draft_stock_missing",
                                "insufficient": "draft_stock_insufficient",
                                "price_changed": "draft_price_changed",
                                "expired": "draft_expired_product",
                                "expired_batch": "draft_expired_batch",
                            }.get(entry["status"], "draft_stock_attention")
                            messages.append(f'{entry["barcode"]} ({self.text(reason_key)})')
                        self.stock_status.setText(
                            f'{self.text("draft_stock_attention")}: ' +
                            ", ".join(messages)
                        )
            else:
                self.stock_status.setText("")
