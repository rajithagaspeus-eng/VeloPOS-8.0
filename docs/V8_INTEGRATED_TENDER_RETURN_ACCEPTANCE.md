# VeloPOS 8.0 — Integrated Tender and Return Financial Contracts (TEST ONLY)

**Release status: NOT commercial-ready.** This batch is deliberately isolated to synthetic V8 preview transactions. None of these models authorizes, collects, captures, refunds, credits, prints or posts money; `main`, V7 production services and customer data remain untouched.

## 1. Split tender plan (pure, zero side effects)

`velopos_qt/tender_plan.py` provides `plan_preview_tender(amount_due, tenders, customer_id=None)`. Accepted types intentionally match legacy labels `Cash`, `Card`, `QR`, `Credit` as draft declarations only. The model requires 1–10 entries, exact two-decimal nonnegative currency amounts, valid methods and constrained references. Card/QR declarations require a reference string but **the reference is unverified** and is never proof of charge, capture, refund or settlement.

Noncash allocations may not exceed the amount due; the declared allocation must cover the total, and change may only arise from cash. Positive Credit allocations require a selected numeric `customer_id` but that does NOT verify identity, debt ceiling, approval, available credit or existing receivable; the output explicitly marks `credit_limit_unverified=True`. `can_settle` and `persisted` are always False. The immutable plan exposes cash, noncash, credit, external-uncertainty and change amounts for diagnostics.

`RollbackOnlySaleRehearsal.simulate` accepts optional `tenders=` and `customer_id=`; when present, it binds the normalized declared tenders and customer marker to its test-only idempotency fingerprint, validates allocation against the same `PreviewSalePlan` subtotal, and includes the pure preview in the return result. It NEVER calls a payment provider or posts to customer/credit/payment tables.

## 2. Return stock ledger and replay safety

`RollbackOnlyReturnRehearsal.simulate` now stages a **synthetic positive stock movement per barcode** in its existing `BEGIN IMMEDIATE` lock alongside stock restoration, return header, return items and idempotency claim. Every stage is rolled back unconditionally, including an apparent success.

Repeated original sale-item IDs are aggregated and capped; quantities in the fingerprint are canonically normalized; return lines use explicit decimal HALF_UP currency rounding. After completing a request journal claim, the rehearsal reclaims the *same* request/payload to verify the same synthetic return reference is obtained without a second result. Two new test-only failure points, `after_stock_ledger` and `after_journal_complete`, prove both movement and request journal state are discarded on interruption.

**Important:** partial-return price-only math here is not a commercial refund calculation. Discount, VAT/service allocation, credit offset, loyalty reversals, provenance of batches, units, COGS and original tender reversal are still unimplemented. No real returned stock or cash moves occur.

## 3. Automated and physical QA

`tests/test_v8_tender_plan.py` adds six pure model tests of cash change, mixed external methods, credit binding with unverified flags, strict underpayment/noncash-overpayment, fractional-currency/NaN/Inf rejection and invalid references/methods.

`tests/test_v8_integrated_tender_return.py` adds five isolated SQLite subprocess tests. They prove that draft tender plans stay unpaid, malformed payments are denied, synthetic return restoration and repeated-line quantities are reconciled, each injected failure rolls back all staged effects, retries after rollback remain synthetic, and ineligible returns cannot over-return or cross invoices.

**Windows CI acceptance:** exact PR-head `python -m compileall -q velopos_qt tests` plus complete `python run_v8_checks.py`, no failures or skips. Re-run on exact merged `develop-v8` SHA. Owner physical Windows/EPOS/hardware/regulatory acceptance is a separate release gate.

## 4. Next commercial milestones — gates remain blocked

- Authenticate and authorize every production financial service call using a verified persisted actor, shift, branch and trusted entitlement inside the actual atomic transaction. Legacy direct services remain reachable until refactored.
- Implement a trustworthy hosted activation/revocation and device transfer service, durable replay resistance, safe recovery from interruption, and production idempotent invoice/return/payment writes.
- Establish tax-inclusive/exclusive allocation, COGS, multi-unit/batch inventory, customer credit and loyalty posting/undo, payment provider references and reconciliation of real settlement.
- Prove full migration/restore and audited financial reports; test printers, barcode scanners, Windows scaling, installers and multi-user failure modes.

**No release gates A/B/C/D/E have been certified by this batch.** An all-green preview CI is evidence of these specified cases only, not software completion. This batch makes the target architecture more testable without taking unsafe shortcuts.