"""Read-only demand-planning preview. Not predictive AI or an order screen."""
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


class ForecastPage(QWidget):
    def __init__(self, reader, text, authorized):
        super().__init__()
        self.reader, self.text, self.authorized = reader, text, authorized
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size:19pt; font-weight:650;")
        layout.addWidget(self.heading)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        controls = QHBoxLayout()
        self.horizon_label = QLabel()
        controls.addWidget(self.horizon_label)
        self.horizon_input = QLineEdit("7")
        self.horizon_input.setMaximumWidth(75)
        controls.addWidget(self.horizon_input)
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("secondaryAction")
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_button)
        controls.addStretch()
        layout.addLayout(controls)
        self.status = QLabel("—")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.table = QTableWidget(0, 7)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.retranslate()
        self.refresh()

    def retranslate(self):
        self.heading.setText(self.text("forecast_title"))
        self.horizon_label.setText(self.text("forecast_horizon"))
        self.refresh_button.setText(self.text("refresh_stats"))
        self.table.setHorizontalHeaderLabels([
            self.text(k) for k in (
                "barcode", "product_name", "stock", "forecast_sale_days",
                "forecast_28d", "forecast_expected", "forecast_coverage")
        ])
        if not self.authorized():
            self._clear(self.text("forecast_admin_only"))

    def _clear(self, reason):
        self.notice.setText(reason)
        self.status.setText("—")
        self.table.setRowCount(0)

    def refresh(self):
        if self.reader is None or not self.authorized():
            self._clear(self.text("forecast_admin_only"))
            return
        try:
            info = self.reader.snapshot(horizon=self.horizon_input.text())
        except (ValueError, RuntimeError, OSError, PermissionError) as exc:
            self._clear(str(exc))
            return
        self.notice.setText(self.text("forecast_caveat"))
        self.status.setText(
            f'{info["history_from"]} – {info["history_to"]}  •  '
            f'{self.text("forecast_eligible")}: {info["ready_products"]}/'
            f'{info["evaluated_products"]}'
        )
        self.table.setRowCount(len(info["products"]))
        for index, rec in enumerate(info["products"]):
            forecast = (
                f'{rec["units_expected"]:,.2f}'
                if rec["status"] == "baseline"
                else self.text("forecast_insufficient")
            )
            cover = (
                f'{rec["stock_coverage_days"]:,.1f}'
                if rec["stock_coverage_days"] is not None else "—"
            )
            values = (
                rec["barcode"], rec["product"], f'{rec["stock"]:g}',
                rec["observed_sale_days"], f'{rec["units_28d"]:g}',
                forecast, cover,
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.table.setItem(index, col, item)
