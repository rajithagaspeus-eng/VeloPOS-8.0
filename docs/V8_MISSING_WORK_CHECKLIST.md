# VeloPOS 8.0 — Missing work, blockers and acceptance checklist

**Current baseline:** 3ed6d8f7866f95111d221f4d309938f1fc5fb4d5, 2026-11-05. **Scope:** develop-v8 only; main/V7/real data unchanged. **Commercial checkout:** OFF.
This is a living dependency-driven worklist, not a claim that unchecked items are absent from code; they remain **unaccepted**.

## P0 — fix the release blockers before expanding scope

- [ ] **CI runner / exact-head regression** (Gate E): investigate latest push runs 42077102970 / 42077100600, check Actions job annotations, hosted runner eligibility/settings; obtain at least one *executed* Windows regression at current HEAD, full logs and zero unapproved skips. Do not invent a CI cause or declare app tests failed from an empty job.
- [ ] **Consolidated local environment**: pin a supported Python interpreter + PySide6 and cryptography, ensure spawned test subprocesses use sys.executable, isolate VELOPOS_HOME, and avoid requesting repeated owner installations after each commit.
- [ ] **Known regression triage**: rerun and fix credit-note repayments, foreign-charge ownership, duplicate/missing stock movement, receipt top-spacing, SQLite connection lifetime/Windows locks, legacy service-boundary expectations and PySide6 import issues. Record exact tests and SHA for every fix.
- [ ] **Trusted service boundary (Gate A)**: every actual financial service entry point verifies current session/role, entitlement, branch and shift inside its own transaction. A disabled Qt button cannot be the only protection; direct legacy entry points must be considered.
- [ ] **Durable sale integration (Gate A)**: implement real but isolated/disposable service-owned atomic invoice, line items, discounts, VAT, tender, stock/FEFO, audit and exactly-once crash recovery; all failed attempts leave no writes. Preserve hard-deny Qt commercial UI until accepted.
- [ ] **Reversal integration (Gate A)**: returns, voids, credit notes, supplier and customer payments; partial refund, quantity and original-invoice constraints; adverse concurrent/retry cases and original service behavior.
- [ ] **Independent accounting (Gate B)**: reconcile every representative sale/return tax, discounts, COGS, customer debt, loyalty, stock batches, purchase GRN, supplier payments/advances, shifts and Z-report from authoritative records; cover multi-day fixtures.
- [ ] **V7 copy migration safety (Gate B/D)**: compatibility inventory, reversible schema migrations, backed-up copied V7.2 DB, backup/restore round trip, rollback on failed upgrade, currency/tax/decimal fidelity. Never test on an active shop DB.
- [ ] **Feature parity audit**: adjudicate every F01–F26 row in V8_FEATURE_PARITY_MATRIX.md using actual source + Windows workflows, not README text alone.

## P1 — minimal saleable offline retail/hardware V8 release

- [ ] Complete premium Qt flows for Product, Billing, Customers, Inventory, Supplier/GRN, Returns, Reports, Shifts, Settings, Backup and Admin security after trusted financial adapters are accepted.
- [ ] Full scanner-first Windows keyboard, weight/unit workflows, barcode scanner test, receipt printer models, cash drawer, thermal/A4 layouts and failure feedback.
- [ ] Validate 100%, 125%, 150% DPI, Sinhala/Tamil/English shaping and translations, dark/light high contrast, keyboard-only navigation and slower hardware/catalog size.
- [ ] Mature secure offline licensing, activation, renewal/transfer, rate-limited trial continuity, key custody and verified recovery; avoid promises of uncrackability.
- [ ] Construct V8 Windows installer and uninstall/upgrade path, license-safe packaging, SBOM/third-party license review, optional code signing policy, malware checks, demo-only data and support documentation.
- [ ] Automated full-scenario and clean-profile manual acceptance: new Windows device, copied V7 upgrade, network outage, power loss, backup restore, long receipt, long session, owner UAT.
- [ ] Define owner-facing first saleable scope, trial/license SKU and price explicitly after measured feature acceptance, not before.
- [ ] Record release candidate SHA, actual executed no-skip regression output, 0/5-gate status transitions and owner acceptance separately; never enable checkout prematurely.

## P2 — extensions after reliable retail core

- [ ] Secure owner mobile/PWA summary with read-only least-privilege API; verify V7 Cloudflare Worker does not leak PII.
- [ ] Real authenticated tenant/branch cloud database, offline queue, idempotent sync, conflict/merge policy, audit, restore and hosting cost estimates. Offline core must remain functional without hosting.
- [ ] Pharmacy module: FEFO plus jurisdiction-specific prescription/regulated-stock handling and privacy.
- [ ] Salon/studio module: bookings, service packages, commissions, advance payments, delivery/status workflows.
- [ ] Explainable local AI demand analytics with calibration/backtesting, confirmed accounting sources and explicit uncertainty. No mandatory paid AI API.
- [ ] Extended multi-location inventory transfers, pricing, promotions, tax/local market regulatory profiles and internationalization.

## Issues explicitly carried forward from reconstructed conversations

- [ ] Historical UI design target (premium enterprise appearance) is not yet owner-accepted on real Windows screens.
- [ ] Avoid conflating **demo stock movements** with production stock writes or **Cloudflare dashboard upload** with two-way multi-branch sync.
- [ ] Avoid frequent ZIP downloads, isolated test commands and small unverified security commits as substitutes for an integrated milestone.
- [ ] Keep project history and parity matrix synchronized when decisions change or original requirements are deferred.
- [ ] Maintain a single evidence ledger instead of repeating unmeasured 35/60% as proof of commercial completion.
- [ ] Never touch V7 signing secrets, main or production data. Keep the original V7 app runnable until accepted migration and owner go/no-go.

## Recommended immediate next engineering batch

**Restore executable Windows CI for exact develop-v8 HEAD, diagnose real failures, then integrate one verified billing-to-ledger vertical slice behind a hard-denied commercial gate**. Include stock/credit/receipt fault injection and a single consolidated Windows acceptance artifact. Block any saleable build until Gates A/B are passed, followed by D/E. Gate C separately gates connected SKU claims.

## Status update protocol

On every significant delivery: add date, exact branch SHA, completed acceptance IDs, tests actually run (not merely written), environment/log link, remaining blockers and the next named milestone to V8_VERIFIED_EVIDENCE_LEDGER.md and V8_AUTONOMOUS_PROGRESS.md. If no tests ran, explicitly say **NOT EXECUTED**. Owner time should be requested for a **combined milestone acceptance**, not every micro-commit.


## Update — strict no-skip release evidence (2026-11-06)

- [x] Commit a strict legacy no-skip policy and make combined full regression require it (see `tests/run_all.py --fail-on-skips` and `run_v8_full_regression.py`).
- [x] Add disposable contract tests for strict skip rejection, valid non-skipped tests, historical nonstrict behavior, and combined-runner strict flag forwarding.
- [ ] **EXECUTE** targeted regression tests and the full combined suite at an exact current `develop-v8` SHA on isolated Windows. All code above is **COMMITTED ONLY**, not verified as PASS. Resolve real failures/skips rather than weakening the no-skip contract.
- [ ] Diagnose GitHub-hosted run `42081895568` (unassigned runner, no steps) and `42081892649`, and restore trustworthy CI execution and archived test output.
- [ ] Continue Gates A/B service-owned transaction integrity and accounting reconciliation; **production checkout remains disabled**.
