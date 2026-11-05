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
