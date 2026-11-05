# VeloPOS V7.2 → V8.0 feature-parity and release matrix

**As-of source snapshot:** 3ed6d8f7866f95111d221f4d309938f1fc5fb4d5, 2026-11-05. **Branch:** develop-v8. **Checkout:** DISABLED.

This is a matrix of **documented legacy behavior**, **known V8 preview/source availability** and **missing commercial proof**. A legacy README claim is NOT current V7 hardware proof. V8 preview screens, code and test files are NOT automatically completed commercial features.

Status vocabulary:
- **PREVIEW**: visible test-data-only screen or read-only workflow; no live financial posting.
- **SANDBOX**: isolated persistence/rehearsal, not production authority.
- **REFERENCE**: signed-token/service model or design without complete deployment/production verification.
- **UNVERIFIED**: legacy/partial code exists but full V8 behavior not accepted.
- **MISSING**: feature needed to meet the vision but no accepted complete V8 implementation.
- **BLOCKED**: depends on failed/unaccepted commercial release gate.

| ID | Capability | V7 legacy README / owner record | V8 evidence as of snapshot | V8 acceptance gap | Priority / gate |
|---|---|---|---|---|---|
| F01 | Windows app startup, navigation | CustomTkinter desktop | PREVIEW PySide6 shell, 14 routes, light/dark | Windows DPI, accessibility, startup performance, full flows | P1 / E |
| F02 | English/Sinhala/Tamil UI | Multilingual assistant | PREVIEW locale switch and translated routes | Complete forms/options, Unicode shaping, manual QA | P1 / E |
| F03 | Product catalogue & category | Products, categories, pictures, price history | PREVIEW guarded product display/editor | Full V7 parity, price-history and catalog scale | P1 / B,E |
| F04 | Barcode/scanner fast billing | V7 sale and shortcuts | PREVIEW searchable billing draft, cart controls | Device scanner, discounts/tax/tender/checkout integration | P0 / A,B,E |
| F05 | Atomic sales and receipts | Legacy financial sales and printing | SANDBOX sale ledger + draft receipt | Trusted actual service-owned posting, printing and crash QA | P0 / A,B |
| F06 | Tenders, change, split payment | V7 cash/credit and tender rules | SANDBOX tender declarations | Cash/card/QR/credit mixed tender accounting, drawer & receipts | P0 / A,B |
| F07 | Returns, refunds & voids | V7 returns/refunds/void | SANDBOX return/credit-note flows | Full original invoice tax/discount/COGS/reversal parity | P0 / A,B |
| F08 | Stock ledger & stock-take | V7 stock ledger, stock-take | SANDBOX stock history guards; preview insights | Production-safe stock/adjustments/stock-take reconciliation | P0 / B |
| F09 | Batches, expiry, units & FEFO | V7 batch/expiry/units | REFERENCE legacy engine and preview diagnostics | Commit-time FEFO, expired stock, unit conversion acceptance | P0 / A,B |
| F10 | Suppliers, purchasing & GRN | V7 supplier invoices/payables | PREVIEW purchasing/read-only balances; tests | Real authorized GRN, supplier advances/payments and inventory tie-out | P0 / A,B |
| F11 | Customers and customer credit | V7 credit book, contact editor | PREVIEW directories; SANDBOX credit ledger & allocations | Live credit and branch/accounting audit, migration | P0 / A,B |
| F12 | Customer loyalty | V7 points and redemption | PREVIEW read-only estimated earning/lookup | Earn/redeem expiry, credit/return/void integrated ledger | P0 / B |
| F13 | Staff, permissions & sessions | V7 roles, audit and shifts | PREVIEW role/session/branch/shift tests | Original service entry points must reject unauthorized calls | P0 / A |
| F14 | Cash shifts, Z-report & drawer | V7 shifts & cash drawer | PREVIEW shift visibility, financial mutations denied | Actual closeout, reconciliation, device acceptance | P0 / A,B,E |
| F15 | Receipts and peripherals | V7 ESC/POS and printer settings | PREVIEW config + draft receipt; print blocked | Real printer/barcode/drawer tests across hardware | P1 / E |
| F16 | Backup/restore and recovery | V7 backup/reset/recovery | REFERENCE prior services and crash rehearsals | Copied V7 DB migration, restore, rollback and outage tests | P0 / B,D,E |
| F17 | Reports / P&L / VAT | V7 reports, VAT/service charge | PREVIEW read-only descriptive analytics | True invoice cost, original COGS, taxes, dates, expense reconciliation | P0 / B |
| F18 | Smart inventory/forecast | V7 low stock, expiry and assistant | PREVIEW stock insights and transparent demand baseline/backtest | Representative scale, bias/backtest quality, no false AI claims | P1 / B,E |
| F19 | AI assistant and insight | V7 offline rule assistant | REFERENCE local analytics/heuristics | V7 assistant parity and privacy-safe optional advanced AI | P2 |
| F20 | Owner mobile dashboard | V7 Cloudflare summary Worker | REFERENCE historical upload architecture | Secure multi-branch read-only service, retention and owner access | P2 / C |
| F21 | Offline-first multi-branch | Owner-required future enhancement | REFERENCE branch scopes/authorization only | Authenticated server sync, queues, conflicts, tenant isolation | P2 / C |
| F22 | License, trial and activation | V7 key and online trial registry | REFERENCE signed preview activation, grace and device recovery | Production backend, threat model, rollout, customer recovery | P1 / D |
| F23 | Verified-email password reset | V7 recovery code/email option | REFERENCE security contract | Trusted server tokens, verified ownership, rate limits | P1 / D |
| F24 | Installer, upgrades and branding | V7 installer/logo/trial code | REFERENCE old build paths and V8 planning | Clean machine V8 install, upgrade, signed release policy | P1 / D,E |
| F25 | Industry modules | Owner wanted pharmacy, salon, studio, hardware | MISSING accepted end-to-end modules | Regulatory/pharmacy, appointments/studio, business-type onboarding | P2 after safe core |
| F26 | Full test and monitoring | Legacy unit/GUI smoke suites | PREVIEW extensive V8 regression files and workflows | Exact current HEAD Windows no-skip full pass, useful CI logs | P0 / E |

## Hard exclusions

- PREVIEW and SANDBOX rows do not enable the live cashier checkout button; they cannot settle real payments or mutate production shop stock.
- Source existence is a development indicator only. For parity approval, record the exact test SHA, environment, assertions, source-of-truth balances and a real Windows user workflow.
- No V7 feature should be deleted or overwritten during migration without explicit mapping, negative tests, rollback and owner approval.
- Business-specific pharmacy/medical/tax requirements must be assessed per jurisdiction before marketing.

## Next audit action

Review each F-row against copied V7 fixture and V8 Qt source, assigning an owner, acceptance test and exact-SHA evidence link. Start with F04–F17 core finance and F26 reproducible testing. Link accepted rows to docs/V8_VERIFIED_EVIDENCE_LEDGER.md. Until then **0/5 commercial gates accepted**.
