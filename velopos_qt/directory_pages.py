"""Read-only customer and supplier tables for safe VeloPOS 8 preview."""
from PySide6.QtWidgets import (
    QAbstractItemView, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)


class DirectoryPage(QWidget):
    def __init__(self, directory, kind, text):
        super().__init__()
        if kind not in ("customers", "suppliers"):
            raise ValueError("Unknown directory type")
        self.directory = directory
        self.kind = kind
        self.text = text
        self.records = []
        self.fields = (
            ("name", "phone", "address", "credit_balance") if kind == "customers"
            else ("name", "contact", "phone", "active")
        )
        layout = QVBoxLayout(self)
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size:19pt; font-weight:650;")
        layout.addWidget(self.heading)
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)
        self.table = QTableWidget(0, len(self.fields))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.retranslate()
        self.refresh()

    def retranslate(self):
        self.heading.setText(self.text(self.kind))
        self.search.setPlaceholderText(self.text("directory_search"))
        self.table.setHorizontalHeaderLabels([self.text(field) for field in self.fields])
        self.notice.setText(self.text("directory_read_only"))

    def refresh(self, _value=None):
        try:
            reader = getattr(self.directory, self.kind)
            self.records = reader(self.search.text(), limit=100)
        except Exception as exc:
            self.records = []
            self.notice.setText(str(exc))
        else:
            self.notice.setText(self.text("directory_read_only"))
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            for column, key in enumerate(self.fields):
                value = record[key]
                if key == "credit_balance":
                    value = f"{float(value):,.2f}"
                elif key == "active":
                    value = self.text("active") if value else self.text("inactive")
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
