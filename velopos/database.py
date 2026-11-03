"""SQLite layer: schema, settings store, audit log, safe backup."""
import os, sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import branding as _B

_base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
DATA_DIR = os.environ.get("VELOPOS_HOME") or os.path.join(_base, "VeloPOS")
DB_PATH = os.path.join(DATA_DIR, "velopos.db")


def p(*parts):
    return os.path.join(DATA_DIR, *parts)


for _d in ("Backups", "Receipts", "Exports", "Assets", "ProductImages"):
    os.makedirs(p(_d), exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY, pw_hash TEXT NOT NULL, role TEXT NOT NULL, created TEXT);
CREATE TABLE IF NOT EXISTS products (
    barcode TEXT PRIMARY KEY, name_en TEXT NOT NULL, name_local TEXT DEFAULT '',
    keywords TEXT DEFAULT '', cost_price REAL DEFAULT 0, selling_price REAL DEFAULT 0,
    wholesale_price REAL DEFAULT 0, stock_qty REAL DEFAULT 0, expiry_date TEXT DEFAULT '',
    image_path TEXT DEFAULT '', warranty TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT UNIQUE,
    address TEXT DEFAULT '', credit_balance REAL DEFAULT 0, loyalty_points REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS credit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, date TEXT, time TEXT,
    description TEXT, amount REAL, type TEXT);
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_no TEXT UNIQUE, date TEXT, time TEXT,
    subtotal REAL, discount REAL, redeemed REAL DEFAULT 0, total_amount REAL, paid_amount REAL,
    balance REAL, payment_method TEXT, payment_ref TEXT, profit REAL, cashier TEXT,
    customer_id INTEGER, customer_name TEXT, status TEXT DEFAULT 'OK');
CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_no TEXT, barcode TEXT, item_name TEXT,
    qty REAL, cost_price REAL, selling_price REAL, total REAL, serial_no TEXT DEFAULT '',
    warranty TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, category TEXT, description TEXT,
    amount REAL, added_by TEXT);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user TEXT, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cashier TEXT, opened_at TEXT, closed_at TEXT,
    opening_cash REAL DEFAULT 0, counted_cash REAL, expected_cash REAL, difference REAL,
    status TEXT DEFAULT 'OPEN', note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS cash_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT, shift_id INTEGER, ts TEXT, kind TEXT, amount REAL,
    reason TEXT, user TEXT);
CREATE TABLE IF NOT EXISTS returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT, return_no TEXT UNIQUE, invoice_no TEXT, date TEXT, time TEXT,
    amount REAL, refund_method TEXT, reason TEXT, cashier TEXT, shift_id INTEGER, profit_adj REAL);
CREATE TABLE IF NOT EXISTS return_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, return_no TEXT, sale_item_id INTEGER, barcode TEXT,
    item_name TEXT, qty REAL, price REAL, total REAL);
CREATE TABLE IF NOT EXISTS quotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, quote_no TEXT UNIQUE, date TEXT, valid_until TEXT,
    customer_name TEXT, phone TEXT, subtotal REAL, discount REAL, total REAL, note TEXT,
    status TEXT DEFAULT 'OPEN', created_by TEXT);
CREATE TABLE IF NOT EXISTS quote_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, quote_no TEXT, barcode TEXT, item_name TEXT,
    qty REAL, price REAL, total REAL);
CREATE TABLE IF NOT EXISTS license_state (id INTEGER PRIMARY KEY, blob TEXT);
CREATE TABLE IF NOT EXISTS reset_attempts (
    scope TEXT PRIMARY KEY, fails INTEGER DEFAULT 0, locked_until REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL COLLATE NOCASE UNIQUE, sort_order INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, barcode TEXT, ts TEXT, user TEXT,
    cost_old REAL, cost_new REAL, sell_old REAL, sell_new REAL, whole_old REAL, whole_new REAL, reason TEXT);
CREATE INDEX IF NOT EXISTS idx_price_hist ON price_history(barcode);
CREATE TABLE IF NOT EXISTS stock_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, barcode TEXT, qty_change REAL, qty_after REAL, reason TEXT,
    ref TEXT DEFAULT '', user TEXT DEFAULT '', batch_id INTEGER, note TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_moves_barcode ON stock_moves(barcode);
CREATE INDEX IF NOT EXISTS idx_moves_ts ON stock_moves(ts);
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT, barcode TEXT, batch_no TEXT DEFAULT '', expiry_date TEXT DEFAULT '',
    qty_remaining REAL DEFAULT 0, cost_price REAL DEFAULT 0, received_ts TEXT, source TEXT DEFAULT '', ref TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_batches_barcode ON batches(barcode);
