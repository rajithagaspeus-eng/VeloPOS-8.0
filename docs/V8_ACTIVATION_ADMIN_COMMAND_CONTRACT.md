# VeloPOS 8 — Authenticated Activation Command Contract (PREVIEW ONLY)

**Status:** Reference protocol, not a production authentication gateway, network service, license activation client or billing authority. The Python classes are only usable with isolated disposable `VeloPOS8PreviewData`. No external API, live activation, trial or financial posting has been enabled.

## Command envelope

An operator signs the *exact JSON bytes* of a V8 request body with their own Ed25519 key. The envelope is `base64url(json).base64url(signature)`, with fields: `v`, `operator_id`, `request_id`, `operation`, `issued_utc`, `expires_utc`, and `payload`.

Supported **reference operations**: `register` (immutable license/device/branch/expiry), `revoke` (permanent server-side license status) and `issue` (monotonic signed activation receipt). A request ID of at least 8 characters is required. Only canonical UTC timestamps within a 10-minute signed validity interval are accepted. Unknown/extra request fields, duplicate JSON keys, forged signatures, expired/future commands and unrecognized operations fail closed.

## Authorization and replay contract

- A trusted server **must** maintain a protected roster of Ed25519 operator public keys. The signed `operator_id` is authenticated against that roster in the same transaction. Request bodies carry no trusted role flag. Inactive/unknown keys fail closed.
- The `Admin` role can register, revoke and issue. The `Issuer` role can issue receipts only, never register/revoke. These example roles are not customer/cashier permissions and are not evidence of multi-tenant server isolation.
- All commands are stored as an `(operator_id, request_id)` key, SHA-256 of the exact signed payload, operation, result and UTC audit timestamp in the caller-owned transaction. Retrying an **identical, still-valid and still-authorized** signed command returns its stored response without reissuing or incrementing the activation sequence.
- Reusing the same request ID for a different signed body is rejected. A retry of an issue command is also rejected if the issued receipt has been revoked, expired or superseded since initial delivery.
- A return from the reference gateway is **not** confirmation that the caller committed. The real backend must commit the command journal and license state atomically **before transmitting success**, with secure transport retry semantics and recovery from lost responses.
- Duplicate operator provisioning is not permitted. Disabled operators cannot replay successful signed requests. Provisioning/disabling operators are **UNAUTHENTICATED TEST FIXTURE METHODS** and MUST NOT be exported as client-facing endpoints.

## Security limits — must be resolved before production

1. There is no deployed HTTP/TLS backend, multi-tenant authorization model, server-held database or physically protected signing key. Keys and clocks used in tests are ephemeral; a local client database/time is not a trust root.
2. Do **not** expose `provision_operator`, `disable_operator`, `dispatch` or `PreviewServerActivationAuthority` methods to a cashier device or unauthenticated network transport. A production API needs trusted bootstrap, key rotation/revocation, operator MFA, least privilege, audit integrity, rate limits, tenant scoping, concurrency/lock and disaster-recovery design.
3. These reference signed commands use short UTC freshness windows. The backend's real clock must be protected. Replayed valid envelopes cannot create new operations after a successful immutable command; restoring *all* state from a compromised server backup remains a separate operational risk.
4. A customer PC offline cannot learn fresh server revocations. A fair, bounded offline grace policy needs separate threat modeling; avoid claiming tamperproof unlimited offline licensing or cost-free high-availability hosting.
5. Command authentication is completely separate from commercial POS authorization. Checkout, refunds, purchase, stock and financial services remain hard-denied in V8 preview. All commercial release gates remain blocked.

## Verification

Run Windows CI with `python -m compileall -q velopos_qt tests` and `python run_v8_checks.py` (no skips) on the **exact PR head SHA**. `tests/test_v8_phase2_activation_admin_gateway.py` covers valid roles, forged operators, stale commands, immutable idempotency, revocation and key disablement, invalid JSON, rollback, production-path isolation and no business writes.

## Next priority

Design a deployable **optional** backend with proper authentication, key custody, signed server receipts and server database, then a separately tested customer-safe offline grace and recovery policy. Preserve the zero-mandatory-paid-cost constraint for local POS functionality; do not promise a permanently free hosted service.
