# VeloPOS 8.0 — repository instructions for coding agents

This file is persistent guidance for Codex and other agents working from the
**VeloPOS-8.0 repository root**. It is not permission to run unattended or to
perform destructive operations.

## Mission and source of truth

Deliver a commercially safe, offline-first Windows POS under the VeloPOS brand,
with optional cloud integrations, using existing Python/SQLite legacy code and
the isolated PySide6 V8 preview. The owner requires **zero mandatory spend**.

Read these files at the beginning of each development session, before deciding
what is already complete or what to change:

1. `docs/V8_CONSOLIDATED_PROJECT_HISTORY.md`
2. `docs/V8_FEATURE_PARITY_MATRIX.md`
3. `docs/V8_VERIFIED_EVIDENCE_LEDGER.md`
4. `docs/V8_MISSING_WORK_CHECKLIST.md`
5. `docs/V8_MASTER_ROADMAP.md`
6. `docs/V8_COMMERCIAL_RELEASE_GATES.md`
7. `docs/V8_FIVE_PHASE_EXECUTION_PLAN.md`
8. `docs/V8_AUTONOMOUS_PROGRESS.md` (read recent entries as relevant)

Check actual source and current Git HEAD; documentation is not a substitute for
execution evidence. The consolidated history was reconstructed from accessible
historical material, not every original ChatGPT message.

## Hard safety rules

- **Work only on branch `develop-v8`**. Before editing, check `git branch
  --show-current` and `git status --short`. If the branch is wrong, STOP
  before editing and request a safe branch switch; do not discard changes.
- Never edit, merge into, push or rewrite `main`, V7's production behavior or
  live customer databases without a separate explicit owner-approved release
  plan. Do not force push or mass-delete files.
- Do not run migrations, resets or destructive test commands against live DBs,
  synced production folders, customer data or original signing keys.
- Do not expose passwords, license private keys, service tokens or personal
  customer data in code, test fixtures, commits, telemetry or chat.
- **Real checkout, payment, refund and stock posting remain disabled.**
  Keep `can_checkout=False` and deny production actions until trusted service
  authorization and financial reconciliation are independently proven under
  commercial Gates A and B and a release decision is explicitly approved.
  An isolated sandbox rehearsal does not constitute safe commercial posting.
- Never treat UI-only checks as authorization; audit direct legacy financial
  service entry points and require persisted session, branch, shift, license,
  stock and idempotency validation inside one authoritative transaction.
- Keep optional cloud/Supabase outside the core Windows offline path. Supabase
  access is NOT currently required; do not request its credentials.
- The owner wants substantial, cohesive feature slices rather than a stream of
  unverified micro-commits or repetitive manual Windows commands.

## Execution and verification

1. Identify a narrow, high-value P0/P1 objective from the missing-work list.
2. Inspect source, test coverage and applicable acceptance gate before editing.
3. Prefer safe disposable fixtures and explicit no-production-writes assertions.
4. Implement the feature and targeted regressions, preserving legacy compatibility.
5. Run only tests available in this environment. If Windows/hardware tests are
   unavailable, mark **NOT EXECUTED**, never fabricate PASS.
6. For local Windows milestone tests use the documented safe isolated test
   runners; report interpreter/environment, exact SHA, tests run, failures,
   errors and skips. Distinguish an Actions job with no assigned runner/steps
   from Python test failure.
7. Update the evidence ledger and remaining-work checklist for meaningful
   milestones and append a concise progress note. Do not rewrite old evidence.
8. Commit only reviewed, intended files to `develop-v8`, or explicitly report
   if a commit was not made. Never stage secrets or production files.
9. Report what changed, source SHA, verified results, blockers, next task and
   checkout-off status. Speak to the owner in straightforward Sinhala and end
   development updates with "Continue කරන්නද?"

The ~60% development figure is unmeasured informal context, **not** a readiness
or acceptance score. Current commercial acceptance is **0/5 gates** until
evidence is updated by verified approval.

## Codex skill

For requests to continue VeloPOS development, review the project-local
`.agents/skills/velopos-development/SKILL.md` workflow and use it if available.
Starting a new session does not automatically restore full previous chat
transcripts; the GitHub docs are the canonical continuity ledger.