CREATE TABLE IF NOT EXISTS sale_item_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT, sale_item_id INTEGER, barcode TEXT, batch_id INTEGER, qty_base REAL, returned_base REAL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_sib_item ON sale_item_batches(sale_item_id);
CREATE TABLE IF NOT EXISTS stock_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, started_ts TEXT, user TEXT, scope TEXT DEFAULT 'all', category TEXT DEFAULT '',
    status TEXT DEFAULT 'OPEN', finalized_ts TEXT, note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS stock_count_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT, count_id INTEGER, barcode TEXT, counted_qty REAL, system_qty REAL, applied_qty REAL, ts TEXT,
    UNIQUE(count_id, barcode));
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL COLLATE NOCASE UNIQUE, contact TEXT DEFAULT '', phone TEXT DEFAULT '',
    whatsapp TEXT DEFAULT '', address TEXT DEFAULT '', notes TEXT DEFAULT '', active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT, grn_no TEXT UNIQUE, supplier_id INTEGER, supplier_invoice TEXT DEFAULT '', date TEXT, ts TEXT, user TEXT,
    subtotal REAL DEFAULT 0, discount REAL DEFAULT 0, total REAL DEFAULT 0, paid REAL DEFAULT 0, status TEXT DEFAULT 'OK', note TEXT DEFAULT '',
    void_reason TEXT DEFAULT '', void_ts TEXT, void_user TEXT);
CREATE TABLE IF NOT EXISTS purchase_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, purchase_id INTEGER, barcode TEXT, name TEXT, qty REAL, unit TEXT DEFAULT '', factor REAL DEFAULT 1,
    base_qty REAL, cost_price REAL, line_total REAL, batch_id INTEGER, batch_no TEXT DEFAULT '', expiry TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_pitems_purchase ON purchase_items(purchase_id);
CREATE TABLE IF NOT EXISTS supplier_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_id INTEGER, purchase_id INTEGER, ts TEXT, date TEXT, amount REAL, method TEXT DEFAULT 'Cash',
    ref TEXT DEFAULT '', note TEXT DEFAULT '', user TEXT, shift_id INTEGER);
CREATE INDEX IF NOT EXISTS idx_spay_supplier ON supplier_payments(supplier_id);
CREATE TABLE IF NOT EXISTS reminder_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, ts TEXT, channel TEXT, amount REAL, message TEXT, user TEXT);
CREATE TABLE IF NOT EXISTS cloud_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT, backup_name TEXT, target_dir TEXT, attempts INTEGER DEFAULT 0, last_error TEXT DEFAULT '',
    created_ts TEXT, last_try_ts TEXT, UNIQUE(backup_name, target_dir));
