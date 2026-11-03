"""Premium, localized KPI dashboard for safe VeloPOS 8 test previews."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)


class MetricCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setMinimumWidth(140)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        self.label = QLabel()
        self.label.setObjectName("metricLabel")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.value = QLabel("—")
        self.value.setObjectName("metricValue")
        layout.addWidget(self.value)


class DashboardOverview(QWidget):
    """Stats are fetched on explicit refresh/page entry, not stale cached."""
    keys = ("metric_products", "metric_customers", "metric_suppliers", "metric_low_stock")

    def __init__(self, reader, text, open_inventory=None):
        super().__init__()
        self.reader = reader
        self.text = text
        self.open_inventory = open_inventory
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 0)
        heading = QHBoxLayout()
        self.section_title = QLabel()
        self.section_title.setStyleSheet("font-size:14pt; font-weight:650;")
        heading.addWidget(self.section_title)
        heading.addStretch()
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("secondaryAction")
        self.refresh_button.clicked.connect(self.refresh)
        heading.addWidget(self.refresh_button)
        outer.addLayout(heading)
        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.cards = []
        for _ in self.keys:
            card = MetricCard()
            self.cards.append(card)
            metrics.addWidget(card, 1)
        outer.addLayout(metrics)

        self.alert_frame = QFrame()
        self.alert_frame.setObjectName("stockPanel")
        alert_layout = QVBoxLayout(self.alert_frame)
        alert_layout.setContentsMargins(18, 16, 18, 16)
        alert_heading = QHBoxLayout()
        self.alert_title = QLabel()
        self.alert_title.setStyleSheet("font-size:12pt; font-weight:650;")
        alert_heading.addWidget(self.alert_title)
        alert_heading.addStretch()
        self.open_stock_button = QPushButton()
        self.open_stock_button.setObjectName("secondaryAction")
        self.open_stock_button.clicked.connect(self._open_stock)
        self.open_stock_button.setEnabled(open_inventory is not None)
        alert_heading.addWidget(self.open_stock_button)
        alert_layout.addLayout(alert_heading)
        self.alert_body = QLabel()
        self.alert_body.setWordWrap(True)
        self.alert_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        alert_layout.addWidget(self.alert_body)
        outer.addWidget(self.alert_frame)

        self.data_note = QLabel()
        self.data_note.setObjectName("hint")
        self.data_note.setWordWrap(True)
        outer.addWidget(self.data_note)
        self.last_snapshot = None
        self.retranslate()
        self.refresh()

    def _open_stock(self):
        if self.open_inventory is not None:
            self.open_inventory()

    def retranslate(self):
        self.section_title.setText(self.text("dashboard_overview"))
        self.refresh_button.setText(self.text("refresh_stats"))
        self.alert_title.setText(self.text("low_stock_heading"))
        self.open_stock_button.setText(self.text("open_inventory"))
        self.data_note.setText(self.text("dashboard_test_data_note"))
        for key, card in zip(self.keys, self.cards):
            card.label.setText(self.text(key))
        self._render()

    def refresh(self):
        if self.reader is None:
            self.last_snapshot = None
        else:
            try:
                self.last_snapshot = self.reader.snapshot()
            except (OSError, ValueError, RuntimeError) as exc:
                self.last_snapshot = None
                self.data_note.setText(f'{self.text("dashboard_stats_error")}: {exc}')
                self._render()
                return
        self.data_note.setText(self.text("dashboard_test_data_note"))
        self._render()

    def _render(self):
        current = self.last_snapshot
        for key, card in zip(("products", "customers", "suppliers", "low_stock"), self.cards):
            card.value.setText(str(current[key]) if current is not None else "—")
        if current is None:
            self.alert_body.setText(self.text("dashboard_data_unavailable"))
            return
        alerts = current["alerts"]
        if not alerts:
            self.alert_body.setText(self.text("no_low_stock"))
            return
        lines = []
        for row in alerts:
            lines.append(f'{row["name_en"]}  ·  {row["barcode"]}  ·  {row["stock_qty"]:g}')
        self.alert_body.setText("\n".join(lines))
