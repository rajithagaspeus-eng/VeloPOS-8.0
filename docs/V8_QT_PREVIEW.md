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

## Phase 1 — larger integrated batch: refund reconciliation, metadata safety, permissions & engine checks

This batch closes several high-risk gaps *without turning on production checkout*:

- **Product metadata preservation:** editing a product's name, retail price or stock in isolated preview now forwards its existing keywords, wholesale price, expiry date and warranty to the original upsert service, instead of accidentally resetting those fields. The original service already preserves cost, category, tax status and image. A regression test checks those fields and the recorded stock change.
- **Refund-adjusted reporting:** read-only reports use the same `sales + returns + expenses` accounting convention as legacy `services.report_data`: returns reduce revenue, `profit_adj` adjusts gross profit, VAT/service charges are offset by their return adjustments. Report outputs remain **indicative**, not certified P&L. Refund test data is reconciled against the original reporting service, with dates checked and voided sales excluded.
- **Role checks at preview adapter boundary:** the *Qt-owned* demo product/customer/supplier editors now check the current Admin identity on every mutation, including after logout. The display-only hide/show gate is no longer the only check. Existing test adapters without an authorization callback retain compatibility. **Legacy service methods do not yet enforce production session permissions**; do not use them as commercial authorization endpoints.
- **Original transaction engine regression:** subprocess tests execute the existing `services.create_sale` against disposable preview storage to verify stock ledger/audit consistency and rollback when stock is insufficient. These tests do **not** expose any checkout/payment action in the Qt preview; full role, session, licensing, shift and transaction-hardening gates remain mandatory before real use.

Run `python run_v8_checks.py` once after `git pull origin develop-v8` at the next combined Windows milestone. Until then the new tests are committed but not verified on the user's Windows environment. The previous combined suite ran **84 tests successfully**.

## Phase 1 — larger billing readiness delivery: cash, discount and stock checks

The scanner-first Billing draft now accepts a **draft discount** and **cash given** input, with **estimated payable**, change or remaining cash calculated locally. Discount amounts use Decimal validation, cannot be negative or exceed subtotal, and are passed to the original read-only `services.preview_bill` so that taxable/exempt items and VAT/service policies use the original billing mathematics. No credit, cash transfer, invoice creation, receipt or shift mutation occurs. All amounts are visually marked as preview only.

The test-only Stock Reader checks draft lines for **removed products, insufficient on-hand stock or changed selling prices**. Alerts are localized to Sinhala, Tamil and English. It executes read-only parameterized queries, guarded against the production data directory. A positive result is **never authorization to checkout**; the original transaction engine must check units, batches, stock, licensing, authentication, payment and shift again inside one transaction.

For speed, cash/discount typing updates in-memory calculations without repeatedly querying the stock database. Stock signals refresh when the cart changes or on Billing page entry; line totals use the same per-line currency rounding convention as the original service.

The Admin-only Reports Reader also checks the Qt-owned Admin gate at the data-adapter boundary, not just when its page is visible. This remains preview-only: the legacy services are **not** yet secured by a production-grade session/permission boundary.

New automatic tests cover model validation, cash estimates, read-only stock/price signals, VAT/tax parity with the original service, display localization, query caching and report access after sign-out. They are discovered automatically by `python run_v8_checks.py` alongside prior tests. The previous confirmed milestone was **84/84 Windows checks passed**; newly committed tests have not yet been run on Windows.


## Premium Reports & Cashier Session UX — integrated visual/security batch

After the November Windows screenshot review, the Reports & activity screen has **nine localized KPI cards** instead of a single compressed text line. Tiles distinguish bill count, recorded sales, returns, revenue after returns, adjusted gross, expenses, indicative net, VAT and service charge. Read-only sales and audit tables remain below. Financial fields are **indicative**, not finalized accounting, and use the existing guarded summary logic. With no authenticated Admin, or after an invalid date/reader error, the KPI cards and report tables are cleared to placeholders instead of leaving stale sensitive values onscreen. Card colors support both light and dark themes.

The Billing draft adds cashier-oriented **F4 Discount** and **F5 Cash Given** focus shortcuts, a per-item-scrolling product results table and improved compact summary layout. **Sign out discards the in-memory draft cart, discount, tender and quantity**, so a second cashier cannot inherit the prior user's unsaved work. There is still no real checkout or receipt/payment operation. The dashboard remains separate and operational metrics are always test-only.

New offscreen Qt tests cover KPI contents, invalid-read/error clearing, Sinhala translation, keyboard shortcuts and sign-out draft reset. Continue to run the single combined `python run_v8_checks.py` at the next Windows milestone; these newest tests have not yet been verified in the user's Windows environment.


## Phase 1 combined milestone — Smart Inventory and cashier hold/resume

An Admin-only **Smart inventory** screen has been added to the sidebar. It reads the existing, isolated preview `products`, `batches` and `stock_moves` schema, and shows:

