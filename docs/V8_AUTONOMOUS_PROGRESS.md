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
- Last **verified** full Windows CI milestone for this core batch:
  **169 tests PASS**, run 41749040073, SHA
  `03a0a71ed541d469783c81fd747507a65f846d01`.
  The later documentation-only checkpoint commit must still receive its own
  CI result; never imply the prior test run covers unverified code.

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

## Gate D signed activation freshness diagnostic — November 4, 2026

Added `velopos_qt/activation_status.py`: a read-only, isolated-preview
Ed25519-signed activation status inspector with explicit machine/license
binding, revoked/inactive rejection, canonical UTC timestamp parsing, bounded
offline freshness (0–168 hours), future timestamp and clock rollback checks.
`tests/test_v8_phase2_activation_status.py` exercises ephemeral signed
server-status envelopes, forged signatures, expired status, revocation,
binding mismatches, future timestamps, rollback and production path refusal.
It is not connected to any transaction gateway, local license installation,
remote activation API or V7 code, and `can_execute` is always False.

**Security limitation:** `now` and `last_seen_utc` are caller-provided
diagnostic observations, NOT trustworthy clock attestations; an attacker
controlling local time/storage can bypass naive offline expiry logic. No
server activation service, authenticated server clock, tamper-resistant
continuity, signed key rotation, revocation cache or commercial grace
enforcement is implemented. Gate D and Gate A remain blocked.

**Next batch:** integrate independently signed entitlement and activation
status as a single fail-closed read-only policy with transaction-scoped
session/shift checks, then test tampered status and rollback against
disposable DB. Never turn any diagnostic into permission to post.

**CI:** New test commit `aaa7d56607c72dd9995f811d531a19346f0193f5`
awaits an exact-head Windows combined run; previous completed success
`974734c724b7cc9d2646bc08eea4e5f100690132` does not verify this code.


## Three-way signed activation diagnostic — November 4, 2026

Added `PreviewCombinedAuthorization.inspect_with_activation()` and
`require_with_activation()` to combine transaction-scoped persisted
session/role/shift inspection, signed action entitlement inspection and
independently signed activation freshness/status inspection. This is strictly
preview-only, read-only, fail-closed: `can_execute=False` regardless of
inputs. A separate `signed_license_id_binding_unverified` blocker documents
that the existing signed entitlement has no cryptographically bound license
identifier, so a caller-provided license ID cannot link it to a signed
activation status. No checkout, return, payment or stock mutation is enabled.

New disposable-database regression:
`tests/test_v8_phase2_three_way_authorization.py` tests valid-but-denied
credentials, revoked status, malformed status, hard-deny require and no
financial table writes. Code commits `f7660520cc587dbdb30c3d539c6ef7664e96ef22`
and `16820725f7a09367aa80d2a38e4eda1146607774`.
**Test status: not independently executed or Windows-CI verified yet.**
The next run must verify exact-head Windows CI and repair any failures.

**Next priority:** introduce an explicitly versioned signed V8 entitlement
license ID and enforce its equality with the signed activation license ID,
with adversarial tests (cross-license substitution, malformed IDs, forged
status, stale status, session revocation), still hard-denying all financial
writes. Then audit service-bound transaction authorization and replay.
Gate A/B/D/E remain blocked; never infer release readiness from this diagnostic.
