# VeloPOS 8.0 — Commercial release gates (develop-v8 only)

This is the acceptance contract for the integrated development program. It is **not**
a statement that all items are implemented. The PySide6 V8 application remains
an isolated **TEST DATA ONLY**, nontransactional preview.

## Current evidence

- Owner-confirmed Windows regression milestone: **121 tests, OK**, before the
  Billing scroll, purchasing reconciliation, analytics, demand, session and
  later privacy commits. A fresh combined Windows run is still required.
- Preview pages include Dashboard, Inventory, Billing Draft, directory editors,
  Reports, Smart Inventory, Purchasing, historical Business Intelligence and
  demand-baseline planning. Preview mutations are restricted to test product /
  directory editors; they do **not** demonstrate production transaction safety.
- Historical demand estimates are transparent heuristics, **not** validated
  predictive AI. Indicative P&L is not certified accounting.

## Gate A — Transaction integrity (BLOCKING)

A checkout button or production sale MUST NOT be enabled until the service
boundary, not just the UI, enforces all of the following inside a single
transaction with rollback on any failure:

1. Verified current authenticated session; role and per-action permissions
   rechecked against canonical persistent state; account deletion/password
   rotation/role change revokes access.
2. License acceptance and entitlement verified at the trusted transaction
   boundary. Never trust a Qt boolean, unsigned local license, or secret
   embedded inside a desktop executable.
3. Required open cashier shift, branch attribution, correct cash/card/credit
   tender handling, nonnegative balances, consistent rounding, and tax rules.
4. Product existence, price changes and valid discounts; stock and active
   batch availability/expiry rechecked atomically at **commit time**.
5. Invoice number uniqueness, sale items, stock movements, customer ledger,
   loyalty earn/redeem, credit limits, tax, receipt metadata and audit history
   committed **exactly once**; idempotency key handles retries and crashes.
6. Returns/voids/reversals have similarly authenticated, audited and
   transactional compensating flows. Failed transactions leave **no writes**.
7. Original services must not remain callable with arbitrary cashier username
   strings and no verified session from an alternate Python entry point.
8. Disposable DB integration tests cover concurrent checkout, power loss /
   rollback simulation, duplicate submission, expired batches, insufficient
   stock, altered price, invalid shift, demotion, license denial and refund.

**Gate A status: BLOCKED.** Real sale, payment and stock-deduction UI stays off.

## Gate B — Financial and inventory acceptance (BLOCKING)

- Independently reconcile invoice sales, returns, tax and the original
  recorded COGS/profit; handle partial returns and date of event properly.
- Reconcile each supplier's all-time successful GRNs minus all subsequent
  payments. Report supplier advances separately, not as concealed liability
  offsets. Compare preview figures with legacy supplier balances.
- Reconcile loyalty points, customer credit outstanding, stock ledger and
  batch quantities across sale, return, purchase, void and adjustment.
- Produce exportable and tested daily close-out, audit evidence and backup
  restore. Test lossless migration on copied, never-live data.
- Repeatable multi-day scenario tests with known expected numbers and
  round-trip receipts and reports.

**Gate B status: IN PROGRESS — preview-only accounting summaries.**

## Gate C — Cloud / branches / owner mobile (BLOCKING for cloud SKU)

- Offline-first local transaction journal and server-issued branch identity;
  ordered, idempotent sync with retries, deduplication and conflict rules.
- Authenticated HTTPS API, scoped branch permissions, encrypted credentials,
  server-side validation, backups, retention, recovery and observability.
- Owner phone dashboard uses a least-privilege **read-only** API. No direct
  mobile/branch database access; no unverified public dashboard.
- Test disconnected operation, duplicate uploads, simultaneous branch edits,
  clock skew, partial sync and corrupted messages.
- Publish actual hosting/deployment costs and a sustainable free/low-cost
  operating model; **zero recurring expense cannot be guaranteed** for a
  continuously hosted service.

**Gate C status: NOT PRODUCTION-READY.** Do not fake branch sync.

## Gate D — Commercial licensing and recovery (BLOCKING)

- Offline license verification with a protected **private** signing key kept
  off customer devices; signed entitlements and expiration handling.
- Online activation/revocation is authenticated server-side, with privacy,
  offline grace periods, anti-abuse and legitimate recovery procedures.
- Trial state and uninstall/reinstall behavior designed with server
  entitlement and abuse controls where connectivity permits. No promise that
  any offline commercial software is literally uncrackable or impossible to
  reset.
- Password recovery by **verified email ownership only** through expiring,
  single-use, rate-limited server-generated tokens. Never allow a local
  unauthenticated reset just because someone enters an email address.
- Code signing, reproducible release build, dependency inventory, installer,
  update/rollback, backup/restore, malware scanning and license QA.

**Gate D status: NOT PRODUCTION-READY.**

## Gate E — Quality and accessibility (BLOCKING)

- Full `python run_v8_checks.py` passes without skips on Windows for the
  final release candidate, with snapshot of the exact Git commit.
