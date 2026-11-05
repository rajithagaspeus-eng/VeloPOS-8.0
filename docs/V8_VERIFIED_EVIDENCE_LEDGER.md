# VeloPOS 8.0 — Exact-commit evidence and uncertainty ledger

**Prepared:** 2026-11-05. **Snapshot SHA:** 3ed6d8f7866f95111d221f4d309938f1fc5fb4d5. **Branch:** develop-v8.

## Evidence rules

1. **Executed PASS** means a named test runner actually executed, returned exit 0, had the expected test count and zero unapproved skips at the *recorded SHA*.
2. **Executed FAIL** means a runner actually executed and reported failures/errors/skips. A failure on an older SHA is not proof of current-head failure.
3. **Not executed / CI infrastructure blocked** means no job steps or test output; do NOT describe it as a Python regression failure.
4. **Code inspection / committed only** means repository artifacts exist; never turn this into PASS.
5. **Owner-reported historic** is useful context but lacks independent immutable logs here; re-run for present-day certification.
6. A RELEASE gate is accepted only when its exact requirements, integration evidence and owner manual QA (where needed) are signed off. No estimated percentage substitutes for that.

## Ledger

| ID | Date / code SHA | Evidence and source | Actual observation | Classification | What it does not prove |
|---|---|---|---|---|---|
| E01 | V7.2 / SHA unavailable | Recovered owner-provided historical chat excerpt regarding uploaded velopos_v7_2_fixed6 ZIP | Phase 7.3 17/17, static and GUI smoke reported PASS | OWNER-REPORTED HISTORIC | V8 feature parity or Windows hardware readiness |
| E02 | 2026-11-04 / da535008b708511fbb8cf64529e5c9d2fc983ebd | docs/V8_COMMERCIAL_RELEASE_GATES.md; recorded Windows run with verified Python environment | run_v8_checks.py: 296 tests, 0 failures, 0 skips, exit 0, 121.843s | OWNER-CONFIRMED EXECUTED PASS AT OLD SHA | Any later V8 commits or commercial transaction safety |
| E03 | Earlier local milestone / exact SHA not established in this ledger | Prior conversation test summary | 412/412 tests reported PASS | OWNER-REPORTED HISTORIC | Exact-SHA release certification |
| E04 | Older post-milestone suite / exact SHA and full log unavailable here | Prior Windows regression summary | 612 tests: 6 failures, 66 errors, 77 skipped | EXECUTED FAIL REPORTED FOR OLDER CODE | Current-head failure counts after fixes |
| E05 | 2026-11-05 / 8f8cd2eb9318dfda9e09a6fc22d8d4b27a9cf944 | GitHub commits on develop-v8 | Credit allocation / stock movement / receipt and fixture corrections in source | COMMITTED ONLY | Fixed failures unless rerun |
| E06 | 2026-11-05 / 3ed6d8f7866f95111d221f4d309938f1fc5fb4d5 | GitHub Actions push run 42077102970, https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/42077102970 | Windows workflow conclusion failure; one job with runner_id=0, runner_name empty and steps=[] | CI INFRASTRUCTURE/PRERUN FAILURE; TESTS NOT EXECUTED | Python assertions failing or passing; root cause unknown |
| E07 | 2026-11-05 / 3ed6d8f7866f95111d221f4d309938f1fc5fb4d5 | GitHub Actions push run 42077100600, https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/42077100600 | Sandbox workflow conclusion failure, jobs endpoint returned 0 jobs | CI PRERUN FAILURE; TESTS NOT EXECUTED | Actual sandbox regressions' outcome |
| E08 | 2026-11-05 / 3ed6d8f7866f95111d221f4d309938f1fc5fb4d5 | velopos_qt/release_readiness.py, docs/V8_COMMERCIAL_RELEASE_GATES.md | preview_only=true, can_checkout=false, production_ready=false; A-E all not passed | SOURCE-INSPECTED POLICY | Installed Windows UI cannot be externally bypassed |
| E09 | 2026-11-05 / 3ed6d8f7866f95111d221f4d309938f1fc5fb4d5 | GitHub branch API, legacy README, roadmap, Qt-preview docs | develop-v8 exists separately from main; main SHA 194c1844f3e7979c8d44bff0ce83e7d7a9621db3 at snapshot | SOURCE-INSPECTED SNAPSHOT | Any future unobserved branch changes or file-system safety outside GitHub |

