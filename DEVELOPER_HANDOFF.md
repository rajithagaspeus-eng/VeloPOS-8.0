# VeloPOS v6 - developer hand-off (read this first in a NEW chat / for another AI)

Windows desktop POS: Python 3, CustomTkinter UI, SQLite, no server. Owner-operated shop in Sri Lanka (Sinhala/English labels).
Current state: **PHASE 6 IS COMPLETE** (6.1 catalogue, 6.2 stock control, 6.3 buying & money rules, 6.4 hardware & extras) + **6.5 quality pass**. Next step: the owner tests on his real PC and reports problems. Reply to the owner in Sinhala
(technical terms in English); write code and comments in English.

## Hard rules (the owner's, never break)
* NEVER touch `license.py`, `tools/keygen.py`, `_pubkey.py`, `private_key.pem`; never run `keygen init`. Never put secrets in source.
* All money logic inside ONE SQLite transaction with rollback. Business logic lives in `services.py` (headless, no UI).
* Every sensitive action writes `audit_log` (inside the same transaction: use `_audit_c(c, user, action, detail)`).
* Every new feature gets a Settings on/off toggle: `database.DEFAULTS` + `database.FEATURES` (+ safe default: new UI that changes the
  billing workflow ships OFF).
* All colours from `theme.C` tokens (light,dark pairs) so the white theme stays readable.
* Schema changes only via `CREATE TABLE IF NOT EXISTS` / `_ensure_column` in `database.init_db()` so existing data survives upgrades.
* Deliver ONE zip `velopos_v6_phaseN.zip` that extracts over the owner's folder. It must NOT contain `_pubkey.py`, `private_key.pem`,
  `tools/` or any test data. Update README. Tell the owner exactly which pip packages are new (he runs `install_requirements.bat`).
* Be honest about what could not be tested (real GUI, printers, Windows-only APIs).

## Layout
    run.py                      entry point
    velopos/main.py             App shell (login, nav, auto-backup tick, day-end summary tick, floating assistant button)
    velopos/database.py         SCHEMA, Settings kv store (DEFAULTS/FEATURES/PERMS), init_db, audit, backup_db
    velopos/services.py         ALL business logic (sales, returns, shifts, reports, reset/recovery, catalogue). Headless.
    velopos/security.py         PBKDF2, LoginGuard, vault_encrypt/decrypt (machine-bound Fernet)
    velopos/license.py          DO NOT TOUCH
    velopos/backup.py           backup / verify / restore / prune / auto schedule (headless)
    velopos/otp.py              OTP, SMTP e-mail (plain+HTML), wa.me links
    velopos/assistant.py + assistant_i18n.py   offline "Ask VeloPOS" engine, 6 languages, daily summary
    velopos/voice.py            Windows System.Speech output (text via env var), optional online voice input
    velopos/thumbs.py           picture thumbnails: LRU + disk cache + placeholders (headless)
    velopos/printing.py         ESC/POS image printing, GDI fallback, A4/A5 HTML
    velopos/dialogs.py          Forgot-password, Factory-reset, OTP panel
    velopos/screens/            billing, inventory, customers, returns, quotes, shift, expenses, reports, audit, settings, backup,
                                assistant, wizard, itemgrid, categories, pricetools, about   (Screen subclasses; UI only)
    velopos/screens/stock.py    Stock Control screen (adjust + log, stock-take, batches);  screens/units.py: units dialog
    velopos/screens/suppliers.py  Suppliers / Purchases (GRN) / Payables screen
    velopos/barcodes.py, shortcuts.py, updates.py, poledisplay.py   headless modules of 6.4;  screens/labels.py, pole.py, shortcut_sheet.py
    tests/                      test_phase4/5/6_1/6_2/6_3/6_4.py (headless), check_static.py, gui_smoke.py, run_all.py

## How to work (and test) without a display
    python tests/run_all.py                                                         # EVERYTHING in one go (PASS/FAIL summary)
    python -m unittest tests.test_phase4 tests.test_phase5 tests.test_phase6_1 tests.test_phase6_2   # headless logic, temp data folder
    python tests/check_static.py        # undefined names + every app.xxx used by screens exists on App
    python tests/gui_smoke.py           # replaces customtkinter/tkinter with permissive STUBS, builds screens and runs button handlers
