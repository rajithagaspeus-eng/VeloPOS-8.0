# VeloPOS v6.5 + Phase 7.1 (owner phone dashboard)

## Run
    pip install -r requirements.txt
    python tools/keygen.py init        # ONCE, on YOUR PC only -> private_key.pem + velopos/_pubkey.py
    python run.py

## Sell a license
    python tools/keygen.py issue POS-XXXX-XXXX-XXXX --customer "Shop name"
Send the printed key to the customer. It only works on that one machine.

## Never ship to customers
tools/ folder (keygen.py, private_key.pem, issued_licenses.csv). Back up private_key.pem offline.

## Build the .exe (harder to patch than PyInstaller)
    pip install nuitka
    python -m nuitka --standalone --onefile --windows-disable-console --enable-plugin=tk-inter --include-package=velopos run.py
(Build from a folder that does NOT contain tools/private_key.pem.)

## Data location
%LOCALAPPDATA%\VeloPOS  (database, receipts, backups). The old pos_database.db is not touched.

## Phase 2 (this version)
Shifts & cash drawer (Z-Report), Returns & Refunds (credit notes), Void bill (Admin), Reports with charts,
Expenses (optionally paid from drawer), Audit Log, Cashier permission matrix (Settings -> 4b).
Upgrading from Phase 1: extract over the old folder and choose "Replace". Your data, velopos/_pubkey.py and
tools/private_key.pem are NOT in the zip, so they stay untouched. Do NOT run `keygen.py init` again.

## Phase 3 (this version): Printing
Settings -> 3b: choose Printer brand (Xprinter / Epson / Other ESC/POS), Connection (Windows RAW, Windows driver,
LAN IP, COM/Bluetooth), paper size, and the CASH DRAWER switch (off by default). Use "Width calibration" once.
Windows needs:  pip install pywin32   (already in requirements.txt)

