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

## DDL regression fix and crash-after-commit contract (2026-11-05)

- Discovered and fixed a real application defect: canonical DDL normalization
  accidentally used regex `r"\\\\s+"` (literal backslash-s) instead of
  `r"\\s+"` (whitespace). The bug caused valid initialized preview
  journals to be rejected on reopen. Added a repository regression that
  checks SQLite's retained newlines, reopen and idempotent replay.
- Executed a direct local SQLite DDL reproduction: valid table DDL
  normalization PASS with the corrected regex, FAIL with the old regex.
  This is a focused SQL/regex reproduction, not the application suite.
- Added a crash-after-COMMIT subprocess test to the dependency-free
  SQLite contract, checking both request row and sequence durability
  and full `PRAGMA integrity_check`.
- Executed local equivalent SQLite contract tests: **5 PASS, 0 FAIL**,
  including crash before and after COMMIT. This is not a checked-out
  VeloPOS application regression run.
- Windows run `41935712645` still fails with empty runner and zero
  steps; Linux `41935710879` fails with no jobs. GitHub Actions
  permissions/runner/billing diagnostics remain inaccessible via the
  connector; root cause is not confirmed.
- No main/V7/production changes. Commercial checkout remains blocked.

## Actual local SQLite regression execution and pinned-file no-create (2026-11-05)

- Actually ran the existing local SQLite contract modules using
  `python -m unittest -v test_sqlite_transaction_contract tests.test_v8_sqlite_crash_contract`:
  **8 tests executed, 8 PASS, 0 FAIL, 2.662s**. The local modules
  are SQLite contracts, not the entire VeloPOS application regression suite.
- Added 8-process distinct-request concurrent journal regression asserting
  exactly eight gapless references, sequence=9, and idempotent reopen.
- Once a journal is pinned, `_connect` now uses SQLite URI `mode=rw`
  to prohibit silently recreating a deleted database. Initial disposable
  journal creation still uses normal sqlite3 connect. Added two application
  tests for deletion/no recreation and explicit read-write URI.
- Local `git ls-remote https://github.com/rajithagaspeus-eng/VeloPOS-8.0.git HEAD`
  failed: `Could not resolve host: github.com`. No repository checkout,
  hence no claim that the complete VeloPOS application suite ran.
- Windows Actions run `41936262256` failed with no runner assigned and
  zero steps; Linux `41936260144` failed with zero jobs. GitHub connector
  explicitly rejected actions/permissions and actions/runners endpoints.
  Root cause remains unknown; workflow YAML and requested windows-latest /
  ubuntu-latest labels have been inspected. Investigate GitHub Actions
  billing/runner provisioning and workflow validation in repository UI.
- main/V7/production data and commercial checkout unchanged.

## SQLite sidecar pre-open security and CI root-cause investigation (2026-11-05)

- Hardened `DurablePreviewSaleJournal._connect` with pre-open
  `-journal`, `-wal`, `-shm` sidecar validation. Reject symlinks,
  hardlinks and nonregular existing sidecars before SQLite may read or
  write those paths. Regular single-link hot rollback journals remain
  permitted for crash recovery.
- Added repository application regressions for all three symlink
  sidecars, hardlinked rollback journal, untouched external target and
  unconsumed request sequence.
- Executed **8 actual local standalone SQLite contract tests** via
  `python -m unittest -v test_sqlite_transaction_contract tests.test_v8_sqlite_crash_contract`:
  8 PASS, 0 FAIL, 3.048 seconds. These are NOT the checked-out
  VeloPOS application regression suite; the new sidecar tests are
  committed but have not been executed.
- Windows Actions run `41937890160` failed with runner_name empty and
  zero steps; Linux `41937888328` failed with zero jobs. Fetching
  Windows job `126950902142` logs returned GitHub storage
  `404 BlobNotFound`. This supports failure before normal step log
  generation, but **does not identify** the underlying cause.
  GitHub Actions account billing/runner allocation/workflow validation
  needs checking in GitHub UI; connector cannot access these settings.
- Full repository application regression remains blocked by private
  repo checkout DNS resolution and unavailable GitHub Actions runners.
  main/V7/production and commercial checkout unchanged.

## Sidecar open-race regression and CI scheduling evidence (2026-11-05)

