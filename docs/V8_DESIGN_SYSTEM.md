# VeloPOS 8.0 — Next-Generation UX and Visual Design Contract

**Status:** Development standard for all Qt screens. Commercial readiness is not implied.
**Branch:** develop-v8; keep main stable until validated.
**Product vision:** An eye-catching, modern, fast, easy-to-learn international POS product that serves small shops and high-volume counters with zero mandatory paid design tools.

## Core product principles

1. **Clear at a glance.** The primary task, totals, selected items and next action should be instantly legible. Use a coherent grid, generous spacing, restrained accent colors and strong hierarchy.
2. **Fast under real checkout pressure.** Keyboard- and barcode-scanner-first billing; avoid blocking printer discovery, long synchronous startup tasks and full-screen rebuilds. Paginate/search bounded records; cache only non-sensitive display state with explicit refresh, never monetary/stock truth.
3. **Beautiful but practical.** Contemporary premium appearance (rounded surfaces, subtle elevation, polished icons, restrained animation). No decorative visual clutter, distracting gradients or slow transitions on critical tasks.
4. **Designed for Sinhala, Tamil and English.** Translate all UI copy, handle text expansion, support Unicode shaping and locale-aware fonts. Never render important text as an image. Keep numeric/barcode inputs exact, independent of language.
5. **Accessible and responsive.** Large touch targets, visible focus states, meaningful keyboard shortcuts, adequate contrast, clear validation/error messages and sensible minimum window sizes. Test both bright and low-light themes.
6. **Error resistant.** Clear destructive-action confirmations, validation before write, persistent unsaved-change indication, keyboard-safe navigation and readable success/error states.
7. **Trustworthy finance.** Always reuse existing VeloPOS transaction engine for actual checkout, discounts, VAT, stock moves, receipts and audits. Never invent amounts. Preview data cannot be represented as live sales.
8. **User-role aware.** Sensitive supplier costs, customer credits, financial reports and administrative actions require existing authorization controls before production enabling.
9. **International, modular.** Screens should remain usable for groceries, hardware, pharmacies, salons and studios without showing irrelevant specialized controls by default.
10. **Test in meaningful batches.** Automated unit/integration/offscreen Qt tests per batch; owner sees one combined Windows test build. Do not equate passing preview tests with production acceptance.

## Visual system direction (guidance, not implemented feature claims)

- **Layout:** fixed-width, clearly labelled sidebar; flexible content panel; consistent top header with location, task and language; dense but breathable data tables.
- **Color:** neutral canvas with a teal/emerald primary action, subtle borders, distinct semantic states. Use red only for errors/destructive actions; don't use color alone to convey state.
- **Typography:** Segoe UI/appropriate Sinhala-Tamil fallback, clear hierarchy and sufficiently large labels. Test glyph shaping on actual Windows machines.
- **Reusable UI pieces:** app shell, section headers, metric tiles, search bars, tables, empty/loading/error states, form rows, confirmation dialogs and nonblocking toasts.
- **Billing first:** high-visibility barcode/search focus, quick cart edits, meaningful totals, payment shortcuts and clear receipt status only after safe services are integrated.
- **Performance budgets:** measure interaction responsiveness and screen load time before setting numeric acceptance thresholds. Avoid synchronous hardware/network calls on UI thread.

## Acceptance checks for each batch

- Can a new cashier find the primary action without a tutorial?
- Are Sinhala, Tamil and English labels complete and unclipped?
- Can keyboard-only users complete the preview workflow?
- Is the interface usable at the supported minimum window size and on Windows display scaling?
- Is the UI responsive with larger catalogue sizes, and is any blocking call identifiable?
- Do risky actions run only after validation, authentication and tested business-service integration?
- Are demo records and estimations unmistakably labelled, and production data untouched?
- Does the batch pass automated tests and a single combined Windows manual QA pass?

## Current implementation boundary

The existing PySide6 preview is a **functional foundation**, not yet the full next-generation redesign. It has basic theming, navigation, three languages, read-only inventory/customer/supplier views and a draft billing cart. Production workflows remain in the original application. Future design improvements must upgrade these progressively without breaking business logic or the persistent dedicated preview data isolation.

## Premium shell polish — November 2026 (preview only)

The Qt preview shell now uses a clearer dark/light visual hierarchy:
a dedicated branded navigation panel, distinct workspace surface, roomy
header and form gutters, hover/selected navigation states, a prominent
read-only dashboard hero, larger dashboard KPI cards with consistent
labels, a restrained teal palette and improved keyboard-focus contrast.
Default preview window size is 1220×780 while the original 760×520
minimum stays supported. The same fourteen navigation routes, locale
translations, data readers and restrictive transaction policy remain.

This is visual polish of the existing PySide6 shell, **not** a claim of
production-grade finish. In particular, the minimum-size viewport,
high-DPI scaling, Sinhala/Tamil text shaping, iconography, complex
business workflows and hardware must receive the final combined Windows
visual/manual acceptance. UI style cannot be certified from offscreen
tests alone. The standalone preview still uses isolated test data and
does not permit checkout or financial posting.