Tests set `VELOPOS_HOME` to a temp folder before importing velopos (database.py reads it at import). `tests/test_phase4.fresh()`
resets the DB (creates users `admin`/Admin and `cash`/Cashier). The GUI smoke test catches NameError / wrong signatures, NOT layout.
New UI code must keep widget calls that the stubs allow (they accept any method) and create dialogs as `ctk.CTkToplevel`.

## Conventions worth knowing
* `app` = the App window: `app.s` (Settings: `.get/.bool/.int/.set_many`), `app.user`, `app.can(perm)`, `app.is_admin`, `app.cur`, `app.f(size_delta, weight)`,
  `app.btn(parent, text, colour, command, ...)`, `app.card(parent)`, `app.navigate(key)`, `app.accent`.
* Permissions (cashier): `cperm_stock` (edit inventory), `cperm_see_cost`, `cperm_reports`, `cperm_expenses`, `cperm_returns`, `cperm_discount`. Admin can do all.
  Anything showing cost prices must check `can("see_cost")`; anything with sales/profit totals needs `can("reports")`.
* DB access: `with dbm.db() as c:` (commits on success, rolls back on exception, rows are `sqlite3.Row`). Do not call `dbm.audit()` inside an
  open write transaction (second connection) - use `_audit_c(c, ...)`.
* Backups are verified single-file `.db` copies; `backup.restore` keeps the CURRENT licence rows. A Factory Reset keeps users/licence/settings/audit
  (tables wiped are listed in `services._WIPE` - add new business tables there).
* Money/stock tolerance: compare floats with 0.004-0.005 epsilon; prices are REAL rounded to 2 decimals.
* Low-stock threshold is ONE setting: `services.low_stock_level()` (Settings 4d, default 5).

## Stock rules (Phase 6.2) - READ BEFORE TOUCHING STOCK
* `products.stock_qty` is changed ONLY by `services.apply_stock_move(c, barcode, qty_change, reason, ref, user, batch_id=None, note="")`
  (it also updates the batch when `batch_id` is given, and appends a `stock_moves` row). Everything else goes through it:
  `consume_stock` (remove; FEFO when batch tracking is ON), `restore_stock` (void / return: back into the SAME batches via `sale_item_batches`),
  `_set_stock` (absolute edits from Inventory / CSV import). A test (`test_stock_qty_is_only_written_by_apply_stock_move`) fails if another
  `UPDATE products SET ... stock_qty` appears anywhere. (The `_UPSERT` statement rewrites stock_qty with its CURRENT value only.)
* Reasons: SALE VOID RETURN ADJUST DAMAGE EXPIRED LOST FOUND COUNT EDIT IMPORT RESET PURCHASE OPENING. **Phase 6.3 purchases must use PURCHASE**.
* Ledger check: `verify_stock_ledger()` (sum of moves == stock_qty for every product) must be `[]` after every operation; `repair_stock_ledger()` fixes drift.
  On first start after upgrading, one OPENING move per product with stock is written (guarded by setting `stock_ledger_ready`).
* Batches (`feat_batches`, default OFF): table `batches`; invariant = sum(batch.qty_remaining) <= stock_qty, the difference is "loose" stock with no batch
  (`verify_batches()`). FEFO = earliest expiry first, undated batches last, then loose stock. `feat_block_expired` skips expired batches at sale time.
  **GRN (6.3): call `services._add_batch(c, barcode, batch_no, expiry, qty, cost, user, reason="PURCHASE", ref=grn_no, source="PURCHASE")` inside your own transaction.**
  `enable_batches(user)` runs when the toggle is switched ON in Settings (builds OPENING batches, trims over-full batches). Expiry alerts: `expiry_alert_rows()`
  (batch-aware; used by Inventory status, assistant, daily summary), `product_expiry_map()`.
* Multi-unit (`feat_multi_unit`, default OFF): stock is always in the BASE unit (`products.base_unit`); `product_units(barcode, unit_name, factor_to_base, price_override)`.
  `selling_price` is per base unit; a unit's price = override or base x factor (`unit_price`). A cart line may carry `unit`; `create_sale` re-reads the factor
  from the database (never trusts the client), stores `sale_items.unit/factor`, `qty` in the SOLD unit, `cost_price` per sold unit, `item_name` as `Name [unit]`.
  Returns use `qty * factor` for stock. Quantity limited to 3 decimals when the feature is ON. Reports that sum `sale_items.qty` mix units (known limit).