- Live low-stock item counts and bounded detail rows (adjustable threshold, default 5)
- Product-level and active-batch expiration alerts, including items already expired or expiring within a chosen window (default 30 days, capped to 365); depleted batches are ignored, repeated batches are counted as **one product**; details show the earliest known expiry
- The 30 most recent stock ledger movements showing time, barcode, signed quantity change, ending balance, reason and user (up to 100 per request)
- Three-language labels and dark/light styled summary cards

**Privacy/security:** the Qt preview-owned read adapter checks the current Admin identity **at each query**, and its page immediately clears counts and tables upon logout. It cannot perform purchases, adjust/receive stock, delete products, open a shift or make sales; the original production ledger remains untouched. The date/quantity limits and SQL are bounded/parameterized. The scanner-first Billing draft also warns when a product-level expiry date has passed, or an active batch carries a past expiry date. An empty/depleted batch is ignored. Warnings are advisory only and never authorize a sale; batch availability/expiry must be enforced independently by the original transactional services when commercial checkout is developed. Tests run with disposable test database paths only.

**Faster cashier flow:** Billing draft can **Hold draft (F6)** and **Resume held (F7)**, with one in-memory held slot. A held draft includes cart lines, discount and cash tender estimate. Holding clears the current draft so the next customer can begin; resuming is allowed only when the active cart is empty, so it will not silently overwrite another draft. The held state is **not persisted**, no transaction or stock change occurs, and signing out discards both active and held drafts (including any tender values). F2 barcode, F3 quantity, F4 discount, and F5 tender remain.

The combined Windows check is `git pull origin develop-v8` and `python run_v8_checks.py` **once per milestone**, followed by `python run_v8_preview.py` for the optional GUI acceptance check. New Smart Inventory and Qt hold/resume tests are committed but have **not yet been executed on Windows**. The confirmed previous Windows suite was 97/97 and subsequent unverified batches have added more tests.


## Phase 1 larger batch — Customer loyalty lookups and actionable replenishment

The cashier Billing draft now supports an **opt-in customer search** by existing name or phone and a selector for an authorized, signed-in **Admin or Cashier**. It displays the customer's stored loyalty points, outstanding credit balance and credit limit **read-only**. The original `customers` table and schema migrations are reused. There is no redemption, point creation, credit sale, payment or customer write. The preview data adapter checks the current login at **every query** and rejects non-preview storage. Unauthenticated UI controls are disabled, and an unsaved held draft stores only the customer ID (not name/phone); the ID is revalidated when resuming.

**Privacy:** on Sign out, the cashier UI discards the active cart, held cart, selected customer, cached selector names/phones, discount and tender. A new cashier never inherits the prior user's customer selection or unsaved draft. If a customer is removed while a draft is held, the UI will not silently treat the deleted record as valid. Production transaction rights remain disabled.

**Smart Inventory:** the Low Stock table also contains a *Suggested top-up* column, calculated as the amount required to take stock **above** the selected threshold. This is a basic arithmetic planning hint only, not an AI forecast, purchase order, or automatic stock change. The underlying original stock ledger is unchanged.

New isolated database tests cover authenticated lookups, literal wildcard escaping, read-only points/credit, production-folder rejection and logout revocation; Qt tests cover customer selection, held-draft association and privacy, as well as reorder quantities. They join the existing one-command suite. **This latest batch is committed but not yet Windows-tested.** No changes were made to `main`, the real shop database, private license signing keys, or real checkout.

## Phase 1 larger batch — Purchasing, points projection & transaction boundary

**Purchasing overview (Admin only):** a new sidebar screen queries the original `purchases`, `suppliers` and initial GRN payment fields from the **isolated preview database**. It displays successful GRN count, purchase totals, initially paid amount, an **initial unpaid estimate**, recent GRN records and active suppliers. The estimate deliberately does **not** represent live supplier payables: subsequent `supplier_payments` must be reconciled for authoritative balances, and the original `services.supplier_balances` remains the source of truth. Supplier and purchase record information is cleared upon sign-out. No purchase, stock receipt, supplier payment or purchase order is generated from this screen.

**Purchasing draft math:** `preview_purchase_line(qty, unit_cost)` is an isolated Decimal cost calculation with rejection of negative, zero, NaN, Infinity and out-of-bounds values. It is not a transaction operation.

**Loyalty planning:** when a signed-in cashier selects a customer in Billing, a small read-only projected points label uses the legacy full-payment earning rule `round(net / 100, 2)` to show possible points on the **estimated payable**. This is a *projection only*: actual points are recomputed by the original service at checkout using net minus credit due. No credit is extended and no points are earned/redeemed. Drafts still cannot be checked out, and held/customer identity data are wiped on logout.