- Manual test covers 100% of the 14 preview navigation screens and all
  commercial actions *only after* Gate A is implemented. Include Sinhala,
  Tamil and English, keyboard shortcuts, 100% / 125% / 150% DPI, printer,
  short windows, error handling and empty-state UX.
- Repeat run from new Windows profile and a clean installer with verified
  backup/restore. No production shop DB is used in development or QA.
- Log zero unhandled exceptions, check performance for representative product
  and invoice volume, and test long session / network outage recovery.
- Review user screenshots and track blocking UI regressions. The previous
  visible Billing 'Draft items' overlap was patched, **not yet manually
  confirmed** on the new build.

**Gate E status: PENDING current combined run and later manual acceptance.**

## Delivery discipline

All new work stays on `develop-v8`. Keep `main` untouched until a passing,
reviewed and explicitly approved release promotion. Prefer integrated batches:
core service contracts before checkout UI, accounting before owner analytics,
secure sync before mobile dashboard, verified cloud recovery before password
reset UI. Add an automated regression for every corrected defect. Never mark a
gate passed solely because code was committed, a preview button looks right or
an older test milestone passed.

Next recommended integrated batch: audited service transaction authorization
with disposable-schema tests, then atomic sale/return flows. Don't enable
payments, printing, cloud or paid licenses from the preview beforehand.

## Preview transaction gateway baseline (November 2026)

The PySide6 preview now constructs `PreviewTransactionGateway` backed by
`PreviewTransactionGate`. All nine contemplated financial actions
(sale, return, GRN, supplier/credit payments, points redemption, shift
open/close and receipt printing) **always raise PermissionError**, even if
a caller passes an Admin identity and fabricated license/shift claims.
This is explicitly **not** a commercial transaction authorization service:
the original `velopos.services` functions can still be imported and invoked
directly. The new gateway is therefore a deliberate interface and release
safety barrier, *not* an assertion that legacy transaction calls have been
secured. Do not add a Qt Checkout button until Gate A service-boundary
authentication, atomic rechecks, idempotency, shift validation and financial
rollback testing are completed.

Preview product and customer/supplier editor `get()` operations now
also recheck Admin authorization on every detail read; previously only writes
were authorized. Customer lookup failures clear prior customer identity,
selector and loyalty projection, and a revoked session cannot use a cached
role to search or display protected customer data. Disposable DB regressions
cover these cases.


## Atomic checkout diagnostic foundation (not checkout)

`PreviewCheckoutPreflight` provides a *read-only, fail-closed diagnostic* over
the canonical isolated preview SQLite schema. It validates draft inputs and
uses `BEGIN IMMEDIATE` to inspect persisted cashier identity/password-hash
fingerprint, an assigned open shift, combined stock requirements for repeated
barcodes, current sale prices, product expiry and active expired-batch
warnings in one locked snapshot. It **always rolls the transaction back**
and sets `can_checkout=False`; no payment, invoice, stock deduction,
receipt or idempotency reservation is created. The diagnostic deliberately
includes `idempotency_not_implemented` and `license_not_verified`, since a
well-formed request identifier or a UI license flag cannot be trusted to
authorize a commercial sale.

This is not a full sale validator: unit conversions, mixed batches, tax,
discounts, credit, loyalty, true duplicate request reservation, receipt
printing and verified commercial licensing are still missing. A locked
preflight does not reserve stock for a later sale; all rules must be
revalidated **inside the future atomic write transaction**. Disposable DB
tests exercise the true schema, stale sessions, shift closure, stock,
repeated lines, altered price, expired/missing items, hostile inputs, and
zero sale/payment/stock mutations. The preflight is constructed by
`SettingsPreview` but is not a Checkout UI action.


## Gate A next foundation: transaction-scoped idempotency ledger

The preview now includes `PreviewIdempotencyLedger`, an isolated **TEST DATA
ONLY** SQLite request-journal contract. It is a low-level building block for
future atomic sale/return service transactions, **not** a checkout feature or a
production guarantee. Callers must obtain `BEGIN IMMEDIATE` on the canonical
preview DB connection and keep the claim, any business mutations and result
marking in that **same** transaction. The helper never commits by itself.
`claim()` tracks a bounded request ID and SHA-256 of canonical request data;
identical completed requests return the existing result reference, changed
payloads using a previously claimed key raise an explicit conflict. Unfinished
committed claims fail closed, rather than being treated as safe automatic
retries. A rollback removes both uncommitted claim and related business writes.

The implementation includes disposable-DB tests for restart/crash rollback,
identical replay, conflicting payloads, malformed identifiers and payloads,
scope isolation, unrelated DB rejection and concurrent serialized claims.
Only the request metadata and opaque result reference are stored in the test
ledger; no live invoice, payment, stock movement or paid-license check is
performed. Crucially, none of the legacy `velopos.services` functions or V8
Qt Checkout is wired to this helper yet. Secure production transactions still
need verified session/license/shift authorization inside the same atomic
service-boundary operation, and appropriate operational idempotency recovery.

