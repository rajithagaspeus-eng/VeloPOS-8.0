"""Read-only reporting and staff activity preview, with Admin-role gate."""
from datetime import date, timedelta
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel,
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
        controls.addWidget(self.start_label)
        controls.addWidget(self.start)
        controls.addWidget(self.end_label)
        controls.addWidget(self.end)
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("secondaryAction")
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_button)
        outer.addLayout(controls)

        self.metrics = QFrame()
        self.metrics.setObjectName("billingTotals")
        metric_layout = QVBoxLayout(self.metrics)
        self.metrics_text = QLabel()
        self.metrics_text.setWordWrap(True)
        metric_layout.addWidget(self.metrics_text)
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
        self.sales.setHorizontalHeaderLabels([self.text(key) for key in
                                               ("invoice", "date_to", "amount", "payment_method")])
        self.audit.setHorizontalHeaderLabels([self.text(key) for key in
                                               ("event_time", "username_label", "event_action")])
        if not self.authorized():
            self._locked()

    def _locked(self):
        self.warning.setText(self.text("admin_report_only"))
        self.metrics_text.setText("—")
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
        fields = (
            ("report_sales_count", result["sale_count"]),
            ("report_sales_total", result["sales_total"]),
            ("report_returns", result["returns_total"]),
            ("report_net_revenue", result["net_revenue"]),
            ("report_gross", result["adjusted_gross_profit"]),
            ("report_vat", result["vat_net"]),
            ("report_service", result["service_net"]),
            ("report_expenses", result["expenses"]),
            ("report_net", result["indicative_net"]),
        )
        self.metrics_text.setText("   |   ".join(
            f'{self.text(key)}: {value}' for key, value in fields
        ))
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
