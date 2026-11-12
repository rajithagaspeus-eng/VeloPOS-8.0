"""Admin-only historical business intelligence preview (no forecasts, no writes)."""
from datetime import date, timedelta
from PySide6.QtWidgets import (
    QAbstractItemView, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QFrame, QWidget,
)


class AnalyticsPage(QWidget):
    def __init__(self, reader, text, authorized):
        super().__init__()
        self.reader, self.text, self.authorized = reader, text, authorized
        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size:19pt; font-weight:650;")
        outer.addWidget(self.heading)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        outer.addWidget(self.warning)
        filters = QHBoxLayout()
        self.start_label = QLabel()
        self.start_input = QLineEdit((date.today()-timedelta(days=30)).isoformat())
        self.start_input.setMaximumWidth(125)
        self.end_label = QLabel()
        self.end_input = QLineEdit(date.today().isoformat())
        self.end_input.setMaximumWidth(125)
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("secondaryAction")
        self.refresh_button.clicked.connect(self.refresh)
        for item in (self.start_label, self.start_input, self.end_label,
                     self.end_input, self.refresh_button):
            filters.addWidget(item)
        filters.addStretch()
        outer.addLayout(filters)
        grid = QGridLayout()
        self.cards = []
        self.metrics = (
            ("analytics_sales", "sales_total"),
            ("analytics_refunds", "refunds_total"),
            ("analytics_revenue", "net_revenue"),
            ("analytics_net", "indicative_net"),
        )
        for index, (label_key, _key) in enumerate(self.metrics):
            tile = QFrame()
            tile.setObjectName("reportMetricCard")
            inside = QVBoxLayout(tile)
            name = QLabel()
            name.setObjectName("reportMetricLabel")
            number = QLabel("—")
            number.setObjectName("reportMetricValue")
            inside.addWidget(name)
            inside.addWidget(number)
            grid.addWidget(tile, index // 2, index % 2)
            self.cards.append((name, number))
        outer.addLayout(grid)
        self.daily_label = QLabel()
        outer.addWidget(self.daily_label)
        self.daily_table = self._table(6)
        outer.addWidget(self.daily_table, 2)
        self.expense_label = QLabel()
        outer.addWidget(self.expense_label)
        self.expense_table = self._table(3)
        outer.addWidget(self.expense_table, 1)
        self.products_label = QLabel()
        outer.addWidget(self.products_label)
        self.products_table = self._table(4)
        outer.addWidget(self.products_table, 1)
        self.retranslate()
        self.refresh()

    @staticmethod
    def _table(count):
        table = QTableWidget(0, count)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setMinimumHeight(90)
        return table

    def retranslate(self):
        self.heading.setText(self.text("analytics"))
        self.start_label.setText(self.text("date_from"))
        self.end_label.setText(self.text("date_to"))
        self.refresh_button.setText(self.text("refresh_stats"))
        for (key, _), (name, _) in zip(self.metrics, self.cards):
            name.setText(self.text(key))
        self.daily_label.setText(self.text("analytics_daily"))
        self.expense_label.setText(self.text("analytics_expenses"))
        self.products_label.setText(self.text("analytics_products"))
        for table, keys in (
            (self.daily_table, ("report_date", "report_sales_count", "analytics_sales",
                                "analytics_refunds", "analytics_revenue", "analytics_net")),
            (self.expense_table, ("analytics_category", "analytics_entries", "amount")),
            (self.products_table, ("barcode", "product_name", "quantity", "analytics_sales")),
        ):
            table.setHorizontalHeaderLabels([self.text(key) for key in keys])
        if not self.authorized():
            self._clear(self.text("analytics_admin_only"))

    def _clear(self, notice):
        self.warning.setText(notice)
        for _, number in self.cards:
            number.setText("—")
        for table in (self.daily_table, self.expense_table, self.products_table):
            table.setRowCount(0)

    @staticmethod
    def _fill(table, records, keys):
        table.setRowCount(len(records))
        for index, row in enumerate(records):
            for col, key in enumerate(keys):
                value = row[key]
                if key in ("sales", "refunds", "net_revenue", "indicative_net",
                           "total", "revenue"):
                    value = f"{value:,.2f}"
                cell = QTableWidgetItem(str(value))
                cell.setToolTip(str(value))
                table.setItem(index, col, cell)

    def refresh(self):
        if self.reader is None or not self.authorized():
            self._clear(self.text("analytics_admin_only"))
            return
        try:
            result = self.reader.snapshot(
                self.start_input.text(), self.end_input.text()
            )
        except (ValueError, RuntimeError, OSError, PermissionError) as exc:
            self._clear(str(exc))
            return
        self.warning.setText(self.text("analytics_caveat"))
        for (_, key), (_, number) in zip(self.metrics, self.cards):
            number.setText(f'{result[key]:,.2f}')
        self._fill(self.daily_table, result["daily"],
                   ("date", "bills", "sales", "refunds", "net_revenue", "indicative_net"))
        self._fill(self.expense_table, result["expenses_by_category"],
                   ("category", "entries", "total"))
        self._fill(self.products_table, result["top_products"],
                   ("barcode", "product", "qty", "revenue"))
