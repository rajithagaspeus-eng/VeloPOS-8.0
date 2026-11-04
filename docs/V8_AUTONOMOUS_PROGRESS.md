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


## Signed V8 license/activation identity binding — November 4, 2026

Added optional `signed_license_id` to the fail-closed entitlement decision:
only a signature-verified envelope explicitly declaring `v=8` and a bounded
ASCII license ID can expose it. `inspect_with_activation` now compares this
signed identifier against the activation status's required license ID.
Cross-license substitution, malformed IDs and legacy envelopes retain
`signed_license_id_binding_unverified`. The existing test now covers
matching V8 identity, substitution, malformed identity, legacy fallback,
revocation, forged status, and no financial mutations.

Commits: `74518e4402a6e8c6448a82096dc26ce734a7b4e9`,
`ba1a329a03fcf5bd4e0009166346405c44e90d81`,
`13ecf90cecf3a899373e784cf0229dd4b844de7b`.
**Verification:** tests not executed locally; commit status and
pull-request-filtered workflow lookup returned no entries for code head
`13ecf90cecf3a899373e784cf0229dd4b844de7b`.
No exact-head Windows CI PASS can be claimed. The workflow lookup does
not cover push-triggered runs, so an empty response is inconclusive.

**Next:** verify Windows push CI using an Actions run listing that includes
push events; fix any regression. Continue adversarial entitlement validation
and activation policy with trusted server time/revocation, then service-side
atomic transaction architecture. Existing V7 behavior untouched. All
commercial gates remain blocked; preview always denies posting.


## Signed-envelope ambiguity hardening — November 4, 2026

Signed V8 license and signed activation status JSON now reject duplicate
object keys (including nested duplicate claims) rather than silently using
the last value. This prevents cross-parser claim confusion where one verifier
could interpret `status=active` or `license_id` differently from another.
The V8 version discriminator now requires an actual integer 8; JSON boolean
`true` can no longer masquerade as Python `8` for signed ID binding.
Changes remain entirely inside isolated preview diagnostics and do not
authorize financial writes or change V7 licensing.

Code commits: `4897db05e596a78e8025949bd4b9b4204d36e3e7`,
`8cc9355a0a18fb43700af5bb0f709531ab64679b`;
adversarial regression commit `d7401e7f60be38601dd6223016df4f9da02f9074`.
**Verification:** tests not executed in this tool session; exact-head
Windows CI must be checked independently. The available commit workflow
lookup covers pull requests only and cannot establish push-run status.

**Next priority:** obtain reliable push-triggered Windows Actions run
status for exact head; fix any regressions. Then harden license and
activation canonical claim schemas, signed server observation continuity,
and transaction-scoped branch authorization. All Gate A/B/C/D/E release
requirements remain outstanding; checkout stays disabled.


## Signed activation identity type hardening — November 4, 2026

Hardened `velopos_qt/activation_status.py` so caller-supplied license IDs
must be bounded ASCII alphanumeric/underscore/hyphen strings, matching the
V8 signed entitlement identifier grammar. Signed activation machine/license
identities must be actual JSON strings, never booleans, numbers, arrays or
objects. A non-string signed status cannot satisfy `active`. The existing
disposable-db activation test now covers these malformed and substituted
claims and rejects malformed caller IDs.

Code commit: `b0aec15bff3fab0542e0087af296bb7ad58a5737`.
Test commit: `69296f4a56d0090185bb3c57e44e8a8408f1445a`.
**Verification:** no test runner was executed in this session. Combined
commit-status lookup returned no statuses; the available workflow lookup
returned no PR-triggered runs. Neither establishes whether push-triggered
Windows CI ran. Exact-head Windows acceptance remains **UNVERIFIED**.

**Next priority:** verify push-triggered Windows Actions CI with a reliable
all-event run listing or Windows runner, then strengthen signed activation
continuity/revocation against clock rollback and replay. Develop
transaction-scoped branch identity and service-bound checks on isolated
preview DB only. Gate A/B/C/D/E remain blocked; no financial posting.


## Signed activation replay-watermark diagnostic — November 4, 2026

The preview activation inspector now flags
`activation_observation_replay_suspected` when a cryptographically signed
observation predates the caller-provided `last_seen_utc` watermark.
Previously, the watermark only detected local-clock rollback and could
silently accept older signed observations as current. Equal observation
timestamps remain valid. The existing disposable-db activation regression
now checks older observation rejection and equality acceptance.

Code: `5dd407b580a5a418d0fdba62b264f6da8f11fb78`.
Regression: `07f14bbba51dd49a999b4a9c7f5ee5637d8d1e1c`.
**Verification: not run locally; Windows exact-head CI remains unverified.**
This is NOT anti-replay protection against an attacker who can alter the
local watermark: it is caller-supplied and has no trusted storage, server
attestation or monotonic counter. `can_execute` remains False; Gate A/D
blocked. No V7 production service or financial posting path was touched.

**Next priority:** obtain push-triggered Windows CI evidence for exact head,
then add a trusted signed server sequence/watermark continuity contract and
adversarial tests, followed by transaction-scoped branch authorization.


