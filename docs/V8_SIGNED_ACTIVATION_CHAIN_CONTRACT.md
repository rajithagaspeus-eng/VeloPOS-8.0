# VeloPOS 8 — Signed Activation Chain Preview Contract

**Status:** Experimental diagnostic on `VeloPOS8PreviewData` only. **No production activation or transaction permission.**

## Threat model and design

- Server-origin observations are Ed25519 signed; only an explicit public verification key is used. No private production signing key belongs in the installer, repository, client logs, or CI.
- A version-8 payload must have canonical machine, license, branch IDs, active/revoked status, signed integer sequence, UTC observation timestamp and UTC expiry.
- The successor observation signs the hexadecimal SHA-256 digest of the previous *signed payload bytes* using `previous_payload_sha256`. Both signatures are independently verified.
- Diagnostic checks reject duplicate JSON keys, invalid version/identities, different branch/machine/license, invalid signature, revoked observation, non-increasing sequence, descending UTC timestamp, mismatched previous digest, expired/stale status and future observations.
- `PreviewSignedActivationChainInspector.require()` always rejects. `can_execute=False` is intentional even if `chain_consistent=True`; it never touches real checkout, V7 licenses or customer data.

## Critical security limitations

**A pair of signed envelopes is not a trusted continuity anchor.** Anyone controlling client storage can replay an older *valid pair*. Client-provided `now`, SQLite tables and monotonic sequence watermarks are not trusted time or durable revocation state. Passing this diagnostic must never unlock checkout or lengthen trial time.

True commercial offline grace will require a carefully reviewed service design including server-maintained, monotonic per-license activation sequence, revocation, remote trusted time, authenticated device/branch entitlements and explicit outage policy. A fully offline client cannot guarantee uncrackable licensing or impossible-to-reset trials.

## Test acceptance

- Run `python run_v8_checks.py` using the Windows GitHub Actions PR workflow and verify the exact feature head.
- Adversarial test fixture creates disposable `VeloPOS8PreviewData`, test-only ephemeral Ed25519 keys, no cloud/API calls and no business transaction writes.
- Real Windows hardware, printer, full commercial checkout and migration are **not tested** by these preview unit tests.

## Next engineering batch

Review production trusted-clock/sequence options, signed server activation endpoint and offline grace abuse model; independently audit service-bound authorization before enabling any sales. Commercial Gates A/B/C/D/E remain blocked.