## Phase 4 (this version): Safety & recovery
**No new pip packages** (cryptography is already in requirements.txt; e-mail uses Python's built-in smtplib).

* **Backup & Restore** (left menu, Admin): list, verify, restore (safety backup of the current data first, then a
  safe file swap, then the app restarts), "Backup to USB / folder", restore from any .db file, delete.
  Automatic backups: every N hours + when the program is closed, keep the last N, optional copy into a Google
  Drive for Desktop folder. Manual / USB / safety backups are never deleted automatically.
  Restoring always keeps the CURRENT licence.
* **Factory Reset** (Settings -> 6): Admin password -> one-time code (Email OTP, WhatsApp link, or Recovery Code)
  -> type RESET -> automatic backup -> wipe (Sales+stock / Products only / Everything) -> restart.
  Users, licence, settings and the audit log are always kept.
* **Forgot password** (login screen): Admin accounts, using the Recovery Code or an e-mailed code.
  5 wrong codes lock this for 15 minutes (the lock survives restarting the program).
* **E-mail codes** (Settings -> 4c): your own Gmail + a Google *App Password* (needs 2-Step Verification).
  Stored encrypted with a key derived from this PC's Machine ID. WhatsApp codes are only a wa.me link opened on this PC -
  a convenience, not strong security. OTP = 6 digits, 5 minutes, 3 attempts.
* **Setup Wizard** after the first-run Admin creation (shop, bank, printer test, owner contact, features);
  re-open it from Settings -> 4c. Existing installs never see it automatically.
* **Printing fixes** (4b adds: logo's empty border auto-cropped, top margin 1mm -> 0.4mm, hyphens drawn as solid bars,
  bottom feed default 0): bottom feed is now a setting (was a fixed 4 lines; 0 = tightest, minimum 4 when auto-cut is off) and the bottom padding is smaller;
  "Shift content LEFT" (use 16 if your left gap is wider than your right gap); "Print darkness" (default 190, was 165)
  so thin strokes such as '-' survive; long bills are measured before drawing, so they are never cut off;
  the Windows GDI text path caches bitmaps and releases GDI handles.

### Tests (developer)
    python -m unittest tests.test_phase4 -v      # headless logic tests (temp folder, never your real data)
    python tests/check_static.py                 # undefined names + app.xxx attributes
    python tests/gui_smoke.py                    # GUI handlers against stub widgets (no display needed)

## Phase 5 (this version): Smart assistant (OFFLINE)
**No new REQUIRED pip packages.** Optional, only for the microphone button:  `pip install -r requirements-voice-input.txt`
(SpeechRecognition + PyAudio - PyAudio can be awkward to install on some Python versions, which is why it is NOT in requirements.txt).

* **Ask VeloPOS** (left menu, everyone) + optional floating button (Settings -> toggles; position in 4d).
  Answers from your own database, no internet, no API: today/yesterday/7-day/month sales and profit, stock of an item
  (fuzzy: typos, local names, keywords, barcode), low stock, top sellers, who owes most credit, expenses, expiry,
  shift status, daily summary, and "how do I ..." help (bill, item, return, void, shift, backup, printer, credit,
  passwords, expenses). Every user only gets what their permissions allow (profit/sales need *View reports*, expenses need *Expenses*).
* **Languages**: English, Sinhala, Tamil, Hindi, Arabic, Spanish. Any language (and Singlish) is understood in a question;
  the answer language is chosen in the chat window / Settings 4d ("Auto" answers in the language you wrote in).
  The translations were written by the developer assistant, not a professional translator - please have them checked.
* **Voice output** (toggle): Windows System.Speech, text passed through an environment variable. Only speaks a language if a
  Windows voice for it is installed (Settings 4d -> *Check installed voices*). **Voice input** is optional and ONLINE (Google).
* **Daily summary**: text + HTML; send to the owner by WhatsApp link (owner presses Send) or by e-mail (needs Settings 4c);
  on shift close and/or every day at a set time (toggles + time in 4d). Chat command: "daily summary".
* **Low-stock level** is now one setting (Settings 4d, default 5) used by Inventory, Insights and the assistant.

### Tests (developer)
    python -m unittest tests.test_phase4 tests.test_phase5 -v
    python tests/check_static.py
    python tests/gui_smoke.py

## Phase 6.1 (this version): Catalogue
**No new pip packages.** Phase 6 is delivered in four parts (6.1 catalogue, 6.2 stock control, 6.3 buying & money rules, 6.4 hardware & extras);
see `DEVELOPER_HANDOFF.md` for the plan and the project rules.

* **Product categories** (Settings toggle): Category box in Inventory (typing a new name creates it), quick filter chips with counts above the
  inventory table, **Categories** button (add / rename / delete / reorder; deleting never deletes products; renaming moves its products).
  CSV import accepts an optional 11th column `category` (old 10-column files still work; a blank category keeps the current one).
* **Item grid on the Billing screen** (Settings toggle, OFF by default, or the *Item grid* button on Billing): picture cards, category chips, search,
  pages (items per page / columns: Settings 4e). Click a card = add to the bill. Pictures: Inventory -> *Picture -> Choose...* (shrunk to 640 px).
  Thumbnails are cached in memory and on disk (`ProductImages/.thumbs`), so big photos do not slow the grid; items without a picture get a coloured
  initials tile.
* **Price history + bulk price update** (Settings toggle): every price change (Inventory save, CSV import, bulk update) is recorded with who/when/why;
  *Price history* button per item; *Bulk price* button: choose scope (all / one category / selected rows), retail / wholesale / cost (cost needs the
  "see cost" permission), % / amount / exact price, rounding, **Preview**, then APPLY (one transaction; refused if a price changed after the preview).
* Product save / CSV import / delete now live in `services.py` (headless-tested); negative prices and negative stock are rejected.
* Factory Reset knows the new tables (categories are kept by "products only"; price history is wiped with products).

### Tests (developer)
    python -m unittest tests.test_phase4 tests.test_phase5 tests.test_phase6_1
    python tests/check_static.py
    python tests/gui_smoke.py

## Phase 6.2 (this version): Stock control
**No new pip packages.** Existing data is upgraded automatically on first start (an opening balance is written to the new stock ledger).

* **Stock ledger**: every stock change (sale, void, return, Inventory edit, CSV import, adjustment, stock-take, factory reset) is recorded in `stock_moves`
  through ONE function, so stock can always be explained. Nothing changes in how sales/returns/voids look or add up.
* **Stock Control screen** (Settings toggle, left menu): *Adjustments & log* - damage / expired / lost / own use / found / correction (stock can never go below zero),
  filterable log with CSV export and write-off value (cost needs the "see cost" permission). *Stock-take* - count sessions (all products or one category),
  barcode-scan entry or CSV import, variance report, **Finalize** (admin) corrects stock in one transaction; a warning lists items that moved during the count.
  *Batches* tab (when batch tracking is ON).
* **Batch & expiry tracking** (Settings toggle, OFF by default): sales take the earliest-expiry batch first (FEFO); void/return put stock back in the same batches;
  optional "refuse to sell expired batches"; expiry alerts (Inventory, assistant, daily summary) use batch dates. Switching it ON builds one opening batch per item
  from its current stock and expiry date.
* **Multiple units** (Settings toggle, OFF by default): Inventory -> *Units* (e.g. base kg + g = 0.001, base pcs + dozen = 12, optional fixed price). On the Billing quantity
  dialog choose the unit; stock is kept in the base unit; the bill, receipt and history show `Item [unit]`.
* `python tests/run_all.py` runs every test file, the static check and the GUI smoke test and prints a PASS/FAIL summary.

### Tests (developer)
    python tests/run_all.py

## Phase 6.3 (this version): Buying & money rules
**No new pip packages.** Everything that changes billing is OFF by default; with it OFF every bill adds up exactly as before.

* **VAT / service charge** (Settings toggles + 4f): Exclusive (added) or Inclusive (extracted); per-item "Taxable" flag in Inventory; shown on thermal receipts, A4/A5 invoices, Reports and the
  daily summary; returns reverse tax in proportion. YOU must set the legal VAT rate and registration number - the default 18 is only a starting value.
* **Customer credit limit**: set it in the Credit Book (Admin); a credit sale above the limit is refused with a clear message; an Admin (or a cashier with an Admin's password) can approve it, and it is audited.
* **Overdue view + WhatsApp reminders** (Credit Book): payments settle the oldest credit first; *Overdue only* filter; *Remind via WhatsApp* opens a pre-filled chat (you press Send); a cool-down
  stops the same customer being nagged daily; message template in Settings 4f.
* **Suppliers & Purchases** (left menu): suppliers, GRN (stock + batches + cost update + price history in one transaction, optional payment, printable), Void (Admin), Payables with ageing and
  supplier payments (cash from the drawer is recorded as a cash-out of the open shift).
* Ask VeloPOS: "who do I owe?" (6 languages); daily summary shows payables and VAT.

### Tests (developer)
    python tests/run_all.py

## Phase 6.5 (this version): quality pass - bug fixes found by a full QA review
No new features, no new pip packages. Nothing in your data changes (two small columns and a few speed indexes are added automatically).

* **Bad numbers can no longer get in.** `nan`, `inf`, negative prices, zero / negative quantities, a discount bigger than the bill, redeeming more points than the bill,
  an unknown payment method or a closed shift are refused with a clear message - in the screens AND in the service layer.
* **Returning a CREDIT bill for cash** now takes the unpaid part off the customer's debt first; only the rest is paid from the drawer (the credit note shows both parts).
* **Void is refused** when the customer has already paid back part of that credit (it used to silently swallow their payment). Use Returns & Refunds.
* **Delete product + add the same barcode again** no longer revives the old batches / units or breaks the stock ledger.
* **Expenses** are saved in one transaction with the drawer cash-out; deleting an expense puts the cash back (open shift) and the audit line records the amount.
* **Customers**: Edit and Delete buttons, phone numbers are checked and `077 123 4567` / `0771234567` / `+94771234567` count as the same number.
* **Staff accounts**: the last Admin can no longer be demoted by mistake; nobody can change their own role; new usernames / passwords are checked.
* **Login lock-out** (5 wrong passwords = 60 s) now survives closing the program.
* **Invoice / return / quotation / GRN numbers** keep counting correctly after 9999 in one day.
* **Reports**: "Top sellers" and "Dead stock" ignore voided bills; the reorder heading shows your real low-stock level.
* **CSV import** refuses barcodes that Excel damaged (`8.90123E+12`); **CSV exports** are safe against spreadsheet formulas.

## Phase 6.4: Hardware & extras
**No new pip packages** (barcodes are drawn with Pillow; the update check uses Python's own urllib).

* **Keyboard shortcuts**: press **F1** (or About -> *Keyboard shortcuts*) for the cheat sheet; it is generated from the same list that installs the keys, so it is always correct. F2 edit line, F4 hold bill, F5 pay.
* **Barcode Labels** (left menu): pick items (search / category), copies (or = stock), label size in mm and DPI, EAN-13 or Code 39 (Auto picks by the item's barcode), live preview. Print on a receipt/label
  printer that accepts images (same path as receipts, one job) or open an **A4 sheet** (columns x rows, margins) and print it from the browser at 100 %. Printers that only understand TSPL / ZPL are NOT supported.
* **Customer display** (Settings toggle, OFF): a second window with the current bill, the total and a thank-you after payment; idle message and shop name otherwise. Settings 4g: position X/Y, size, font, full-screen.
* **Cloud / network backup folders** (Backup & Restore screen): copy every automatic backup to several folders (Google Drive for desktop / OneDrive / Dropbox sync folders or a network share), each copy verified with
  SHA-256; an offline folder puts the copy in a retry queue (retried every minute); status line; *Cloud backups / restore...* lists and restores from a cloud folder. No login is stored; a real Google Drive API upload
  needs OAuth secrets and is not implemented.
* **Update checker** (Settings toggle, OFF; Settings 4g update link): you host a small `version.json` -> `{"version": "6.5.0", "notes": "...", "download": "https://..."}`; VeloPOS checks at most once a day over HTTPS,
  tells you, and opens the download page only when you agree. It never downloads or installs anything.

### Tests (developer)
    python tests/run_all.py


## Phase 7.1: Owner phone dashboard (optional add-on)
Settings -> 4h + feature switch "Owner phone dashboard". The POS uploads a small sales SUMMARY (today, last 30 days, top items, low stock,
total credit owed - never customer names/phones, bills or cost prices) to YOUR Cloudflare Worker; the owner opens a private link on the phone.
Billing never waits for the internet. Deploy guide for you (the developer): `cloud/README_CLOUD.txt`. Do NOT ship the `cloud/` folder to customers
(`installer/build_windows.bat` already leaves it out). No new pip packages. Tests: `tests/test_phase7_1.py` (end-to-end against the real worker.js, needs Node 22+).

## Phase 7.2: support code, online trial registry
* **Support code** (Forgot password -> "Support code"): challenge-response so YOU can reset an Admin password remotely when the Recovery Code is lost.
  `python tools/support_code.py <MACHINE-ID> <CHALLENGE>` (needs tools/private_key.pem). One-time, one PC, 30 minutes. See installer/README_INSTALLER.txt.
* **Online trial registry**: set `TRIAL_SERVER_URL` in velopos/branding.py (same Worker as the dashboard) so deleting local files no longer restarts the trial.
* Factory Reset now offers the Recovery Code first (Gmail is not needed).


## Review fixes (on top of 7.2)
* **Version numbers** are now 7.2.0 everywhere (app, About screen, installer, build script).
* **Removed `velopos/ownerview.py`** - an old, incompatible dashboard client that was never used (`cloudsync.py` is the real one).
* **Sell when stock is 0** (Settings -> feature list, OFF by default): "Allow selling when stock is zero / not enough". Stock then goes negative and is corrected by a stock-take.
* **Receipt adds up**: the subtotal is the sum of the rounded lines (3 x 0.335 no longer shows 1.02 lines but a 1.01 subtotal).
* **Credit sale with more cash than the bill**: only the bill amount is recorded, so the Z-report no longer shows a false shortage.
* **Loyalty points** are earned on the amount actually paid (not on unpaid credit); void reverses exactly that.
* **Customer phone number is optional** (a typed number is still validated; duplicates still refused).
* **Licence is re-checked at every login**, so a trial that ends while the program stays open blocks the next login.
* `branding.py`: `DEFAULT_DASH_URL` / `DEFAULT_UPDATE_URL` pre-fill the Settings boxes for customers. **Set `TRIAL_SERVER_URL`, `DEFAULT_DASH_URL`, `DEFAULT_UPDATE_URL` before you build.**
* New tests: `tests/test_phase7_3.py`.
* **`tools/VeloPOS_Admin.bat` + `tools/velopos_admin.py`** (developer only): a small window to make dashboard invite codes (no curl needed) and to issue licence keys through your own `tools/keygen.py`. Copy both files into your real tools folder (next to keygen.py). Never ship them.
* `installer/build_windows.bat` is now a one-click build: checks Python, installs Nuitka, asks for the old folder to copy `_pubkey.py` from, builds, makes the installer. `WHAT_TO_DO_SI.txt` = 3-step cheat sheet in Sinhala.
* **User-Agent fix**: web requests now say `VeloPOS/<version>` instead of `Python-urllib/3.x` (Cloudflare answers 403 to the Python default, which broke the dashboard upload and the online trial check). `velopos/netua.py` does it for every urllib call without touching licence.py.
* `cloud/wrangler.toml` already contains the owner's D1 database id.
* **Your own QR pictures and logo** (`qr_codes/`, `branding/`, next to run.py - read the README.txt inside each): the Activate screen tabs (Card / Bank / Binance / WhatsApp) and the About screen show your pictures; `dev_logo.png` replaces the text title on Login / About / Activate / Setup; `app_icon.ico` is the window + taskbar + .exe icon. A missing picture = the old text QR / text title. `build_windows.bat` now packs both folders into the .exe folder. Code: `velopos/assets.py`.
* Fixed an undefined button colour name (`indigo`) that could break the About and Inventory screens.
