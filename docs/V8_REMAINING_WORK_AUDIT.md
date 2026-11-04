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

## Durable preview schema constraints and CI follow-up (2026-11-05)

- Hardened the disposable journal connection with SQLite
  `trusted_schema=OFF` and `foreign_keys=ON`.
- Refuse silent reconstruction of a missing sequence even when the existing
  journal contains zero requests. Enforce request primary keys and unique
  reference index in addition to column-name checks.
- Added three regressions covering empty-ledger sequence deletion, missing
  reference uniqueness and missing request primary key.
- Windows Actions run `41923058146` was retried: attempt 2 again ended
  in `failure`, `runner_name=""`, `steps=[]`. GitHub Actions has not
  produced executable Python test output for this batch.
- A direct container checkout attempt could not resolve `github.com`.
  Root cause of runner allocation failure remains unconfirmed; investigate
  repository Actions permissions and runner eligibility in GitHub UI.
- These checks protect disposable test rehearsals only; no production
  transaction authorization is provided.

## Disposable database file-identity defense (2026-11-05)

- Pin the temporary rehearsal SQLite file's device/inode after initialization;
  reject subsequent path substitution, symlinks, hard links and missing files.
- Verify the main SQLite database path on reopened connections.
- Added two regressions for replacement database and symlink substitution.
- GitHub Actions Windows run `41923359470` was retried (attempt 2).
  The latest observed job metadata had no assigned runner and zero steps.
  Repository Actions permissions and runner endpoints are inaccessible through
  the current GitHub connector, so runner root cause remains **unconfirmed**.
- No claim is made that the newly added tests executed or passed.
- Inode checks are defense-in-depth, not a guarantee against every filesystem
  race; production database posting remains disabled.

## Durable journal error handling and SQLite local checks (2026-11-05)

- Fixed journal initialization to validate file identity before commit,
  and avoid masking an original error by rolling back after commit.
- Added validation for required NOT NULL declarations and all persisted
  request ID formats; three additional repository regression cases cover
  these error paths.
- Executed **three standalone SQLite stdlib tests locally**, all PASS:
  transaction rollback, rollback of uncommitted work on connection close,
  and SQLite schema/index PRAGMA inspection. These are NOT the repository's
  VeloPOS regression tests and do not establish VeloPOS test pass status.
- GitHub Actions Windows run `41924230708` attempt 2 completed
  `failure`, runner empty, steps zero. Job log download for the earlier
  run failed with HTTP 404 (BlobNotFound). No Python test output exists.
- Repository Actions permissions/runners endpoints remain inaccessible via
  connector; root cause is not yet proven.
- This remains a disposable preview-only ledger, not production checkout.

## Abrupt process crash regression coverage (2026-11-05)

- Added subprocess-based SQLite crash tests that terminate the child with
  `os._exit` before and after COMMIT. The first must recover with no
  persisted row/sequence gap; the second must replay the committed request
  and issue the next contiguous reference.
- Set `PRAGMA synchronous=FULL` on preview journal connections and added
  a focused regression for that setting.
- These new repository tests are committed but **not yet executed**: a direct
  GitHub clone in the test container fails DNS resolution of github.com.
  GitHub Actions run `41925586307` was retried; its last observed state
  was queued attempt 2 with no runner and zero steps.
- The preceding run had failed with zero steps and no runner, and its
  log blob was unavailable. Actions runner/account policy root cause
  remains unconfirmed.
- Tests simulate abrupt process termination, not power loss or storage
  hardware failure. All paths remain disposable and checkout remains denied.

## Executed dependency-free crash contract and sequence CHECK hardening (2026-11-05)

- Added `tests/test_v8_sqlite_crash_contract.py`, a dependency-free
  subprocess SQLite test module. Its identical source was executed locally:
  `python -m unittest -v tests/test_v8_sqlite_crash_contract.py`
  produced **3 tests, 0 failures**. This verifies SQLite rollback, committed
  state recovery and uniqueness only, not the VeloPOS application integration.
