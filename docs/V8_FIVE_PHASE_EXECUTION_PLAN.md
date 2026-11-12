# VeloPOS 8.0 — Five-phase integrated commercial execution plan

**Branch:** `develop-v8` ONLY. **Status:** execution plan, not a completion
claim. **Baseline:** `docs/V8_MASTER_ROADMAP.md` and
`docs/V8_COMMERCIAL_RELEASE_GATES.md` take precedence over this plan.

The five phases are consecutive **acceptance milestones**, not five releases
or an excuse to bypass dependency gates. Multiple implementation/test batches
may be needed inside each phase. A phase closes only with code, repeatable
regressions, exact-SHA Windows CI evidence, and every named exit condition
satisfied. Do not estimate completion percentages by intuition or by test
count alone; use the evidence table below.

## Phase 1 — Verified service boundary and safe transaction foundation

**Status: IN PROGRESS — not accepted.**

- Service-owned, persisted authentication/session checks at every original
  financial entry point; password rotation, deletion, demotion, role and
  permission revocation invalidate stale sessions.
- Canonical tenant/branch/shift identity rechecked under one caller-owned
  locked transaction; signed device/license/entitlement and activation
  continuity verified through trusted boundaries, with no embedded private
  signing secret.
- Persistent exactly-once request journal tied to the same atomic business
  transaction; safe crash, retry, concurrency and cross-branch behavior.
  Reconcile stranded or corrupted records rather than blindly retrying.
- Audit existing V7 public financial services and preserve V7 compatibility;
  do not switch V8 UI to these services until the reviewed service wrapper
  and all downstream acceptance requirements exist.
- Disposable SQLite tests: deleted/demoted actor, rotated password, forged
  identity, expired/revoked license, mismatched branch and shift, concurrent
  requests, crash before/after commit, DB path substitution, corrupted journal,
  untrusted UI bypass and immutable payload replay.

**Exit:** trusted service architecture and tests evidenced, including
independent review of boundary bypasses. **Gate A is still a hard blocker
until all its integrated invoice/accounting conditions also pass in Phase 2.**
Preview diagnostic booleans must never authorize checkout.

## Phase 2 — Complete core POS, inventory and financial reconciliation

**Status: NOT ACCEPTED.** Existing billing, return, tender and stock
rehearsals remain test-only and rollback-only.

- Single-transaction invoice, sale items, tax/discount/tender, receipts,
  batch/expiry/stock movements, cash/card/QR/credit, cashier shifts and audit.
- Purchasing/GRNs, supplier payments and advances; returns, partial refunds,
  void/reversal semantics, original COGS, loyalty and customer-credit ledgers.
- Canonical branch attribution and invariant-driven multi-day financial
  reconciliation against source ledgers, including historical/V7 copied data.
- Lossless backup/restore on disposable DB; concurrency, crash/failpoints,
  negative stock, mixed tenders, partial returns, rounding and migration.
- No user-visible real financial action until **all Gate A and Gate B
  evidence** is approved; a successful preview scenario is not approval.

**Exit:** exact-once durable write invariants and independent complete
accounting/stock reconciliation. **Gate A/B accepted with evidence**, not
just UI success.

## Phase 3 — Offline-first branches, secure cloud and owner dashboard

**Status: NOT PRODUCTION-READY.**

- Local-first journal with secure, authenticated tenant + server-issued branch
  identities; ordered incremental sync, deduplication, conflict policies,
  retries, reconnect, key rotation and stable reconnect after crash.
- Secured HTTPS backend, least-privilege owner read-only phone/PWA dashboard,
  data minimization, access/audit policies, backups, observability and
  retention. Owner dashboard must not use direct branch DB credentials.
- Test clock skew, duplicate uploads, offline periods, corrupt messages,
  concurrent edits, branch isolation, stale owner views and restore.
- Publish practical recurring hosting costs and free-tier limitations;
  do not imply offline equals instant cross-shop sync or free unlimited cloud.

**Exit:** **Gate C accepted** for cloud SKU. Offline POS must remain
functional without the cloud.

## Phase 4 — Commercial licensing, recovery and distribution safety

**Status: NOT PRODUCTION-READY.** Signed preview token inspection is not
a trusted entitlement service.

- External private signing key custody; signed activation/revocation,
  binding, renewal, limited offline grace, lawful legitimate device transfer,
  rate-limited server-authoritative trial continuity.
- Verified-email password reset with expiring single-use server tokens,
  enumeration resistance and rate limits; offline admin recovery policy.
- Windows installer/update signing where available, reversible migration,
  backup/restore, license compatibility, secret scanning, dependency/SBOM
  audit and safe upgrade rollback.
- Test expired/tampered/revoked tokens, rollback clocks, reinstall, deleted
  identities, offline grace, stolen token replay and transfer disputes.
- Production secrets, real paid licenses and customer data never used as
  development fixtures.

**Exit:** **Gate D accepted**, secure installer and restore evidence.