CREATE TABLE IF NOT EXISTS product_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT, barcode TEXT, unit_name TEXT COLLATE NOCASE, factor_to_base REAL, price_override REAL DEFAULT 0,
    UNIQUE(barcode, unit_name));
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(date);
CREATE INDEX IF NOT EXISTS idx_items_inv ON sale_items(invoice_no);
"""

DEFAULTS = {
    "shop_name": "MY ENTERPRISE STORE", "address": "123, Main Street", "phone": "011-2345678",
    "currency": "Rs.", "theme": "light", "accent": "Blue", "font_family": "Segoe UI",
    "font_size": "15", "paper_size": "80mm", "printer": "Default System Printer",
    "bank_name": "", "bank_branch": "", "bank_acc": "", "bank_holder": "",
    "whatsapp_mode": "Desktop App", "second_lang": "English Only",
    # ---- feature toggles (Settings -> Smart Features) ----
    "feat_qty_popup": "1", "feat_warranty": "1", "feat_wholesale": "1", "feat_loyalty": "1",
    "feat_whatsapp": "1", "feat_voice": "0", "feat_dual_lang": "0",
    "recovery_hash": "", "feat_shift": "1",
    # ---- printing & cash drawer ----
    "printer_brand": "Xprinter", "print_mode": "Windows RAW (ESC/POS)", "lan_ip": "192.168.1.100",
    "lan_port": "9100", "com_port": "COM3", "com_baud": "9600", "print_width_dots": "0",
    "print_copies": "1", "receipt_font": "Nirmala UI", "receipt_footer": "Thank You! Come Again!",
    "cut_cmd": "Partial cut (GS V 66)", "feat_print_logo": "1", "feat_auto_print": "1",
    "feat_cut": "1", "feat_cash_drawer": "0", "drawer_pin": "Pin 2", "drawer_open_on": "Cash sales only",
    # ---- printing fine-tuning (Phase 4) ----
    "print_bottom_feed": "0", "print_shift_left": "0", "print_threshold": "190",
    # ---- backup & recovery (Phase 4) ----
    "feat_autobackup": "1", "feat_backup_on_exit": "1", "feat_backup_gdrive": "0",
    "backup_interval_hours": "6", "backup_keep": "20", "backup_gdrive_dir": "",
    "last_auto_backup": "", "last_backup_msg": "",
    # ---- owner contact, e-mail OTP, password recovery (Phase 4) ----
    "owner_email": "", "owner_whatsapp": "", "smtp_host": "smtp.gmail.com", "smtp_port": "465",
    "smtp_user": "", "smtp_pass_enc": "", "feat_otp": "1", "feat_forgot_pw": "1",
    "setup_done": "1",     # existing installs never see the wizard; first-run setup sets it to 0
    # ---- smart assistant, voice, daily summary (Phase 5) ----
    "feat_assistant": "1", "feat_assistant_fab": "0", "feat_assistant_voice": "0", "feat_voice_input": "0",
    "assistant_lang": "Auto (match my question)", "assistant_fab_pos": "Top-right", "low_stock_level": "5",
    "feat_daily_summary": "0", "feat_summary_on_close": "1", "feat_summary_dayend": "0",
    "summary_channel": "WhatsApp", "summary_time": "21:00", "last_summary_date": "",
    # ---- catalogue: categories, item grid, price tools (Phase 6.1) ----
    "feat_categories": "1", "feat_item_grid": "0", "feat_price_history": "1", "grid_page_size": "12", "grid_cols": "3",
    # ---- stock control (Phase 6.2) ----
    "feat_allow_oversell": "0", "feat_stock_screen": "1", "feat_batches": "0", "feat_block_expired": "0", "feat_multi_unit": "0",
    # ---- buying & money rules (Phase 6.3) ----
    "feat_suppliers": "1", "purchase_cost_policy": "Last cost", "grn_update_cost": "1",
    "feat_vat": "0", "vat_percent": "18", "vat_mode": "Exclusive", "vat_number": "", "vat_on_service": "0",
    "feat_service_charge": "0", "service_percent": "10",
    "feat_credit_limit": "0", "feat_overdue_reminders": "0", "overdue_days": "30", "reminder_cooldown_days": "7",
    "reminder_template": "Dear {name}, this is a friendly reminder from {shop}: Rs. {amount} has been outstanding for {days} days. Please settle it at your earliest convenience. Thank you!",
    # ---- hardware & extras (Phase 6.4) ----
    "feat_shortcut_help": "1", "feat_labels": "1", "label_w_mm": "50", "label_h_mm": "30", "label_dpi": "203", "label_symbology": "Auto",
    "label_shop": "1", "label_name": "1", "label_price": "1", "label_cols": "3", "label_rows": "8", "label_margin_mm": "8", "label_cut": "0",
    "feat_pole_display": "0", "pole_x": "0", "pole_y": "0", "pole_w": "800", "pole_h": "600", "pole_fullscreen": "0", "pole_font": "28",
    "pole_promo": "Welcome! Thank you for shopping with us.",
    "feat_cloud_sync": "0", "cloud_dirs": "", "cloud_last_ok": "", "cloud_last_msg": "",
    "feat_dashboard": "0", "dash_url": _B.DEFAULT_DASH_URL, "dash_invite": "", "dash_shop_id": "", "dash_key_enc": "", "dash_view_token": "",
    "dash_last_ok": "", "dash_last_msg": "",
    "feat_update_check": "0", "update_url": _B.DEFAULT_UPDATE_URL, "last_update_check": "", "update_notified_version": "", "update_info": "",
    # ---- cashier permissions (Admin can always do everything) ----
    "cperm_reports": "0", "cperm_stock": "1", "cperm_see_cost": "0", "cperm_returns": "1",
    "cperm_discount": "1", "cperm_expenses": "1",
}

PERMS = [
    ("cperm_reports", "View reports & profit"),
    ("cperm_stock", "Add / edit inventory items"),
    ("cperm_see_cost", "See cost prices"),
    ("cperm_returns", "Process returns & refunds"),
    ("cperm_discount", "Give discounts on bills"),
    ("cperm_expenses", "Add expenses / petty cash"),
]

FEATURES = [
    ("feat_shift", "Shift & cash drawer management (cashier must open a shift before billing)"),
    ("feat_qty_popup", "Ask quantity & price when adding an item (off = add 1 instantly)"),
    ("feat_warranty", "Warranty & Serial / IMEI tracking on bills"),
    ("feat_wholesale", "Wholesale / Retail price mode switch on billing screen"),
    ("feat_loyalty", "Loyalty points earn & redeem"),
    ("feat_whatsapp", "1-click WhatsApp digital bill"),
    ("feat_voice", "Talking voice assistant (announces items & totals)"),
    ("feat_dual_lang", "Show second-language item names on screen & receipts"),
    ("feat_autobackup", "Automatic backups every N hours (schedule: Backup & Restore screen)"),
    ("feat_backup_on_exit", "Automatic backup when the program is closed"),
    ("feat_backup_gdrive", "Also copy automatic backups to the Google Drive folder (set on Backup & Restore screen)"),
    ("feat_otp", "Require a one-time code (OTP) before a Factory Reset"),
    ("feat_forgot_pw", "Show 'Forgot password?' on the login screen"),
    ("feat_suppliers", "Suppliers, purchases (GRN) & supplier payables screen"),
    ("feat_vat", "VAT on bills (rate / inclusive-exclusive in Settings 4f) - check the legal rate yourself"),
    ("feat_service_charge", "Service charge on bills (percent in Settings 4f)"),
    ("vat_on_service", "...VAT also applies to the service charge (Exclusive VAT mode only)"),
    ("feat_credit_limit", "Customer credit limit (blocks credit sales above the limit; Admin can override)"),
    ("feat_overdue_reminders", "Overdue credit view + WhatsApp reminders in the Credit Book"),
    ("feat_shortcut_help", "Keyboard-shortcut cheat sheet (F1)"),
    ("feat_labels", "Barcode Labels screen (EAN-13 / Code 39 stickers, label printer or A4 sheet)"),
    ("feat_pole_display", "Customer display window (second screen: items + total)"),
    ("pole_fullscreen", "...customer display starts full-screen (drag it to the second monitor first, then set X/Y in Settings 4g)"),
    ("feat_cloud_sync", "Copy backups to cloud / network folders (Google Drive, OneDrive, Dropbox sync folders...)"),
    ("feat_dashboard", "Owner phone dashboard: uploads a sales SUMMARY (no customer names / phones) to your Cloudflare Worker (setup: Settings 4h)"),
    ("feat_update_check", "Check once a day whether a newer VeloPOS version is announced (needs the update link in Settings)"),
    ("feat_allow_oversell", "Allow selling when stock is zero / not enough (stock goes negative; fix it later with a stock-take)"),
    ("feat_stock_screen", "Stock Control screen (adjustments / damage log / stock-take)"),
    ("feat_batches", "Batch & expiry tracking (FEFO: earliest expiry is sold first) - turn on carefully"),
    ("feat_block_expired", "...refuse to sell expired batches (needs batch tracking)"),
    ("feat_multi_unit", "Multiple units per item (kg/g, dozen/pcs, box...) on the Billing screen"),
    ("feat_categories", "Product categories (Inventory field + quick filter chips)"),
    ("feat_item_grid", "Item grid with pictures on the Billing screen (categories, pages)"),
    ("feat_price_history", "Log every price change + bulk price update tool (Inventory)"),
    ("feat_assistant", "Ask VeloPOS smart assistant (offline chat screen)"),
    ("feat_assistant_fab", "Floating 'Ask VeloPOS' button on every screen (position: Settings 4d)"),
    ("feat_assistant_voice", "Assistant speaks its answers aloud (Windows voice for that language needed)"),
    ("feat_voice_input", "Microphone button in the assistant (ONLINE: audio goes to Google; needs SpeechRecognition + PyAudio)"),
    ("feat_daily_summary", "Daily summary to the owner (WhatsApp link or e-mail)"),
    ("feat_summary_on_close", "...send / offer the daily summary when a shift is closed"),
    ("feat_summary_dayend", "...send / offer the daily summary every day at the time set in Settings 4d"),
]


def connect():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _opening_moves(c):
    """First start with the stock ledger: record every product's current stock as an OPENING move (exactly once)."""
    if c.execute("SELECT 1 FROM settings WHERE key='stock_ledger_ready'").fetchone():
        return
    c.execute("INSERT INTO stock_moves(ts, barcode, qty_change, qty_after, reason, ref, user, note) "
              "SELECT ?, barcode, stock_qty, stock_qty, 'OPENING', '', 'system', 'Opening balance (ledger start)' FROM products WHERE stock_qty != 0",
              (datetime.now().isoformat(timespec="seconds"),))
    c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('stock_ledger_ready', '1')")


