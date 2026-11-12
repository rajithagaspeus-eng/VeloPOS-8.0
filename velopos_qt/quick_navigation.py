"""Keyboard-first quick page navigation for the isolated V8 preview.

This is a UI-only page chooser: it never calls services, loads private data,
changes authentication, touches licensing or authorizes a POS transaction.
A selection must flow through SettingsPreview.nav and open_page() so all
existing session revalidation remains in the same place as sidebar clicks.
"""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout,
)

from .i18n import translate


class PreviewQuickJumpDialog(QDialog):
    """Search all 14 preview pages by localized or English label."""

    def __init__(self, nav_keys, text, parent=None):
        super().__init__(parent)
        self._keys = tuple(nav_keys)
        self._text = text
        self.selected_index = None
        self.setObjectName("quickJumpDialog")
        self.setWindowTitle(text("quick_jump_title"))
        self.setMinimumWidth(420)
        self.resize(510, 480)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 19, 22, 19)
        outer.setSpacing(12)
        heading = QLabel(text("quick_jump_title"))
        heading.setObjectName("quickJumpHeading")
        outer.addWidget(heading)
        self.search = QLineEdit()
        self.search.setObjectName("quickJumpSearch")
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText(text("quick_jump_placeholder"))
        self.search.setAccessibleName(text("quick_jump_title"))
        self.search.installEventFilter(self)
        outer.addWidget(self.search)

        self.results = QListWidget()
        self.results.setObjectName("quickJumpResults")
        self.results.setAccessibleName(text("quick_jump_title"))
        self.results.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.results.setTextElideMode(Qt.TextElideMode.ElideRight)
        outer.addWidget(self.results, stretch=1)

        self.hint = QLabel(text("quick_jump_hint"))
        self.hint.setObjectName("quickJumpHint")
        self.hint.setWordWrap(True)
        outer.addWidget(self.hint)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton(text("quick_jump_cancel"))
        cancel.setObjectName("secondaryAction")
        cancel.clicked.connect(self.reject)
        self.go_button = QPushButton(text("quick_jump_open"))
        self.go_button.setObjectName("quickJumpOpen")
        self.go_button.clicked.connect(self.accept_selected)
        actions.addWidget(cancel)
        actions.addWidget(self.go_button)
        outer.addLayout(actions)

        self.search.textChanged.connect(self.refresh)
        self.search.returnPressed.connect(self.accept_selected)
        self.results.itemActivated.connect(lambda _item: self.accept_selected())
        self.refresh()
        self.search.setFocus()

    def refresh(self, _text=None):
        """Retain canonical indices; filtering may not renumber navigation."""
        query_words = self.search.text().casefold().split()
        self.results.clear()
        for index, key in enumerate(self._keys):
            label = self._text(key)
            english = translate("en", key)
            searchable = (label + " " + english).casefold()
            if not all(word in searchable for word in query_words):
                continue
            item = QListWidgetItem(f"{index + 1:02d}   {label}")
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(english if english != label else label)
            self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)
        self.go_button.setEnabled(self.results.count() > 0)
        self.hint.setText(
            self._text("quick_jump_hint")
            if self.results.count()
            else self._text("quick_jump_no_results")
        )

    def eventFilter(self, watched, event):
        """Allow arrow navigation while keeping typing focus in the search."""
        if (watched is self.search
                and event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up)
                and self.results.count()):
            delta = 1 if event.key() == Qt.Key.Key_Down else -1
            current = self.results.currentRow()
            self.results.setCurrentRow(
                max(0, min(self.results.count() - 1, current + delta))
            )
            return True
        return super().eventFilter(watched, event)

    def accept_selected(self):
        current = self.results.currentItem()
        if current is None:
            return  # An empty search never navigates to a fabricated page.
        index = current.data(Qt.ItemDataRole.UserRole)
        if type(index) is not int or not 0 <= index < len(self._keys):
            return
        self.selected_index = index
        self.accept()