- Added a second `_check_sidecars()` after sqlite3.connect, before
  journal transactions, narrowing the pre-open sidecar substitution
  window. This does NOT eliminate a fully adversarial filesystem TOCTOU
  race; OS-level secure directory ownership or fd-based safeguards
  would be needed for a stronger guarantee.
- Added application regression that injects a symlinked rollback
  journal between the initial check and connect completion and
  requires fail-closed behavior, unchanged external target and no
  consumed preview row. Windows symlink privilege restrictions skip
  this one test explicitly.
- Windows Actions run `41939391326` failed in roughly two seconds
  (started 00:10:53Z, completed 00:10:55Z) with runner_name empty and
  zero steps. Linux `41939389325` reported zero jobs. This strongly
  points to a pre-execution scheduling or workflow-level failure,
  not an application test assertion; root cause is still unconfirmed.
- No checked-out VeloPOS application regression execution was
  possible in this environment; newly committed application tests
  remain UNEXECUTED. Earlier local SQLite contract results must not
  be presented as current application suite results.
- main/V7/production unchanged; V8 is noncommercial test-only.

## Dangling SQLite sidecar protection and runner isolation (2026-11-05)

- Changed preview sidecar inspection from separate `is_symlink()` /
  `exists()` / `stat()` calls to one `lstat()` and a regular-file
  mode/hardlink check. This fails closed on dangling symlinks and
  directory sidecars, and reduces metadata check race windows.
- Added two application regressions: dangling rollback sidecar symlink
  and rollback sidecar directory, each requiring refusal before
  request/sequence mutation. Tests committed, not locally executed.
- Added `.github/workflows/v8-runner-diagnostic.yml`: a minimal
  ubuntu-latest job with no checkout, Python setup, or dependencies.
  It runs on changes to its own file or manual dispatch and will
  distinguish runner allocation failures from app/dependency failures.
  Await its run result before attributing a specific root cause.
- Latest observed Windows `41939814662` and Linux `41939812993`
  still fail before application test execution. Existing evidence
  remains insufficient to identify a definitive GitHub Actions cause.
- Private repository clone remains blocked by DNS in the execution
  environment. Full VeloPOS application suite NOT executed, and no
  new test pass counts are claimed. main/V7/production untouched.

### Diagnostic result

- Minimal no-checkout `V8 runner allocation diagnostic` run
  `41939831430` failed. Job `126957490685` has
  `runner_name=""`, `steps=[]`, and failed in ~2 seconds
  (00:14:23Z–00:14:25Z). This rules out VeloPOS imports, pip
  dependencies, checkout, and application regression tests as the
  cause of this diagnostic failure. It strongly localizes the problem
  to GitHub Actions workflow admission / runner provisioning / account
  limits, **without distinguishing which**. Check repository Actions
  settings, organization policy and account billing/spending limits
  in GitHub UI; connector does not expose these endpoints.

## Pre-COMMIT sidecar race defense and current test evidence (2026-11-05)

- Revalidate all SQLite preview sidecars immediately before COMMIT,
  in addition to pre-connect and post-connect checks. The guard
  refuses a symlinked, hard-linked or nonregular sidecar discovered
  while the preview write transaction is open.
- Added application regression that injects a malicious `-shm`
  symlink at the third sidecar check (pre-COMMIT), verifies rollback
  of both the row and sequence, confirms external target unchanged,
  and retries the request with reference 00000001. Test committed
  but **not executed** in the application suite.
- Re-executed the locally available standalone SQLite contract
  modules: **8 tests, 8 PASS, 0 FAIL, 2.927 seconds**. These are
  equivalent local copies of the SQLite-only contract tests, NOT a
  checkout of the current VeloPOS repository or the actual application
  regression suite. `git ls-remote` still fails DNS resolution for
  github.com in the execution container.
- The no-checkout GitHub runner diagnostic `41939831430` already
  failed with zero steps and no runner; this establishes a
  pre-application GitHub Actions failure but does not identify the
  precise account/runner/workflow admission cause. Account settings
  and runner provisioning must be inspected with GitHub admin access.
- Filesystem TOCTOU cannot be fully prevented by pathname checks
  alone; a private owned temporary directory / OS-level handle
  security would be a stronger long-term design.
