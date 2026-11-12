"""Preview-only sign-in and first-run Admin enrollment dialog."""
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
    QVBoxLayout,
)


class PreviewLoginDialog(QDialog):
    def __init__(self, authenticator, text, parent=None):
        super().__init__(parent)
        self.authenticator = authenticator
        self.text = text
        self.identity = None
        self.setup = authenticator.needs_setup()
        self.setMinimumWidth(415)
        self.setWindowTitle(text("setup_preview_admin") if self.setup else text("preview_sign_in"))
        outer = QVBoxLayout(self)
        self.notice = QLabel(text("setup_preview_notice") if self.setup else text("preview_sign_in_notice"))
        self.notice.setWordWrap(True)
        outer.addWidget(self.notice)
        form = QFormLayout()
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.returnPressed.connect(self.accept)
        form.addRow(text("username_label"), self.username)
        form.addRow(text("password_label"), self.password)
        outer.addLayout(form)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color:#d45252;")
        outer.addWidget(self.error)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

    def accept(self):
        try:
            if self.setup:
                identity = self.authenticator.bootstrap_admin(
                    self.username.text(), self.password.text()
                )
            else:
                identity = self.authenticator.authenticate(
                    self.username.text(), self.password.text()
                )
        except (ValueError, RuntimeError, OSError) as exc:
            self.error.setText(str(exc))
            self.password.clear()
            return
        self.identity = identity
        super().accept()
