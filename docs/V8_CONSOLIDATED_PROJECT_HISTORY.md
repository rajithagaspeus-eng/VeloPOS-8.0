# VeloPOS — Consolidated project history and decision record

**Reconstructed:** 2026-11-05. **Repository:** rajithagaspeus-eng/VeloPOS-8.0. **Branch:** develop-v8 ONLY.
**Source snapshot:** 3ed6d8f7866f95111d221f4d309938f1fc5fb4d5. This is a historical evidence record, not a release certification.

## Provenance and limits

This record reconciles: (1) the owner's recovered prior conversation excerpt (uploaded 2026-11-04 as Pasted text), including the initial V7.2 ZIP discussion and product commitments; (2) repository README.md and DEVELOPER_HANDOFF.md, which document legacy versions; (3) docs/V8_MASTER_ROADMAP.md, docs/V8_QT_PREVIEW.md, docs/V8_FIVE_PHASE_EXECUTION_PLAN.md, docs/V8_COMMERCIAL_RELEASE_GATES.md, docs/V8_REMAINING_WORK_AUDIT.md and docs/V8_AUTONOMOUS_PROGRESS.md; (4) the GitHub develop-v8 branch and associated Actions metadata; (5) recent assistant/user development exchanges.

**Limitations:** The full text of every historical ChatGPT conversation is not available. A user-provided pasted history is a secondary record, not proof of every previous implementation or test. Some original implementation dates preceding November 2026 are unknown. README features describe historical V7 behavior but cannot establish the V8 Qt feature parity. This document must not silently replace missing evidence with inferred completion.

## Origin and product ownership

- The owner initially asked about low-cost AI coding assistance for improving an existing Windows POS, not creating a new POS from scratch.
- A prior conversation supplied an archive named velopos_v7_2_fixed6 (1).zip; the existing implementation was understood to use Python, CustomTkinter and SQLite. Its V7.2 code and database were to be preserved.
- Owner requested a saleable, professional VeloPOS product under their own brand, initially targeting supermarkets, groceries and hardware, with potential industry modules for pharmacy, salon, photography studio and other retail categories.
- **Zero mandatory spend** was an explicit owner constraint. Do not require paid AI services, paid cloud or paid developer subscriptions for the offline core; commercial cloud capacity, code-signing and support may eventually carry real costs.
- Desired operating model: reliable offline Windows billing with optional online/cloud capabilities. Proposed commercial model: one-time POS license plus optional support/cloud; suggested launch prices were proposals, never accepted market-tested prices.
- Original long-term ambitions: premium dark/light design; Sinhala/Tamil/English; quick scanner-first billing; modern analytics; robust inventory/purchasing; customer loyalty/credit; secure users/shifts; real multi-branch sync; phone dashboard; explainable AI; licensing/trial/recovery; safe Windows installation.

## Legacy VeloPOS development — documentary baseline, not V8 parity

Legacy README.md records these phases/features:
- Early phases: sale/return/refund/void, shifts and cash drawer, financial reports, expenses, user permissions and audit history.
- Phase 3: receipt printing, multiple printer connection modes, cash drawer settings and thermal layout.
- Phase 4: backup/restore, factory reset, recovery code / email password recovery, setup wizard and printing safety fixes.
- Phase 5: offline rule-based multilingual assistant and daily owner summaries.
- Phase 6.1: category/catalog management, photos, price history, bulk edits and CSV.
- Phase 6.2: stock ledger, stock-take, batch/expiry/FEFO and multiple units.
- Phase 6.3: VAT/service charge, customer credit controls, suppliers, GRN and payables.
- Phase 6.4/6.5: barcode labels, keyboard shortcuts, customer display, backup folders, update notification, validation and accounting bug fixes.
- Phase 7.1: optional Cloudflare Worker owner summary phone dashboard; not a cloud POS transactional database.
- Phase 7.2 and subsequent review: online trial registry, support code, installer/branding improvements and Phase 7.3 regressions.

The recovered conversation reported 17/17 Phase 7.3 tests, static checks and GUI smoke checks; **this was a prior record, not a newly rerun V8 test**.

## VeloPOS 8 implementation chronology

### Initial V8 transition — 2026-11-03/04 (approximate from recovered evidence)
- Owner selected upgrading the existing Python/SQLite product, retaining V7 and all real customer data, rather than a risky rewrite.
- A separate velopos_qt PySide6 test preview and dedicated VeloPOS8PreviewData storage were established without replacing legacy run.py or enabling production checkout.
- Preview settings, local language selection, read-only catalog/directories and cart draft grew into 14 navigation routes and premium-themed UI work. A preview screenshot confirmed a Windows UI launch at a previous milestone; that is not acceptance of every screen.