## Current blocking evidence gap

- A current-head combined Windows run with a stable interpreter, PySide6 and cryptography dependency verification, real executed test discovery, logs and artifacts; no unapproved skipped tests.
- Separate stock-movement duplicate/chain corruption, foreign-customer charge allocation, note replay, receipt spacing, SQLite locks and crash recovery regression results.
- CI annotation / runner allocation investigation: GitHub Actions failure with no runner assigned is **not** self-explanatory. Do not claim billing-limit or workflow-config root cause without diagnostic evidence.
- Complete trusted service-bound transaction and independent accounting acceptance in disposable data; production checkout remains explicitly disabled.
- Real Windows printer/scanner, backup/restore, V7 migration, accessibility, installer and owner manual acceptance.

## Exact-SHA verification procedure for future entries

After every meaningful integration batch:
1. Record develop-v8 HEAD SHA, source-tree and test-runner identity. Check main SHA remains unchanged.
2. Confirm test environment identity (Python version/path, PySide6/cryptography imports, isolated VELOPOS_HOME; no real customer data).
3. Execute both current preview unit/integration suite and the legacy-inclusive full suite, preserving full stdout/stderr and nonzero exit codes; do not silently skip tests.
4. Classify CI failures using job count, assigned runner and actual step logs. Attach URLs for push runs, job steps and annotations when accessible.
5. Record counts, observed failures, artifacts, branch SHA and named acceptance gates. Never overwrite historical entries; append a dated correction.
6. Make the current-head release_readiness report show no checkout until Gates A and B are accepted through an explicit reviewed activation process; Gate C is separate for cloud SKU, while D/E govern distribution.

## Current five-gate acceptance

| Gate | Status | Principal missing evidence |
|---|---|---|
| A Transaction/service authority | BLOCKED | Fully authorized commercial atomic sale/returns and legacy entry-point security |
| B Finance/inventory | BLOCKED / IN PROGRESS | Independent invoice COGS/tax/loyalty/credit/stock reconciliation |
| C Secure cloud/multi-branch | NOT READY | Production authenticated tenant sync and offline conflicts |
| D Commercial licensing/distribution | NOT READY | Server authority, verified recovery and installer acceptance |
| E Windows UX/release quality | NOT READY | Exact-head tests, all UI/hardware/migration/owner acceptance |

**Gates accepted: 0/5.** The previously discussed 60% is an **informal development estimate**, not an objective release-readiness measure.


## 2026-11-06 — no-skip full regression gate hardening (implementation, NOT EXECUTED)