* Stock-take (`stock_counts`, `stock_count_lines`): one OPEN session at a time; variance = counted - stock AT FINALIZE (documented); `count_warnings()` lists items that moved
  since the session started; finalize is one transaction, admin only in the UI. Adjustments: `adjust_stock()`; log: `stock_log()`, `export_stock_log()`, `write_off_value()`.
* Factory reset: "sales + stock" zeroes stock through RESET moves (ledger kept, batches zeroed, count sessions wiped); "products only" and "everything" also wipe
  the ledger, batches and units (`services._WIPE`).

## Money rules (Phase 6.3)
* **VAT / service charge** (`feat_vat`, `feat_service_charge`, `vat_on_service`, all OFF): `services.compute_bill(lines, discount, redeem)` is the ONE place that decides
  totals (pure function, also `preview_bill(cart, ...)` for the screen). Rules: discount spread over all lines; service = % of the discounted subtotal;
  Exclusive VAT is ADDED (on taxable items only, `products.taxable`), Inclusive VAT is extracted (profit excludes it); rounding per bill to 2 decimals.
  `create_sale` stores `sales.vat_amount/service_amount/vat_pct/service_pct/vat_mode`; returns store `vat_adj/service_adj` (refund = proportional share of the
  bill total incl. tax); `report_data` returns `vat` and `service`. With the features OFF every total equals the pre-6.3 arithmetic (test: `test_everything_off_is_the_old_arithmetic`).
* **Credit limit** (`feat_credit_limit`, OFF): `customers.credit_limit` (0 = none). `create_sale` raises `CreditLimitError` (a ValueError) for a credit sale that would exceed it;
  re-call with `override_user=<admin username>` (audited as CREDIT_LIMIT_OVERRIDE). A cashier gets approval through `approve_with_admin_password()` (persistent 5-try lock).
* **Overdue + reminders** (`feat_overdue_reminders`, OFF): `overdue_customers()` applies payments to the OLDEST credit sales first (FIFO); `create_reminder()` builds the wa.me
  link, writes `reminder_log` and enforces a cool-down (`ReminderCooldown`); template in `reminder_template` ({name} {amount} {days} {shop}).
* **Suppliers / GRN / payables** (`feat_suppliers`): tables suppliers, purchases, purchase_items, supplier_payments. `create_purchase()` is ONE transaction: stock via
  `apply_stock_move(reason='PURCHASE')` or `_add_batch(...)` when batch tracking is ON, product cost by `purchase_cost_policy` ('Last cost' | 'Weighted average', switch off with
  `grn_update_cost`) + price history, optional payment (Cash with a shift id also writes a drawer OUT `cash_moves` row - DOCUMENTED decision; pass shift_id=None for cash that did not come from
  the drawer). `void_purchase()` (admin in the UI) refuses when the stock/batch was already used; payments stay as an advance. Balance = purchases(OK) - payments;
  `payables_ageing()` settles the oldest purchases first. Printable GRN: `printing.grn_doc()` + `open_html`.
* Assistant: intent `payables` (6 languages) + VAT/payables lines in the daily summary. Factory reset: "sales + stock" also wipes purchases/payments/reminders (suppliers kept);
  "everything" wipes suppliers too; "products only" keeps the money records.

## Hardware & extras (Phase 6.4)
* **Keyboard shortcuts**: `shortcuts.REGISTRY` is the ONLY place keys are defined. Global keys (F1 sheet, F2 edit line, F4 hold, F5 pay) are installed by `App.install_shortcuts()`
  (never write `self.bind("<F..>")` in main.py). Widget-local keys (Enter / Down / Esc in Billing, login Enter) are listed with the file that binds them. `tests/test_phase6_4.py`
  scans the source: any special key bound anywhere (except plain Enter / KeyRelease / mouse) that is not in the registry FAILS the test, so the F1 sheet cannot lie. When you add a key: add it to the registry first.
