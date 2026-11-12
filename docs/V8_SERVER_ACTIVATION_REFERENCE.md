# VeloPOS 8 — Server Activation Reference Ledger (preview only)

## What this implements

Python reference code at `velopos_qt/server_activation_reference.py`, restricted to disposable `VeloPOS8PreviewData`, simulates *server-owned* activation status records. It is not a deployed web service, production authentication flow, license installer, trial enforcement, or billing permission.

- A reference SQLite table stores immutable license ID/device/branch binding, canonical UTC expiration, active/revoked state, last signed sequence, observed UTC and SHA-256 digest of the latest signed payload.
- On trusted-operator registration, `INSERT` rejects duplicate IDs. Re-registering an existing ID cannot reset the signed sequence, revocation or binding.
- A receipt is Ed25519 signed using a test-only, caller-provided in-memory signing key. A chain of receipts includes the prior payload digest; payloads have strict versioned identity, monotonic signed sequence and server observation time.
- Replaying a previously signed receipt can be detected **when the independent server state is intact**: `inspect_current()` compares the signature, identities, sequence, exact latest payload digest and observed time with the server's stored state.
- A revoked license is denied immediately by server state, even before a new signed revoked receipt is issued. Expired active licenses are denied; expired active receipts are not issued.
- Caller-owned SQLite `BEGIN IMMEDIATE` transactions and atomic updates protect each state transition in the reference; signing and the watermark change occur together. No real business transactions are enabled.

## This is NOT trustworthy commercial activation

**Important:** The code intentionally uses an isolated *local preview* database and a caller-injected test clock and signing key. An attacker with control of that local database can restore old state and an old receipt together. Neither this class nor a client-held signed pair provides real anti-rollback protection. Passing the diagnostic is not a right to sell: `can_execute=False` and `require()` always rejects.

Do NOT copy this class into the shipped POS, expose `register`, `revoke` or `issue` as unauthenticated HTTP endpoints, or put any signing private key into client/source/CI. Server state must be independent of the client in an authenticated, secure service.

## Production prerequisites (unimplemented)

1. Secure server-hosted database with backups, transaction isolation, migrations, bounded audit logs and tenant isolation; immutable license creation and authenticated administrator-only revoke/renew/transfer.
2. Protected signing service and key lifecycle, anti-abuse throttling, authenticated device proof and branch/license binding, server-generated UTC time, revocation and expiry enforcement.
3. Explicit offline grace policy for shops disconnected from the server, including recovery and fair-use rules. Offline authorization after server contact cannot guarantee instant revocation and client clocks/storage are tamperable.
4. Replay-safe activation endpoints with idempotent retries and signed response delivery. A signed receipt must not be returned as committed if its state transaction rolled back.
5. Audit and test production service authorization at the financial **service boundary**; cashier sessions, shifts, branch, license, tax, stock, purchase and refunds must be rechecked atomically before any posting.
6. Deployment privacy, commercial hosting costs and availability plan. No always-online free backend can be guaranteed cost-free for all volumes.

## Preview test acceptance

`tests/test_v8_phase2_server_activation_reference.py` uses only ephemeral Ed25519 keys and temporary preview storage. It checks registration, two signed receipts, server-side stale receipt rejection, revoked license denial, expiry, wrong device/branch, forged signature, duplicate registration, clock rollback, transaction rollback, production path rejection and zero financial writes.

Run Windows GitHub Actions using `python run_v8_checks.py` on the exact PR SHA. The test suite is not proof of a live backend or production readiness. V8 commercial Gates A/B/C/D/E remain blocked.
