# VeloPOS 8.0 — Quick Navigation & Premium UX Acceptance

**Scope:** V8 isolated PySide6 **preview-only** shell. This does not affect or authorize checkout, payment, stock posting, license activation, printing, or production customer data.

## Implemented user-visible behavior

- A themed **Find page · Ctrl+K** control in the application header opens a searchable Quick Navigation palette from any of the 14 pages.
- **Ctrl+K** also opens the same palette in the currently focused V8 preview window; this follows the normal Qt application shortcut mechanism, rather than a global OS shortcut.
- Type a full or partial page name in the **current language or English**, even when the UI has switched to Sinhala or Tamil.
- Filtered results keep the canonical 0–13 page indices, with numbered labels, localized page names, and English tooltips for discoverability.
- Use **Down/Up** while the search field is focused, **Enter** to open the selected page and **Escape** or Cancel to close without navigating. If no result matches, Open is disabled.
- Selection changes the existing sidebar index, so the established `open_page()` authorization, draft-clearing and page refresh flows are reused. The modal never calls a POS service directly.
- Header action/help, palette heading, placeholder, buttons and no-results states translate in English, Sinhala and Tamil. The palette uses both dark/light preview themes.

## Manual Windows testing (owner)

1. Open the V8 preview with `python run_v8_preview.py` (not legacy `python run.py`). On a compact 1366×768 display and on a larger display, confirm the header page-search control is visible and not clipped.
2. Press Ctrl+K on Dashboard, type `billing`, press Enter; expect **Billing draft** screen. No checkout, payment, stock-deduction or printing action should appear.
3. Press Ctrl+K, search `inventory` and use Down/Up/Enter; expect Inventory, not the wrong page due to filtered index offset.
4. Switch language to Sinhala and then Tamil; search an **English** page name and a **localized** page name; both should navigate to the expected page.
5. Enter an impossible query; expect localized 'no matching pages' and disabled Open. Press Escape; expect the prior page and its unsaved draft/session unchanged.
6. Sign out of Preview Admin and use Quick Navigation to reach an Admin-only page; expect existing access restrictions and redaction rather than privileged data.
7. Try Dark and Light appearance. Test Windows 100%, 125%, 150% scaling for readability, nonoverlapping header controls, sufficient width of long localized labels and keyboard focus/hover states.
8. Capture any clipped text, awkward spacing, unexpected refresh, navigation/keyboard bugs or accessibility issues in screenshots. Automated Qt offscreen tests are NOT substitutes for physical-screen/assistive testing.

## Automated quality gate

`tests/test_v8_quick_navigation.py` adds six PySide6 offscreen tests that verify 14 canonical indices, localized and English lookup, filtering and no-match denial, Down/Up/Enter navigation, topbar and Ctrl+K shortcut wiring to the canonical nav, Escape/Cancel behavior, dynamically localized header and no transaction gateway access.

Run `python -m compileall -q velopos_qt tests` and `python run_v8_checks.py` on the **exact** feature-head SHA in Windows CI, with zero skips/failures, and repeat on the exact merged `develop-v8` SHA. Keep all commercial release gates A/B/C/D/E blocked.
