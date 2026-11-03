# VeloPOS 8.0 — Experimental Qt Settings Preview

**Not a commercial release.** This is an isolated proof of concept, not a replacement for `run.py`.

## What is implemented

- A new standalone PySide6 window with left navigation, light/dark styles and lazily built pages.
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
python -m unittest tests.test_v8_settings_model tests.test_v8_i18n -v
python -m unittest tests.test_v8_qt_ui tests.test_v8_preview_storage -v
```

These are headless adapter tests only. A successful test run is **not** evidence that the full Windows GUI or existing POS works.

## Manual acceptance checklist (Windows)

1. Launch and verify Shop profile opens without a blank screen or flicker.
2. Switch between Dashboard, Shop profile, Appearance, Printer & receipts, and About repeatedly; observe render time.
3. Switch the top language selector between **English**, **සිංහල** and **தமிழ்**; verify navigation, field labels and messages update immediately and text renders without boxes or clipping. Close and relaunch the preview: the selected language should persist.
4. Change a test shop name and Save; see a translated confirmation.
5. Switch to Appearance, choose dark/light, Save and verify theme changes.
6. Open Printer & receipts, edit paper size, brand, mode, copies and footer, then Save. This must **not** attempt to connect to or enumerate a real printer.
7. Change paper size to A5 and Save, close the window, reopen and confirm **A5 remains selected**. Verify shop name and language preferences also persist as expected.
8. Confirm the existing production VeloPOS database and old desktop application are unaffected. A separate test database must exist under `%LOCALAPPDATA%\\VeloPOS8PreviewData`.

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