- Baseline code and Skill head before this batch: `19c003b52c8985dbb340af903750d5a736fcc70b`.
- Observed on that SHA: GitHub-hosted Windows push [42081895568](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/42081895568) failed with one `runner_id=0`, `steps=[]` job; this does **not** establish Python failures. Sandbox push [42081892649](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/42081892649) also concluded failure, without a verified executed test log here.
- Code inspection established a concrete false-green risk: `tests/run_all.py` returned zero even when Python unittest output contained `OK (skipped=N)`. The combined `run_v8_full_regression.py` treated that return code as successful.
- Implementation: added opt-in `tests/run_all.py --fail-on-skips`, counted/report unittest skips and made them nonzero in strict mode; the combined full gate **always** passes this strict option. Historical standalone `tests/run_all.py` without this option preserves its prior exit-code behavior while still reports skip count. Added disposable strict/permissive contract cases in `tests/test_v8_legacy_skip_gate.py` and invocation assertion in `tests/test_v8_full_regression_runner.py`.
- Code commits: `b07da2403de695f49a10bffa8bd60ae7c58681db`, `e861b5bfcb8e04a2641af3297f23efc06a5ceeab`, `9ec5b86f60cb448b7f57c8fac21bf163f3016505`, `ca0e38a830b6b52cfe3f954c0215b5cfe9718743`.
- **TEST EXECUTION: NOT EXECUTED.** GitHub file inspection confirmed changes but no Windows/Python test output proves correctness at these commits. Changes may deliberately turn historically false-green suites red until real skips are eliminated. Do not mark Gate E accepted.
- Next verification in an isolated Windows local checkout: `python -m unittest -v tests.test_v8_legacy_skip_gate tests.test_v8_full_regression_runner`, then the full combined runner with explicit disposable home; record interpreter, exact code SHA, failures/errors/skips and logs. Protect nested untracked `VeloPOS-8.0/` repo; use no real customer data.
- **Commercial checkout remains disabled; gates accepted 0/5.**


## 2026-11-06 — bounded legacy subprocess execution (commit pending at entry creation)

- Parent HEAD before this change: `91a95cd5fafaefa11cad9ce748a213b767b145bc`; develop-v8 only. GitHub push Windows run [42086500203](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/42086500203) concluded failure with one job without exposed executed step logs; sandbox run [42086498099](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/42086498099) reported zero jobs. **These do not establish Python test failures.**
- Legacy `tests/run_all.py` now bounds each unittest/static/GUI subprocess with a configurable positive `--job-timeout` (600s default); timeout records FAIL (exit 124 internally) and later jobs continue. Strict `--fail-on-skips` is unchanged. Added isolated timeout and invalid-argument contract cases in `tests/test_v8_legacy_skip_gate.py`.
- **TEST EXECUTION: NOT EXECUTED in an exact GitHub/Windows checkout at this entry.** No commercial release gate accepted; checkout remains disabled. Next: obtain a runner with executed steps; perform targeted and full no-skip Windows regressions against exact final commit SHA, and reconcile any observed failures.


## 2026-11-06 — legacy regression timeout reporting repair (code inspection; NOT EXECUTED)

- Pre-change develop-v8 HEAD: `e82143954d5011bb233dc7d040b93260abed3059`. Changes confined to `develop-v8`; no V7, main, production customer database or signing-key operations.
- Inspected `tests/run_all.py`: the `subprocess.TimeoutExpired` path sets `returncode=124` but leaves `r` unbound. Failure reporting then accessed `r.returncode` when `--fail-on-skips` and partial unittest skip output coexist, risking `UnboundLocalError` instead of a clean timeout report. Corrected failure-reason selection to use `returncode`, prioritizing timeout and zero-discovery explanations.
- Updated `tests/test_v8_legacy_skip_gate.py` to assert timeout-specific failure reporting and absence of `UnboundLocalError`; corrected the empty-test-module fixture to use a real Python newline rather than a literal escaped backslash sequence.
- Code commits: `7964eafe1354516f9fbbe6d904974bce1e83792a`, `c7ed710c1cecc8ee9734dce65566c42f8e5aae9f`, `1dc917315c5e528b3afa5d7c9e34a88bf2a7f90e`.
- **TEST EXECUTION: NOT EXECUTED** in this connected GitHub session. Assertions committed are not a PASS. Run `python -m unittest -v tests.test_v8_legacy_skip_gate tests.test_v8_full_regression_runner` on a disposable Windows environment, followed by the strict full suite at exact HEAD. Preserve failure/skip counts and interpreter identity.
- Commercial checkout/payment/refund/stock posting remain disabled; **accepted commercial gates: 0/5**. No production readiness claim.


## 2026-11-06 — isolated runner-contract execution evidence (not Windows release evidence)

