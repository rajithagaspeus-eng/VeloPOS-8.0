# VeloPOS 8.0 — Integrated Atomic Sale Diagnostic Contract (Preview Only)

**Do not wire this to a live checkout, button, cloud server, production license or legacy V7 services.** This module is an internal *fail-closed* integration milestone for the future commercial POS service boundary, not the service itself.

## What this batch implements

`velopos_qt.atomic_sale_boundary.PreviewAtomicSaleBoundary` creates a dedicated **BEGIN IMMEDIATE** transaction on `VeloPOS8PreviewData` and composes these checks against one SQLite snapshot:

1. Current persisted and revalidated cashier identity; role and assigned open shift (`PreviewServiceAuthorization` via `PreviewCombinedAuthorization`).
2. Canonical branch registry, active actor membership and shift/branch relationship (`PreviewBranchAuthorization`).
3. Ed25519 signed, machine/branch/action/expiry-bound V8 license and ID match to signed server observations (`PreviewSignedEntitlementInspector`).
4. Two signed and digest-linked activation observations, exact license/machine/branch IDs, sequence monotonicity, signed timestamps and offline freshness (`PreviewSignedActivationChainInspector`).
5. Actual preview DB stock, combined quantities for repeated barcodes, stored selling prices, expiry and expired batch warnings (`PreviewCheckoutPreflight`).
6. Diagnostic summary, with *unconditional* checkout and execution refusal. Request IDs remain unreserved and no journal claim or financial write is created.

All calls to `inspect()` **always roll back** and close the transaction. `inspect_in_transaction(connection, ...)` provides the same composition using an explicitly supplied canonical preview connection that is already within a caller-owned transaction, without committing or rolling back the caller's transaction. Existing public `PreviewCheckoutPreflight.inspect()` remains backward compatible and can now accept `connection=` for one-snapshot composition, enforcing canonical storage and a transaction before any reads.

The rollback-only `RollbackOnlySaleRehearsal` now runs that same stock, price, expiry and batch preflight in its existing write-locked transaction before staging synthetic invoice, stock and idempotency journal rows — all of which always roll back. No real money is collected.

## How to test the new integration

`python -m unittest tests.test_v8_phase2_atomic_sale_boundary -v` tests disposable preview databases and **seven** integration scenarios: valid but denied diagnostics, repeated-line stock and stored-price failures, expired products/batches, revoked session/closed shift/branch and license mismatches, forged or stale activation, foreign or transactionless connection rejection, malformed draft rollback, and rehearsal expiry rejection without persisted writes.

`python -m compileall -q velopos_qt tests` plus `python run_v8_checks.py` must pass on the **exact** PR head in Windows CI and again on the exact merged `develop-v8` head before reporting verified integration.

## Explicitly NOT completed (Commercial Gate A stays BLOCKED)

- Nothing binds these checks to a live original `velopos.services` sale/return/GRN operation. Existing V7 direct service entry points are not secured by this preview-only module.
- The license public keys are test/diagnostic inputs; there is no deployed trusted online authorization, device key store, server-held monotonic continuity, revocation enforcement or commercial key management.
- No production idempotent request reservation, crash recovery, request deduplication, invoice numbering, tax/VAT, service charge, returns, mixed payment, credit limits or loyalty redemption runs through this boundary.
- Future transactions must repeat ALL checks **inside the same atomic write transaction** and must enforce real production authorization without a UI flag or any test-only allowlist.
- No Windows printer, payment hardware, offline sync, secure installer or physical owner acceptance is claimed.

**Safety invariants**: immutable diagnostic results have both `can_execute=False` and `can_checkout=False`; `require()` always raises `PermissionError`; `inspect()` always rolls back; no financial tables, stock balances or request journal change. Keep `main` and customer databases untouched. All release Gates A/B/C/D/E remain unpassed.