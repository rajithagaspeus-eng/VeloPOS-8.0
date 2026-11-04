# VeloPOS 8.0 — Commercial release gates (develop-v8 only)

This is the acceptance contract for the integrated development program. It is **not**
a statement that all items are implemented. The PySide6 V8 application remains
an isolated **TEST DATA ONLY**, nontransactional preview.

## Current evidence

- Owner-confirmed newer **local Windows** regression milestone:
  `dd7ae38b4adfdfb53f0b23fe9690fd3d76f7ba70` ran
  `python run_v8_checks.py`: **263 tests, OK, 88.806 seconds**;
  `python -m compileall -q velopos_qt tests` returned without visible
  errors. The test runner rejects skipped tests. This evidence is for that
  exact earlier code SHA only, NOT for later Phase 1 safety commits.
  GitHub-hosted push Actions success on the current head remains unverified.
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


## Gate A service-bound authorization diagnostic (preview only)

`velopos_qt/service_authorization.py` introduces a `PreviewServiceAuthorization`
contract for future service-side authorization checks using the **same**
caller-owned SQLite transaction as the operation being evaluated. It rejects
non-preview/foreign DB connections and missing transactions, rechecks the
persisted user role and credential fingerprint, validates per-action roles,
and checks open shifts and cashier assignment for applicable financial
actions. An Admin-looking Qt identity, untrusted boolean, deleted account,
rotated password, demoted user, wrong shift or closed shift cannot bypass
these checks.

**This is intentionally not a license verifier and grants no permission.**
Every returned decision has `can_execute=False` and an explicit
`commercial_license_unverified` and `preview_transactions_disabled`
reason. `require()` raises `PermissionError` unconditionally. Neither this
module nor the idempotency journal is wired to the original V7 financial
service methods, so Gate A remains BLOCKED. Commercial implementation must
enforce signed entitlements, verified sessions, branch, cashier shift, stock,
tax and idempotency within a **single** atomic service transaction and
remove alternate unauthenticated legacy entry points before checkout is
exposed.

The newly added disposable-database tests exercise valid user checks that
still deny checkout, cashier-versus-admin rules, mismatched or missing shifts,
forged identities, persisted role changes, password rotation, invalid
actions, transaction requirements, foreign SQLite connections and database
path isolation. Passing preview tests alone is not production acceptance.

## Gate A — HMAC preview sessions and rollback-only sale integration exercise

Preview sign-ins now receive a process-local **random-nonce HMAC session proof**
bound to the canonical preview database path, username, current role and
stored password hash. This replaces the earlier forgeable
`SHA256(stored_pw_hash)` credential fingerprint. The proof must be present
in the current process's active session set, so copying a user-table password
hash cannot manufacture a valid session; a process restart or explicit UI
sign-out invalidates it. Role mismatch, password rotation or deletion revokes
the proof on detection, preventing a demote-and-repromote cycle from reviving
a session. Checkout preflight, protected service authorization diagnostics,
and normal Admin/Cashier readers share this same verifier. This is a
**preview-only process session**, not a remote/production authentication
infrastructure; stolen live session objects, local machine compromise, and
production entitlement threats are not solved by HMAC alone.

The standalone `RollbackOnlySaleRehearsal` now joins service-authorization
diagnostics, idempotency claim/complete, duplicate-barcode stock aggregation,
current-price validation, synthetic invoice and sale-item staging **inside
one `BEGIN IMMEDIATE` transaction** on the isolated TEST database.
**Every execution, including apparent success, unconditionally rolls back.**
This simulates atomic failure behavior without selling, printing, charging,
persisting invoice records, changing lasting stock, or enabling checkout.
It is intentionally not wired to the Qt gateway or legacy service. Rehearsal
regressions verify injected failures after stock and invoice staging,
invalid data, denied sessions/shifts, idempotency and full state rollback.
It does **not** implement actual revenue, taxes, loyalty, purchase posting,
returns, real idempotent replay, stock batches or commercial licensing.
Release Gate A remains BLOCKED; these are engineering test scaffolds only.

## Gate A — rollback-only partial-return rehearsal