- Inspected branch after follow-on code commits: `c5af2c9365edc1a3bae8b66f5760af730deafc72` (historical point-in-time, branch may advance).
- Executed a **manually reconstructed, dependency-free copy** of the legacy runner and contract fixtures in a disposable Linux container (Python 3.13.5; `/opt/pyvenv/bin/python`) with command `python -m unittest -v tests.test_v8_legacy_skip_gate`: **6 tests executed, 0 failures, 0 errors, 0 skips, exit 0**, approximately 16.96 seconds. Local `python -m compileall -q` on reconstructed fixtures also exited 0. Tests covered skip rejection, permissive legacy behavior, successful normal case, timed-out child process and continuation, invalid timeout, and empty test-module rejection.
- **Evidence boundary:** reconstructed fixture execution is **not an executed test of an exact checked-out GitHub SHA** and is **not Windows full regression**. The exact-repository targeted suite and entire strict regression are **NOT EXECUTED / NOT VERIFIED** here. Do not promote Gate E or declare product tests PASS from this observation.
- Latest GitHub CI runs still require job-step and artifact verification; account/runner diagnosis is unresolved. Checkout remains OFF and Gates A–E accepted remain **0/5**. Next task: an actual exact-head Windows full no-skip regression, followed by Gate A/B transactional reconciliation.


## 2026-11-06 — isolated reconstructed regression contract execution (NOT exact-repository certification)

- Observed remote `develop-v8` HEAD at start of this verification: `a3353639d51d8047b026866248e00661a4517329`. Reviewed current `tests/run_all.py` and `tests/test_v8_legacy_skip_gate.py` via connected GitHub file reads.
- Runtime: container Linux, Python 3.13.5; `git ls-remote`/clone failed because GitHub DNS was unavailable. Constructed a disposable local harness reproducing the current legacy runner logic and the six current skip/timeout test scenarios. **This harness was manually reconstructed, not an exact byte-for-byte repository checkout.** It did not read or write any VeloPOS production/customer database.
- Execution 1: `PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tests.test_v8_legacy_skip_gate` in `/tmp/velopos_isolated`: **6 tests run, 0 failures, 0 errors, 0 skips, exit 0, 18.563 seconds**. Execution 2: same reconstructed tests with `-q`: **6 tests run, exit 0, 19.214 seconds**. Local `py_compile` of reconstructed runner and test module returned exit 0.
- Classification: **EXECUTED PASS — RECONSTRUCTED ISOLATED CONTRACT ONLY**. Does **NOT** certify the exact GitHub HEAD, actual repository tests, PySide6, Windows compatibility, or full strict release regression. No production checkout authorization or release gate is accepted. Full Windows/exact-source test remains **NOT EXECUTED**.
- Next: obtain an exact `develop-v8` checkout on a disposable Windows runner and execute `python -m unittest -v tests.test_v8_legacy_skip_gate tests.test_v8_full_regression_runner`, then `python run_v8_full_regression.py` with logs and zero unapproved skips. Checkout OFF; 0/5 gates.


## 2026-11-06 — isolated Linux legacy-runner contract verification (6/6 PASS, limited scope)

- Source read from GitHub `develop-v8` at branch HEAD `a3353639d51d8047b026866248e00661a4517329`: `tests/run_all.py` and `tests/test_v8_legacy_skip_gate.py`. Runner and tests were copied into a separate disposable directory; **not a full Git checkout** and not a Windows environment.
- Executed `python -m unittest -v tests.test_v8_legacy_skip_gate` using Python 3.13.5 on Linux. Actual output: **Ran 6 tests in 18.326s; OK; 0 failures, 0 errors, 0 skips**, exit 0. Local captured log: `/mnt/data/velopos_v8_targeted_test.log` (conversation runtime artifact, not committed to GitHub).
- Cases: strict skip denial, permitted legacy non-strict skip, valid strict pass, timeout failure reporting with subsequent checks, zero-test denial and nonpositive timeout rejection.
- **Evidence classification: EXECUTED PASS — isolated copied-source contract subset only.** Does NOT establish an exact-head full-repository test PASS, current Windows/PySide6 behavior, all legacy tests, hardware readiness or any commercial gate.
- Full `run_v8_full_regression.py` and Windows tests: **NOT EXECUTED**. GitHub-hosted runner issue unresolved. No checkout, payment, refund or stock posting enabled; Gates accepted **0/5**.


