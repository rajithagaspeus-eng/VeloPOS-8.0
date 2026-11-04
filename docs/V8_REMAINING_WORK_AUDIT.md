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
