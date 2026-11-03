"""Smart Inventory: localized, bounded, read-only stock attention screen."""
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)


class InventoryInsightsPage(QWidget):
    def __init__(self, reader, text, authorized):
        super().__init__()
        self.reader, self.text, self.authorized = reader, text, authorized
        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size:19pt; font-weight:650;")
        outer.addWidget(self.heading)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        outer.addWidget(self.notice)
        control = QHBoxLayout()
        self.low_label = QLabel()
        self.low_input = QLineEdit("5")
        self.low_input.setMaximumWidth(65)
        self.days_label = QLabel()
        self.days_input = QLineEdit("30")
        self.days_input.setMaximumWidth(65)
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("secondaryAction")
        self.refresh_button.clicked.connect(self.refresh)
        for widget in (self.low_label, self.low_input,
                       self.days_label, self.days_input, self.refresh_button):
            control.addWidget(widget)
        control.addStretch()
        outer.addLayout(control)

        tiles = QGridLayout()
        tiles.setSpacing(10)
        self.metric_keys = ("insight_low", "insight_expired", "insight_expiring")
        self.cards = []
        for index, key in enumerate(self.metric_keys):
            card = QFrame()
            card.setObjectName("reportMetricCard")
            card_layout = QVBoxLayout(card)
            caption = QLabel()
            caption.setObjectName("reportMetricLabel")
            caption.setWordWrap(True)
            number = QLabel("—")
            number.setObjectName("reportMetricValue")
            card_layout.addWidget(caption)
            card_layout.addWidget(number)
            tiles.addWidget(card, 0, index)
            self.cards.append((caption, number))
        outer.addLayout(tiles)

        self.stock_title = QLabel()
        outer.addWidget(self.stock_title)
        self.low_table = self._table(3)
        outer.addWidget(self.low_table, 1)
        self.expiry_title = QLabel()
        outer.addWidget(self.expiry_title)
        self.expiry_table = self._table(3)
        outer.addWidget(self.expiry_table, 1)
        self.ledger_title = QLabel()
        outer.addWidget(self.ledger_title)
        self.ledger_table = self._table(6)
        outer.addWidget(self.ledger_table, 1)
        self.retranslate()
        self.refresh()

    @staticmethod
    def _table(columns):
        widget = QTableWidget(0, columns)
        widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        widget.setAlternatingRowColors(True)
        widget.verticalHeader().setVisible(False)
        widget.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        widget.setMinimumHeight(90)
        return widget

    def retranslate(self):
        self.heading.setText(self.text("smart_inventory"))
        self.low_label.setText(self.text("insight_low_threshold"))
        self.days_label.setText(self.text("insight_expiry_window"))
        self.refresh_button.setText(self.text("refresh_stats"))
        self.stock_title.setText(self.text("insight_low_details"))
        self.expiry_title.setText(self.text("insight_expiry_details"))
        self.ledger_title.setText(self.text("insight_recent_moves"))
        for key, (label, _) in zip(self.metric_keys, self.cards):
            label.setText(self.text(key))
        self.low_table.setHorizontalHeaderLabels(
            [self.text(key) for key in ("barcode", "product_name", "stock")])
        self.expiry_table.setHorizontalHeaderLabels(
            [self.text(key) for key in ("barcode", "product_name", "insight_expiry_date")])
        self.ledger_table.setHorizontalHeaderLabels(
            [self.text(key) for key in (
                "insight_time", "barcode", "insight_qty_change",
                "insight_qty_after", "insight_reason", "username_label")])
        if not self.authorized():
            self._clear(self.text("insight_admin_only"))

    def _clear(self, message):
        self.notice.setText(message)
        for _, number in self.cards:
            number.setText("—")
        for widget in (self.low_table, self.expiry_table, self.ledger_table):
            widget.setRowCount(0)

    @staticmethod
    def _set_rows(widget, rows, fields):
        widget.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, key in enumerate(fields):
                value = row[key] if row[key] is not None else ""
                if isinstance(value, float):
                    value = f"{value:g}"
                cell = QTableWidgetItem(str(value))
                cell.setToolTip(str(value))
                widget.setItem(i, j, cell)

    def refresh(self):
        if not self.authorized() or self.reader is None:
            self._clear(self.text("insight_admin_only"))
            return
        try:
            data = self.reader.snapshot(
                low_level=self.low_input.text(),
                expiry_days=self.days_input.text(),
            )
        except (ValueError, RuntimeError, OSError, PermissionError) as exc:
            self._clear(str(exc))
            return
        self.notice.setText(self.text("insight_test_note"))
        for (_, number), key in zip(
                self.cards, ("low_count", "expired_count", "expiring_count")):
            number.setText(str(data[key]))
        self._set_rows(self.low_table, data["low_rows"],
                       ("barcode", "name_en", "stock_qty"))
        self._set_rows(self.expiry_table, data["expiry_rows"],
                       ("barcode", "name_en", "expiry_date"))
        self._set_rows(self.ledger_table, data["movements"],
                       ("ts", "barcode", "qty_change", "qty_after",
                        "reason", "user"))