- No main/V7/production modifications; checkout remains disabled.

## Initialization transaction sidecar hardening (2026-11-05)

- Extended pre-COMMIT sidecar validation to the constructor's
  `BEGIN IMMEDIATE` initialization transaction. This protects the
  first schema creation and sequence insertion as well as subsequent
  `inspect()` writes.
- Added application regression that injects a `-shm` symlink at
  the constructor's third sidecar check, expects PermissionError,
  verifies no schema tables were committed, then reopens and creates
  the first gapless preview reference. External target stays unchanged.
- Latest workflow runs `42000708761` (Windows: empty runner, zero
  steps) and `42000706431` (Linux: zero jobs) fail before any
  application test. The independent no-checkout runner diagnostic
  `41939831430` also failed before steps. This rules out application
  test failures as the cause of that diagnostic run, but not the exact
  GitHub Actions admission / account / runner policy root cause.
- Full actual VeloPOS application suite and this new test remain
  UNEXECUTED; private GitHub checkout is unavailable in local
  execution environment. No new test-pass count is claimed.
- No main/V7/production changes. Commercial checkout remains disabled.

## Four-stage sidecar validation and execution blocker (2026-11-05)

- Added a fourth `_check_sidecars()` immediately after SQLite
  connection PRAGMAs, before yielding a connection to initialization
  or inspection. Existing pre-connect, post-connect and pre-COMMIT
  checks remain. This narrows but cannot eliminate pathname TOCTOU.
- Updated both pre-COMMIT sidecar fault-injection tests to inject on
  the fourth check, and added an explicit success-path regression
  asserting all four checks run for `inspect()`.
- Current Windows run `42000924210` still fails with zero steps
  and no assigned runner; Linux `42000922247` reports zero jobs.
  Independent no-checkout runner diagnostic `41939831430` also
  failed without any steps. Precise GitHub account/workflow admission
  cause remains unconfirmed; inspect GitHub Actions UI billing,
  repository Actions settings and organization policies.
- Local `git ls-remote` for the private repository still fails
  with `Could not resolve host: github.com`. Only a Python SQLite
  runtime smoke check was executed this batch; **no VeloPOS
  application tests were executed**, so no application PASS count
  can be claimed. Do not conflate previous SQLite-only contract
  tests with this branch's full regression suite.
- main/V7/production and commercial checkout remain unchanged.

## Constructor integrity gate (2026-11-05)

- Added `PRAGMA integrity_check` inside the constructor's
  `BEGIN IMMEDIATE` transaction, before schema/sequence COMMIT.
  This prevents a successful initialization commit when SQLite reports
  structural corruption, complementing the existing inspection gate.
- Added an application fault-injection regression returning a simulated
  corrupt integrity result after schema creation. It asserts
  `PermissionError`, no committed schema, and a successful clean
  retry with first preview reference 00000001.
- Executed a local stdlib SQLite initialization integrity/rollback
  **smoke test: PASS**. This is NOT the VeloPOS application suite,
  nor the newly committed application regression; those remain
  UNEXECUTED because private repository checkout cannot resolve
  github.com from the local container.
- Windows run `42001842147` again failed without runner or steps;
  Linux run `42001839686` has zero jobs. The earlier minimal
  no-checkout diagnostic `41939831430` also failed with no runner.
  This excludes VeloPOS application execution as the cause of that
  minimal diagnostic's failure. Exact account/organization policy,
  spending limit, runner provisioning, or workflow admission reason
  is not available via connector; do not claim a confirmed cause.
- No main/V7/production data touched; checkout remains disabled.

## Exact repository SQLite regression execution and pinned-inode lstat (2026-11-05)

- Fetched `tests/test_v8_sqlite_transaction_contract.py` from
  `develop-v8`, copied its complete exact source into a disposable
  local test directory, and executed
  `python -m unittest -v tests.test_v8_sqlite_transaction_contract`:
  **5 PASS, 0 FAIL, 1.527 seconds**. These are genuine repository
  SQLite contract test cases executed locally, but not a checked-out
  repository or the full VeloPOS application suite.
