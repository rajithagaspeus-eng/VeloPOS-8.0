# VeloPOS 8 — Offline Grace / Reconnect Reference Contract

**Status:** Preview-only signed grant protocol. Not production authorization, not a live activation server and not permission to post financial transactions.

## Business goal

Allow a future VeloPOS installation to keep local retail work going during temporary loss of internet **once** the owner-defined commercial licensing/service gates are independently met. The software must recover cleanly without losing shop transactions. Grace cannot become a mandatory online dependency for core billing. The user currently requires zero mandatory paid subscriptions.

## Proposed grant flow (implemented as isolated reference)

1. On a trusted server, verify that the caller presents the latest signed activation receipt **and** that the independent license record is active, bound to the exact license / machine / branch and still unexpired.
2. The reference service `PreviewOfflineGraceAuthority.issue()` signs a v8 `offline_grace` grant for 1–24 hours, never past the signed commercial license expiration. The exact current receipt payload SHA-256 digest and server sequence are signed into the grant. Time and private key are explicitly TEST inputs here. In reality they must be protected by the host.
3. The offline client `PreviewOfflineGraceInspector.inspect()` cryptographically verifies **both** the receipt and the grant against a configured public key, checks identities and sequence/digest binding, chronological validity and bounded expiry. A local rollback watermark can add diagnostic evidence, but cannot anchor trust because users can alter it.
4. An in-window diagnostic returns `window_consistent=True` and **always** `can_execute=False`. `.require_checkout()` always denies, including healthy grants. Neither client clock nor cached receipts can grant commercial posting permission.

## Expected reconnect and renewal / recovery behavior (design only)

- On reconnect, the device must use an authenticated, TLS-protected server endpoint and refresh its server-authoritative license/branch/expiry/revocation state before obtaining a new receipt/grant. This endpoint **does not exist yet**.
- A superseded or revoked receipt must not be treated as the current server state; a newly issued grant requires the new current receipt. Revoked/expired licenses must be rejected on the server. Customers with server-side renewal or legally authorized machine transfer need separate audited workflows.
- During a connectivity outage, an offline device cannot know about newly revoked licenses, and an attacker can roll back the PC clock and locally stored grant pair. An old, valid receipt+grant may still pass local mathematical consistency. Design a humane outage and escalation policy; do not claim instant offline revocation.
- Lost device, damaged DB, reinstall, renewed subscription, clock mismatch or wrong branch should show understandable diagnostics and owner-support recovery paths. Never delete or silently modify financial records to repair license state.
- Commercial billing may eventually have a separate approved short-grace policy, but must not enable until transaction-service permissions, database integrity, backup/restore, and release gates A/B/C/D/E have passed end-to-end verification.

## Data & security boundary

Server-side state and signing keys must be independent of the cashier's PC. The Python class in `velopos_qt/offline_grace_reference.py` uses **disposable** `VeloPOS8PreviewData`, in-memory test Ed25519 keys and an injectable test clock. This is not deployable, reliable anti-tamper offline licensing, or proof a hosted server can stay free of cost.

No real activation API, server database/key custody, device attestation, sync engine, installer, license activation UI, paid trial, transaction posting or commercial authorization is implemented.

## Adversarial regression acceptance

`tests/test_v8_phase2_offline_grace.py` checks signed current receipt binding, short duration cap, commercial license expiry cap, future/expired clock, local rollback observation, wrong identity, forged signatures, receipt digest mismatch, sequence mismatch, duplicate JSON, revoked/superseded server receipt rejection, unchanged V7 customer/transaction records and production path denial. Test explicitly proves a revoked license's *previously issued* grant can still look locally consistent when the device remains offline.

Require exact-head Windows CI with `python -m compileall -q velopos_qt tests` and `python run_v8_checks.py` with no skips. Recheck post-merge CI and document remaining blockers.