## Signed activation monotonic sequence diagnostic — November 4, 2026

Added an explicitly signed, nonnegative 64-bit integer `sequence` claim to
`PreviewActivationStatusInspector`. Missing, boolean, negative, floating,
string or oversized sequence values fail closed with
`activation_signed_sequence_invalid`. When an optional previously accepted
sequence is supplied, an older signed observation is flagged as
`activation_signed_sequence_replay_suspected`. The parsed signed sequence is
reported for diagnostics. `PreviewCombinedAuthorization` now forwards the
optional watermark. Disposable-database regression fixtures and adversarial
sequence cases were updated.

Code commits: `5f59ef0304f6ab48478bb974027d55d6e9ddfd01`,
`8fbc10894ee529730518848a948ef8902a44e1d2`,
`84b22681cea6019c0e2470257858f444adfa98f2`,
`4d5a3a8221e2aeb1790b73e60a348415f628a2cb`.
**Verification: not run locally; exact-head Windows push CI not established.**
The available commit workflow lookup is PR-filtered and cannot prove a
push-triggered CI result. Never claim PASS without exact-head evidence.

**Important:** A caller-provided sequence watermark is not durable or trusted.
An attacker can reset it, and a compromised signing server can issue arbitrary
sequences. Server-issued per-license monotonic sequences, protected persistent
continuity, authenticated revocation, clock attestation and full commercial
service-bound authorization remain unimplemented. Preview `can_execute`
remains False; no V7 service or production database touched.

**Next priority:** verify exact-head Windows push CI via an Actions run listing
with push events; repair failures. Then design transaction-scoped branch
authorization and trusted persistent activation continuity, with adversarial
tests. Gates A/B/C/D/E remain blocked.


## Signed branch scope preview diagnostic — November 4, 2026

Added an optional `expected_branch_id` to the signed V8 entitlement
inspector and propagated it through combined authorization. When supplied,
only a canonical signed V8 `branch_id` matching that expected branch can
produce `entitled=True`; missing, malformed, legacy-version and cross-branch
claims fail closed. No caller-provided branch identity is itself trusted:
the current implementation does NOT resolve branch membership from a
persisted canonical branch registry or authenticate the requested branch.
It remains a read-only preview diagnostic; `can_execute=False` regardless
of branch match. No production transaction or V7 service changed.

Code commits: `2fbc1fb9dd50ada7a0613927e0e2873f2471ec6c`,
`1c73f4817750d8e3453cb761a85937d498407718`,
`2c0bf33ecb4c8278c3358cdedaca0bb956bf52c5`.
Regression: `3fbab8c033fe74e0b231ed363055c09e5c73c0cc`,
`tests/test_v8_phase2_branch_scope.py` with valid, mismatched, absent,
malformed, legacy and forged signed branch claims and no financial writes.

**Verification:** new tests not executed locally. Commit status lookup
returned no statuses; PR-filtered workflow lookup returned no runs.
Neither establishes push-triggered Windows CI status, so exact-head CI
is **UNVERIFIED**, not PASS. No verified new test count.

**Next:** obtain push-event GitHub Actions workflow listing for exact head
and fix failures. Add a transaction-scoped canonical branch registry and
persisted user/shift-to-branch binding (isolated preview only), with
cross-branch adversarial tests. Then trusted activation continuity and
commercial service-bound policy. Gates A/B/C/D/E remain blocked; never
enable financial posting before acceptance.


## Next-session checkpoint — canonical branch diagnostics (November 4, 2026)

**Base verification:** push-triggered Windows Actions run
[41794072185](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41794072185)
completed successfully for exact develop-v8 SHA
`414f365900ccd67f051d601f29d5bd73de2f2e7c`.
It covers the base commit, **not** the changes below.

**Work in review branch:** `feature/v8-preview-canonical-branch-check`.
Added `velopos_qt/branch_authorization.py` and an opt-in
`PreviewCombinedAuthorization.inspect_with_branch_registry()` that inspect
read-only persisted branch registry, active user membership and open
cashier shift-to-branch binding inside the canonical preview transaction.
The expected branch string is untrusted until checked against this registry;
signed entitlements are separately verified. Missing registry, inactive
branches, revoked memberships, mismatched shift, and invalid actor
all fail closed. A disposable-DB adversarial regression test was added at
`tests/test_v8_phase2_canonical_branch.py`.

**Scope:** isolated test DB only. Registry tables are deliberately
created by the test fixture, not by production database migrations.
No Qt checkout, production V7 service, real licensing key, live database
or financial posting path was changed. All decisions have
`can_execute=False`, including valid-branch diagnostics.

**Verification:** Windows PR Actions run
[41800587777](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41800587777)
completed successfully on code head
`3c50abfe15fb3370966bd7d239df3f605d107319`: **177 tests passed, 0 failed**.
That CI exercised the new branch/shift tests, not just the old base code.
The documentation-only commit after this milestone requires its own
exact-head PR check before merge.

**Next:** obtain exact-feature-head CI and repair failures; review branch
registry provenance and initialization lifecycle; design a trusted
persistent activation and service-bound branch policy. Gates A/B/C/D/E
remain blocked; never enable commercial checkout on preview.


