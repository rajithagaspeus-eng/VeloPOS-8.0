"""Experimental, isolated PySide6 settings UI.

No production db, printer discovery, payment, or license operations are invoked.
"""
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)
from .settings_model import SettingsAdapter, PRINTER_BRANDS, PRINT_MODES, PAPER_SIZES
from .i18n import LANGUAGES, translate
from .preview_models import InventoryReader, DirectoryReader
from .directory_pages import DirectoryPage
from .core_pages import InventoryPage, BillingPage
from .product_editor import PreviewProductEditor
from .auth_model import PreviewAuthenticator
from .login_dialog import PreviewLoginDialog
from .dashboard_model import DashboardReader
from .reports_model import PreviewReportsReader
from .shift_model import PreviewShiftReader
from .billing_readiness import DraftStockReader
from .customer_loyalty import DraftCustomerReader
from .inventory_insights import InventoryInsightsReader
from .inventory_insights_page import InventoryInsightsPage
from .reports_page import ReportsPage
from .purchasing_model import PurchaseOverviewReader
from .purchasing_page import PurchasingPage
from .analytics_model import BusinessIntelligenceReader
from .analytics_page import AnalyticsPage
from .forecast_model import DemandForecastReader
from .forecast_page import ForecastPage
from .transaction_gateway import PreviewTransactionGateway
from .checkout_preflight import PreviewCheckoutPreflight
from .dashboard_page import DashboardOverview
from .directory_editor import PreviewDirectoryEditor

DARK = """
QWidget { background:#0a1120; color:#e8eef8; font: 10pt 'Segoe UI'; }
QLabel { background:transparent; }
QFrame#panel { background:#121e31; border:1px solid #283750; border-radius:16px; }
QFrame#brandBar { background:#131e30; border:1px solid #283750; border-radius:14px; }
QFrame#billingTotals { background:#173e42; border:1px solid #316b6d; border-radius:12px; }
QFrame#metricCard { background:#192a40; border:1px solid #2b415e; border-radius:13px; }
QFrame#stockPanel { background:#192b36; border:1px solid #3a5960; border-radius:13px; }
QFrame#reportMetricCard { background:#182d43; border:1px solid #32475c; border-radius:12px; }
QLabel#reportMetricLabel { color:#b2c8dd; font-size:9.5pt; }
QLabel#reportMetricValue { color:#81eed4; font-size:19pt; font-weight:750; }
QLabel#metricLabel { color:#abc0d8; font-size:10pt; }
QLabel#metricValue { color:#81eed4; font-size:25pt; font-weight:750; }
QFrame#billingTotals QLabel { color:#bff7eb; background:transparent; }
QLabel#appTitle { font-size:22pt; font-weight:750; color:#f5f9ff; }
QLabel#previewPill { background:#193b35; color:#8cf4d0; border:1px solid #2c7666;
  border-radius:10px; padding:7px 12px; font-weight:650; }
QLabel#hint { color:#a9b9d0; }
QLineEdit, QComboBox { background:#1b2c42; border:1px solid #344b65;
  border-radius:9px; min-height:36px; padding:3px 11px; selection-background-color:#16a996; }
QLineEdit:focus, QComboBox:focus { border:2px solid #1ed0b1; }
QPushButton { background:#24c3ad; color:#06242c; border:0; border-radius:9px;
  min-height:34px; padding:7px 15px; font-weight:650; }
QPushButton:hover { background:#5bdecf; }
QPushButton#secondaryAction { background:#23354d; color:#e3efff; border:1px solid #3b506a; }
QPushButton#secondaryAction:hover { background:#314961; }
QListWidget { border:0; background:transparent; font-size:10.5pt; outline:0; }
QListWidget::item { padding:10px 13px; margin:2px 0; border-radius:9px; }
QListWidget::item:selected { background:#164f4e; color:#9cfbea; }
QListWidget::item:hover:!selected { background:#20344c; }
QTableWidget { background:#111e30; alternate-background-color:#17283c;
  border:1px solid #30405a; border-radius:10px; gridline-color:#283951;
  selection-background-color:#1b615c; selection-color:white; }
QHeaderView::section { background:#1c2d44; color:#c6d5e9; padding:9px;
  border:0; border-bottom:1px solid #34475d; font-weight:650; }
"""
LIGHT = """
QWidget { background:#f1f5fb; color:#192b42; font: 10pt 'Segoe UI'; }
QLabel { background:transparent; }
QFrame#panel { background:white; border:1px solid #dce5f1; border-radius:16px; }
QFrame#brandBar { background:white; border:1px solid #dce5f1; border-radius:14px; }
QFrame#billingTotals { background:#e0f5f0; border:1px solid #b8ded6; border-radius:12px; }
QFrame#metricCard { background:white; border:1px solid #d6e4f0; border-radius:13px; }
QFrame#stockPanel { background:#f5faf9; border:1px solid #cde6df; border-radius:13px; }
QFrame#reportMetricCard { background:#ffffff; border:1px solid #d3e2ef; border-radius:12px; }
QLabel#reportMetricLabel { color:#557086; font-size:9.5pt; }
QLabel#reportMetricValue { color:#078678; font-size:19pt; font-weight:750; }
QLabel#metricLabel { color:#526b80; font-size:10pt; }
QLabel#metricValue { color:#087d70; font-size:25pt; font-weight:750; }
QFrame#billingTotals QLabel { color:#125749; background:transparent; }
QLabel#appTitle { font-size:22pt; font-weight:750; color:#162d40; }
QLabel#previewPill { background:#e2f6ee; color:#137b65; border:1px solid #b4e1d5;
  border-radius:10px; padding:7px 12px; font-weight:650; }
QLabel#hint { color:#64778e; }
QLineEdit, QComboBox { background:#ffffff; border:1px solid #cedbe9;
  border-radius:9px; min-height:36px; padding:3px 11px; selection-background-color:#0fa390; }
QLineEdit:focus, QComboBox:focus { border:2px solid #10a58f; }
QPushButton { background:#0b8f82; color:white; border:0; border-radius:9px;
  min-height:34px; padding:7px 15px; font-weight:650; }
QPushButton:hover { background:#097b70; }
QPushButton#secondaryAction { background:#eef5f9; color:#236178; border:1px solid #c9dae6; }
QPushButton#secondaryAction:hover { background:#d9edf2; }
QListWidget { border:0; background:transparent; font-size:10.5pt; outline:0; }
QListWidget::item { padding:10px 13px; margin:2px 0; border-radius:9px; }
QListWidget::item:selected { background:#d8f4ed; color:#086b5d; }
QListWidget::item:hover:!selected { background:#eef3f9; }
QTableWidget { background:#ffffff; alternate-background-color:#f7f9fc;
  border:1px solid #d7e3f0; border-radius:10px; gridline-color:#e2eaf3;
  selection-background-color:#c9eae5; selection-color:#164a4b; }
QHeaderView::section { background:#ecf3fa; color:#425a71; padding:9px;
  border:0; border-bottom:1px solid #d7e3f0; font-weight:650; }
"""

