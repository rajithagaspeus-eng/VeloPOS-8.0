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

