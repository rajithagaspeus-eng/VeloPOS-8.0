"""Read-only reporting and staff activity preview, with Admin-role gate."""
from datetime import date, timedelta
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)


class ReportsPage(QWidget):
    def __init__(self, reader, text, authorized):
        super().__init__()
        self.reader, self.text, self.authorized = reader, text, authorized
        outer = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setStyleSheet("font-size:19pt; font-weight:650;")
        outer.addWidget(self.title)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        outer.addWidget(self.warning)
        controls = QHBoxLayout()
        self.start = QLineEdit((date.today() - timedelta(days=30)).isoformat())
        self.start.setMaximumWidth(130)
        self.end = QLineEdit(date.today().isoformat())
        self.end.setMaximumWidth(130)
        self.start_label = QLabel()
        self.end_label = QLabel()
        controls.addStretch(1)
        controls.addWidget(self.start_label)
        controls.addWidget(self.start)
        controls.addWidget(self.end_label)
        controls.addWidget(self.end)
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("secondaryAction")
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_button)
        outer.addLayout(controls)

        # Screenshot-driven redesign: concise 3x3 KPI tiles rather than one
        # long, hard-to-scan text strip. All figures are original DB summaries.
        self.metric_keys = (
            ("report_sales_count", "sale_count"),
            ("report_sales_total", "sales_total"),
            ("report_returns", "returns_total"),
            ("report_net_revenue", "net_revenue"),
            ("report_gross", "adjusted_gross_profit"),
            ("report_expenses", "expenses"),
            ("report_net", "indicative_net"),
            ("report_vat", "vat_net"),
            ("report_service", "service_net"),
        )
        self.metrics = QFrame()
        self.metrics.setObjectName("reportMetrics")
        metric_layout = QGridLayout(self.metrics)
        metric_layout.setContentsMargins(0, 0, 0, 0)
        metric_layout.setHorizontalSpacing(10)
        metric_layout.setVerticalSpacing(10)
        self.metric_cards = []
        for position, (label_key, _value_key) in enumerate(self.metric_keys):
            tile = QFrame()
            tile.setObjectName("reportMetricCard")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(14, 11, 14, 11)
            title = QLabel()
            title.setObjectName("reportMetricLabel")
            title.setWordWrap(True)
            value = QLabel("—")
            value.setObjectName("reportMetricValue")
            value.setTextInteractionFlags(value.textInteractionFlags())
            tile_layout.addWidget(title)
            tile_layout.addWidget(value)
            metric_layout.addWidget(tile, position // 3, position % 3)
            self.metric_cards.append((title, value))
        outer.addWidget(self.metrics)

        self.sales = QTableWidget(0, 4)
        self.sales.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sales.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sales.verticalHeader().setVisible(False)
        self.sales.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self.sales)
        self.audit_title = QLabel()
        self.audit_title.setStyleSheet("font-size:12pt; font-weight:650;")
        outer.addWidget(self.audit_title)
        self.audit = QTableWidget(0, 3)
        self.audit.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.audit.verticalHeader().setVisible(False)
        self.audit.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.audit.setMaximumHeight(170)
        outer.addWidget(self.audit)
        self.retranslate()
        self.refresh()

    def retranslate(self):
        self.title.setText(self.text("reports"))
        self.start_label.setText(self.text("date_from"))
        self.end_label.setText(self.text("date_to"))
        self.refresh_button.setText(self.text("refresh_stats"))
        self.audit_title.setText(self.text("staff_activity"))
        for (label_key, _), (title, _) in zip(self.metric_keys, self.metric_cards):
            title.setText(self.text(label_key))
        self.sales.setHorizontalHeaderLabels([self.text(key) for key in
                                               ("invoice", "report_date", "amount", "payment_method")])
        self.audit.setHorizontalHeaderLabels([self.text(key) for key in
                                               ("event_time", "username_label", "event_action")])
        if not self.authorized():
            self._locked()

    def _locked(self):
        self.warning.setText(self.text("admin_report_only"))
        for _title, value in self.metric_cards:
            value.setText("—")
        self.sales.setRowCount(0)
        self.audit.setRowCount(0)

    def refresh(self):
        if not self.authorized() or self.reader is None:
            self._locked()
            return
        try:
            result = self.reader.snapshot(self.start.text(), self.end.text())
            audit = self.reader.staff_activity()
        except (ValueError, RuntimeError, OSError, PermissionError) as exc:
            self.warning.setText(str(exc))
            self.metrics_text.setText("—")
            self.sales.setRowCount(0)
            self.audit.setRowCount(0)
            return
        self.warning.setText(self.text("report_preview_caveat"))
        for (_label, field), (_title, value) in zip(self.metric_keys, self.metric_cards):
            amount = result[field]
            value.setText(str(amount) if field == "sale_count" else f"{amount:,.2f}")
        self.sales.setRowCount(len(result["recent_sales"]))
        for index, row in enumerate(result["recent_sales"]):
            for col, value in enumerate((row["invoice_no"], row["date"],
                                         f'{row["total_amount"]:,.2f}', row["payment_method"])):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.sales.setItem(index, col, item)
        self.audit.setRowCount(len(audit))
        for index, row in enumerate(audit):
            for col, key in enumerate(("ts", "user", "action")):
                item = QTableWidgetItem(str(row[key]))
                item.setToolTip(str(row[key]))
                self.audit.setItem(index, col, item)