- Hardened pinned database `_identity()` with a single `lstat()`,
  refusing symlinks (including dangling ones), nonregular files,
  missing paths and hardlinks before returning device/inode identity.
  Added application regression for a pinned database replaced by a
  dangling symlink, asserting fail-closed and no target creation.
  This new application test is **committed, not executed**.
- Latest Windows Actions run `42002193662` has zero steps and no
  assigned runner; Linux `42002191214` has zero jobs. The minimal
  independent no-checkout diagnostic `41939831430` also failed
  with no runner, so its failure cannot originate in VeloPOS tests
  or dependency installation. Exact account/runner/workflow admission
  root cause still requires GitHub account/admin UI evidence.
- Remaining priority: run full `tests.test_v8_durable_sale_rehearsal`
  and combined `run_v8_checks.py` against an actual checked-out
  branch, investigate GitHub account spending and Actions policy,
  and preserve fail-closed commercial boundaries.
- main/V7/production untouched.

## Executed SQLite transaction contracts and constructor sequence invariant (2026-11-05)

- Added two stdlib-only repository SQLite contract tests:
  crash after inserting the replay record but before advancing sequence,
  and a failed sequence compare-and-swap followed by rollback.
  Copied the same test source into the local repository-test fixture
  and ran `python -m unittest -v tests.test_v8_sqlite_transaction_contract`:
  **7 PASS, 0 FAIL (2.251 seconds)**. The tests cover actual SQLite
  transaction semantics, not the application journal class.
- Constructor now checks the singleton sequence is exactly one row
  with integer singleton 1 and next_number = committed record count + 1,
  within allowed range, before its transaction COMMIT. This rejects
  ahead-of-record corrupted sequences rather than committing
  initialization over inconsistent application state.
- Added a VeloPOS application regression that corrupts next_number,
  verifies constructor refusal and no silent repair, then verifies
  inspect refusal. **This application test and the full VeloPOS suite
  are not executed**; private repo clone fails DNS resolution.
- Latest Windows Actions run `42002679961`: runner_name empty,
  steps empty, failure. Linux `42002699446`: jobs empty, failure.
  Previous minimal no-checkout runner diagnostic `41939831430`
  likewise failed before steps. This supports a pre-execution GitHub
  Actions provisioning/admission problem but does NOT establish its
  definitive root cause. Account Actions settings/billing/organization
  policy must be inspected via an authorized admin UI.
- No main/V7/production changes; commercial posting remains blocked.

## Constructor replay-data integrity gate (2026-11-05)

- Added constructor-time validation of every persisted replay
  request ID, SHA-256 fingerprint, reference syntax, uniqueness and
  gapless reference chain. Constructor already checked full SQLite
  integrity and sequence count; this closes the gap where a database
  with the correct row count but forged replay contents could pass
  constructor initialization before inspect rejected it.
- Added application regression tests for a malformed persisted
  fingerprint and a noncontiguous reference, verifying constructor
  rejection and unchanged SQLite rows/sequence. These are committed
  but **not executed**.
- Full durable sale rehearsal application suite and `run_v8_checks.py`
  remain **UNEXECUTED** in this batch: the private repository cannot
  be cloned into the local runner because github.com DNS resolution
  fails, and GitHub Actions does not start jobs. No application PASS
  claim is made.
- Windows Actions run `42002982113` was still queued without a
  runner at inspection; Linux run `42002979908` failed with zero
  jobs. Prior Windows failures showed zero steps/no runner and the
  independent minimal no-checkout workflow also failed before steps.
  Root cause is NOT definitive; repository/org Actions permissions,
  runner entitlement and billing/usage must be checked by an account
  admin. Do not attribute the zero-step failure to VeloPOS tests.
- No changes to main, V7, production data or commercial checkout.

## Initial entry lstat hardening and Actions access limits (2026-11-05)

- Replaced constructor's initial `exists()/is_file()/stat()`
  checks with a single `lstat()` on the SQLite path, rejecting
  symlinks (including dangling ones), directories, and hardlinks
  before SQLite opens the preview file. Added an application
  regression asserting a dangling symlink is rejected without
  creating its external target. The test is **committed but unexecuted**.