@contextmanager
def db():
    c = connect()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


class Settings:
    def __init__(self):
        self._c = {}

    def load(self):
        with db() as c:
            self._c = {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")}

    def get(self, key, default=""):
        return self._c.get(key, DEFAULTS.get(key, default))

    def bool(self, key):
        return str(self.get(key, "0")) == "1"

    def int(self, key, default=0):
        try:
            return int(float(self.get(key, default)))
        except (TypeError, ValueError):
            return default

    def set_many(self, d):
        with db() as c:
            for k, v in d.items():
                c.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                          "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
        self._c.update({k: str(v) for k, v in d.items()})


settings = Settings()


def _ensure_column(c, table, col, decl):
    if col not in [r["name"] for r in c.execute(f"PRAGMA table_info({table})")]:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def init_db():
    with db() as c:
        c.executescript(SCHEMA)
        _ensure_column(c, "sales", "shift_id", "INTEGER")     # added in Phase 2
        _ensure_column(c, "products", "category", "TEXT DEFAULT ''")     # added in Phase 6.1
        c.execute("CREATE INDEX IF NOT EXISTS idx_products_cat ON products(category)")
        for ddl in ("CREATE INDEX IF NOT EXISTS idx_sales_customer ON sales(customer_id)",          # Phase 6.5: keeps reports / credit book fast after years of bills
                    "CREATE INDEX IF NOT EXISTS idx_sales_shift ON sales(shift_id)",
                    "CREATE INDEX IF NOT EXISTS idx_credit_cust ON credit_logs(customer_id)",
                    "CREATE INDEX IF NOT EXISTS idx_returns_inv ON returns(invoice_no)",
                    "CREATE INDEX IF NOT EXISTS idx_retitems_item ON return_items(sale_item_id)",
                    "CREATE INDEX IF NOT EXISTS idx_cashmoves_shift ON cash_moves(shift_id)",
                    "CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date)"):
            c.execute(ddl)
        _ensure_column(c, "products", "base_unit", "TEXT DEFAULT 'pcs'")        # added in Phase 6.2
        _ensure_column(c, "sale_items", "unit", "TEXT DEFAULT ''")
        _ensure_column(c, "sale_items", "factor", "REAL DEFAULT 1")
        _opening_moves(c)
        for tbl, col, ddl in (("sales", "vat_amount", "REAL DEFAULT 0"), ("sales", "service_amount", "REAL DEFAULT 0"), ("sales", "vat_pct", "REAL DEFAULT 0"),
                              ("sales", "service_pct", "REAL DEFAULT 0"), ("sales", "vat_mode", "TEXT DEFAULT ''"),     # added in Phase 6.3
                              ("returns", "vat_adj", "REAL DEFAULT 0"), ("returns", "service_adj", "REAL DEFAULT 0"),
                              ("products", "taxable", "INTEGER DEFAULT 1"), ("customers", "credit_limit", "REAL DEFAULT 0"),
                              ("returns", "credit_offset", "REAL DEFAULT 0"), ("expenses", "shift_id", "INTEGER")):     # added in Phase 6.5
            _ensure_column(c, tbl, col, ddl)
    settings.load()


def audit(user, action, detail=""):
    try:
        with db() as c:
            c.execute("INSERT INTO audit_log(ts, user, action, detail) VALUES(?,?,?,?)",
                      (datetime.now().isoformat(timespec="seconds"), user or "-", action, detail))
    except Exception:
        pass


def backup_db(dest=None, tag="manual"):
    """Consistent online backup using SQLite's backup API (safe while the app is running).
    The copy is switched to journal_mode=DELETE so every backup is ONE self-contained .db file."""
    if dest is None:
        base = os.path.join(p("Backups"), f"velopos_{datetime.now():%Y%m%d_%H%M%S}" +
                            ("" if tag == "manual" else f"_{tag}"))
        dest, n = base + ".db", 1
        while os.path.exists(dest):
            n += 1
            dest = f"{base}_{n}.db"
    src, dst = connect(), sqlite3.connect(dest)
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")
    finally:
        dst.close()
        src.close()
    return dest
