# VeloPOS 8.0 — Commercial Security & Recovery Contract

**Status:** Required release criteria. Not all features are implemented. **Never claim the app is uncrackable.**
**Branch:** `develop-v8` only. Zero mandatory paid infrastructure.

## 1. License security and tamper resistance

- Retain the existing Ed25519 public-key verification. The **private signing key and KeyGen never ship in the customer installer and never enter GitHub**. Do not initialize a replacement key or invalidate existing customers.
- Verify signatures, machine binding, expiry/plan/features and a trustworthy activation status **at every entry point** for protected commercial operations; the UI hiding a button is not protection. Use one policy decision object for UI and services. Do not break the pre-existing license format without a documented migration.
- Protect against trivial patching with code signing **if a viable budget becomes available**, hardened packaging, integrity checks and signed releases; those are defense-in-depth, **not a 100% guarantee**. The customer must never be able to create a valid Ed25519 license from the verification key.
- Reevaluate existing `license._mac_key(mid)`: this key derives solely from publicly obtainable machine information; local HMAC trial seals are **not a cryptographic boundary against a determined local attacker**. Do not mislabel them as unforgeable.
- Do not collect unnecessary hardware information or leak internal machine identifiers in logs, UI or API responses.

## 2. Trial that does not simply restart on uninstall/reinstall

- A trial starts at an **authoritative, persisted server first-seen timestamp** for a stable pseudonymous device ID when reachable. The current optional `/trial` Cloudflare Worker integration already records a server date; audit/deploy/test it rather than making a second parallel backend.
- Keep existing multi-store local continuity and rollback checks as offline resilience; **a fully offline, user-controlled PC can erase/forge local state and cannot be guaranteed reset-proof**. Choose a documented offline grace policy for commercial editions; once connected, reconcile to the earliest trustworthy timestamp. Never reset a paid license or erase user data on trial expiry.
- Do not treat reinstall, changing local clock, deleting local SQLite, or editing an app setting as grounds for automatically granting a fresh trial. On integrity failure, prefer an explicit recover/contact-owner path, not destroying customer records.
- Require server-side abuse limits and data-retention/privacy disclosure before public launch. Do not rely on the current endpoint URL alone as evidence that its policy has been deployed/verified.
- Trial durations and commercial plans must come from signed/authoritative claims, not editable local preferences.

## 3. Forgot password via email

- Support an **Admin's verified, unique recovery email**. Non-admin staff reset through the existing Admin-approved staff management workflow. Current `users` table does not have email and old `reset_password(..., via,...)` trusts that a caller already verified proof.
- **Never allow password reset just because the user typed an address, username, or a `via='email'` string.** Desktop app must obtain a short-lived, single-use, random reset token from a trusted backend. Only a server that can verify token ownership and expiration may issue an authoritative proof. Never expose raw reset tokens or passwords in URLs, logs, database dumps or audit details.
- Recovery flow: request reset (uniform response for known/unknown users) → server rate-limit, authenticate installation/device association, send expiring single-use link or OTP to **previously verified** email → server validate and consume token atomically → client validate signed/attested proof binding intended account/device/action → existing password hashing and audited service updates password → invalidate sessions/previous recovery grants.
- Use HTTPS, no baked-in SMTP password, and a free-tier-capable optional mail provider only after checking current limits/terms. Offline fallback: existing one-time physical recovery code or verified developer-assisted procedure; never unverified email-based local reset.
- Separate user password recovery from license activation and from private signing keys. Email reset must not reset trial status.
- Do not automatically email user data or send anything from the preview. Explicit consent and privacy requirements apply.

## 4. Staff authentication and transactions

- Reuse the existing `users`, `security.verify_password`, `services.login_locked_for/login_failed/login_ok` and `save_user` / `reset_password` where safe.
- Every protected action must be gated by a **verified session with explicit role/permission**, with service-layer checks. No default production passwords. Failed authentication never unlocks a transaction.
- Current V8 billing draft remains **non-transactional**; no real checkout, payment, receipt, shift close, stock deduction or admin licensing.
- Test unknown users, wrong passwords, lockout persistence, role assignment, session invalidation, and login success with isolated preview SQLite.
- Do not enable production functions merely because a Qt smoke test passes.

## 5. Release gates

- [ ] Existing Ed25519 key generation and verification audited, backward compatibility proven.
- [ ] Signed license feature/expiry/device policy checked at service boundary.
- [ ] Trial server persistent first-seen semantics and reinstall/clock rollback tests proven.
- [ ] Offline grace/failure mode chosen; no misleading claim of perfect offline reset prevention.
- [ ] Verified-email enrollment and trusted backend with single-use token consumption.
- [ ] Reset request enumeration/privacy/rate limiting, proof validation and audit tests.
- [ ] Login role+session verification and permission checks at write/checkout boundary.
- [ ] Recovery paths documented for lost devices, email change and offline customers.
- [ ] Installer leak scan: no signing private keys, SMTP/API secrets or hardcoded admin credentials.
- [ ] Single combined Windows acceptance suite + real-device multilingual UI QA.

## Current audit (Batch 07)

Already present in legacy: Ed25519 verification, 30-day trial local stores plus an optional Worker first-seen lookup, PBKDF2 hashed passwords, recovery code, persistent login/reset throttling, and an audited Admin-password reset function. The legacy code is **not proof of commercial-grade resistance**; some pieces need hardening and integration. This batch adds a read-only preview authenticator foundation and tests; **it does not ship email delivery, unbreakable licensing, or a live checkout**.
