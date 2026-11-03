"""Compact, accessible preview customer/supplier editing dialog."""
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QLineEdit, QVBoxLayout,
)


class DirectoryDialog(QDialog):
    def __init__(self, editor, kind, text, identifier=None, parent=None):
        super().__init__(parent)
        if kind not in ("customers", "suppliers"):
            raise ValueError("Unknown directory type")
        self.editor, self.kind, self.text = editor, kind, text
        self.identifier = identifier
        self.setMinimumWidth(440)
        self.setWindowTitle(text("edit_record") if identifier is not None else text("new_record"))
        main = QVBoxLayout(self)
        self.notice = QLabel(text("preview_directory_warning"))
        self.notice.setWordWrap(True)
        main.addWidget(self.notice)
        form = QFormLayout()
        self.fields = {}
        keys = ("name", "phone", "address") if kind == "customers" else (
            "name", "contact", "phone", "whatsapp", "address", "notes"
        )
        for key in keys:
            widget = QLineEdit()
            self.fields[key] = widget
            form.addRow(text(key), widget)
        self.active = None
        if kind == "suppliers" and identifier is not None:
            self.active = QCheckBox(text("active"))
            self.active.setChecked(True)
            form.addRow("", self.active)
        main.addLayout(form)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color:#d45252;")
        main.addWidget(self.error)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        main.addWidget(self.buttons)
        if identifier is not None:
            record = editor.get(kind, identifier)
            if record is None:
                raise ValueError("Record no longer exists")
            for key, widget in self.fields.items():
                widget.setText(str(record.get(key) or ""))
            if self.active is not None:
                self.active.setChecked(bool(record["active"]))

    def accept(self):
        payload = {key: widget.text() for key, widget in self.fields.items()}
        if self.active is not None:
            payload["active"] = self.active.isChecked()
        try:
            self.editor.save(self.kind, identifier=self.identifier, **payload)
        except (ValueError, RuntimeError, OSError) as exc:
            self.error.setText(str(exc))
            return
        super().accept()