class SettingsPreview(QMainWindow):
    def __init__(self, adapter: SettingsAdapter, preferences=None, inventory=None):
        super().__init__()
        self.preferences = preferences if preferences is not None else QSettings("VeloPOS", "VeloPOS8Preview")
        self.adapter = adapter
        self.inventory = inventory
        db = getattr(inventory, "database", None)
        self.directory = DirectoryReader(db) if db is not None else None
        self.dashboard_reader = DashboardReader(db) if db is not None else None
        self.reports_reader = PreviewReportsReader(db, authorize=self._is_preview_admin) if db is not None else None
        self.shift_reader = PreviewShiftReader(db) if db is not None else None
        self.stock_reader = DraftStockReader(db) if db is not None else None
        self.customer_reader = DraftCustomerReader(
            db, authorize=lambda: self._is_preview_cashier(),
        ) if db is not None else None
        self.insights_reader = InventoryInsightsReader(db, authorize=self._is_preview_admin) if db is not None else None
        self.purchasing_reader = PurchaseOverviewReader(db, authorize=self._is_preview_admin) if db is not None else None
        self.analytics_reader = BusinessIntelligenceReader(db, authorize=self._is_preview_admin) if db is not None else None
        self.forecast_reader = DemandForecastReader(db, authorize=self._is_preview_admin) if db is not None else None
        # Sole V8-facing financial gateway, intentionally denies ALL actions.
        # Never wire legacy services.create_sale directly into preview Qt.
        self.transaction_gateway = PreviewTransactionGateway(db) if db is not None else None
        # Diagnostics only: never a checkout authorization or a payment handler.
        self.checkout_preflight = PreviewCheckoutPreflight(db) if db is not None else None
        # The guarded editor refuses production DB paths. No authentication
        # or production product mutations are enabled in V8 yet.
        self.product_editor = PreviewProductEditor(db, authorize=self._is_preview_admin) if db is not None else None
        self.directory_editor = PreviewDirectoryEditor(db, authorize=self._is_preview_admin) if db is not None else None
        self.authenticator = PreviewAuthenticator(db) if db is not None else None
        self.identity = None
        self.saved = adapter.read()
        self.controls = {}
        stored_locale = str(self.preferences.value("language", "en"))
        self.locale = stored_locale if stored_locale in LANGUAGES else "en"
        self.translatable_labels = []
        self.save_buttons = []
        self.setWindowTitle("VeloPOS 8.0 | Modern Preview — TEST DATA")
        self.resize(1020, 680)
        self.setMinimumSize(760, 520)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 20, 22, 20)
        brand_bar = QFrame()
        brand_bar.setObjectName("brandBar")
        brand_row = QHBoxLayout(brand_bar)
        brand_row.setContentsMargins(20, 13, 20, 13)
        title = QLabel("VeloPOS 8.0")
        title.setObjectName("appTitle")
        brand_row.addWidget(title)
        brand_row.addStretch()
        self.user_label = QLabel()
        self.user_label.setObjectName("hint")
        brand_row.addWidget(self.user_label)
        self.login_button = QPushButton(self.t("preview_sign_in"))
        self.login_button.setObjectName("secondaryAction")
        self.login_button.setVisible(self.authenticator is not None)
        self.login_button.clicked.connect(self.preview_login)
        brand_row.addWidget(self.login_button)
        self.logout_button = QPushButton(self.t("preview_sign_out"))
        self.logout_button.setObjectName("secondaryAction")
        self.logout_button.setVisible(False)
        self.logout_button.clicked.connect(self.preview_logout)
        brand_row.addWidget(self.logout_button)
        self.preview_badge = QLabel(self.t("test_mode_badge"))
        self.preview_badge.setObjectName("previewPill")
        brand_row.addWidget(self.preview_badge)
        outer.addWidget(brand_bar)
        self.subtitle = QLabel(self.t("subtitle"))
        self.subtitle.setObjectName("hint")
        self.subtitle.setWordWrap(True)
        outer.addWidget(self.subtitle)

        locale_row = QHBoxLayout()
        locale_row.addStretch()
        self.locale_label = QLabel(self.t("language"))
        locale_row.addWidget(self.locale_label)
        self.locale_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.locale_combo.addItem(name, code)
        self.locale_combo.setCurrentIndex(list(LANGUAGES).index(self.locale))
        self.locale_combo.currentIndexChanged.connect(self.change_language)
        locale_row.addWidget(self.locale_combo)
        outer.addLayout(locale_row)

        body = QHBoxLayout()
        outer.addLayout(body, 1)
        navpanel = QFrame()
        navpanel.setObjectName("panel")
        navlayout = QVBoxLayout(navpanel)
        self.nav = QListWidget()
        self.nav.addItems([self.t(key) for key in self.nav_keys])
        # Sinhala/Tamil labels can be wider than English. Avoid the
        # unprofessional horizontal scrollbar and retain keyboard navigation.
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setTextElideMode(Qt.TextElideMode.ElideRight)
        for index, key in enumerate(self.nav_keys):
            self.nav.item(index).setToolTip(self.t(key))
        navlayout.addWidget(self.nav)
        navpanel.setFixedWidth(265)
        body.addWidget(navpanel)
        content = QFrame()
        content.setObjectName("panel")
        contentlayout = QVBoxLayout(content)
        contentlayout.setContentsMargins(26, 26, 26, 22)
        self.pages = QStackedWidget()
        contentlayout.addWidget(self.pages)
        body.addWidget(content, 1)

        # Lazy-create each page on first navigation; never repaint a giant form.
        self._pages = {}
        self.nav.currentRowChanged.connect(self.open_page)
        self.nav.setCurrentRow(0)
        self._apply_theme()

    nav_keys = ("dashboard", "inventory", "billing", "customers", "suppliers", "shop_profile", "appearance", "printer_receipts", "about", "reports", "smart_inventory", "purchasing", "analytics", "forecast_title")

    def t(self, key):
        return translate(self.locale, key)

    def change_language(self, _index):
        self.locale = self.locale_combo.currentData() or "en"
        self.preferences.setValue("language", self.locale)
        self.subtitle.setText(self.t("subtitle"))
        self.preview_badge.setText(self.t("test_mode_badge"))
        self.login_button.setText(self.t("preview_sign_in"))
        self.logout_button.setText(self.t("preview_sign_out"))
        self.locale_label.setText(self.t("language"))
        for index, key in enumerate(self.nav_keys):
            self.nav.item(index).setText(self.t(key))
            self.nav.item(index).setToolTip(self.t(key))
        for label, key in self.translatable_labels:
            label.setText(self.t(key))
        for button in self.save_buttons:
            button.setText(self.t("save"))
        if hasattr(self, "dashboard_intro"):
            self.dashboard_intro.setText(self.t("dashboard_intro"))
            self.dashboard_hint.setText(self.t("dashboard_hint"))
            for button, key in self.quick_buttons:
                button.setText(self.t(key))
            self.dashboard_overview.retranslate()
        if hasattr(self, "about_notice"):
            self.about_notice.setText(self.t("about_text"))
        if hasattr(self, "printer_notice"):
            self.printer_notice.setText(self.t("printer_notice"))
        for page in self._pages.values():
            if isinstance(page, (InventoryPage, BillingPage, DirectoryPage, ReportsPage, InventoryInsightsPage, PurchasingPage, AnalyticsPage, ForecastPage)):
                page.retranslate()

    def add_field(self, form, key, widget):
        label = QLabel(self.t(key))
        label.setMinimumWidth(155)
        form.addRow(label, widget)
        self.translatable_labels.append((label, key))

    def _line(self, key):
        widget = QLineEdit(self.saved.get(key, ""))
        self.controls[key] = widget
        return widget

    def _choice(self, key, values):
        widget = QComboBox()
        widget.addItems(values)
        original = self.saved.get(key, "")
        if original not in values:
            widget.addItem(original)
        widget.setCurrentText(original)
        self.controls[key] = widget
        return widget

    def _current_preview_role(self):
        """Role decisions are rechecked against TEST users for real preview DBs.

        The no-database component demo keeps its synthetic identity for
        offscreen UI tests only; it cannot open a live service/editor.
        """
        if self.identity is None:
            return None
        if self.authenticator is not None and hasattr(self.authenticator, "current_role"):
            try:
                role = self.authenticator.current_role(self.identity)
            except (RuntimeError, OSError):
                return None
            # Demotion immediately removes Admin access without requiring
            # the cashier to explicitly sign out.
            return role
        return self.identity.role if self.authenticator is None else None

    def _is_preview_admin(self):
        return self._current_preview_role() == "Admin"

    def _is_preview_cashier(self):
        return self._current_preview_role() in ("Admin", "Cashier")

    def preview_login(self):
        if self.authenticator is None:
            return
        dialog = PreviewLoginDialog(self.authenticator, self.t, parent=self)
        from PySide6.QtWidgets import QDialog
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.identity:
            self.identity = dialog.identity
            self._update_auth_ui()

    def preview_logout(self):
        self.identity = None
        # A new cashier must never inherit the previous cashier\'s draft.
        bill = self._pages.get(2)
        if isinstance(bill, BillingPage):
            bill.clear_session_draft()
        self._update_auth_ui()

    def _update_auth_ui(self):
        permitted = self._is_preview_admin()
        self.user_label.setText(
            f"{self.identity.username} ({self.identity.role})"
            if self.identity is not None else ""
        )
        self.login_button.setVisible(self.authenticator is not None and self.identity is None)
        self.logout_button.setVisible(self.identity is not None)
        # This gates only the visible test-data editors; commercial writes
        # still require service-layer session validation before release.
        for page in self._pages.values():
            if isinstance(page, InventoryPage):
                page.editor = self.product_editor if permitted else None
                page.add_product_button.setVisible(permitted)
                page.edit_product_button.setVisible(permitted)
                page.retranslate()
            elif isinstance(page, DirectoryPage):
                page.editor = self.directory_editor if permitted else None
                page.new_button.setVisible(permitted)
                page.edit_button.setVisible(permitted)
                page.retranslate()
            elif isinstance(page, ReportsPage):
                page.refresh()
            elif isinstance(page, InventoryInsightsPage):
                page.refresh()
            elif isinstance(page, PurchasingPage):
                page.refresh()
            elif isinstance(page, AnalyticsPage):
                page.refresh()
            elif isinstance(page, ForecastPage):
                page.refresh()
            elif isinstance(page, BillingPage):
                page.refresh_shift()
                page.refresh_customer_summary()

    def _create_page(self, index):
        if index == 1 and self.inventory is not None:
            return InventoryPage(self.inventory, self.t,
                                 editor=self.product_editor if self._is_preview_admin() else None)
        if index == 2 and self.inventory is not None:
            # Only use the original billing preview engine in our test-only DB.
            preview_fn = None
            db = getattr(self.inventory, "database", None)
            if db is not None:
                from pathlib import Path
                if Path(db.DATA_DIR).resolve().name.casefold() == "velopos8previewdata":
                    from velopos import services
                    preview_fn = services.preview_bill
            return BillingPage(self.inventory, self.t, bill_preview=preview_fn,
                               shift_reader=self.shift_reader, identity=lambda: self.identity,
                               stock_reader=self.stock_reader,
                               customer_reader=self.customer_reader,
                               authorize_customer=self._is_preview_cashier)
        if index in (3, 4) and self.directory is not None:
            return DirectoryPage(self.directory, self.nav_keys[index], self.t,
                                 editor=self.directory_editor if self._is_preview_admin() else None)
        if index == 9:
            return ReportsPage(self.reports_reader, self.t, self._is_preview_admin)
        if index == 10:
            return InventoryInsightsPage(self.insights_reader, self.t, self._is_preview_admin)
        if index == 11:
            return PurchasingPage(self.purchasing_reader, self.t, self._is_preview_admin)
        if index == 12:
            return AnalyticsPage(self.analytics_reader, self.t, self._is_preview_admin)
        if index == 13:
            return ForecastPage(self.forecast_reader, self.t, self._is_preview_admin)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        heading = QLabel(self.t(self.nav_keys[index]))
        self.translatable_labels.append((heading, self.nav_keys[index]))
        heading.setStyleSheet("font-size:19pt; font-weight:650;")
        layout.addWidget(heading)
        form = QFormLayout()
        form.setVerticalSpacing(15)
        if index == 0:
            self.dashboard_intro = QLabel(self.t("dashboard_intro"))
            self.dashboard_intro.setWordWrap(True)
            self.dashboard_hint = QLabel(self.t("dashboard_hint"))
            self.dashboard_hint.setWordWrap(True)
            layout.addWidget(self.dashboard_intro)
            layout.addWidget(self.dashboard_hint)
            # One-click access to the most frequent cashier preview tasks.
            self.quick_buttons = []
            quick_row = QHBoxLayout()
            for key, destination in (
                ("open_inventory", 1),
                ("open_billing", 2),
                ("open_customers", 3),
            ):
                action = QPushButton(self.t(key))
                action.setObjectName("secondaryAction")
                action.setMinimumHeight(54)
                action.clicked.connect(lambda _checked=False, idx=destination: self.nav.setCurrentRow(idx))
                quick_row.addWidget(action)
                self.quick_buttons.append((action, key))
            layout.addLayout(quick_row)
            self.dashboard_overview = DashboardOverview(
                self.dashboard_reader, self.t,
                open_inventory=lambda: self.nav.setCurrentRow(1),
            )
            layout.addWidget(self.dashboard_overview)
        elif index == 5:
            fields = [
                ("shop_name", "shop_name"), ("phone", "phone"),
                ("address", "address"), ("currency", "currency"),
                ("bank_name", "bank_name"), ("bank_branch", "bank_branch"),
                ("bank_acc", "bank_acc"), ("bank_holder", "bank_holder"),
            ]
            for label, key in fields:
                self.add_field(form, key, self._line(key))
        elif index == 6:
            self.add_field(form, "theme", self._choice("theme", ["light", "dark", "system"]))
            self.add_field(form, "accent", self._choice("accent", ["Blue", "Green", "Purple", "Orange", "Red"]))
            self.add_field(form, "font_family", self._choice("font_family", ["Segoe UI", "Arial", "Nirmala UI", "Calibri"]))
            self.add_field(form, "font_size", self._choice("font_size", ["13", "14", "15", "16", "18", "20", "22"]))
        elif index == 7:
            self.printer_notice = QLabel(self.t("printer_notice"))
            self.printer_notice.setWordWrap(True)
            layout.addWidget(self.printer_notice)
            self.add_field(form, "printer_brand", self._choice("printer_brand", PRINTER_BRANDS))
            self.add_field(form, "print_mode", self._choice("print_mode", PRINT_MODES))
            self.add_field(form, "paper_size", self._choice("paper_size", PAPER_SIZES))
            self.add_field(form, "print_copies", self._choice("print_copies", [str(i) for i in range(1, 6)]))
            self.add_field(form, "receipt_footer", self._line("receipt_footer"))
        else:
            self.about_notice = QLabel(self.t("about_text"))
            self.about_notice.setWordWrap(True)
            layout.addWidget(self.about_notice)
        if index in (5, 6, 7):
            layout.addLayout(form)
            save = QPushButton(self.t("save"))
            save.clicked.connect(self.save_settings)
            self.save_buttons.append(save)
            layout.addWidget(save, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addStretch()
        return page

    def open_page(self, index):
        if index < 0:
            return
        # Revalidation at navigation boundaries also redacts held drafts,
        # customer selections and visible user identity when the preview
        # account is deleted, its password rotates, or its role changes.
        if (self.identity is not None and self.authenticator is not None
                and hasattr(self.authenticator, "current_role")):
            try:
                current = self.authenticator.current_role(self.identity)
            except (RuntimeError, OSError):
                current = None
            if current is None or current != self.identity.role:
                self.preview_logout()
        if index not in self._pages:
            page = self._create_page(index)
            self._pages[index] = page
            self.pages.addWidget(page)
        self.pages.setCurrentWidget(self._pages[index])
        if index == 0 and hasattr(self, "dashboard_overview"):
            self.dashboard_overview.refresh()
        if index == 9 and isinstance(self._pages.get(9), ReportsPage):
            self._pages[9].refresh()
        if index == 10 and isinstance(self._pages.get(10), InventoryInsightsPage):
            self._pages[10].refresh()
        if index == 11 and isinstance(self._pages.get(11), PurchasingPage):
            self._pages[11].refresh()
        if index == 12 and isinstance(self._pages.get(12), AnalyticsPage):
            self._pages[12].refresh()
        if index == 13 and isinstance(self._pages.get(13), ForecastPage):
            self._pages[13].refresh()
        if index == 2 and isinstance(self._pages.get(2), BillingPage):
            self._pages[2].refresh_shift()
            self._pages[2].refresh_stock()

    def save_settings(self):
        try:
            # Save only the visible page's values, avoiding stale values from other pages.
            page_fields = {
                5: ("shop_name", "phone", "address", "currency", "bank_name", "bank_branch", "bank_acc", "bank_holder"),
                6: ("theme", "accent", "font_family", "font_size"),
                7: ("printer_brand", "print_mode", "paper_size", "print_copies", "receipt_footer"),
            }
            keys = page_fields.get(self.nav.currentRow(), ())
            changes = {
                key: (self.controls[key].currentText()
                      if isinstance(self.controls[key], QComboBox)
                      else self.controls[key].text())
                for key in keys if key in self.controls
            }
            self.adapter.save(changes)
        except (ValueError, OSError, RuntimeError) as exc:
            QMessageBox.warning(self, self.t("failed_title"), str(exc))
            return
        self.saved.update(changes)
        if "theme" in changes:
            self._apply_theme()
        QMessageBox.information(self, self.t("saved_title"), self.t("saved"))

    def _apply_theme(self):
        theme_widget = self.controls.get("theme")
        selected = theme_widget.currentText() if theme_widget else self.saved.get("theme", "light")
        if selected == "system":
            selected = "light"
        self.setStyleSheet(DARK if selected == "dark" else LIGHT)


def run(settings, database=None):
    app = QApplication.instance() or QApplication([])
    window = SettingsPreview(SettingsAdapter(settings),
                             inventory=InventoryReader(database) if database is not None else None)
    window.show()
    return app.exec()