- Both Windows and Linux CI workflows now explicitly run the new module.
- Durable rehearsal journal now checks SQLite sequence CHECK declarations
  on initialization and every inspect; two application regression tests cover
  removed constraints on reopen and after journal construction. These two
  application tests have NOT been executed locally.
- GitHub Actions Windows run `41926776026` was observed queued with no
  runner/steps. Linux run `41926773698` failed with no jobs. Repository
  runner/permissions and check-annotation API endpoints are blocked by
  connector allowlisting (HTTP 400 INVALID_ARGUMENT), so the root cause
  cannot be proven from available telemetry. Local git checkout cannot
  resolve github.com.
- All tests and database work remain preview-only. Production transaction
  posting remains disabled.

## Strict schema and index integrity follow-up (2026-11-05)

- The preview SQLite journal now rejects hidden/generated columns
  (`PRAGMA table_xinfo`), foreign keys, and extra/altered index signatures.
- Replaced `PRAGMA quick_check` with full `PRAGMA integrity_check`
  before every journal replay or append, so index consistency is checked.
- Four new application regression methods cover generated columns, foreign
  keys, injected indexes and integrity after restart/replay. These are
  committed but have **not** run as a repository suite.
- A local standalone SQLite probe verified canonical primary/unique index
  signatures, detection of extra indexes, and detection of generated columns
  (PASS); this is **not** a VeloPOS application test.
- GitHub Actions run `41926999203` completed failure with no runner
  and zero steps; sandbox run `41926997239` completed failure with no jobs.
  Permissions/runner diagnostics are unavailable through the connected
  GitHub API allowlist, and direct checkout failed DNS resolution. Therefore
  runner root cause and application regression PASS remain unverified.
- No V7/main, commercial checkout, or production database changes.

## Journal CAS, multi-process idempotency and SQLite schema filter (2026-11-05)

- Sequence advancement now uses a guarded `UPDATE ... WHERE next_number=?`
  and checks `rowcount == 1`, aborting on a failed compare-and-swap.
- Added a 24-writer distinct-request concurrency/restart regression and a
  four-subprocess same-request idempotency regression. These are application
  tests committed to the branch, **not yet executed**.
- Corrected `sqlite_master` filtering from `NOT LIKE 'sqlite_%'` to
  `NOT GLOB 'sqlite_*'`. SQLite LIKE treats underscore as a wildcard,
  allowing a `sqliteX...` table to evade the old object allowlist.
  A direct local sqlite3 reproduction confirmed the old predicate missed
  the table and the new predicate found it; this is a standalone SQL
  reproduction, not a full application regression run.
- Added strict TEXT/INTEGER column declaration validation and tests for
  altered BLOB fingerprint columns and `sqliteX` extra objects.
- GitHub Actions run `41927393618` failed before runner allocation:
  runner empty, steps zero; Linux run `41927391264` failed with no jobs.
  Runner failure cause remains unknown because administrative diagnostic
  endpoints are blocked by the GitHub connector. Git clone cannot resolve
  github.com in the available container, preventing repository suite execution.
- Preview only. No main/V7/production changes and no commercial posting.

## Canonical SQLite DDL and recovery atomicity follow-up (2026-11-05)

- Durable journal now checks complete normalized canonical CREATE TABLE DDL
  for both preview tables on initialize and every inspect. This rejects
  unexpected CHECK constraints and comment-spoofed required checks; unlike
  previous regex-only checks, it is not satisfied by a matching comment.
- Three new application regressions cover injected CHECK, spoofed sequence
  CHECK comments, and fail-closed schema-tamper rollback followed by
  repaired-journal replay and contiguous next reference.
- Verified locally with sqlite3 that SQLite stores the normalized canonical
  CREATE TABLE text without the original IF NOT EXISTS clause. This is
  a standalone SQLite compatibility check, not a VeloPOS regression PASS.
- Latest available Windows Actions run `41927782959` failed with no
  assigned runner, zero steps; Linux run `41927799678` failed with
  zero jobs. Fetching Windows job logs returned HTTP 404 BlobNotFound
  and job steps returned []. GitHub connector rejects administrative
  runner/permissions API endpoints. Root cause cannot be confirmed.
