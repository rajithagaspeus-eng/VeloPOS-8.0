# VeloPOS 8 — License Renewal and Device/Branch Recovery Reference

**Status:** Preview-only, in-process reference on disposable `VeloPOS8PreviewData`. This is **not** a deployed licensing API, real customer renewal, online authorization, payment workflow, machine attestation or commercial POS checkout.

## Operations

`PreviewLicenseRecoveryReference` adds two admin-only **reference transitions** through `PreviewSignedActivationGateway`. The gateway authenticates an Ed25519-signed Admin command from a server-held operator public-key roster, checks a short signed validity window and journals the exact request ID/body hash/response in the same caller-owned preview transaction.

- **Renew:** Require an existing active license and the exact currently recorded activation `expected_sequence`. The new canonical UTC expiry must strictly extend the previous expiry, lie after the backend clock, and not exceed 366 days into the future. Renewal can restore an elapsed but **not revoked** active license. The signing key and server clock are test fixtures in this implementation.
- **Transfer:** Require active, unexpired license, exact server-observed sequence and *both* previously assigned machine and branch IDs. New device/branch must differ; the transition is administrative only, not self-service. Revoke status, last signed activation sequence and previous signed-payload SHA-256 digest are **not reset**.
- Previous signed activation receipts become invalid against live **server** state after either renewal (changed signed expiry) or transfer (changed signed identities). A new `issue` signed command is needed for the new server binding, advancing the existing sequence.
- Same valid signed command/request ID returns a journaled idempotent result only while the current server binding, expiry and sequence still match that result. If a receipt is issued, license transferred again, renewed again or revoked, an earlier retry fails closed instead of implying fresh authorization.

## Operations deliberately NOT implemented

- No real customer lookup, secure tenant isolation, anti-fraud proof of ownership, order/payment verification, administrator MFA, physical-device attestation, lost-device termination confirmation, automatic payment refund or license product tiers.
- No Web UI/HTTP endpoint, hardened database/key backup, rate limits, reseller admin API, key rotation, live SSL/TLS service or actual user account integration.
- No automatic reactivation of revoked licenses. Revocation remains permanent in this reference.
- **Offline security limitation:** old signed offline grace grants may remain mathematically valid while the old machine is disconnected; a remotely authorized transfer cannot instantly invalidate locally cached grants. A production service needs explicit grace/transfer handling, customer communication, session safety and risk management.
- All existing V8 preview authorization decisions remain `can_execute=False`; neither renewal nor transfer grants checkout, refund, stock, purchasing or payment privileges.

## Crash safety and audit constraints

A future server must own the database and sign/commit its activation result atomically before sending success. This reference assumes the caller opens `BEGIN IMMEDIATE`, commits the command journal and license state together, and never exposes test-only privileged bootstrap methods as HTTP endpoints. All operations keep the same immutable `license_id`; no `INSERT OR REPLACE` resets the prior sequence, signature chain or revocation.

## Verification

`tests/test_v8_phase2_license_recovery.py` exercises valid signed renewal/transfer, Admin vs Issuer roles, unchanged activation sequence, stale signed receipts, fresh re-issuance after transfer, rejected stale response replays, wrong previous device/branch/sequence, revoked or expired recovery, illegal expiry extensions, transaction rollback, no financial writes and rejection of production-like paths.

Before merging require exact SHA Windows GitHub Actions with `python -m compileall -q velopos_qt tests` and `python run_v8_checks.py`, zero failures and skips. Independently verify merged-head push CI. Commercial release Gates A/B/C/D/E remain blocked.

## Next priorities

Design secure tenant-aware owner approval, license support and validated recovery with real independent backend, key custody and durable audit. Then inspect the **actual financial service boundary** and premium UI acceptance. Maintain the zero-mandatory-paid-cost constraint for offline desktop POS.
