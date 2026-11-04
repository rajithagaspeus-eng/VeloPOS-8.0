# V8 integrated atomic return boundary — preview diagnostic

**Status: TEST DATA ONLY. This does not implement a return, refund, stock restoration, or checkout service.**

PreviewAtomicReturnBoundary inspects persisted session and role, cashier shift, canonical branch membership, signed V8 return entitlement, activation chain, original invoice eligibility, and cumulative returnable quantity in one caller-owned SQLite transaction. It reports the rounded return amount as diagnostic evidence. It does not write rows, reserve an idempotency key, call legacy services, or commit a caller transaction. Its owned transaction always rolls back; require() always denies.

## Coverage

tests/test_v8_phase2_atomic_return_boundary.py uses an isolated temporary preview database and ephemeral Ed25519 keys. It covers duplicate return quantities, prior partial returns, void and missing invoices, wrong session, branch membership revocation, closed shift, forged activation signature, malformed input, immutable deny behavior, caller-owned rollback, and production-like storage refusal.

## Commercial blockers

This diagnostic does not establish trusted commercial license, clock or revocation; tax and discount allocation; refund tender or credit/loyalty reversals; batch restoration; authorization in legacy service entry points; committed idempotent refunds; concurrency acceptance; or Windows/manual device QA. Gate A and Gate B remain blocked. Do not connect this diagnostic to the Qt action path or enable refunds or stock mutations based on a passing preview check.
