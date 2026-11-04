# VeloPOS 8.0 — Autonomous Development Checkpoint

**Branch:** `develop-v8` only. **Production readiness:** NOT APPROVED.
**Execution:** Each autonomous development run should read this file and
`docs/V8_MASTER_ROADMAP.md`, `docs/V8_COMMERCIAL_RELEASE_GATES.md`.
This records verifiable implementation evidence; update after each major batch.

## Current work (November 4, 2026)

- Functional isolated V8 UI preview with 14 navigation routes, English/Sinhala/
  Tamil drafts, editing restricted to preview storage, and design polish.
- Transaction gateway is intentionally hard-deny. No commercial checkout,
  payment, refund, supplier posting or shift mutation is enabled.
- Preview session proof, transaction-scoped authorization diagnostics,
  idempotency building block, rollback-only sale/return rehearsals and
  Admin-gated financial/stock ledger diagnostics exist in test-only code.
- Added `velopos_qt/license_entitlements.py`, a **pure fail-closed**
  Ed25519 signed license scope/machine/expiry inspector for the isolated
  preview. It accepts an explicit test public key, verifies cryptographic
  signatures and refuses unspecific legacy entitlements, but even a
  valid signed result always returns `can_execute=False`. It does not
  access, replace or generate production signing keys, install licenses,
  call trial servers, or authorize a sale. Ephemeral test-only key cases
  cover tampering, machine mismatch, expiry, unsupported action and V7
  payload compatibility. No real licensing integration was enabled.
- Last **verified** full Windows CI milestone before this batch:
  **167 tests PASS**, run 41747090462, SHA
  `d5d2ba33198b526725c9a3367afc70f5506d65ce`.
  Update with the latest CI result only after it completes.

## Blocking acceptance gates

- **Gate A BLOCKED**: production transaction service still permits legacy
  direct calls without verified commercial session and signed entitlement.
  Licensing, cashier shifts, branch scope, tax/stock validation and crash-safe
  replay must all be enforced at the **service boundary** inside one atomic
  transaction before any real posting is exposed.
- **Gate B IN PROGRESS**: no certified per-event invoice COGS, tax,
  loyalty and stock batch reconciliation or full migration acceptance.
- **Gate C NOT READY**: real authenticated offline-first cloud multi-branch
  sync, conflict handling and mobile dashboard API absent.
- **Gate D NOT READY**: signed commercial entitlements, server-authoritative
  trial protection, verified-email recovery and installer/upgrade hardening
  not proved end-to-end.
- **Gate E NOT READY**: final Windows DPI, multilingual/hardware/manual QA
  and signed release acceptance outstanding.

## Next actionable engineering batch

Implement a **single, trusted commercial license policy contract** separate
from Qt and global V7 license state: validate signed device/action/expiry
claims, define fail-closed trial and offline grace handling, and test forged,
missing and expired claims. Do not assume signed legacy licenses contain V8
feature scopes; preserve existing paid license use in V7. Then integrate
with a transaction-scoped service authorization design, still denying all
real transactions until every Gate A/B acceptance rule is proven.

## Operational safety

Never mutate `main` or real customer databases. Never rotate, generate or
commit real Ed25519 private signing keys. Do not equate CI preview passes with
commercial transaction release approval. Preserve the original V7 services
until a reviewed, backward-compatible production integration plan exists.

## Gate A combined authorization inspection — November 4, 2026

`velopos_qt/combined_authorization.py` composes the existing preview
transaction-scoped persisted cashier-role/shift/session check and a
cryptographically signed machine/action/expiry entitlement inspection.
The first check enforces an isolated canonical SQLite transaction;
neither a valid signature nor a live Admin/Cashier session can turn
`can_execute` on. `require()` always raises PermissionError.
It does not trust UI privilege flags or modify installed V7 licensing.
Disposable-db regressions cover valid-but-denied credentials, forged key,
wrong role, password rotation/revocation, nontransaction access, bad
actions and production-path rejection. This is an integration diagnostic,
**not** commercial licensing, revocation, offline grace, trial enforcement,
or authorization to post financial transactions. Gate A remains BLOCKED.

Next: design signed entitlement policy with a trusted clock/server-backed
revocation model, audit transaction boundary threats and atomic replay/
stock batch consistency. No production transactions until every gate passes.