* **Barcodes** (`barcodes.py`, pure Python + Pillow): EAN-13 (check digit, UPC-A = leading 0) and Code 39 encoders with decoders used by the tests (rendered bars are scanned back from the image),
  `render_label` / `render_queue`, `printer_canvas` (centres a label on the printer width), `sheet_html` (A4 grid, labels as embedded PNGs). `printing.print_labels()` sends all labels as ONE raster job
  through the existing ESC/POS / Windows-driver path. TSPL / ZPL label printers are NOT driven natively (documented in the UI and README).
* **Customer display** (`feat_pole_display`, OFF): `poledisplay.DisplayModel` (headless) is fed by `App.pole_update(cart)` from the Billing `refresh()` and `App.pole_thanks()` after payment;
  the window (`screens/pole.py`) only polls snapshots. Every App-side hook swallows errors - the display can never break or slow down billing.
* **Cloud backups** (`feat_cloud_sync`, OFF): `backup.cloud_targets()` (folders separated by `|` + the older Google Drive folder), `copy_verified()` (SHA-256), table `cloud_queue` (retry queue,
  retried every minute by `App._auto_tick`), `process_queue()`, `cloud_status()`, `list_cloud_backups()`; restore from a cloud copy uses the normal `restore()`. NO login / OAuth is stored; a real
  Google Drive API upload is deliberately not implemented.
* **Update checker** (`feat_update_check`, OFF, `updates.py`): HTTPS only (redirects to http refused), 6 s timeout, 64 KB limit, strict JSON validation, semantic compare, at most once a day,
  background thread, silent when offline. It only tells the owner and opens the download link on request - a test fails if the module ever contains download/install/exec code.

## Phase history
* **6.5 (done, QA pass)**: `services.num()` (rejects nan/inf) is THE way to parse any typed number - screens pass raw text to services. `create_sale` / `create_return` / `void_sale` validated;
  credit-sale cash refunds offset the debt first (`returns.credit_offset`); `delete_product` closes the ledger and removes batches / units; expenses (`add_expense` / `delete_expense`, `expenses.shift_id`),
  customers (`add/update/delete_customer`) and staff (`save_user` / `delete_user`) moved from the screens into `services.py`; login lock persists (`login_*`); `_next_no()` numbering; `csv_safe()`.
* 1-3 foundation, billing, shifts, returns, quotes, reports, printing, licence.   * 4 backup/restore, factory reset, OTP, forgot password, wizard.
* 5 offline assistant (6 languages), voice, daily summary.
* **6.4 (done)**: shortcut registry + F1 sheet, barcode labels (EAN-13 / Code 39, printer + A4 sheet), customer display, cloud backup folders with verified copies and retry queue, update checker.
* **6.3 (done)**: VAT / service charge, credit limit, overdue reminders, suppliers, GRN, supplier payments & ageing, assistant payables.
* **6.2 (done)**: stock ledger + the single stock writer, adjustments / damage log (CSV export), stock-take, batches with FEFO, multi-unit, `tests/run_all.py`.
* **6.1 (done)**: categories (+ chips in Inventory and the Billing item grid), item grid with picture cards/pages/thumbnail cache,
  product pictures (Inventory -> Picture), price history, bulk price update (preview -> one-transaction apply), product save/import/delete moved
  from the Inventory screen into `services.py` (`save_product`, `import_products`, `delete_product`), `services.list_products` (pagination, category, text).

## Known limits / not testable here
Real GUI layout and colours (Stock Control, Suppliers, Labels, Credit Book additions, Billing quantity dialog with units); printers (ESC/POS, GDI Sinhala fallback, "Windows driver" mode, label printing and whether a label printer feeds/cuts correctly); a second monitor for the customer display; real cloud-sync folders; Windows System.Speech voices; microphone;
Gmail SMTP; Arabic RTL shaping in Tk; floating-button overlap on the Billing screen. The owner tests these and sends screenshots/tracebacks.

## Starting the next part in a new chat
Attach the latest zip, paste the owner's standard project prompt (rules above), and say: "Do Phase 6.N exactly as planned in
DEVELOPER_HANDOFF.md: list your changes first, write headless tests, run check_static.py and gui_smoke.py, give me one zip."