## 2026-11-06 — current-head CI blocker and strict timeout regression coverage

- Branch HEAD at start: `34d06c435bad1ae256ba636c5692f90fc5b8ff88`. GitHub Actions Windows/preview run [42088382476](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/42088382476) for that SHA concluded failure; job `preview-tests` reported no exposed steps/logs in connector. Companion sandbox run [42088380417](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/42088380417) concluded failure and returned zero jobs. **No executed Python assertion failure or PASS can be inferred.** Hosted runner allocation and workflow diagnostics remain blocked.
- Direct git clone from the current disposable Linux container could not connect to github.com (DNS resolution failed), so full repository checkout and exact-head combined regression **NOT EXECUTED**. No customer data or production database accessed.
- Code inspection found the existing timeout regression did not exercise the historical unbound-variable branch when a timed-out unittest emitted partial `skipped=1` output. Added `test_timeout_with_partial_skip_summary_fails_without_runner_crash` in `tests/test_v8_legacy_skip_gate.py`; commit `5bdd580a5472104b7fa4706e1a7f682a656bad28` on `develop-v8`. This is regression coverage, not a claim of execution.
- **Current session tests: NOT EXECUTED** (0 verified passes); the earlier isolated copied-source 6/6 result applies only to its prior source snapshot. New test must be executed with the strict legacy runner and full Windows regression in a disposable checkout. Checkout/payment/refund/stock posting OFF; **0/5 gates accepted**.


## 2026-11-06 — timeout plus partial skip-output probe (isolated execution)

- GitHub `develop-v8` observed at `34d06c435bad1ae256ba636c5692f90fc5b8ff88` before the test commit; remote branch can advance independently. Current push Windows Actions run 42088382476 concluded failure, but job response exposed no executed step evidence. No Windows PASS is inferred.
- Executed a **manually mirrored subset** of current `tests/run_all.py` in a disposable Linux Python 3.13.5 directory `/tmp/velopos_runner_probe`, with a synthetic test subprocess printing `Ran 1 test` and `OK (skipped=1)` before sleeping past `--job-timeout 1`. Command: `PYTHONDONTWRITEBYTECODE=1 python tests/run_all.py --fail-on-skips --job-timeout 1`.
- **Observed exit 1 (expected failure)**; output contained `FAILED (subprocess timed out)`, `REPORTED UNITTEST SKIPS: 1`, and `1 JOB(S) FAILED`, with no `UnboundLocalError`. This verifies the specific manually mirrored timeout/skip branch, **not** an exact-source repository test run or Windows acceptance.
- Added the same case to actual repository regression test `tests/test_v8_legacy_skip_gate.py` at commit `2913bff893b28675cf632884e09a206b82f8607b`. **New committed regression test NOT EXECUTED** from the exact GitHub source. Full strict suite and commercial gates remain unverified (0/5).
- Production checkout/payment/refund/stock posting remain disabled. No main/V7/customer database or signing key was modified. Next: execute exact-source targeted contract tests and full Windows regression on a disposable runner; capture exit codes, test totals, skips and logs.


## 2026-11-06 — current-head Actions runner restriction diagnosis (NOT EXECUTED)

