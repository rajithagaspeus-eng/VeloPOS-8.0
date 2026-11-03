"""Read-only customer and supplier tables for safe VeloPOS 8 preview."""
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .directory_dialog import DirectoryDialog


class DirectoryPage(QWidget):
    def __init__(self, directory, kind, text, editor=None):
        super().__init__()
        if kind not in ("customers", "suppliers"):
            raise ValueError("Unknown directory type")
        self.directory = directory
        self.editor = editor
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
        actions = QHBoxLayout()
        actions.addWidget(self.search)
        self.new_button = QPushButton()
        self.new_button.setObjectName("secondaryAction")
        self.new_button.setVisible(editor is not None)
        self.new_button.clicked.connect(self.create_record)
        actions.addWidget(self.new_button)
        self.edit_button = QPushButton()
        self.edit_button.setObjectName("secondaryAction")
        self.edit_button.setVisible(editor is not None)
        self.edit_button.clicked.connect(self.edit_selected)
        actions.addWidget(self.edit_button)
        layout.addLayout(actions)
        self.table = QTableWidget(0, len(self.fields))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(self.fields)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
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
        self.new_button.setText(self.text("new_record"))
        self.edit_button.setText(self.text("edit_record"))
        self.notice.setText(
            self.text("preview_directory_warning") if self.editor is not None
            else self.text("directory_read_only")
        )

    def _show_dialog(self, identifier=None):
        if self.editor is None:
            return
        try:
            dialog = DirectoryDialog(
                self.editor, self.kind, self.text,
                identifier=identifier, parent=self,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, self.text("failed_title"), str(exc))
            return
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def create_record(self):
        self._show_dialog()

    def edit_selected(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.records):
            self._show_dialog(self.records[row]["id"])

    def refresh(self, _value=None):
        try:
            reader = getattr(self.directory, self.kind)
            self.records = reader(self.search.text(), limit=100)
        except Exception as exc:
            self.records = []
            self.notice.setText(str(exc))
        else:
            self.notice.setText(
                self.text("preview_directory_warning") if self.editor is not None
                else self.text("directory_read_only")
            )
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            for column, key in enumerate(self.fields):
                value = record[key]
                if key == "credit_balance":
                    value = f"{float(value):,.2f}"
                elif key == "active":
                    value = self.text("active") if value else self.text("inactive")
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.table.setItem(row, column, item)
