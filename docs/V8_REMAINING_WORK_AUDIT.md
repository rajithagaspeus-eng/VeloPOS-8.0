# VeloPOS 8.0 — Remaining-work audit and prioritized delivery

Branch audited: `develop-v8`. Scope: repository tree, roadmap, release gates,
transaction gateway and recent GitHub Actions runs. This is a **source-level
audit**, not an end-to-end functional certification. Do not treat it as a
production-readiness percentage.

## What exists

- PySide6 Windows preview pages for billing draft, inventory, reports,
  dashboard, purchasing, analytics, forecasts and directories.
- Test-only sale/return rehearsal, sandbox ledgers, signed-claim inspectors,
  idempotency and reconciliation experiments.
- A deliberately fail-closed `PreviewTransactionGateway`; no commercial
  checkout, payment, refund or supplier posting is enabled.
- Preview regression tests and GitHub Actions definitions. Test presence is
  **not** proof that the current branch passes.

## Critical CI discovery

The 2026-11-04 `develop-v8` runs for commit
`be109cefde852d4f3dd90acc45b3c2d8f4f5c68a` report **failure**:

- Windows preview tests: run 41917882158, job 126882284246.
- Sandbox regression: run 41917879483.
- The Windows job metadata reports `runner_id=0`, an empty runner name,
  **zero steps**, and completion within seconds. No test execution can be
  established from this job. The job log endpoint returned 404.
- The sandbox workflow returned no jobs in the queried run. Its failure also
  does not establish a Python test assertion failure.

These symptoms point to a workflow scheduling/configuration/runner availability
problem requiring investigation in GitHub Actions settings and run annotations.
They do **not** justify changing application logic blindly. The connected
GitHub API did not expose a definitive root-cause message. Verify runner
eligibility and account Actions limits before treating CI as a code regression.
No production credentials or payments are required to run the local tests.

## Priority order

| Priority | Workstream | Acceptance evidence needed |
| --- | --- | --- |
| P0 | Restore reproducible CI | Runner starts, executes compile and tests; full Windows suite 0 failures, 0 skips at exact SHA |
| P0 | Transaction integrity (Gate A) | Service-side authenticated commercial session, license, shift, stock, price, tax and exactly-once commit; adversarial tests |
| P0 | Financial/inventory correctness (Gate B) | Invoice COGS, returns, taxes, loyalty, stock batches and accounting reconciled against disposable fixtures |
| P1 | Commercial licensing (Gate D) | Server-authoritative activation, expiry, offline grace, recovery, migration and installer acceptance |
| P1 | Branch/offline sync (Gate C) | Tenant isolation, conflict resolution, authenticated queue, replay and secure mobile reporting |
| P1 | Windows UX and release (Gate E) | Scanner/receipt/peripheral, keyboard, DPI, Sinhala/Tamil, accessibility, signed installer and upgrade QA |

## Changes in this batch

- Added `velopos_qt.release_readiness` for a deterministic, machine-readable,
  **fail-closed** snapshot of all five commercial gates.
- Added unit and CLI tests for immutable gates, report isolation, and explicit
  `can_checkout=false` / `production_ready=false` signals.
- Wired the release-gate report into sandbox CI artifact generation.
- Preserved all V7, `main`, production data and commercial licensing behavior.

## Next implementation milestone

First obtain a runner-executed Windows test result for the exact latest
`develop-v8` SHA. Then address actual failures and build the trusted
commercial transaction service behind an explicitly disabled release gate,
using disposable data until all Gate A/B acceptance criteria are proven.

## CI follow-up and sale service implementation (2026-11-05)

- The latest inspected Windows run `41919490086` reports failure with
  `runner_name=""` and `steps=[]`. Sandbox run `41919504663`
  exposes `jobs=[]`. This confirms **no executed test result is available**
  for these runs; it does not confirm a Python regression failure.
- Prior CI test code contained a stale expectation that `sale_void` was an
  unknown assessment action even though that action had been implemented.
  The stale test was corrected.
- Added `sale_request_service.py`: deterministic, side-effect-free draft
  arithmetic, canonical SHA-256 request fingerprint, and an unconditional
  mandatory-deny `commit()`. It neither accesses production data nor grants
  checkout permission.
- Integrated read-only rehearsal into `PreviewTransactionGateway` and added
  unit/integration regressions. Both CI workflows now include its unit suite.
- **Action needed for CI**: inspect GitHub Actions run annotations and account
  runner eligibility/billing limits; re-run only when runners can actually
  start. A zero-step run cannot certify tests. Do not weaken security gates
  to make a CI badge green.

## Durable rehearsal integrity follow-up (2026-11-05)

- Hardened the disposable SQLite rehearsal ledger to check every stored
  reference against its contiguous sequence and to reject missing rows,
  sequence rewinds/jumps, and forged references before replay.
- Added SQLite `PRAGMA quick_check` to the preview-only inspection transaction.
- Added four tampering regressions: deleted middle row, sequence rewind,
  sequence jump, and forged reference.
- Retried GitHub Actions Windows run `41920582409` through the connected
  GitHub API. Attempt 2 also completed **failure** with no runner assigned
  and zero executed steps. No Python test outcome is available from that run.
- Root cause remains unconfirmed without GitHub Actions account/organization
  runner eligibility, billing/usage and workflow annotation visibility.
  Do not classify this as a Python test failure or claim passing tests.
- This journal is **not** a production transaction ledger: it contains only
  disposable rehearsal references and cannot post sales.

## Preview journal schema-hardening batch (2026-11-05)

- Added strict SQLite schema-object allowlisting to the disposable durable
  rehearsal journal. Unexpected triggers, views, tables and columns are
  rejected both at initialization and before each journal transaction.
- Added regression tests for a pre-existing trigger, extra view/table,
  altered columns, and a trigger injected after journal construction.
- Retried Windows Actions run `41921621446`. Attempt 2 again finished
  `failure` with `runner_name=""` and `steps=[]`; therefore **no Python
  test was executed in that job**. A prior job-log download returned 404
  (missing log blob). This is not evidence of an application assertion failure.
- Next CI diagnostic requires Actions job/check annotations and repository
  runner/account eligibility information not exposed by the current job
  metadata. Do not declare a runner/billing root cause without those details.
- The durable journal remains **test-only** and cannot authorize checkout.

## Atomic journal initialization and recovery follow-up (2026-11-05)

- Journal initialization now runs in an explicit `BEGIN IMMEDIATE`
  transaction with commit/rollback and prevalidates existing column layouts
  before any initialization writes.
- Existing rehearsals with a missing sequence row are rejected rather than
  silently repaired. New regressions check lost sequence, malformed schema,
  conflicting request rollback, and corrupted sequence rollback.
- GitHub Actions run `41922033188` was retried via the connected API.
  Attempt 2 completed with `failure`, no assigned runner, and zero job
  steps. Actual repository regression tests **did not execute on Actions**.
  Local GitHub checkout was also unavailable in this environment because
  the container could not resolve github.com.
- The exact runner failure root cause is still unknown; it requires access
  to Actions account/organization policy, usage, and run annotations.
- Do not interpret this test-only rehearsal ledger as certified production
  crash recovery or permission to enable checkout.
