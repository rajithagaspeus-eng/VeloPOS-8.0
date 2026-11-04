# VeloPOS 8.0 — Responsive Preview Shell and Sidebar QA

**Scope:** V8 isolated PySide6 UI only. The work improves compact Windows usage and accessibility; it does NOT implement sales, payments, refund, stock mutation, authentication changes or commercial checkout.

## User-facing improvements

- Desktop widths **1040px and above** start with the existing 244px sidebar displayed.
- Compact widths **below 1040px** start with the sidebar collapsed to reserve space for the active page and reduce workspace clipping; while shown it is 216px wide.
- A permanent, theme-aware, screen-reader-labeled **menu button** in the V8 header toggles the sidebar; **Ctrl+B** provides the same window-local shortcut.
- On a compact display, selecting a sidebar page collapses the sidebar, keeping the main screen visible. Page changes continue to go through the canonical navigation and session-redaction code.
- Crossing the compact/desktop breakpoint restores the appropriate initial sidebar state. Within a width range, the user's explicit show/hide choice persists.
- Compact layout reduces outer and workspace margins. The header displays `VeloPOS 8` and `Ctrl+K`, while preserving descriptive, localized accessibility names and hints. Larger widths retain the existing full VeloPOS 8.0 heading and translated page-search label.
- Theme styling and new accessibility hints cover English, Sinhala and Tamil; the existing Ctrl+K page chooser continues to work even when the sidebar is hidden.

## Manual Windows acceptance still required

1. Start `python run_v8_preview.py` with disposable preview data only; maximize, restore and resize the desktop window to widths near 760, 820, 1039, 1040 and 1220.
2. On a compact width, confirm the sidebar is initially hidden, active page has greater usable width and the visible Menu button is not clipped. Toggle with the button and `Ctrl+B`.
3. Click Billing through the compact sidebar: it should close and show only a draft, with no checkout/printing/stock posting buttons or actions. Ctrl+K should still navigate.
4. Switch light/dark modes, three languages, 100/125/150% Windows display scaling; check header controls, accessible focus, page title, tables and no unreadable/overlapping widgets.
5. Test that sidebar manual state persists through same-width resizing but resets predictably on crossing compact/desktop threshold.
6. Sign out/demote the preview user and try navigating via sidebar and Ctrl+K. Existing access restrictions and draft clearing must still apply; no financial writes should occur.

**Automated coverage:** `tests/test_v8_responsive_shell.py` has six offscreen PySide6 regressions; physical monitor, keyboard/assistive-tech and actual DPI screenshot acceptance remains **unverified**.

## Gate requirements

Require clean **exact feature SHA** Windows Actions `python -m compileall -q velopos_qt tests` plus `python run_v8_checks.py` (zero failures/skips) before any merge to `develop-v8`. Independently verify post-merge push Actions exact merged SHA. Preserve `main`, V7 transactions and customer data. Commercial Gates A/B/C/D/E remain BLOCKED.