**Fail-closed policy:** `PreviewTransactionGate` explicitly refuses every sale, return, purchase, supplier payment, credit payment, points redemption, shift action and printing request, even for an Admin. This test-build gate is a development contract, **not** evidence of production-grade authentication. The original service APIs are not yet universally protected against direct programmatic invocation; real checkout remains disabled. Regression coverage also checks that legacy credit sales earn points **only on the amount actually paid**, whereas the preview label explicitly assumes full payment. Any commercial credit/loyalty processing must use the original transaction service rather than trusting the projected UI number. A commercial gateway must enforce authenticated session, role, valid license, shift and transaction state at the service boundary.

**Combined tests:** disposable test subprocesses exercise the *original* `create_purchase` stock/GRN/audit path and original `create_sale` loyalty accrual/failed-redemption rollback, without exposing transactions through Qt. Qt tests verify Purchasing Admin gate and logout clearing, multilingual labels, customer points illustration, and hold/resume privacy. Model tests verify financial input validation and production-path rejection. These latest tests are committed but **have not been executed on the user's Windows installation**. Run `python run_v8_checks.py` at the next combined milestone instead of separate tests for each small change.


## Windows screenshot feedback — Billing layout (121-test milestone)

The owner confirmed **121/121 automated checks passed** on Windows on the pre-fix `develop-v8` snapshot. Only the Billing screenshot was inspected, not a complete manual acceptance run. It showed **"Draft items" visibly overlapping the product results table** and an unnecessarily tall sidebar navigation.

The follow-up layout fix places the full Billing draft in a scrollable Qt canvas, with minimum product-results and draft-cart table heights, instead of compressing those widgets when customer, loyalty and hold controls exceed the available window height. The sidebar item spacing was reduced for twelve navigation pages in both light and dark themes. A new offscreen regression test checks non-overlap and vertical scrolling at small heights. **This fix has not yet been Windows-tested**; defer full manual testing until the next combined milestone, as requested. Do not present untested Smart Inventory, Purchasing or Customer Loyalty manual workflows as passed.

## Phase 1 accuracy batch — Supplier reconciliation and purchasing date filters

The Purchasing overview now separates **date-scoped GRN totals** from **all-time current supplier balances**. The earlier `unpaid_estimate` field used only `purchases.paid` at receiving time, and did not reflect follow-up `supplier_payments`; it is retained with a precise label rather than represented as a current payable.

For actual outstanding balances, a read-only query separately groups all status=`OK` purchase totals and all later supplier payment amounts by supplier. The page displays each supplier's purchased amount, total paid, and current net balance. It also displays (1) sum of positive supplier balances as **current payables** and (2) absolute value of negative supplier balances as **supplier advances**. Keeping these totals separate prevents an advance to one supplier from silently hiding debt owed to another. These figures reconcile against the legacy `services.supplier_balances()` and `services.payables_total()` semantics in disposable-database regression tests.

Admin can filter the **GRN history and purchasing totals by date** while the real supplier balances remain all-time; the scope is explicitly explained. Invalid date or permission loss clears all financial figures and tables. Date inputs are on a separate row to fit narrower Windows screens. The page remains **read-only**: no GRN creation, supplier payments, or stock movement operations are wired in.

A Windows test milestone **121/121** passed before the current screenshot-driven Billing scroll/overlap fix and this reconciliation batch. Subsequent new code and tests have not yet been verified on Windows; following the owner's preference, defer full manual UI acceptance until a later combined milestone.


## Phase 2 preview foundation — Historical Business Intelligence

An **Admin-only Business intelligence** sidebar view has been added with three-language labels (English, Sinhala, Tamil). It reads only isolated test storage and supplies four accounting summary cards: recorded sales, refunds, revenue after refunds, and **indicative** net profit. Additional views show the per-event-date daily trend (including days with expense/return activity but no new sales), grouped expense categories, and top products sold by original sale-item turnover. These figures use the same `sales.status='OK'`, `returns.date`, `returns.profit_adj`, and `expenses.date` semantics as the original V8 Reports model.

**Accounting caveats:** Historical descriptive analysis is **not a forecasting engine** and not independently certified P&L. Daily refunds belong to the refund-processing day, and a negative daily number may be legitimate. Top-selling products are ranked by sales **before** returns; there is no false claim of item-level net-return margin. Original recorded `sales.profit` is used rather than reconstructing costs from today's product prices. Final cost of goods sold, tax, returns and stock valuation reconciliation still requires commercial accounting acceptance.

**Safety and limits:** Reader requires Preview Admin on every call and passes the isolated database guard. Date ranges are validated and capped at 367 inclusive calendar days, top-N queries limited to 50 rows. Invalid dates, query errors, logout or role loss clear all displayed analytics figures and tables. There is no sales, stock, payment, third-party AI/cloud call, or production-data mutation. Tests include ledger parity with `PreviewReportsReader`, void exclusion, returns, expenses, top-selling original line items, Admin revocation, date limits and offscreen Qt data clearing/localization.

The previous confirmed Windows milestone was **121/121 checks passed**. The Billing scrollbar screenshot fix, supplier payable reconciliation, and this analytics batch have **not yet been verified by another Windows run**. The owner's preferred workflow remains a single combined test and manual QA later, not tests after each small commit.