- Latest Windows run `42005434469` failed with no runner and
  zero steps; Linux `42005432389` failed with zero jobs.
  Attempts to inspect repository Actions permissions/runners and
  account billing via available GitHub API connector were rejected
  as unsupported endpoints. Therefore definitive root cause is
  **not established**. Account owner should check repository
  Settings > Actions > General and account billing/usage and any
  spending limit, plus GitHub Actions service notices.
- **Full VeloPOS durable sale rehearsal application suite and
  `run_v8_checks.py` not executed this batch.** Repository access
  through connector permits source edits but does not provide a
  runnable checkout in the local environment; GitHub-hosted jobs
  are failing before starting. Do not report application PASS.
- No changes to main/V7/production data; preview checkout stays disabled.

## Concurrency contract and FULL synchronous enforcement (2026-11-05)

- Added 32-thread / 8-worker independent SQLite connection
  contract verifying serialized `BEGIN IMMEDIATE` claims, gapless
  references 1..32, CAS sequence 33 and `integrity_check=ok`.
  An equivalent locally constructed executable test using the
  exact transaction operations **passed: 1 test, 0.250s**.
  This is **not** a run of the actual checked-out repository test.
- Application `_connect` now reads back `PRAGMA synchronous`
  and requires value 2 (FULL) after setting it; a successful
  setter call alone does not prove durability. Added a regression
  injecting a connection that reports NORMAL (1), expecting
  PermissionError and unchanged records/sequence. **Application
  regression not executed.**
- Latest Windows Actions `42006131775`: failed, zero steps,
  runner_name empty. Linux `42006157550`: failed, zero jobs.
  Independent no-checkout diagnostic previously failed likewise.
  GitHub API access to account billing/runner policy endpoints
  remains unavailable. No definitive runner failure root cause.
- Full VeloPOS application regression suite remains unexecuted.
  Private repository checkout is unavailable in the local container
  (github.com DNS failure); GitHub Actions jobs never start.
- main/V7/production data untouched. Commercial checkout blocked.

## SQLite security PRAGMA readback and pre-run Actions failures (2026-11-05)

- `_connect` now verifies `PRAGMA trusted_schema` is 0 and
  `PRAGMA foreign_keys` is 1 after setting both, before any
  transaction is handed to application callers. This complements
  the previously enforced readback of `synchronous=FULL`.
- Added an application regression injecting ineffective SQLite
  security PRAGMAs, requiring fail-closed PermissionError and no
  consumed reference/sequence. **Application test committed,
  not executed**.
- Executed a local real-SQLite stdlib smoke check for security
  PRAGMA readbacks and DDL transaction rollback: **PASS**.
  This is not the repository application regression suite.
- GitHub Actions Windows `42006685057` failed with no assigned
  runner and zero steps; Linux `42006682920` failed with zero
  jobs. Root cause still not definitive; billing/policy/runner
  entitlement endpoints unavailable through current connector.
- The complete `run_v8_checks.py` suite remains **unexecuted**:
  local git clone cannot resolve github.com and hosted CI fails
  before runner execution. No main/V7/production data touched;
  commercial checkout stays disabled.

## Concurrent aborted-claim regression execution (2026-11-05)

- Committed `test_concurrent_aborted_claims_do_not_consume_references`:
  30 independent connection attempts across eight threads, with
  every third transaction rolled back. Asserts exactly 20 committed
  rows, gapless references 1..20, sequence 21, and SQLite integrity.
- **Actually executed** nine repository SQLite transaction contract
  test cases in local Python unittest after copying the committed
  new test into the existing local test module:
  `python -m unittest -v tests.test_v8_sqlite_transaction_contract`.
  **9 PASS, 0 FAIL, 2.792 seconds**, including crash-before/after
  COMMIT, CAS rollback, concurrent 32-commit and 30-attempt
  abort/commit interleavings. This is the real SQLite contract test
  module, NOT the full application suite.
- Windows Actions `42007078215` failed before steps, no runner;
  Linux `42007075399` failed with zero jobs. The minimal
  no-checkout diagnostic had also failed. Billing/runner policy
  endpoints are not accessible via the current GitHub connector;
  no definitive root cause or claimed CI fix.
- Full VeloPOS application regression suite remains **UNEXECUTED**
  because local private GitHub checkout fails DNS resolution and
  GitHub Actions runners do not start.