## Phase 5 — Premium UX, localization, hardware and final QA

**Status: NOT ACCEPTED.** Foundation Qt preview screens exist, but this
phase is reserved for final visual polish, not for papering over unsafe core.

- Premium theme, responsive scanner-first workflows, touch/keyboard input,
  accessible high-DPI layouts, dark/light modes, errors and recovery UX.
- Sinhala/Tamil/English translation and localization, accessibility,
  all preview navigation paths, receipt/printer/scanner and Windows profiles.
- Performance at representative scale, hardware/connectivity stress,
  clean install/upgrade/backup round-trip, real release-candidate exact-SHA
  no-skip Windows suite, malware and installer signing evidence.
- Issue the final manual acceptance checklist ONLY after Gates A-D have
  passed; retain user acceptance as an explicit final step.

**Exit:** **Gate E accepted** and all A-D complete; call the build
**READY FOR MANUAL QA**, not shipped. Declare completion only after
the owner accepts final manual QA.

## Evidence-ledger and non-negotiable controls

| Evidence | Currently verified | Open |
|---|---|---|
| Windows local preview suite | User ran 263 tests, OK, at code SHA `dd7ae38` | Rerun on latest head |
| GitHub-hosted Windows CI | Prior SHA `e19232a` had 245 tests PASS | Confirm push Actions on every exact newer head |
| Commercial Gate A | Preview session/signature/branch diagnostics and rollback rehearsals exist | Trusted service and real atomic posting, integrations |
| Commercial Gate B | Preview financial summaries and limited regressions | Full accounting/stock reconciliation |
| Cloud Gate C | Design/prototypes only | Secure deployable sync and dashboard |
| Licensing Gate D | Signed preview inspections | Real server authority, recovery, installer |
| Quality Gate E | Earlier 263-test local pass, no RC hardware evidence | Final Windows/hardware/manual QA |

**Current commercial acceptance:** **0/5 gates accepted**. The earlier
~35% development figure is an unmeasured informal estimate; it is not a
verified completion metric and should not be incremented just because
another test is added.

**Per-batch discipline:** read roadmap, gates, source, existing checkpoint
and CI; select highest-priority safe task; implement code + regression tests;
commit to `develop-v8` only; inspect exact-head Windows Actions and record
what was *actually* executed; update `docs/V8_AUTONOMOUS_PROGRESS.md` with
commit SHA, evidence, blocker and single next priority. No unattended
work claim without a configured automation. Never touch `main`, production
records, customer licenses, paid keys or any commercial post/checkout path
while Gate A/B are unapproved.

**Current next task:** finish Phase 1 by validating an immutable single-
snapshot sale request across canonical service/branch/license checks and
idempotency journal; obtain exact-head Windows CI and implement a
separately reviewed service-owned transaction boundary. Real posting
remains disabled.


## Delivery acceleration rule — vertical feature slices instead of micro-commits

**Owner constraint (2026-11-04):** The owner cannot repeatedly spend time
running local Windows suites or reviewing a stream of small security-only
batches. A 35% informal development estimate repeated after each batch is
not useful evidence and does not establish actual readiness.

- Deliver **end-to-end user-visible feature slices** and measure each by a
  demonstrable screen/workflow, its domain rules, regressions and independent
  acceptance evidence. Never pad the completion percentage for number of
  commits, lines of code or unit tests.
- Preserve Gate A/B service safety before enabling transactional POS.
  Continue backend integration inside feature slices; don't treat the
  safety blocks as permission to ship an unsafe workaround.
- For every `develop-v8` push, use
  `.github/workflows/v8-preview-windows.yml` to run an isolated Windows
  full-suite check with missing dependencies or skipped tests counted as
  verification failure. **Workflow has been committed but the hosted first
  run is not yet independently verified.** Do not ask the owner for routine
  local terminal runs between individual commits.
- Batch requests for owner time into a **single milestone demonstration
  and acceptance**. Owner decisions/manual hardware tests still matter at
  a real release gate, not at every code checkpoint.
- The immediate Billing Draft slice includes an in-memory receipt-style
  preview with estimated discount/cash/change and copy action; it is
  explicitly marked NOT A SALE and has no print or payment side effects.
  This is a user-visible preview increment, NOT completion of Phase 2
  financial posting.
- Milestone reporting must say **working/blocked/accepted** for the
  integrated feature and exact tested commit, rather than an arbitrary
  percentage. Overall completion remains **unmeasured** until the team
  maintains a weighted objective feature/acceptance ledger.

**Current highest-value deliverable after the draft receipt slice:**
a real, fully accounted sale path behind a service-owned authority
boundary in disposable V8 storage, with idempotent stock/receipts/tenders
and refunds integrated into the original service contract, then Gate A/B
independent reconciliation. Only once proven and accepted can checkout
be enabled. Cloud, licensing, premium UI and release gates follow the
five-phase dependency structure above.
