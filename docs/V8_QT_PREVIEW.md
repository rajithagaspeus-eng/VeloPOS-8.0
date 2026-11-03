# VeloPOS 8.0 — Experimental Combined UI Preview (Batch 01)

**Not a commercial release.** This is an isolated proof of concept, not a replacement for `run.py`. Billing Checkout and live product edits are intentionally unavailable.

## What is implemented

- A new standalone PySide6 window with left navigation, light/dark styles and lazily built pages.
- **Inventory**: read-only searchable product catalogue (up to 100 rows per query), using parameterized SQL over the existing SQLite products table in the dedicated preview database.
- **Billing draft**: search catalogue, add/remove items, clear cart, view subtotal and a read-only estimate from the existing `services.preview_bill` (only for the isolated preview database). No checkout, payment processing, receipt printing or stock mutation.
- **Customers and Suppliers**: separate localized, searchable, read-only tables with credit balance and supplier active status. Fictional demo records are seeded into empty preview-only tables.
- Five sample products are inserted only if the dedicated preview inventory is empty. Existing preview products are retained.
- An isolated **Dashboard placeholder** (no fabricated sales data) and live **English / Sinhala / Tamil** text switcher. Language choice applies to preview UI only; the chosen language is now preserved across launches using Qt QSettings under a separate **VeloPOS8Preview** application identity.
- Existing Settings values and technical combo-box option values remain in English; **full localization is not yet implemented**. Preview language persistence does not modify the production VeloPOS database.
- Functional **Shop profile**, **Appearance**, and **Printer & Receipts** settings forms backed by the existing `velopos.database.Settings` API.
- Printer page is lazily constructed with existing configuration values; **no printer enumeration, test print, connection attempt or device I/O** occurs in this preview.
- Each Settings page saves only its own fields, reducing accidental overwrites of unsaved changes on other pages.
- Input validation and a whitelist that excludes secrets and license-related settings.
- Existing UI, `run.py`, licensing, billing, stock and schema untouched.
- The preview launcher now stores a **persistent test-only database** under `%LOCALAPPDATA%\\VeloPOS8PreviewData\\velopos.db` (or the user's home directory if LOCALAPPDATA is absent). It forces `VELOPOS_HOME` to this location *before importing the database*. It never uses `%LOCALAPPDATA%\\VeloPOS\\velopos.db`. Preview settings, including printer paper size, now survive closing and reopening. Data from older temporary previews cannot be recovered.
- No printer discovery on UI startup.

## Run on Windows

Open the project in VS Code on `develop-v8`; activate the Python environment that has PySide6 installed.

```powershell
git pull origin develop-v8
python -m pip install -r requirements.txt
python -m pip install PySide6
python run_v8_preview.py
```

If your `.venv` is one directory higher than the cloned repo:

```powershell
& "$HOME\VeloPOS8\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& "$HOME\VeloPOS8\.venv\Scripts\python.exe" run_v8_preview.py
```

**Safety:** Do not use the existing `run.py` for this preview. Do not test against a real customer database. No license keys need to be generated; never run `tools/keygen.py init` as part of this preview.

## Unit tests

```powershell
python -m unittest tests.test_v8_settings_model tests.test_v8_i18n tests.test_v8_preview_storage tests.test_v8_batch01 tests.test_v8_batch02_directories tests.test_v8_batch03_inventory tests.test_v8_batch04_directories tests.test_v8_batch05_billing tests.test_v8_batch05_engine tests.test_v8_batch06_dashboard tests.test_v8_batch07_auth tests.test_v8_batch07_license tests.test_v8_qt_ui -v
```

These include headless model and isolated offscreen Qt smoke tests. A successful run is **not** evidence that the full Windows GUI, live POS, or hardware works.

## Manual acceptance checklist (Windows)

1. Launch and verify Dashboard opens without a blank screen or flicker. Visit Inventory and verify sample products appear.
2. Switch between Dashboard, Inventory, Billing draft, Customers, Suppliers, Shop profile, Appearance, Printer & receipts, and About repeatedly; observe render time.
3. Switch the top language selector between **English**, **සිංහල** and **தமிழ்**; verify navigation, field labels and messages update immediately and text renders without boxes or clipping. Close and relaunch the preview: the selected language should persist.
4. Search Rice in Inventory. Open Billing draft, select Sample Rice and Add selected; confirm subtotal and estimated payable. Remove or Clear Cart. **Checkout does not exist by design.**
5. Browse Customers and Suppliers; search fictional demo records; switch Sinhala and Tamil. These tables cannot edit data.
5. Change a test shop name and Save; see a translated confirmation.
6. Switch to Appearance, choose dark/light, Save and verify theme changes.
7. Open Printer & receipts, edit paper size, brand, mode, copies and footer, then Save. This must **not** attempt to connect to or enumerate a real printer.
8. Change paper size to A5 and Save, close the window, reopen and confirm **A5 remains selected**. Verify shop name and language preferences also persist as expected.
9. Confirm the existing production VeloPOS database and old desktop application are unaffected. A separate test database must exist under `%LOCALAPPDATA%\\VeloPOS8PreviewData`.

## Pending before VeloPOS 8 can be released

- Validate Windows scroll and repaint behavior on actual target PCs.
- Implement all settings pages, complete internationalization including localized option labels, and integrated application language settings, together with security/role guard in the eventual integrated app.
- Build Qt adapters for billing, inventory, reports and printer integration.
- Full regression and migration tests, packaging, licensing audits, code-signing decision and country-specific regulatory checks.
- Audit dependency obligations, including PySide6/Qt's commercial redistribution requirements.

This code is not ready for live shop use. Never merge this experimental UI directly into stable `main` without a reviewed integration plan.

## Status

The preview has been committed to GitHub. **Unit and GUI tests have not been executed in this editing session**; run the commands above on Windows before treating it as validated. The user's subsequent screenshot showed Sinhala navigation and dashboard labels rendered on Windows, and they reported **14/14 preview tests passing** before this language persistence change. Re-run the tests and the Windows preview after updating.

## Recent Phase 1 change

The Printer & Receipts page is a limited configuration preview only. Supported fields: printer brand, connection mode, paper size, receipt copies (1–5), and receipt footer (up to 250 characters). The actual Windows printer selector, hardware test, full receipt functionality, and roles/permissions are **not yet migrated**. The added tests have not been executed in this session; run them on Windows before assessing readiness.

## Preview persistence fix

Previously, the preview database lived in a temporary directory removed on exit; therefore printer paper-size changes disappeared on restart, while the language setting persisted in Qt QSettings. The updated launcher now persists **only test data** in a dedicated `VeloPOS8PreviewData` directory. It does not migrate real shop data or modify the existing app. Before the first launch after this fix, the preview starts with default shop/printer values because earlier temporary data was deleted automatically.

**Never copy a live-shop database into the preview directory.** If you want a clean preview reset, close the preview and manually delete only the dedicated `VeloPOS8PreviewData` directory after verifying its exact path. Do not delete the standard `VeloPOS` data directory.

## Batch 01 — scope boundary

This batch delivers preview foundations **only**, not full Billing/Inventory migration. A real checkout must use the existing transactional service and must be built with customer authorization, stock/expiry/discount/VAT verification, shift requirements, rollback and recovery tests before any production enablement. Inventory remains read-only, and cart subtotals are preliminary, not tax-inclusive invoices. Sample product data is demo-only and cannot be used for real business operations.

## Batch 02 — customer, supplier and safe billing bridge

- Customer and supplier screens use bounded parameterized read-only SQL against the separate preview DB. No real contacts are imported.
- Only the existing read-only `services.preview_bill` is called from Billing Draft, not `create_sale`. Actual stock movement, checkout and payments remain disabled.
- Qt GUI and headless tests were added, but **new tests have not yet been run** during this editing session. Run the combined test command once on Windows.

## Batch 03 — Modern interface and preview-only inventory

The UI now has refreshed dark/light styles and a prominent TEST MODE indicator. A product Add/Edit dialog uses the existing VeloPOS stock service, but only for the isolated preview database. Stock is the new total quantity (not an increment). Production checkout remains unavailable.

New inventory regression tests cover stock ledger records, audit logs, validation and refusal of production-like storage. The tests are committed but still require execution in the developer's Windows environment.

## Batch 04 — guarded customer and supplier editing

Customer and supplier directories now provide **Add new** and **Edit selected** buttons in the dedicated preview environment. The forms reuse the original validated and audited `services.add_customer`, `update_customer`, `add_supplier` and `update_supplier` workflows. Customer credit balances and loyalty balances are never directly edited, and supplier payment workflows are not available. Invalid phone numbers and supplier duplicate names remain guarded by the original business services.

The adapter checks the canonical preview database path before every operation and never enables editing on the production POS database. No commercial login or role-based security is implemented in this preview, so these actions must not be enabled for real shop use.

Run the combined command above once after pulling `develop-v8`. New tests have not yet been executed in the user's Windows environment.

## Batch 05 — modern billing draft, no checkout

The isolated Qt **Billing draft** now has a barcode-first search field, Enter-to-add for exact barcode or a unique result, F2 to focus search, F3 to focus the draft quantity field, double-click-to-add product results, and editable positive cart quantities. Ambiguous searches cannot auto-add an arbitrary item. Product and cart tables expand product names; hover reveals full cell text. A clearly separated totals panel presents rounded draft subtotals and the existing engine's **read-only** estimated payable amount when available.

All changes are **in-memory draft state**. No checkout, payment, receipt, invoice, stock deduction, or customer credit operation is accessible. For tax/service charge estimates the preview uses the original `services.preview_bill` only against test data. Updated models reject negative/zero, overlarge and nonfinite quantities. Tests in `tests/test_v8_batch05_billing.py` and offscreen Qt smoke cases verify model rules and scanner workflow.

Run the single combined command above. The new Batch 05 tests have been committed, but **not yet executed on the user's Windows machine**.

## Batch 06 — Premium overview dashboard (preview-only)

The Dashboard now displays **four verified counts from isolated preview storage**: product catalogue size, customer count, active suppliers and products with stock **5 or below**. A separate low-stock panel shows up to six products with actual demo stock balances. It has an Inventory shortcut and a Refresh button. Counts automatically refresh when the Dashboard is opened again. This is a lightweight four-count query plus a bounded six-row alert query; it makes no network or hardware calls.

All totals are **test-only operational counts, not real business reports**. No actual sales, revenue, profit or payment KPI is fabricated. When no database is supplied, cards show an em dash rather than invented values. The dashboard rejects the production data directory before reading, and it does not write to products, customers, suppliers or stock. Three languages and two-column cards support narrower Windows screens.

Run the combined test command above. Tests include isolated SQLite model checks, no-write assertions, refresh behavior, a production path guard and offscreen Qt KPI/navigation/translation tests. This batch is committed but its new tests have **not yet been run in the user's Windows environment**.

## Batch 07 — authentication and commercial security foundations

Commercial security requirements are now tracked in [V8_SECURITY_TRIAL_RECOVERY.md](V8_SECURITY_TRIAL_RECOVERY.md). This includes resisting license tampering, preventing trivial trial resets after reinstall, and verified-email forgotten-password recovery (not yet implemented). These items are mandatory release checks, **not completed claims**.

A preview-only `PreviewAuthenticator` verifies **already-existing** user credentials with the original PBKDF2 verifier and persistent per-user lockout logic. It returns a narrow, immutable role identity. There is no preset production login, no email dispatch, no checkout authorization and no ability to mutate a user's license or trial. UI login and write-action session enforcement remain future implementation work.

Additional tests use isolated subprocess databases for successful Admin/Cashier logins, bad credentials, persistent lockouts and production-folder refusal. Ed25519 license test signatures are generated using ephemeral in-memory keys without creating or replacing any genuine license signing key.

**Important audit:** the current offline trial HMAC is derived from public device information and does not prevent a knowledgeable local user from rewriting their own files. The existing remote first-seen Worker integration is a useful building block but must be independently deployed/audited. Email recovery requires a previously verified address, trusted email backend and expiring single-use token verification before any password update.

Run the single combined test command above once. The new Batch 07 tests are committed but not yet executed in the user's Windows environment.

### Batch 07 addendum — Preview sign-in and Admin setup

The preview top bar includes Sign in for the isolated demo database. An empty demo users table triggers first-run setup, where the developer chooses a new Admin username and password of 12+ characters. No shared password is created. Later logins use existing PBKDF2 password checks and persistent lockout. Sign out clears the Qt identity.

Inventory/Customer/Supplier Add/Edit controls are visible only to an Admin identity. **This is a preview UI gate only, NOT a production authorization boundary.** Legacy service APIs do not yet uniformly require an authenticated Qt session, so actual checkout and commercial write access remain disabled. The real release must check service permissions independent of UI visibility.

The global product feature scope is recorded in [V8_MASTER_ROADMAP.md](V8_MASTER_ROADMAP.md). It includes advanced dashboards, stock, billing, multi-branch, local-first BI, optional cloud sync, phone owner dashboard, loyalty, P&L, staff security, online/offline commercial licensing, trial continuity and verified-email recovery. These are roadmap requirements, not promises of completed features.

## Fast combined validation — one command

Close the Windows preview window, then from the project root run:

```powershell
python run_v8_checks.py
```

The runner discovers every `tests/test_v8_*.py` test automatically, including new batches, prints one compact pass/fail summary and fails if tests are skipped. Use `python run_v8_checks.py --verbose` to investigate failures. It runs offscreen PySide6 tests without opening a desktop GUI; separate live Windows rendering/hardware acceptance is still required at milestones. If dependencies are missing, install the project's requirements and PySide6 in the project's virtual environment; the script does not install packages or access production storage.

To update the branch and test in one paste:

```powershell
git pull origin develop-v8
python run_v8_checks.py
```

The additional `test_v8_batch07_trial.py` suite covers the existing trial decision logic with **mocked server first-seen**, local clock rollback and corrupted-store cases; no real server call, registry mutation, license signing or private key use occurs. It is **not** proof against deliberate offline trial reset or piracy.

## Phase 1 — bigger-batch delivery: financial reports & staff activity foundation

The Qt navigation now has an **Admin-only Reports & activity** preview at the end of the sidebar. The screen accepts a strict date range and reads the existing `sales` and `expenses` tables plus recent (metadata-only) `audit_log` entries. It displays recorded successful-sale counts, recorded sales totals, the existing sale profit field, expenses and an **indicative** net figure, alongside up to 30 invoices and 30 staff activity records. On logout/non-Admin view the screen clears its data; staff audit details are never displayed in the table. All queries are bounded/parameterized and only run against the dedicated preview DB.

**Accuracy warning:** these are preview operational summaries, **not production-ready P&L or tax accounting**. Return/void reconciliation, discounts, partial credit, VAT, adjustments, cost valuation, purchase liabilities, branch reconciliation and accounting-period close require verification before launch. The old transaction engine and production data were not modified. No checkout or payment workflow was enabled.

A new `tests/test_v8_phase1_reports.py` file tests schema integration, date parsing, void exclusion, totals, metadata privacy and production guard. The existing Qt tests cover Admin gating, sign-out clearing and Sinhala labels. Run `python run_v8_checks.py` after pulling to validate the combined changes. At commit time these new tests have not yet been executed on the user's Windows environment.

### Cashier shift status added in the same Phase 1 batch

The Billing draft now shows the currently signed-in preview username (or a not-signed-in label) and the most recent **OPEN** shift from the isolated database. A missing shift is explicitly shown. This is **informational only**: it does not authorize checkout, open/close a shift, assign a cashier, or bypass the original `services._require_open_shift` transaction rule. The shift reader is separately guarded to preview storage, and tests check real schema compatibility, no writes and multilingual UI. All real commercial operations will need service-enforced permissions, a validated active shift and licensed transaction rights before release.

The combined one-command runner `python run_v8_checks.py` automatically discovers `tests/test_v8_phase1_reports.py`, so there is no long test list to copy. New Phase 1 tests still need a Windows run before this delivery is marked verified.
