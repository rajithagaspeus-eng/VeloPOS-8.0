"""Admin-only purchasing overview for isolated preview data; no GRN writes."""
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


class PurchasingPage(QWidget):
    def __init__(self, reader, text, authorized):
        super().__init__()
        self.reader, self.text, self.authorized = reader, text, authorized
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        heading_row = QHBoxLayout()
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size:19pt; font-weight:650;")
        heading_row.addWidget(self.heading)
        heading_row.addStretch()
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("secondaryAction")
        self.refresh_button.clicked.connect(self.refresh)
        heading_row.addWidget(self.refresh_button)
        layout.addLayout(heading_row)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)
        self.summary = QLabel("—")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("hint")
        layout.addWidget(self.summary)
        self.liabilities = QLabel("—")
        self.liabilities.setObjectName("hint")
        self.liabilities.setWordWrap(True)
        layout.addWidget(self.liabilities)
        self.recent_title = QLabel()
        layout.addWidget(self.recent_title)
        self.table = QTableWidget(0, 6)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.suppliers_title = QLabel()
        layout.addWidget(self.suppliers_title)
        self.suppliers = QTableWidget(0, 2)
        self.suppliers.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.suppliers.verticalHeader().setVisible(False)
        self.suppliers.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.suppliers.setMaximumHeight(135)
        layout.addWidget(self.suppliers)
        self.balances_title = QLabel()
        layout.addWidget(self.balances_title)
        self.balances = QTableWidget(0, 4)
        self.balances.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.balances.setAlternatingRowColors(True)
        self.balances.verticalHeader().setVisible(False)
        self.balances.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.balances.setMinimumHeight(110)
        layout.addWidget(self.balances, 1)
        self.retranslate()
        self.refresh()

    def retranslate(self):
        self.heading.setText(self.text("purchasing"))
        self.refresh_button.setText(self.text("refresh_stats"))
        self.recent_title.setText(self.text("purchase_recent"))
        self.suppliers_title.setText(self.text("purchase_active_suppliers"))
        self.balances_title.setText(self.text("purchase_supplier_balances"))
        self.balances.setHorizontalHeaderLabels([
            self.text(k) for k in ("suppliers", "purchase_total",
                                   "purchase_all_payments", "purchase_balance")
        ])
        self.table.setHorizontalHeaderLabels([
            self.text(key) for key in (
                "purchase_grn", "report_date", "suppliers",
                "purchase_total", "purchase_paid", "purchase_status"
            )
        ])
        self.suppliers.setHorizontalHeaderLabels([
            self.text("purchase_supplier_id"), self.text("suppliers")
        ])
        if not self.authorized():
            self._clear(self.text("purchase_admin_only"))

    def _clear(self, reason):
        self.warning.setText(reason)
        self.summary.setText("—")
        self.liabilities.setText("—")
        self.table.setRowCount(0)
        self.suppliers.setRowCount(0)
        self.balances.setRowCount(0)

    @staticmethod
    def _display(table, rows, columns):
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, col in enumerate(columns):
                value = row[col]
                cell = QTableWidgetItem("" if value is None else str(value))
                cell.setToolTip(cell.text())
                table.setItem(i, j, cell)

    def refresh(self):
        if self.reader is None or not self.authorized():
            self._clear(self.text("purchase_admin_only"))
            return
        try:
            snap = self.reader.snapshot()
        except (PermissionError, OSError, RuntimeError, ValueError) as exc:
            self._clear(str(exc))
            return
        self.warning.setText(self.text("purchase_preview_notice"))
        self.summary.setText(
            f'{self.text("purchase_count")}: {snap["purchase_count"]}   •   '
            f'{self.text("purchase_total")}: {snap["total"]:,.2f}   •   '
            f'{self.text("purchase_paid")}: {snap["paid"]:,.2f}   •   '
            f'{self.text("purchase_estimate")}: {snap["unpaid_estimate"]:,.2f}'
        )
        self._display(self.table, snap["recent"], (
            "grn_no", "date", "supplier", "total", "paid", "status"
        ))
        self._display(self.suppliers, snap["suppliers"], ("id", "name"))
        # Supplier balances are all-time, unlike the initial payment summary.
        # Never mix these accounting scopes into one unexplained figure.
        self.liabilities.setText(
            f'{self.text("purchase_current_payables")}: '
            f'{snap["supplier_payables"]:,.2f}   •   '
            f'{self.text("purchase_supplier_advances")}: '
            f'{snap["supplier_advances"]:,.2f}'
        )
        self._display(self.balances, snap["balances"],
                      ("name", "bought", "paid", "balance"))