`RollbackOnlyReturnRehearsal` is a **test-only** counterpart to the sale
rehearsal and has **no** UI, refund or production-service entry point. It
opens a canonical preview `BEGIN IMMEDIATE` transaction, inspects current
session and cashier shift, claims a scoped idempotency key, validates an
existing `OK` invoice and original sale-item IDs, and calculates each
remaining return allowance as sold quantity minus all earlier recorded
returned quantities. Repeated items in the new request are combined, so
multiple lines cannot conceal an over-return. It stages stock restoration,
synthetic `returns` and `return_items` rows and completion of the request
claim only within that same transaction. Its `finally` block **always rolls
everything back, including on apparent success**.

Automated disposable-DB tests cover partial prior returns, repeated lines,
over-return and cross-invoice rejection, invalid quantities, missing/void
invoices, closed shifts, injected failures after stock and return rows, and
the absence of lasting refund, stock or idempotency changes. The simulated
refund is based on original sale-item price and is NOT valid tax/discount,
loyalty, credit or COGS accounting. No real return, payment or stock posting
is enabled. Gate A and Gate B remain blocked for commercial operations.

## Gate B — invoice and stock-ledger diagnostic auditing

`PreviewLedgerAuditor` adds a small **read-only, Admin-gated** audit entry
point on the isolated V8 test database. `audit_invoice(invoice_no)`
compares the original sale's recorded subtotal to the sum of persisted
sale-item totals, looks for missing/invalid sale lines, verifies that return
items point back to the same original invoice and barcode, checks that
cumulative returned quantity does not exceed sold quantity, and identifies
orphan/foreign return references. It includes *all historical returns* for
the targeted invoice, not just a selected date range. The original sale
may be OK or VOID; an audit never converts it to a sale or issues a refund.

`audit_stock(barcode)` compares a product's current stored stock balance
to the latest recorded movement's `qty_after`, identifying missing
movement history and endpoint discrepancies. This is **not** a comprehensive
stock genealogy, unit-conversion, purchase batch or per-shift reconciliation.

Audit methods require a live Admin authorization callback at each read;
they never change, repair, export or certify financial data. They return
specific findings and `certified=False`. Because legitimate returns can
have VAT, discounts and loyalty adjustments, the auditor deliberately does
**not** call a raw sum of return-item prices an exact refund/COGS amount.
This does not yet cover taxes, credit, loyalty, supplier advances or
profit adjustments. Gate B remains **IN PROGRESS**, not passed.

Disposable-schema automated tests cover a balanced invoice, earlier partial
return, over-return through repeated historical entries, wrong-invoice
references, missing return items, subtotal drift, stock-ledger drift and
revoked/no Admin access. Full financial reconciliation must eventually use
authoritative posted transactions rather than fabricated rehearsal records.

## Gate B — invoice totals, customer credit and supplier liabilities diagnostics

The read-only, Admin-gated `PreviewLedgerAuditor` now also supports
`audit_sale_totals(invoice_no)`, `audit_customer_credit(customer_id)`, and
`audit_supplier_balance(supplier_id)` on isolated V8 test storage.
Sales checks reconstruct the net amount from original subtotal, discounts,
redeemed points, service charge and inclusive/exclusive VAT treatment,
and flag obvious payment/change mismatches. They do **not** independently
recalculate taxable allocations, rounded tax rates, split payments or COGS.

Customer credit checks compare the present balance to known
`CREDIT_SALE` inflows less `PAYMENT`, `RETURN` and `VOID` outflows.
A difference is recorded as an **unverified** balance rather than silently
repairing it; opening balances, migration history or unknown event types may
explain mismatches. Loyalty has no complete standalone event ledger in V7:
only obvious invalid negative balances are flagged and
`loyalty_reconciled=False` is returned, never a fictional certification.

Supplier balances use all historical successful GRNs minus
`supplier_payments` and **do not deduct GRN initial payments twice**, as
the original purchase service also creates their payment ledger entries.
Payments after purchase dates still count. Negative balances are supplier
advances, not hidden reductions to other supplier payables. Cross-supplier
purchase references and invalid/negative payments are reported. These
per-record checks do not prove every payment was posted correctly or replace
a production accounting audit.

The new regression suite covers clean and intentionally inconsistent sales,
VAT-inclusive/exclusive totals, customer credit logs, supplier advances,
voided GRNs, wrongly linked payment rows, authorization revocation and
the absence of audit writes. **Gate B remains IN PROGRESS.**