### Larger November 4 batches
- Preview dashboard, inventory insights, purchasing, read-only reports, historical analytics, baseline demand planning, loyalty projections and staff/permission checks.
- Preview session revocation, signed license/activation/branch policy diagnostics, safe offline grace reference models and isolated transaction authorization probes.
- Rehearsal/sandbox SQLite request journals; atomic sale/return simulations; stock history, tender declarations, returns, customer credit charges, repayments, allocations and notes.
- Earlier Windows local milestones include a documented **296 tests, 0 failures, 0 skips** at exact SHA da535008b708511fbb8cf64529e5c9d2fc983ebd, per docs/V8_COMMERCIAL_RELEASE_GATES.md. These do not certify later commits.
- The owner directed larger user-visible, verified vertical slices rather than repetitive tiny security-only changes and repeated local installation/test commands.

### November 5 and recent follow-ups
- Defensive SQLite crash/sidecar/schema/transaction integrity; journal exactly-once tamper tests; credit-note replay and allocation safety; stock-movement history checks; targeted receipt layout adjustment.
- Recent commits in the conversation include 099c5527 (foreign charge allocation ownership rejection), eeba1065 (foreign charge regression), 78a669c (duplicate stock move count rejection), 15ff3b0 (primary-key duplicate regression) and 8f8cd2e (foreign-charge test fixture starts reconciled).
- Since 8f8cd2e, other branch work continued; the inspected head for this history snapshot is 3ed6d8f7866f95111d221f4d309938f1fc5fb4d5. Never label an older assistant-reported SHA as latest without reading the branch.
- **Tests for the latest fixes are NOT known to have passed on Windows.** One historical wider local suite reported 612 tests, 6 failures, 66 errors and 77 skips before several repairs. Treat this as prior failure evidence, not current-head test output.

## Decisions that remain binding

1. Write only to develop-v8; no main merge, V7 overwrite, production data migration or real customer-key use without explicit, separately reviewed release approval.
2. Keep Qt checkout, actual money acceptance/refunds and stock posting disabled while Gates A and B are not accepted. A sandbox declaration/rehearsal is not a cash capture or real stock change.
3. Enforce authorization at trusted service boundaries, not only via disabled UI buttons. The original legacy services can be imported independently; Gate A must cover all entry points.
4. Core offline Windows sale operations must not depend on paid cloud/AI services.
5. Preserve original signing keys; never run keygen init for upgrade/test and never ship developer tools/secrets.
6. Prefer integrated features and exact-SHA regression evidence, recording errors, skips, Windows/Qt/hardware verification and owner acceptance.
7. Do not infer percent-complete from number of commits or unit tests. Previously quoted 35%-60% values are informal estimates, not measured acceptance.
8. Revisit proposed future releases (8.1 pharmacy, 8.2 salon/studio, 8.3 cloud, 8.4 AI) only after a safe retail/hardware V8.0 core is established; these are plans, not delivered SKUs.

## Recovered omissions, rework and risks

- V7-to-V8 feature-by-feature parity was never fully demonstrated; old README is not evidence that V8 Qt supports its full behavior.
- Cloudflare owner-summary upload must not be confused with tenant-safe multi-branch operational synchronization.
- Historical preview analytics and heuristics are not validated AI forecasting or audited profit/COGS.
- Payment/stock/recovery code hardening generated significant commits, but running current end-to-end POS sale/print/shift and full Windows suite still blocks commercialization.
- Hosted Windows Actions failures on recent commits often have no runner assigned and zero steps; no Python failure/success can be inferred from such metadata. The root cause is not yet verified.
- Older regression passes belong to their exact SHA and environment; later failures and missing PySide6/subprocess interpreter issues need retesting.
- UI visual acceptance, locale font shaping, scanner/printer behavior, installer and V7 data migration are unverified.
- Documentation and launch estimates were sometimes ahead of tested software. Keep both feature claims and progress numbers evidence-bound.

## Living records

- docs/V8_FEATURE_PARITY_MATRIX.md — legacy V7 claims vs V8 test preview vs commercial acceptance.
- docs/V8_VERIFIED_EVIDENCE_LEDGER.md — exact-SHA passes/failures, provenance and unresolved Actions failures.
- docs/V8_MISSING_WORK_CHECKLIST.md — actionable P0/P1/P2 acceptance backlog.
- docs/V8_MASTER_ROADMAP.md and docs/V8_COMMERCIAL_RELEASE_GATES.md — controlling product scope and hard release gates.
- docs/V8_AUTONOMOUS_PROGRESS.md — chronological engineering notes.

Update the three living records **after** meaningful verified milestones, not after every cosmetic edit. No data-less success claims.
