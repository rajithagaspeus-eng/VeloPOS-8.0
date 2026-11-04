"""Experimental, isolated PySide6 settings UI.

No production db, printer discovery, payment, or license operations are invoked.
"""
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QKeySequence, QShortcut
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
from .auth_model import PreviewAuthenticator, revoke_preview_session
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
from .quick_navigation import PreviewQuickJumpDialog

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


# Premium visual hierarchy for the 2026 preview shell. This changes paint
# only; no transaction or backend behavior.
DARK += """
QFrame#navigationPanel { background:#101c2d; border:1px solid #26394c; border-radius:20px; }
QFrame#workspacePanel { background:#111d2d; border:1px solid #283a50; border-radius:20px; }
QLabel#sideBrand { color:#e6fcf9; font-size:17pt; font-weight:800; letter-spacing:1px; }
QLabel#sideCaption { color:#8ba7b9; font-size:9pt; }
QLabel#sideFooter { color:#83a4aa; font-size:8.5pt; }
QLabel#metricIndex { color:#78d6cb; font-size:8pt; font-weight:750; letter-spacing:1px; }
QLabel#pageEyebrow { color:#54d8bd; font-size:9pt; font-weight:750; letter-spacing:1px; }
QFrame#heroPanel { background:#143345; border:1px solid #236175; border-radius:16px; }
QLabel#heroTitle { color:#f0ffff; font-size:19pt; font-weight:750; }
QLabel#heroDescription { color:#c6e4e5; font-size:10.5pt; }
QLabel#dashboardSection { color:#f0f6ff; font-size:14pt; font-weight:750; }
QListWidget#mainNavigation { background:transparent; border:none; outline:none; }
QListWidget#mainNavigation::item { padding:13px 15px; margin:3px 1px; border-radius:11px; color:#bdd0df; }
QListWidget#mainNavigation::item:selected { background:#1e5c5b; color:#e4fff7; font-weight:750; border-left:3px solid #57e0bb; }
QListWidget#mainNavigation::item:hover:!selected { background:#223850; color:#ffffff; }
QFrame#metricCard { background:#192f40; border:1px solid #2b4a5e; border-radius:16px; }
QPushButton#quickAction { background:#183e4c; color:#e0fbf6; border:1px solid #2a6c73; border-radius:12px; text-align:left; padding-left:17px; font-weight:700; }
QPushButton#quickAction:hover { background:#205362; }
QPushButton#quickJumpAction { background:#1a3545; color:#b7f3e8; border:1px solid #35666e; padding:6px 12px; }
QPushButton#quickJumpAction:hover { background:#245267; }
QPushButton#sidebarToggle { background:#193a4d; color:#d2fbf4; border:1px solid #376775; min-width:37px; padding:6px; }
QPushButton#sidebarToggle:hover { background:#24576b; }
QPushButton#sidebarToggle:checked { background:#165b59; border:1px solid #50cdb2; }
QLabel#quickJumpHeading { color:#edffff; font-size:17pt; font-weight:750; }
QListWidget#quickJumpResults { background:#101d2e; border:1px solid #2d4961; border-radius:12px; }
QPushButton:disabled { background:#253342; color:#798899; }
QScrollBar:vertical { background:#111d2d; width:10px; margin:3px; }
QScrollBar::handle:vertical { background:#40576c; border-radius:5px; min-height:36px; }
QFrame#searchPanel { background:#152638; border:1px solid #2d4761; border-radius:16px; }
QLabel#screenTitle { color:#edf6ff; font-size:21pt; font-weight:750; }
QLabel#sectionTitle { color:#e9f6fc; font-size:13pt; font-weight:750; }
QLabel#previewSafetyNotice { color:#f8d9a3; background:#3a3028; border:1px solid #695139; border-radius:9px; padding:11px 13px; }
QLabel#catalogStatus { color:#91a8b9; font-size:9pt; }
QLabel#billingSearchHelp { color:#9bcfc6; font-size:9pt; padding:4px 2px; }
QLineEdit#barcodeSearch { background:#102235; border:2px solid #376b79; border-radius:11px; min-height:45px; font-size:12pt; padding-left:15px; }
QLineEdit#barcodeSearch:focus { border:2px solid #49e4c0; }
QTableWidget#catalogTable, QTableWidget#draftCartTable, QTableWidget#searchResults { border:1px solid #31495e; border-radius:12px; }
QFrame#billingTotals { background:#154343; border:1px solid #368778; border-radius:15px; }
QFrame#billingTotals QLabel { color:#d2fff4; }
QFrame#directorySearchPanel { background:#152638; border:1px solid #2d4761; border-radius:16px; }
QLineEdit#directorySearch { background:#102235; border:2px solid #345f70; border-radius:10px; min-height:43px; font-size:11pt; padding-left:13px; }
QLineEdit#directorySearch:focus { border:2px solid #49e4c0; }
QTableWidget#directoryTable { border:1px solid #31495e; border-radius:12px; }
QLabel#directoryNotice { color:#9fb9c7; font-size:9pt; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
"""
LIGHT += """
QFrame#navigationPanel { background:#ffffff; border:1px solid #d9e4ed; border-radius:20px; }
QFrame#workspacePanel { background:#ffffff; border:1px solid #dce6ef; border-radius:20px; }
QLabel#sideBrand { color:#133447; font-size:17pt; font-weight:800; letter-spacing:1px; }
QLabel#sideCaption { color:#678392; font-size:9pt; }
QLabel#sideFooter { color:#63818e; font-size:8.5pt; }
QLabel#metricIndex { color:#1d9185; font-size:8pt; font-weight:750; letter-spacing:1px; }
QLabel#pageEyebrow { color:#0d9285; font-size:9pt; font-weight:750; letter-spacing:1px; }
QFrame#heroPanel { background:#e2f6f2; border:1px solid #a8dcd3; border-radius:16px; }
QLabel#heroTitle { color:#12514f; font-size:19pt; font-weight:750; }
QLabel#heroDescription { color:#39716d; font-size:10.5pt; }
QLabel#dashboardSection { color:#18374b; font-size:14pt; font-weight:750; }
QListWidget#mainNavigation { background:transparent; border:none; outline:none; }
QListWidget#mainNavigation::item { padding:13px 15px; margin:3px 1px; border-radius:11px; color:#3e6074; }
QListWidget#mainNavigation::item:selected { background:#d8f4ed; color:#086b5d; font-weight:750; border-left:3px solid #0c9c88; }
QListWidget#mainNavigation::item:hover:!selected { background:#eff6fa; color:#103f53; }
QFrame#metricCard { background:#f8fcff; border:1px solid #d4e7ec; border-radius:16px; }
QPushButton#quickAction { background:#edf8f6; color:#125e5b; border:1px solid #b9ddd6; border-radius:12px; text-align:left; padding-left:17px; font-weight:700; }
QPushButton#quickAction:hover { background:#d9f0eb; }
QPushButton#quickJumpAction { background:#eff9f8; color:#11695f; border:1px solid #c4dfdc; padding:6px 12px; }
QPushButton#quickJumpAction:hover { background:#d9f1eb; }
QPushButton#sidebarToggle { background:#eaf6f4; color:#135a5d; border:1px solid #b5d7d6; min-width:37px; padding:6px; }
QPushButton#sidebarToggle:hover { background:#d0ece7; }
QPushButton#sidebarToggle:checked { background:#c8ebe0; border:1px solid #2a9d8d; }
QLabel#quickJumpHeading { color:#164f4c; font-size:17pt; font-weight:750; }
QListWidget#quickJumpResults { background:#ffffff; border:1px solid #d1e3e6; border-radius:12px; }
QPushButton:disabled { background:#e8edf2; color:#8da0ab; }
QScrollBar:vertical { background:#ffffff; width:10px; margin:3px; }
QScrollBar::handle:vertical { background:#c4d4df; border-radius:5px; min-height:36px; }
QFrame#searchPanel { background:#f7fbff; border:1px solid #d1e1ed; border-radius:16px; }
QLabel#screenTitle { color:#17384c; font-size:21pt; font-weight:750; }
QLabel#sectionTitle { color:#173b4b; font-size:13pt; font-weight:750; }
QLabel#previewSafetyNotice { color:#86561c; background:#fff5e8; border:1px solid #f2d4ac; border-radius:9px; padding:11px 13px; }
QLabel#catalogStatus { color:#5e788c; font-size:9pt; }
QLabel#billingSearchHelp { color:#26786f; font-size:9pt; padding:4px 2px; }
QLineEdit#barcodeSearch { background:white; border:2px solid #a7cfcf; border-radius:11px; min-height:45px; font-size:12pt; padding-left:15px; }
QLineEdit#barcodeSearch:focus { border:2px solid #059e87; }
QTableWidget#catalogTable, QTableWidget#draftCartTable, QTableWidget#searchResults { border:1px solid #d7e3ec; border-radius:12px; }
QFrame#billingTotals { background:#ddf5ed; border:1px solid #a5d7c8; border-radius:15px; }
QFrame#billingTotals QLabel { color:#14594d; }
QFrame#directorySearchPanel { background:#f7fbff; border:1px solid #d1e1ed; border-radius:16px; }
QLineEdit#directorySearch { background:white; border:2px solid #b7d4dc; border-radius:10px; min-height:43px; font-size:11pt; padding-left:13px; }
QLineEdit#directorySearch:focus { border:2px solid #059e87; }
QTableWidget#directoryTable { border:1px solid #d7e3ec; border-radius:12px; }
QLabel#directoryNotice { color:#617d8b; font-size:9pt; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
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
        self._compact_mode = None
        stored_locale = str(self.preferences.value("language", "en"))
        self.locale = stored_locale if stored_locale in LANGUAGES else "en"
        self.translatable_labels = []
        self.save_buttons = []
        self.setWindowTitle("VeloPOS 8.0 | Modern Preview — TEST DATA")
        self.resize(1220, 780)
        self.setMinimumSize(760, 520)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        self.outer_layout = outer
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)
        brand_bar = QFrame()
        brand_bar.setObjectName("brandBar")
        brand_row = QHBoxLayout(brand_bar)
        self.brand_row = brand_row
        brand_row.setContentsMargins(20, 13, 20, 13)
        self.brand_title = QLabel("VeloPOS 8.0")
        self.brand_title.setObjectName("appTitle")
        brand_row.addWidget(self.brand_title)
        brand_row.addStretch()
        self.menu_button = QPushButton("☰")
        self.menu_button.setObjectName("sidebarToggle")
        self.menu_button.setAccessibleName(self.t("navigation_toggle"))
        self.menu_button.setToolTip(self.t("navigation_toggle_hint"))
        self.menu_button.setCheckable(True)
        self.menu_button.clicked.connect(self.toggle_sidebar)
        brand_row.addWidget(self.menu_button)
        self.quick_jump_button = QPushButton(self.t("quick_jump_action"))
        self.quick_jump_button.setObjectName("quickJumpAction")
        self.quick_jump_button.setToolTip(self.t("quick_jump_hint"))
        self.quick_jump_button.clicked.connect(self.open_quick_jump)
        brand_row.addWidget(self.quick_jump_button)
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
        self.navpanel = navpanel
        navpanel.setObjectName("navigationPanel")
        navlayout = QVBoxLayout(navpanel)
        navlayout.setContentsMargins(15, 19, 15, 17)
        navlayout.setSpacing(9)
        side_brand = QLabel("VELO  /  POS")
        side_brand.setObjectName("sideBrand")
        navlayout.addWidget(side_brand)
        side_caption = QLabel("8.0  ·  WORKSPACE")
        side_caption.setObjectName("sideCaption")
        navlayout.addWidget(side_caption)
        self.nav = QListWidget()
        self.nav.setObjectName("mainNavigation")
        self.nav.addItems([self.t(key) for key in self.nav_keys])
        # Sinhala/Tamil labels can be wider than English. Avoid the
        # unprofessional horizontal scrollbar and retain keyboard navigation.
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setTextElideMode(Qt.TextElideMode.ElideRight)
        for index, key in enumerate(self.nav_keys):
            self.nav.item(index).setToolTip(self.t(key))
        navlayout.addWidget(self.nav)
        footer = QLabel("PREVIEW  •  NO LIVE CHECKOUT")
        footer.setObjectName("sideFooter")
        footer.setWordWrap(True)
        navlayout.addWidget(footer)
        navpanel.setFixedWidth(244)
        body.addWidget(navpanel)
        content = QFrame()
        content.setObjectName("workspacePanel")
        contentlayout = QVBoxLayout(content)
        self.workspace_layout = contentlayout
        contentlayout.setContentsMargins(27, 24, 27, 22)
        self.pages = QStackedWidget()
        contentlayout.addWidget(self.pages)
        body.addWidget(content, 1)

        # Lazy-create each page on first navigation; never repaint a giant form.
        self._pages = {}
        self.nav.currentRowChanged.connect(self.open_page)
        self.nav.currentRowChanged.connect(self._close_compact_sidebar_on_navigation)
        self.sidebar_shortcut = QShortcut(QKeySequence("Ctrl+B"), self)
        self.sidebar_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.sidebar_shortcut.activated.connect(self.toggle_sidebar)
        self.quick_jump_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self.quick_jump_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.quick_jump_shortcut.activated.connect(self.open_quick_jump)
        self.nav.setCurrentRow(0)
        self._apply_theme()
        self._apply_responsive_layout()

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
        self.quick_jump_button.setText(self.t("quick_jump_action"))
        self.quick_jump_button.setToolTip(self.t("quick_jump_hint"))
        self.menu_button.setAccessibleName(self.t("navigation_toggle"))
        self.menu_button.setToolTip(self.t("navigation_toggle_hint"))
        self._refresh_header_navigation()
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

    def _refresh_header_navigation(self):
        """Keep compact controls understandable in every preview language."""
        if self._compact_mode:
            self.quick_jump_button.setText("Ctrl+K")
            self.brand_title.setText("VeloPOS 8")
        else:
            self.quick_jump_button.setText(self.t("quick_jump_action"))
            self.brand_title.setText("VeloPOS 8.0")
        self.quick_jump_button.setAccessibleName(self.t("quick_jump_action"))
        self.menu_button.setChecked(not self.navpanel.isHidden())

    def _apply_responsive_layout(self):
        """Reserve the content workspace on compact desktop windows."""
        compact = self.width() < 1040
        changed = compact != self._compact_mode
        self._compact_mode = compact
        self.outer_layout.setContentsMargins(
            *(10, 10, 10, 10) if compact else (20, 18, 20, 18)
        )
        self.brand_row.setContentsMargins(
            *(10, 9, 10, 9) if compact else (20, 13, 20, 13)
        )
        self.workspace_layout.setContentsMargins(
            *(12, 14, 12, 14) if compact else (27, 24, 27, 22)
        )
        self.navpanel.setFixedWidth(216 if compact else 244)
        if changed:
            # On crossing the width breakpoint, restore the predictable
            # default. Within a width range preserve the user's toggle.
            self.navpanel.setVisible(not compact)
        self._refresh_header_navigation()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "navpanel") and self._compact_mode is not None:
            self._apply_responsive_layout()

    def toggle_sidebar(self):
        """One visible menu entry remains when the sidebar is collapsed."""
        should_show = self.navpanel.isHidden()
        self.navpanel.setVisible(should_show)
        self.menu_button.setChecked(should_show)
        if should_show:
            self.nav.setFocus()
        else:
            self.menu_button.setFocus()

    def _close_compact_sidebar_on_navigation(self, _index):
        if self._compact_mode and not self.navpanel.isHidden():
            self.navpanel.hide()
            self.menu_button.setChecked(False)

    def open_quick_jump(self):
        """Navigation-only command palette; canonical open_page checks still run."""
        from PySide6.QtWidgets import QDialog
        dialog = PreviewQuickJumpDialog(self.nav_keys, self.t, parent=self)
        try:
            if (dialog.exec() == QDialog.DialogCode.Accepted
                    and dialog.selected_index is not None):
                self.nav.setCurrentRow(dialog.selected_index)
        finally:
            dialog.deleteLater()

    def preview_login(self):
        if self.authenticator is None:
            return
        dialog = PreviewLoginDialog(self.authenticator, self.t, parent=self)
        from PySide6.QtWidgets import QDialog
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.identity:
            self.identity = dialog.identity
            self._update_auth_ui()

    def preview_logout(self):
        if self.identity is not None:
            revoke_preview_session(self.identity)
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
        eyebrow = QLabel("VELOPOS  /  TEST WORKSPACE")
        eyebrow.setObjectName("pageEyebrow")
        layout.addWidget(eyebrow)
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
            hero = QFrame()
            hero.setObjectName("heroPanel")
            hero_layout = QVBoxLayout(hero)
            hero_layout.setContentsMargins(22, 18, 22, 18)
            hero_layout.setSpacing(7)
            self.dashboard_intro.setObjectName("heroTitle")
            self.dashboard_hint.setObjectName("heroDescription")
            hero_layout.addWidget(self.dashboard_intro)
            hero_layout.addWidget(self.dashboard_hint)
            layout.addWidget(hero)
            # One-click access to the most frequent cashier preview tasks.
            self.quick_buttons = []
            quick_row = QHBoxLayout()
            for key, destination in (
                ("open_inventory", 1),
                ("open_billing", 2),
                ("open_customers", 3),
            ):
                action = QPushButton(self.t(key))
                action.setObjectName("quickAction")
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