- Repository regression suite has not executed; container GitHub checkout
  still fails DNS resolution. No production financial writes or V7/main edits.

## Internal SQLite metadata and pre-commit inode guard (2026-11-05)

- Added a fail-closed check for unexpected `sqlite_*` schema objects
  while permitting SQLite's two legitimate autoindexes on the
  `preview_rehearsals` table. This detects `sqlite_stat1` created by
  `ANALYZE` and refuses untrusted internal metadata before journal writes.
- Added an inode identity recheck immediately before `inspect` COMMIT.
  A mismatch aborts the transaction, preserving the request/sequence pair.
- Two new repository regression methods cover `sqlite_stat1` refusal
  and simulated precommit identity failure with rollback and retry.
- Executed three **standalone Python sqlite3 tests locally**, all PASS:
  canonical autoindex recognition, `ANALYZE` metadata detection and
  atomic rollback of request plus sequence. These are NOT VeloPOS
  application tests and do not establish repository regression PASS.
- Windows Actions run `41928421205` failed in two seconds (22:48:13
  to 22:48:15 UTC) with empty runner name and zero steps. Linux
  `41928419169` failed with zero jobs. This is consistent with a
  pre-execution CI provisioning/configuration failure, but the actual
  account/runner root cause is not accessible through the connector.
  Full application regression execution remains blocked by GitHub
  Actions and container github.com DNS failure.
- Preview-only changes. Main/V7/production data/commercial posting untouched.

## Preview journal mode and fault-injection follow-up (2026-11-05)

- Corrected precommit inode fault-injection test: the second identity check
  during inspect is the pre-COMMIT check; previously the test targeted a
  nonexistent third call. This fixes a test defect, not a verified PASS.
- SQLite preview connections now reject non-DELETE journal modes (including
  WAL) to avoid unpinned `-wal`/`-shm` persistence; the code does not
  silently rewrite a database's journal mode. Added a regression asserting
  WAL refusal leaves the ledger row count and sequence unchanged.
- Executed local stdlib sqlite3 compatibility checks for default DELETE
  mode and WAL switching (PASS), but these are not the application's
  repository test suite.
- The latest available Windows run `41928502888` failed with runner
  empty and zero steps; its job requested `windows-latest`. Linux
  workflow `41928500689` failed with zero jobs. Repository metadata
  reports private=true, archived=false, disabled=false, admin=true.
  This narrows investigation to GitHub Actions scheduling/account/workflow
  configuration, but does not establish a specific root cause.
- GitHub cannot be resolved by DNS in the local container, and the
  GitHub connector provides file APIs but no executable checkout/test
  runner. Consequently the current application regression suite remains
  UNEXECUTED, not PASS. Production/V7/main unchanged.

## SQLite transaction contract and runner investigation (2026-11-05)

- Fixed a prior incorrect change to the precommit fault-injection test:
  `_connect` checks inode identity before and after opening the DB, so
  the actual pre-COMMIT check is the THIRD `_identity()` call.
- Added `tests/test_v8_sqlite_transaction_contract.py` with four
  dependency-free SQLite checks: WAL mode detection, atomic rollback
  of insert+sequence, abrupt subprocess exit before COMMIT, and
  `sqlite_stat1` metadata detection. Added it to both V8 CI workflows.
- A locally executed equivalent standalone SQLite script completed
  **4 tests PASS, 0 failures**. The GitHub-committed test file itself
  has not been executed on a checked-out repository; do not conflate
  equivalent local tests with actual application regression suite.
- GitHub Actions private repository metadata confirms admin access and
  that the repository is neither disabled nor archived. The latest
  Windows jobs have empty runner_name and zero steps, while Linux
  workflow runs have no jobs. Root cause cannot be confirmed without
  GitHub Actions account/billing/runner or workflow-validation diagnostics.
- Full VeloPOS application regression suite still not executed in this
  environment. No changes to main, V7 or production data.