- All commits restricted to develop-v8; main, V7, production data
  and real commercial checkout unchanged.

## Post-sequence-update crash atomicity regression (2026-11-05)

- Added repository SQLite transaction contract
  `test_crash_after_sequence_advance_before_commit_rolls_back_both`.
  Child process inserts a preview record, advances sequence, then
  exits via `os._exit(39)` before COMMIT. Parent asserts both
  changes rolled back and SQLite integrity remains OK.
- **Actually executed** local
  `python -m unittest -v tests.test_v8_sqlite_transaction_contract`
  with the new committed test copied into the local repository-test
  module: **10 PASS, 0 FAIL, 3.910 seconds**. These are genuine
  SQLite contract cases; not the durable sale rehearsal application
  suite or complete project regression suite.
- GitHub Actions Windows `42007144246`: failure, empty runner,
  zero steps; Linux `42007142101`: failure, zero jobs. These
  failures occur before any checkout or Python test step. The
  independent no-checkout diagnostic has the same pre-run failure.
  Exact runner/account/policy/billing root cause is not established.
- Full application regression suite **UNEXECUTED**. Private repo
  cannot be cloned in this local container due to DNS resolution
  failure; GitHub-hosted CI never reaches a runner. Account owner
  needs to inspect Actions run annotations, Actions policy and
  billing/usage from the GitHub UI.
- Only develop-v8 changed. main/V7/production data untouched.
  Commercial checkout remains disabled.

## Busy timeout fail-closed and repeatable SQLite regression (2026-11-05)

- `_connect` now reads back `PRAGMA busy_timeout` after setting
  10000 ms, and rejects a connection reporting less than 10000.
  Added an application fault-injection regression asserting a
  shortened timeout is rejected before request insert, preserving
  the initial record count and sequence. **Application test is
  committed but not executed.**
- **Actually executed** the existing local repository SQLite
  transaction contract module with `python -m unittest -q
  tests.test_v8_sqlite_transaction_contract`: **10 PASS,
  0 FAIL, 4.027 seconds**. This local module was copied from
  GitHub in prior batches; it is not the full VeloPOS suite.
- GitHub Actions Windows `42007387264`: failed, zero steps,
  no assigned runner, zero billable Windows milliseconds;
  Linux `42007385023`: failed with zero jobs and empty
  billable timing. Independent minimal no-checkout diagnostic
  also previously failed pre-run. These results isolate the
  symptom to pre-execution infrastructure/policy, but do NOT
  establish the exact billing/runner/policy root cause.
- Full durable sale rehearsal application suite and complete
  VeloPOS regression suite remain **UNEXECUTED**: local private
  checkout cannot resolve github.com; hosted Actions jobs do
  not start. Requires account-side Actions/billing inspection
  or an accessible checkout to execute them.
- Only develop-v8 changed. main, V7, production data and
  commercial checkout unchanged.

## Waiting-writer rollback recovery and runner-log investigation (2026-11-05)

- Added `test_waiting_writer_recovers_after_aborted_transaction`
  to the committed SQLite contract suite. One connection obtains
  `BEGIN IMMEDIATE`, inserts a preview row, advances the sequence,
  and rolls back; a second connection subsequently commits the
  first reference with no gap. Verifies only the surviving row,
  sequence 2 and `PRAGMA integrity_check=ok`.
- **ACTUALLY EXECUTED** local repository SQLite contract tests
  using `python -m unittest -v
  tests.test_v8_sqlite_transaction_contract`: **11 PASS,
  0 FAIL, 3.525 seconds**. The new test was copied verbatim from
  the committed GitHub test into the existing local test module.
  This is not a full VeloPOS application test run.
- Windows run `42007613870` failed before runner assignment.
  The job logs endpoint for job `127178243554` returned
  `404 BlobNotFound`, consistent with no logs being produced;
  it does not prove the precise underlying account/runner
  failure. Linux and the no-checkout diagnostic also fail
  pre-execution. Definitive root cause remains unknown.
- Full durable sale rehearsal application suite and full VeloPOS
  regression suite remain **UNEXECUTED**: private checkout
  unavailable to local runner; hosted Actions cannot start jobs.
- Only develop-v8 changed; main/V7/production data untouched.
  No commercial checkout enabled.
