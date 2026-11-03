# VeloPOS 8.0 — Global Commercial Product Master Roadmap

**Branch:** develop-v8 only. **Budget:** zero mandatory monthly spend. **Stage:** planning plus partial experimental preview implementation. This document captures owner-requested commitments; unchecked capabilities must never be marketed as completed.

## Product requirements — all included in scope

1. **Modern professional next-generation UI/UX:** fast, polished dark/light themes, touch-and-keyboard-friendly, Sinhala/Tamil/English, fast barcode workflows, readable data-heavy screens, accessible labels, global usability.
2. **Advanced dashboard:** revenue/transaction/stock/credit/sales performance KPIs, filtering, role-aware charts, actionable alerts and drill-down. Current preview has only test DB product/customer/supplier/low-stock counters; revenue is not yet implemented.
3. **Smart inventory:** product/category/stock, reorder alerts, opening/adjustment audit ledgers, supplier/purchase links, batch/expiry/barcode, multiple units, forecasted demand and multi-location transfers with validation.
4. **Advanced billing:** fast scanner-first cart, discounts, tax/VAT/service charge, returns, receipt modes, cashier shifts, split/mixed payment where commercially required, offline reliability, transactional stock deduction and payment audit. Current V8 draft has no checkout or payment writes.
5. **Multi-branch management:** branch identities, permission boundaries, local branch POS that works offline, conflict-aware reconciliation, transfer ledger, centralized stock/reporting. Explicitly no false promise of instantaneous sync while offline.
6. **AI/business intelligence:** local-first trend analysis and demand forecasting; explainable forecasts and confidence ranges before optional external AI. Never require a paid AI API for core functions or send personally identifiable sales/customer records without agreement.
7. **Real cloud database + sync:** optional cloud backend with a correctly permissioned tenant/branch model, secure authentication, encrypted transport, idempotent operations, queues/retries/conflict resolution, backups and observability. A dashboard-upload API is **not** a multi-branch operational database. Verify actual free-tier quotas and realistic commercial scaling costs before promising a free unlimited service.
8. **Mobile owner dashboard:** secure phone-friendly/PWA access to permitted summary KPIs, reports, alerts and shops with explicit privacy controls and refresh timestamps. Audit existing signed shop-upload Worker, which is not a substitute for full multi-branch sync.
9. **Advanced customer loyalty:** points earning/redeeming rules, expirations, tiered benefits and safe returns/void handling, staff permissions and customer data consent.
10. **Automated P&L and reports:** sales, COGS, gross profit, expenses, refunds, taxes and net profit across time ranges and branches; reconciled against original accounting/transaction records, not invented summary values.
11. **Advanced security and staff activity monitoring:** login + roles + session authorization at service boundaries, persistent lockout, audit logs, role-aware alerts, data encryption/backups, intrusion/tamper signals and transparent privacy controls.
12. **Commercial licensing online + offline:** existing Ed25519 license signatures with signing private key kept outside installer/repo; activation, renewals, device binding, trial expiry, optional server first-seen and policy-based offline access; preserve paid licenses and customer data.
13. **Trial cannot trivially reset after reinstall:** server-authoritative earliest trial activation where reachable, local continuity and rollback checks offline. **No wholly offline app on a customer-controlled computer is guaranteed reset-proof or uncrackable.** Never claim 100% crack resistance.
14. **Forgot password by verified email:** optional trusted backend issuing expiring single-use reset tokens to a previously verified address. Protect against account enumeration, rate-limit attempts, keep delivery secrets server-side; existing Admin recovery-code mechanism remains safe offline fallback.
15. **Commercial distribution:** multilingual installer, updates, release signing if feasible, licensing KeyGen owned/admin-only, data migration, automated+manual QA, backup/restore, accessibility and stable maintenance. Never regenerate an existing real signing key.

## Dependency-driven implementation batches

| Stage | Scope | Gate |
|---|---|---|
| Foundation (current) | Qt navigation, isolated test database, demo records, billing draft, directories, stock preview and dashboard | 97 Windows combined tests passed at prior milestone; newer changes await a new run |
| Security foundation | preview auth, role controls, trusted transaction authorization boundary; license/trial threat model | No real checkout until authorization integrated & proven |
| Cashier operations | complete billing, receipts, returns, purchases, stock/expiry, shift controls | Reuse original transaction engine, rollback/audit tests |
| Analytics & loyalty | advanced dashboard, P&L, BI, local forecasting, customer points | Validate figures against source-of-truth transactions |
| Optional connected services | secure owner phone dashboard, cloud DB design, sync and multi-branch | Threat model, conflicts, retries, backups, permissions, free-tier feasibility |
| Commercial readiness | activation/renewal, anti-reset, verified-email recovery, packaging, QA and localization | Key secrecy, migration compatibility, Windows/hardware acceptance |

## Nonnegotiable engineering rules

- Never alter stable `main` or production databases without explicit review and production migration strategy; use `develop-v8`.
- Avoid a feature-complete claim until code, tests, and operational acceptance criteria exist.
- Do not use online AI/cloud as a required dependency of core in-store billing.
- Use a locally installed POS even when the internet is unavailable; keep cloud as a well-defined optional feature.
- Batch work + automated tests; one combined Windows acceptance cycle per significant delivery.
- Protect test-only previews; keep paid customer data, secret keys and passwords out of public GitHub, logs and chatbot output.

See also: [Next-generation UX contract](V8_DESIGN_SYSTEM.md), [Security & Recovery](V8_SECURITY_TRIAL_RECOVERY.md), and [Qt Preview](V8_QT_PREVIEW.md).

## Current Phase 1 delivery note — November 2026

Additional preview-only modules are now committed on `develop-v8`: Admin purchasing GRN and active-supplier overview, original-engine purchasing regression tests, read-only estimated full-payment loyalty earning points, and a fail-closed preview transaction gate that explicitly rejects checkout, purchase, payment, loyalty redemption and shift changes. Tests for direct role revocation, purchase ledger accuracy and loyalty rollback were added. They are **not yet confirmed by a new Windows test run**; earlier milestone results must not be misrepresented as proof that these later commits passed.

The Admin purchasing page intentionally reports **initial** payment estimates only; the original `supplier_payments` ledger and `supplier_balances()` must be used for real outstanding liabilities. A commercially writable transaction gateway with validated role, session, license, shift and per-action service authorization remains future work. This delivery did not enable any Qt checkout or edit the production database.

## Phase 2 analytics delivery note — November 2026

The preview has moved beyond static dashboard inventory counters: a new read-only **Business intelligence** view now shows historical daily sales, returns, indicative net contribution after expenses, top sales items, and expenses grouped by category, with Admin-only access and trilingual Qt labels. Its queries cross-check the original Reports ledger. This is descriptive analytics only, **not AI demand forecasting**, finalized COGS, cross-branch reporting, or a customer-facing production feature.

Next dependencies for a responsible commercial analytics release: transaction/session authorization, verified historical cost/revenue accounting under partial returns and voids, source-of-truth loyalty/credit/supplier reconciliations, reusable trend/forecast methodology with confidence ranges, and performant multi-branch boundaries when that stage begins. Preserve the existing isolated TEST DATA behavior and do not enable checkout or cloud writes simply to populate graphs.