## Canonical branch role/shift fail-closed correction — November 4, 2026

Reviewed roadmap, commercial gates, previous Windows Actions evidence and
canonical branch diagnostics on `develop-v8`. Found a correctness gap:
`PreviewBranchAuthorization.inspect()` could return `branch_verified=True`
for an active branch membership despite a persisted Cashier role being denied
the requested Admin-only action, or a missing/invalid cashier shift. The
service authorization reasons were discarded when computing the branch result.

The branch diagnostic now carries all non-permanent service denial reasons
into its branch reasons, while preserving the explicit preview/commercial
hard-deny independently. Regression tests in
`tests/test_v8_phase2_canonical_branch.py` cover a Cashier attempting
Admin-only purchasing with otherwise valid branch membership, and a member
attempting a sale without an assigned shift. No financial writes enabled.

Code: `212af3c7f960ff9f976483360b09955619fc9f95`.
Regression: `d9c2a403fed5dc684013e844348b386fbb6e0eb3`.
**Verification:** tests have NOT been executed in this run. PR-filtered
exact-head workflow lookup for regression SHA returned no runs; it cannot
establish push-triggered CI. The previous known Windows PR run
[41800587777](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41800587777)
reported 177 passing tests for the earlier `3c50abfe...` code head only.
Do not attribute that success to this patch.

**Next priority:** verify exact-head Windows push/PR Actions execution and
repair failures. Then audit persisted branch registry schema provenance,
revocation lifecycle and cross-branch authorization before any production
service integration. Gate A/B/C/D/E remain blocked; all preview financial
operations remain denied.


## Signed activation pair diagnostic — November 4, 2026

**Pull request:** #4 (`feature/v8-signed-activation-chain-preview`).
Added `velopos_qt/activation_chain.py` (read-only, isolated
`VeloPOS8PreviewData`) and adversarial tests at
`tests/test_v8_phase2_activation_chain.py`. Two independently
Ed25519-signed, versioned server observations are inspected for identical
signed machine/license/branch identities, active state, nondecreasing
observation UTC, increasing integer sequence, current signed expiry,
freshness and a SHA-256 digest of the previous signed payload.
The inspector always has `can_execute=False` and `require()` rejects.

**Critical limitation:** the checker cannot authenticate the caller clock,
prove persistent continuity or stop an attacker replaying an earlier valid
pair. It is NOT a durable anti-rollback mechanism, commercial activation
service, or reason to enable posting. Server-held monotonic per-license
state, revocation, trusted time, and a reviewed service-bound transaction
policy are still required. Gate A/B/C/D/E remain blocked.

**Independent repair:** the base develop-v8 SHA `7962e2a...` had 5
Windows CI failures from literal escaped newline characters in
`velopos_qt/branch_authorization.py` (IndentationError). The PR fixes the
syntax without weakening the intended persisted role/shift denials.

**Verified PR code milestone:** GitHub Windows Actions run
[41802314954](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41802314954)
PASS: **180 tests, 0 failures**, SHA
`2905b06c15dc5e6be372359a37ae4dbde4727f68`.
Because this checkpoint text is being committed after that code head,
the final documentation-inclusive SHA must receive its own exact-head
Actions result before PR merge.

**Next:** Verify final PR SHA and post-merge Windows CI; then design
authenticated server continuity/revocation, safe offline grace and the
service-bound commercial policy. No live checkout, production key,
customer data or stable `main` modifications were made.


## Preview combined activation-chain policy — November 4, 2026

Branch: `feature/v8-composed-activation-chain-policy`, PR #5.
Reviewing Issue #3 and the merged `a37d53d...` security checkpoint,
the signed activation *pair* had no composed diagnostic alongside the
transaction-scoped persisted cashier/shift, canonical branch membership
and V8 signed machine/action/license/branch scope.

New `PreviewCombinedAuthorization.inspect_with_activation_chain()`
composes those independent checks while the caller owns a transaction
on disposable `VeloPOS8PreviewData`, returning explicit signed-license-ID
binding and a `policy_consistent` *diagnostic*, not permission.
Even when every check is healthy, `can_execute=False` and
`require_with_activation_chain()` always raises PermissionError.

Adversarial tests in `tests/test_v8_phase2_composed_activation_chain.py`
cover valid but denied credentials, substituted signed license identity,
mismatched branch, forged login, missing shift, wrong cashier role,
revoked branch membership, revoked/stale/forged activation envelopes,
production path denial, and no financial table mutations.

**Security limits:** This integration still trusts no local clock or
client-storage watermark for real offline activation, and cannot detect
rollback of both valid signed server receipts. No server-hosted anchor,
renewal/revocation endpoint, actual license installation, trusted clock
or commercial transaction service is implemented. Gates A/B/C/D/E blocked.

**Verification:** New changes have not yet passed Windows CI at the time
of this checkpoint; run `python run_v8_checks.py` on the exact PR SHA
and record GitHub Actions evidence before considering merge.

**Next:** Review and test this composition, then design the future
server-maintained per-license monotonic activation anchor and
service-bound transaction enforcement. `main` and paid V7 data untouched.