- Observed `develop-v8` HEAD `b846ea603e7b27171c8f9c7ee53037be368720c7` before this documentation update.
- Push [42088602076](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/42088602076), workflow `V8 preview automated tests`: conclusion failure; `preview-tests` job `127460325898`, `runner_id=0`, `runner_name=""`, `steps=[]`. Fetching job logs returned HTTP 404 BlobNotFound. **No Python commands executed in exposed job evidence.**
- Push [42088599520](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/42088599520), workflow `v8-sandbox-regression.yml`: conclusion failure; Jobs API returned `jobs=[]`. No test results available.
- Inspected `.github/workflows/v8-preview-tests.yml`, `v8-sandbox-regression.yml`, `v8-preview-windows.yml` and `v8-runner-diagnostic.yml`: Windows preview requests `windows-latest`, sandbox requests `ubuntu-latest`, and the existing minimal diagnostic requests `ubuntu-latest` without checkout/dependencies. The diagnostic is manual dispatch or triggered by edits to its own workflow. No diagnostic run appeared in the latest 30 workflow runs inspected. **Runner allocation root cause remains unverified**; repository Actions permissions/runner APIs are not exposed by this connector.
- No source or CI workflow edits made in this diagnostic step; no repeated ungrounded CI rerun. **Tests NOT EXECUTED; 0 new verified PASS**. Next action: dispatch existing `V8 runner allocation diagnostic` on `develop-v8` and inspect its job steps/annotations. If it also fails before runner assignment, inspect GitHub Actions account/repository billing or runner restrictions in GitHub UI. Do not change paid settings without approval.
- Main/V7/customer data unchanged; commercial checkout, payments, refunds and stock posting remain disabled; **0/5 gates accepted**.


## 2026-11-06 — actual escaped-newline regression fixture defect corrected

- Observed exact remote `develop-v8` pre-change HEAD `b846ea603e7b27171c8f9c7ee53037be368720c7`. Read actual GitHub contents for `tests/run_all.py`, `tests/test_v8_legacy_skip_gate.py`, `run_v8_full_regression.py`, and `tests/test_v8_full_regression_runner.py` at that SHA.
- **Actual source defect:** `test_timeout_with_partial_skip_summary_fails_without_runner_crash` built its synthetic Python test using literal escaped `\\\\n` text rather than newline characters. This would cause a syntax error in the generated test instead of executing its intended partial skip-output/timeout path, and could produce a misleading regression failure.
- Fixed only those five source-string newline escapes in `tests/test_v8_legacy_skip_gate.py` on `develop-v8`, commit `2987ed8d389a6e9253e279f1c7863dbe9d663bb0`. Other test scenarios, financial services, checkout and customer data unchanged.
- **Executed limited isolated verification:** created disposable synthetic `tests/test_sample.py` matching corrected fixture on Linux Python 3.13.5; `python -m py_compile` returned 0. `timeout 1s python -m unittest tests.test_sample` printed `skipped=1` and returned **124** (expected forced timeout). This tests the corrected Python fixture syntax/timeout, not the actual repository's unittest contract.
- Exact-source targeted GitHub repository test execution: **NOT EXECUTED** (GitHub clone DNS unavailable from execution environment). Pre-fix exact-HEAD Windows Actions runs 42088602076 and 42088599520 concluded failure, but no assertion-level execution evidence obtained. **No PASS count claimed for actual GitHub test suite.**
- Next: run `python -m unittest -v tests.test_v8_legacy_skip_gate tests.test_v8_full_regression_runner` on exact current `develop-v8` checkout, then full strict Windows regression; record test counts, skips, exit codes and failures. Commercial gates 0/5, checkout OFF; main, V7, production data untouched.


## 2026-11-06 — owner-supplied GitHub Actions annotation identifies billing/spending-limit restriction

