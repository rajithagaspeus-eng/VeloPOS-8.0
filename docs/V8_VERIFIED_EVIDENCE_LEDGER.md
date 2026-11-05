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
