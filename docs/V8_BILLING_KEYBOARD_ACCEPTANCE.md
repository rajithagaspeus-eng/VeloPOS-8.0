# VeloPOS 8 — Draft Billing Keyboard Search and Product Selection Acceptance

**Status: preview UI only.** No real sale, payment collection, receipt printing, stock deduction, customer credit or commercial checkout is introduced. Use only `python run_v8_preview.py` with dedicated `VeloPOS8PreviewData`.

## User-facing behavior

- Type an exact barcode and press **Enter**: exact barcode match wins, even if a different product's name contains the barcode text.
- Type a product name with **one match** and press Enter: add that one item to the **in-memory draft**.
- For **multiple matches**, simply pressing Enter does **nothing**, avoiding accidental product selection. Use **Down/Up** in the scan field to highlight a specific result, then Enter to add that item. Alternatively click the result row then Enter, or click `Add selected` / double-click the row.
- Changing the query resets the old highlighted result and its keyboard/mouse selection intent, even if a new query happens to return the same number of products. This prevents a previously selected row index from choosing a different product.
- A small help/status line below the search table reports empty, single, and multiple match states. Search and results have localized screen-reader names. English, Sinhala and Tamil labels explain the safe selection behavior.
- F2 still focuses the barcode field; existing F3/F4/F5/F6/F7 draft shortcuts, hold/resume, stock inspection and checkout-denial protections are unchanged.

## Manual Windows QA

1. Navigate to Billing Draft. Type `DEMO` (seeded preview products): expect several results and instruction to use arrow keys, Enter or click; pressing Enter without choosing must not add anything.
2. With `DEMO` still in the search field, press Down twice and Enter: only the highlighted demo item should enter the draft, totals should update, and focus should return to the scan field.
3. Change a search with a manually highlighted row to a different query and then back. Enter without selecting again must not add an item from a stale index.
4. Scan or type an exact demo barcode (for example `DEMO-001`) and press Enter: it should add the exact item and not another similarly named product.
5. Type a nonexistent barcode: expect localized no-results guidance and no change in draft.
6. Switch English → Sinhala → Tamil and check long help text, fonts, accessibility name and no clipped labels under Dark/Light themes, at 100%,125%,150% Windows display scaling.
7. Use Clear, Hold/Resume and Preview Sign Out; confirm cart data is cleared or held only in memory as intended. No sale, stock deduction, tax posting, invoice, checkout or printing button is enabled.

## Automated coverage and release boundary

`tests/test_v8_billing_keyboard_search.py` adds six offscreen Qt tests for deliberate arrow selection, stale row reset, exact-scan priority, mouse choice, three-language status and screen-reader labels, and single-result in-memory draft behavior. No customer/production database is opened.

Require exact PR-head Windows Actions `python -m compileall -q velopos_qt tests` and `python run_v8_checks.py` with no failures or skips; repeat at exact merged `develop-v8` SHA. Manual physical Windows acceptance is separate and remains required. No commercial Gate A/B/C/D/E is passed by this change.
