# VeloPOS 8.0 — Safe Sale Plan, Stock Ledger and Retry Rehearsal (TEST ONLY)

**No commercial checkout is enabled.** This is a preview-only core engineering milestone for upcoming authenticated, idempotent atomic billing; do not expose it through production Qt, plugins, or legacy V7 transaction entry points.

## New common sale plan

`velopos_qt/sale_plan.py` builds a pure, immutable `PreviewSalePlan` from 1–100 draft lines. It validates finite Decimal quantities/prices, canonical barcodes, line and aggregate quantity bounds, and calculates each line's amount with `ROUND_HALF_UP` to cents. **The subtotal is the sum of rounded line amounts**, not a rounded sum of unrounded line amounts; this keeps a sample item receipt and its subtotal reconciled when fractional units are used. It does not calculate VAT, service charge, discounts, loyalty, credit, stock allocation or payment.

Comparable numeric representations such as `2`, `2.0`, and `Decimal('2.000')` normalize to the same quantity string in the *test-only* idempotency fingerprint payload. The payload contains barcode, canonical quantity, canonical unit price and the resulting rounded line amount, plus a caller-supplied identity/shift/date in the rehearsal.

The existing `PreviewCheckoutPreflight` and `RollbackOnlySaleRehearsal` both now consume this common arithmetic plan. That prevents their sub/line figures from diverging due to independent Decimal rounding. **Important limit:** the legacy V7 service uses float arithmetic and additional real billing rules. This plan does not certify equivalence with real invoices; accounting reconciliation and a production-approved currency/tax policy remain Gate B tasks.

## Atomic rollback-only rehearsal improvements

`RollbackOnlySaleRehearsal` continues to require an actual persisted preview cashier session, assigned open shift, currently valid price, sufficient stock and non-expired products/batches **inside one isolated BEGIN IMMEDIATE transaction**. It stages:

- A test-only scoped idempotency claim.
- Conditional stock reduction with aggregate duplicate-barcode quantities.
- A matching `stock_moves` row per affected barcode, recording negative delta, resulting stock and synthetic invoice reference (reason `SIMULATED_SALE`).
- A synthetic invoice and rounded per-line `sale_items` totals.
- Completion of the in-transaction idempotency claim and an immediate same-payload/same-key replay check to confirm the journal returns the original result reference rather than a second new request.
- Internal count checks of staged sale items and corresponding stock-movement rows.

**Every success and every failure rolls the entire transaction back**. New synthetic failpoints after stock-ledger stage and after journal completion prove the journal, invoice, sale lines, stock and movements are not stranded. There is no way to opt into commit. Retrying after rollback is a new simulation, not a real settled sale.

## Test coverage

`tests/test_v8_phase2_sale_plan_ledger.py` adds **seven** independent test methods, covering fractional-unit rounding, canonical request fingerprints, invalid/malformed/oversized values, staged stock-ledger count and same-key replay, four failure stages and rollback, checkout-preflight/rehearsal subtotal consistency, price/stock/batch rejection and invariant unchanged production tables.

Automated CI gate: exact PR-head Windows `python -m compileall -q velopos_qt tests` plus `python run_v8_checks.py` with zero failures/skips. Repeat on exact post-merge `develop-v8` head. Physical Windows UI and printer/hardware acceptance remain outstanding.

## Remaining blockers — all commercial gates still incomplete

- No actual V8 transaction service commits, no production session/shift/license/branch authority boundary, no secret-key or revocation backend, and no signed offline monotonic continuity.
- No safe invoice-number reservation, crash recovery, persistent exactly-once sale, mixed/card/credit tender, VAT/service charge, loyalty, COGS, returns and reversal reconciliation in a write-capable service.
- No production-safe migration, full ledger accounting acceptance, owner hardware QA, installer or secure release.
- The isolated rehearsal is not a trusted write path; the original V7 services remain callable outside this preview. Do not wire the rehearsal, preflight or new plan to real Checkout.

**Data safety:** `main` unchanged, no V7 production DB touched, no live transaction performed, no commercial release promise. Keep release Gates A/B/C/D/E blocked.