- Owner supplied a screenshot of the `V8 runner allocation diagnostic` workflow, run #1, on `develop-v8` (displayed short SHA `21a7199`). Status: Failure after approximately 3 seconds; `runner-diagnostic` job red. Annotation visible: `The job was not started because recent account payments have failed or your spending lim...` (screenshot cuts off the rest; do not invent missing words).
- **Root-cause category now evidenced:** GitHub Actions account billing/payment or spending-limit restriction prevents runner start. Screenshot does not distinguish which alternative applies; do not assert an actual failed charge or exact spending cap. The separate Ubuntu 26 migration notice is informational, not a demonstrated cause.
- This is **pre-run infrastructure failure**, not a Python/Flutter regression result. Verified executed assertions from this diagnostic: **0**. Previous job metadata with runner_id=0 and steps=[] is consistent. No release gate changes; **0/5 accepted**.
- **LKR 0 policy:** no paid runner, card/payment change or billing upgrade. Next safe action: check GitHub account Billing and licensing / Actions spending limit or available included minutes in the user's own UI, without making paid changes; then use isolated local regression execution if GitHub-hosted runners remain blocked.
- This ledger entry only; no checkout, payments, refunds, stock posting, main, V7 or customer production data changed.


## 2026-11-06 — exact Git blob verified legacy runner contract execution (PASS)

- Read branch `develop-v8` HEAD `283f9ec118e9d18fb7aad415f0dd37066631f127`. Fetched `tests/run_all.py` and `tests/test_v8_legacy_skip_gate.py` from this exact commit via GitHub connector. Assembled only these two source files and `tests/__init__.py` in isolated `/mnt/data/velopos_exact_tests` (no production databases, POS application or customer records).
- **Byte-for-byte source integrity independently verified:** local `git hash-object tests/run_all.py` = `5381f8ef31b3680c3ce613c3169bead5aac702d4`, matching GitHub content blob SHA; `git hash-object tests/test_v8_legacy_skip_gate.py` = `0664f64390d0d963df7d907ab71c48eabadf90ee`, matching GitHub content blob SHA. This establishes exact-source parity for these two files, despite GitHub clone being unavailable.
- Executed `PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tests.test_v8_legacy_skip_gate` on Linux isolated filesystem. **Result: 8 tests run in 23.313 seconds; 0 failures, 0 errors, 0 skipped; exit code 0.** Both partial-skip timeout cases, no-test detection, strict skip rejection, timeout argument validation and legacy compatibility passed.
- Classification: **PASS for exact-Git-blob two-file targeted regression only**. The remaining repository files, Windows execution, full strict suite, Qt/POS integration and commercial release gates were not exercised. No Windows/full-suite pass is claimed; release gates remain **0/5** and commercial checkout OFF.
- Next single verification task: run the full strict `python run_v8_full_regression.py` on an isolated Windows checkout of the latest exact `develop-v8` SHA and record every test count, skip, failure and runner log before accepting release gates. Preserve main, V7, signing keys and customer data.


## 2026-11-06 — exact-head Windows regression CI inspection (infrastructure evidence only)

- Inspected remote `develop-v8` HEAD `56450ac9d5e451440f9666d620839d3d0e925b82`. Windows workflow `V8 preview automated tests` push run [42089411804](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/42089411804) concluded failure. The returned job `127463199570` had no exposed step execution data; its job log download returned GitHub 404 `BlobNotFound`. No Python test failure or passing count can be extracted from this job.
- Sandbox workflow run [42089409426](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/42089409426) also concluded failure; its jobs endpoint returned zero jobs. This is not evidence of executed sandbox assertions.
- Read `.github/workflows/v8-preview-tests.yml`: it configures `windows-latest`, Python 3.12, exact checkout SHA verification, disposable `VELOPOS_HOME`, and `python run_v8_full_regression.py` with preserved output artifact. Read `.github/workflows/v8-sandbox-regression.yml`: it configures `ubuntu-latest` and separate sandbox contracts. No exact-head Windows full-suite execution logs were accessible. **Full strict Windows regression remains NOT VERIFIED.**
- The previously recorded exact-Git-blob targeted legacy runner tests (8/8 on Linux) remain the only executed passing assertion evidence for that subset. No new code changes were justified by a proven test failure; no speculative financial/checkout changes made. Commercial gates **0/5**, checkout OFF; main, V7, production data and signing keys unchanged.
- Next: obtain actual runner-assigned Windows test logs for the exact current branch commit (or execute the same strict command on an isolated Windows checkout) and triage genuine test failures before changing application code.
