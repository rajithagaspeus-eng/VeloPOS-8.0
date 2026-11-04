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


## Reference server-owned activation ledger (November 4, 2026)

**Branch:** `feature/v8-preview-server-activation-ledger` from exact
`develop-v8` SHA `c16b5fb723f597aa76fbb4e0869ceeef53b6d539`.
The previous base Windows CI passed **182 tests** at this SHA
(run 41804733823). The base CI does not verify this new batch.

New `velopos_qt/server_activation_reference.py` is an *isolated*
backend reference (not a deployed service): the server's latest signed
activation sequence/payload digest and active/revoked license state are
kept inside a disposable SQLite database. Duplicate registration is
rejected; a successful issue atomically increments signed sequence and
links the prior signed payload. A reference server-side inspection detects
old signed receipt replay when its independently held state is intact.

Added `tests/test_v8_phase2_server_activation_reference.py` with
ephemeral Ed25519 keys and tests for stale/replayed receipts, forged
signatures, revoked/expired credentials, duplicate registrations,
wrong branch/machine, clock rollback, transaction rollback, preview-only
storage enforcement, and no financial writes.
Read `docs/V8_SERVER_ACTIVATION_REFERENCE.md` for the threat model.

**Unimplemented/blocked:** no hosted/authenticated activation API,
server-held production database, trusted server clock/key storage,
revocation delivery, secure offline grace, client hardware binding,
real V8 license installation or commercial checkout integration.
Local preview storage is *not* trusted anti-rollback; entirely offline
licensing on a customer-controlled PC can be reset/bypassed.
All commercial Gates A/B/C/D/E remain blocked.

**Verification:** GitHub Windows PR Actions
[41806537819](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41806537819)
completed SUCCESS for exact code SHA
`28e0af49891c2a9734ac54162037ca65ff25404b`:
**185 tests passed, 0 failures** (`python run_v8_checks.py`).
This documentation-only checkpoint commit still needs its own exact-head
Windows PR run. After merge, independently verify the merged SHA push CI.
Never extrapolate an earlier PASS to an unverified commit.

**Next:** verify and repair CI, then design authenticated server
activation API and bounded/offline grace with careful key custody;
do not enable real sales until every service-bound acceptance gate passes.


## Server continuity clock rollback inspection — November 4, 2026

Reviewed roadmap, release gates, previous activation reference and Windows push CI.
Exact base SHA `51aad6e0be72130417d59dd91f06fc011ed02dc9` has successful
Windows push Actions run [41807248172](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41807248172).
That success does **not** verify the subsequent commits.

Found a reference server-continuity diagnostic gap: `inspect_current()`
accepted a valid current signed receipt when its supplied server observation
clock preceded the latest server-held observation. It now reports
`server_observation_clock_rollback` and fails the diagnostic closed. Added
an adversarial regression asserting rejection of a valid receipt inspected
with a regressed clock. Code commit `92e3375072c0a02a74c93a4b10a018bac3a48709`;
test commit `91ce89e73290a9b2bfc810aa89a8e0b352f81cde`.

**Scope:** preview-only reference; no commercial activation, payment, stock,
production data or main branch modification. This check depends on a trusted
server clock and durable server database; client-controlled time or storage
cannot establish commercial trust. Gates A/B/C/D/E remain blocked.

**Verification:** new regression is committed but not yet proven PASS on its
exact head; inspect Windows push Actions for the documentation-inclusive SHA.
**Next:** verify exact-head CI, repair failures, then design authenticated
server API, durable activation custody and trusted service-bound transaction
authorization with crash-safe idempotency. Never enable real checkout early.


## Signed operator activation command gateway (November 4, 2026)

**Base checkpoint:** `develop-v8` SHA
`51aad6e0be72130417d59dd91f06fc011ed02dc9`, verified by Windows
push Actions 41807248172: 185/185 V8 preview tests passed.

New feature branch: `feature/v8-signed-activation-admin-gateway`.
`velopos_qt/activation_admin_gateway.py` is a preview-only signed-command
contract, layered over the isolated server activation authority reference.
The server roster stores Ed25519 operator public keys and active Admin /
Issuer roles. Signed version-8 commands have bounded UTC freshness,
strict schemas and canonical immutable request IDs. Admins can register/
revoke/issue; Issuers can issue only. Idempotent signed retries retain
the original response/sequence and reject conflicting reused request IDs.
Issue retries after revocation/expiration/supersession do not re-deliver
obsolete signed activation receipts.

New tests: `tests/test_v8_phase2_activation_admin_gateway.py`,
with ephemeral Ed25519 keys and disposable DB; no real financial writes.
The Windows PR workflow now checks `python -m compileall -q velopos_qt tests`
before the full V8 test suite to catch syntax defects in unimported modules.

**Security / commercial limitations:** NOT a deployed API, authenticated
operator bootstrap, trusted backend clock, production key custody,
hosted anti-rollback database, offline grace service or POS financial gateway.
Operator provisioning/disable methods are test fixtures with NO
production authentication, and must NEVER be exported to shop clients.
All V8 commercial transaction decisions remain `can_execute=False`.
V7 services, `main`, existing customer data and production signing keys
are untouched. Gates A/B/C/D/E remain blocked.

**Verification:** original feature SHA
`605e1277479e72450375415c0ac5d2223167578f` passed Windows
[PR CI 41809490960](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41809490960):
**187/187 tests PASS** and Python compileall PASS. The new integration
merge commit with concurrent server-clock fixes must independently pass CI,
and post-merge `develop-v8` SHA requires its own push CI.

**Next:** review this authenticated-command model and replay/expiry
semantics; design a real authenticated activation service, server-owned
key storage, operator onboarding, and offline grace/recovery separately.
See `docs/V8_ACTIVATION_ADMIN_COMMAND_CONTRACT.md`.


## Integrated concurrent server clock rollback hardening — November 4, 2026

During PR #7 review `develop-v8` advanced to SHA
`c50fcfb22bfc586205522d58c2a3fd97c7eeeded` with extra reference
server clock rollback enforcement and its regression. The feature PR
became temporarily unmergeable. Resolved by a two-parent integration
commit `2c7b0a50a6d8f766ca099e2d3ec1fc3d2b787721` that preserved
*both* branch histories and kept the concurrent base implementation,
new signed-command gateway, compileall CI and both progress sections.

Base SHA `c50fcfb...` has successful Windows push Actions run
[41809697777](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41809697777).
The earlier feature SHA `605e127...` passed 187/187 tests in
[PR CI 41809490960](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41809490960).
Neither result establishes the combined merge commit's success.

**Verification:** CI for the new integration-plus-checkpoint head is
UNVERIFIED at this moment. Run the Windows preview suite on the exact
new PR SHA and check mergeability before merging. Post-merge
`develop-v8` push CI must also pass. Commercial checkout remains
permanently disabled in this preview code.


## Bounded signed offline grace preview — November 4, 2026

**Baseline:** `develop-v8` SHA
`e33226abbc42c4a445abdc781eaeaeb68a0ddb26`, whose exact-head
Windows push Actions [41810352575](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41810352575)
passed **187/187** tests and module compileall checks.

New feature branch: `feature/v8-offline-grace-signed-grants`.
Added `velopos_qt/offline_grace_reference.py`, an isolated test-only
server-signed bounded offline grant for the latest committed active
activation receipt. Grant binds license, machine, branch, receipt digest
and sequence, is capped at 24 hours and never exceeds license expiry.
An offline read-only inspector rejects forged or mismatched signatures,
expired or oversized grants, invalid chronology and observed clock rollback.
Test-only issuer checks server revocation and superseded receipts.

New adversarial tests:
`tests/test_v8_phase2_offline_grace.py` with ephemeral signing keys
and disposable VeloPOS8PreviewData. Documentation:
`docs/V8_OFFLINE_GRACE_RECOVERY_CONTRACT.md`.

**Critical security limit:** customer-controlled local time and stored
receipts cannot be a trusted anti-rollback clock or watermark; an
old legitimate pair can look mathematically valid after server revocation.
`window_consistent=True` does **not** mean permission to charge,
and all preview decisions have `can_execute=False`; both require_checkout
methods always raise. No offline POS sales, commercial renewal/trial,
real hosted server, device attestation or network API was enabled.
All commercial gates A/B/C/D/E remain blocked.

**Verification:** this new feature head has NOT YET been verified
by Windows CI at the moment of writing. Run the full no-skips
`python run_v8_checks.py` suite and Python compileall on the exact
PR head; fix any failures. Then separately verify exact post-merge
`develop-v8` Windows push CI.

**Next:** implement a separate authenticated reconnect-and-renewal
backend contract with tenant-aware key custody, server-side revocation,
device transfer recovery and commercial service-bound authorization.
Keep zero mandatory paid costs for offline POS and preserve main/V7.


## License renewal and device recovery reference (November 4, 2026)

**Base verified:** `develop-v8` SHA
`9b479de684a8b77d8ca107e16b53dcfb264930f6`, exact push Actions
[41811611347](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41811611347):
190/190 Windows tests PASS and Python compileall PASS.

**Feature branch:** `feature/v8-license-renewal-device-recovery`.
Added `velopos_qt/license_recovery_reference.py` with fail-closed
admin-only renewal and device/branch-transfer reference methods.
Signed gateway now accepts strict `renew` and `transfer` payloads
only for active authenticated Admin operators. All operations
require expected current server sequence and are journaled with
immutable request IDs, and only re-deliver retries while current
server state still matches the recorded transition.

Renewal can only strictly extend expiry at most 366 days forward;
device transfer requires exact previous device+branch binding.
Both preserve the original license ID, activation sequence and
prior payload SHA-256 digest and never un-revoke a revoked license.
The prior signed activation receipt stops matching online server
state until a new receipt is issued. Offline old grants may remain
locally inspectable and NEVER authorize financial posting.

Added `tests/test_v8_phase2_license_recovery.py` with three
disposable-DB regression tests and full threat model at
`docs/V8_LICENSE_RECOVERY_REFERENCE.md`.

**Verification:** initial Windows PR CI 41813009958 found a
regression fixture assumption about rolled-back SQLite DDL (not a
production logic failure). Fixed test and exact-code-head Windows
[Actions 41813302325](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41813302325)
PASS **193/193 tests, 0 failures + Python compileall**, at SHA
`83cbb3514cc18fa3f857e31cb0315707b0a83483`.
This documentation-only checkpoint commit still needs its own CI
verification before PR merge; after merge confirm exact-head push CI.

**NOT production:** no actual hosted service, real tenant/account
recovery, proof-of-ownership/attestation, encrypted key custody,
offline rollback protection or commercial transaction permission.
No V7 money/stock, customer data or stable main branch touched.
All commercial gates A/B/C/D/E remain blocked. Next: secure
customer-owner approval/renewal and service-bound financial security.

**Commercial note:** updating the server reference expiry does not
reissue or extend a separately signed V8 entitlement/license file;
real license renewal payment/identity verification and new signed
entitlement distribution are still unimplemented.


## Recovery boundary adversarial regression — November 4, 2026

Reviewed the master roadmap, commercial release gates, prior checkpoint,
recent branch history, and Windows push CI. Baseline develop-v8 SHA
`ce0f265ae3b26c9d2b9062bbc7860e6bc0a1648f` completed Windows
push Actions [41813917120](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41813917120)
SUCCESS (compileall and combined test steps). This is baseline evidence,
not verification of the new test.

Added `tests/test_v8_phase2_recovery_boundary.py` at code commit
`6aba3568b7059c882fac2ee015811d8d0dad4ea3`. It uses disposable
preview data and ephemeral Ed25519 signing keys to assert that server
clock rollback and an expired license cannot transfer machine/branch
binding, and that failed recovery preserves persisted binding, expiry,
sequence and receipt digest. It also asserts recovery cannot authorize
checkout. No real license, customer record or money/stock path touched.

**Verification:** new test and this checkpoint require exact-head Windows
push CI. Do not claim new tests passed until the run completes. Commercial
Gates A/B/C/D/E remain blocked; the reference service is not deployed.

**Next priority:** inspect and repair exact-head CI, then implement
trusted service-bound session/branch/shift authorization and persistent
idempotency on a disposable transaction schema before any financial writes.


## Premium UI — localized quick navigation (November 4, 2026)

**Starting point:** Latest verified `develop-v8`
`e57a8b17e6beae88fdf4cca84d6465dffd119fba` with Windows
Actions [41815417759](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41815417759)
success. Stable `main` and V7 production data are untouched.

**Feature branch:** `feature/v8-premium-quick-navigation`.
Added `velopos_qt/quick_navigation.py` as a localized,
keyboard-accessible 14-page command palette. The header button
and Ctrl+K both open the palette; English/current-locale matching,
live results, Down/Up/Enter/Escape, no-match disabled action,
dark/light visuals and bilingual discovery tooltips are included.
Canonical page selection goes through `SettingsPreview.nav` and
`open_page()`; no new route bypasses authorization, page refresh,
session cleanup or hard-denied commercial checkout.

Added six Qt offscreen regressions in
`tests/test_v8_quick_navigation.py`, with empty/unauthorized
checks and no production database. Added manual acceptance
steps at `docs/V8_QUICK_NAVIGATION_ACCEPTANCE.md`.

**CI verification pending:** run Python compileall and all
`python run_v8_checks.py` Windows tests on exact PR SHA,
fix any failures and confirm independent post-merge push CI.
No real POS sales/stock/printing, licensing or payment code changed.
All commercial release gates A/B/C/D/E remain blocked.

**Next:** use owner screenshots to validate clipped labels,
focus, 100%/125%/150% scaling and premium visual polish.
Continue service-side financial safety and commercial release
gates only in separately tested future batches.


## Premium V8 compact shell / keyboard sidebar (November 4, 2026)

**Base:** Verified merged `develop-v8` SHA
`f3e98da8f1887ec5cd0eec682e25ce4ab5f2d567`;
Windows Actions [41819057960](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41819057960)
**200/200 PASS, 0 failures + compileall PASS**. Stable `main`
and existing V7 live transactions/customer data untouched.

**Feature branch:** `feature/v8-responsive-preview-shell`.
`velopos_qt/app.py` adds a responsive 1040px width breakpoint:
on compact windows the 244px sidebar initially collapses,
the workspace/outer margins contract, and a permanent menu button
plus Ctrl+B keyboard shortcut can reveal the 216px sidebar.
Choosing a page from the compact sidebar hides it again.
Desktop starts with the full sidebar; manual toggle within a
width range is retained. The small header shows shorter
`VeloPOS 8` / `Ctrl+K` labels while preserving full accessible
descriptions and controls in all three languages.

`velopos_qt/i18n.py` adds menu accessibility text in English,
Sinhala and Tamil. Six new Qt offscreen tests cover compact,
desktop, keyboard toggle, nontransactional Billing, language,
theme and continued Ctrl+K page selection.
`docs/V8_RESPONSIVE_SHELL_ACCEPTANCE.md` provides owner manual
Windows QA for 760px/820px, threshold edges and scaling.

**Verification pending**: exact SHA Windows compileall and combined
`python run_v8_checks.py` must pass with zero skips/failures;
after PR merge verify exact SHA `develop-v8` push Actions.
No commercial checkout/stock/payment action is enabled;
security and commercial Gates A/B/C/D/E remain BLOCKED.


## V8 Billing draft keyboard search and stale result hardening (November 4, 2026)

**Base:** `develop-v8` exact SHA
`f6faf800b69f538b9d25d2045ce29e7bdbf7e0a5`,
merged Windows Actions [41821125162](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41821125162)
**206/206 PASS, 0 failures + compileall PASS**.

**Feature branch:** `feature/v8-billing-search-keyboard-safety`.
In `velopos_qt/billing_page.py` keyboard Up/Down in the barcode
field now navigates product result rows. On Enter, an exact
matching barcode wins, a unique name result can be selected,
and ambiguous results require an explicit current-query arrow
or mouse selection. A changed query clears all previous row
selection intent before new results are populated, preventing
accidental additions due to stale table row indices.

Added a localized help/status message below the search table,
screen-reader labels and dark/light styling in
`velopos_qt/i18n.py` and `velopos_qt/app.py`.
Six disposable, offscreen, no-DB regressions in
`tests/test_v8_billing_keyboard_search.py` validate keyboard
movement, conflicting matches, stale selections, scan priority,
localized guidance and zero financial/stock operations.
See `docs/V8_BILLING_KEYBOARD_ACCEPTANCE.md` for owner
physical Windows, DPI and three-language manual testing.

**Windows CI still pending at this checkpoint:** require exact
feature HEAD run of compileall plus all `python run_v8_checks.py`
without skips/failures, then exact merged-head post-merge CI.
Stable `main` and V7 real data remain untouched.
Commercial checkout continues hard disabled and Gates A/B/C/D/E
remain blocked.


## Recovery stale-binding regression checkpoint — November 4, 2026

Reviewed master roadmap, commercial release gates, current progress and the
existing disposable-data recovery boundary. Base develop-v8 head was
`f6faf800b69f538b9d25d2045ce29e7bdbf7e0a5`.

Added adversarial recovery assertions to
`tests/test_v8_phase2_recovery_boundary.py`: stale expected sequence,
wrong previous machine and wrong previous branch must all raise
`PermissionError` and preserve machine, branch, expiry, sequence and
signed-receipt digest. Code commit:
`d71c3b1cac9c5d8ac77cc3f08b554ab6c325b921`.
This is test-only and uses disposable preview data and ephemeral keys.

**Verification:** no test runner executed in this environment; verified
new test count = 0. The GitHub PR-only workflow lookup and combined commit
status returned no results for the previous head; these do NOT verify
push-triggered Windows CI. Exact-head CI for the new test commit and this
checkpoint remains UNVERIFIED. Do not claim passing tests or release readiness.

**Release blockers:** Gate A service-bound identity, signed commercial
entitlements, shift/branch enforcement, idempotency, atomic stock/accounting
and recovery remain blocked; Gate B reconciliation, Gate C cloud SKU,
Gate D deployment/recovery and Gate E final Windows/hardware QA outstanding.
Real financial posting stays disabled. No main, V7 production data or
private signing keys modified.

**Exact next priority:** verify Windows push Actions for this checkpoint
head with an all-event Actions listing (PR-filtered lookup is insufficient),
run full no-skip `python run_v8_checks.py`, repair failures, then implement
trusted service-bound session/branch/shift and persistent idempotency on
isolated disposable schema before enabling any money/stock writes.


## Fast Development Mode: integrated atomic sale boundary (November 4, 2026)

**Start:** `develop-v8` SHA
`a76e2304dd076d380d753746a3d2828a9fbbae4f`, Windows
Actions [41823957374](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41823957374)
**212/212 PASS + compileall PASS**.

**Feature branch:** `feature/v8-integrated-atomic-sale-boundary`.
Instead of more isolated UI polish, this integrated core batch
adds `velopos_qt/atomic_sale_boundary.py` to combine current
persisted session, open shift, canonical branch, signed license,
signed activation chain, and line/price/stock/expiry checks
inside one `BEGIN IMMEDIATE` SQLite snapshot on isolated test data.
All diagnostics are immutable; `can_checkout` and `can_execute`
always False, and `require` always denies. The inspecting wrapper
ALWAYS rolls back, even when local checks appear healthy.

`PreviewCheckoutPreflight.inspect` now optionally accepts a
canonical already-open transaction without committing/rolling
back caller work; existing own-lock public behavior is retained.
`RollbackOnlySaleRehearsal` now invokes the shared preflight
inside its existing transaction to guard current price,
aggregated stock, product expiry and expired active batches.

`tests/test_v8_phase2_atomic_sale_boundary.py` adds seven
disposable-database cases for valid-but-denied chained
authorization, denial and expiry, forged sessions, contract
boundary enforcement, immutable results, injected failure
rollback and rehearsal safety. See
`docs/V8_INTEGRATED_ATOMIC_SALE_BOUNDARY.md`.

**Verification status: PENDING** Windows exact PR-head full
`run_v8_checks.py` and compileall (zero skips/failures), then
independent exact merged-head push CI. All commercial Gates
A/B/C/D/E stay blocked. No V7 checkout, production data,
`main`, signing keys or hosted services were modified.


## Fast core batch: deterministic sale arithmetic and synthetic stock ledger (2026-11-04)

**Base:** exact `develop-v8` SHA
`268d72ea0f27e85c6fc572112ed8cd3512d70c52`; Windows Actions
[41826561205](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41826561205)
**219/219 PASS + compileall PASS**.

**Feature branch:** `feature/v8-sale-plan-ledger-idempotency`.
Added immutable, pure, Decimal-based `PreviewSalePlan`: deterministic
HALF_UP cent rounding per line (then sum), bounded repeated-barcode
quantities and canonical payload values for test-only idempotency.
Refactored `PreviewCheckoutPreflight` and rollback-only
`RollbackOnlySaleRehearsal` to share plan calculations. Rehearsal
now stages matching `stock_moves` for each stock reduction under
the original BEGIN IMMEDIATE lock, and verifies replay of the
completed request claim within that same doomed transaction.
New synthetic failpoints after ledger changes and after journal
completion exercise unconditional rollback, including on success.

Seven new methods in `tests/test_v8_phase2_sale_plan_ledger.py`
cover decimal receipt reconciliation, canonical request signatures,
malformed value denial, staged movement/line counts, replay,
failpoints, expired batch and no persistent sale/stock/journal.
Acceptance and explicit commercial limits:
`docs/V8_SALE_PLAN_LEDGER_ACCEPTANCE.md`.

**Verification PENDING:** exact feature-head Windows compileall +
`python run_v8_checks.py` (no failures/skips), then exact merged-head
push CI. No commercial service, tax, payment, license, cloud,
`main` or production V7 data modified. Gates A/B/C/D/E remain blocked.


## Core input hardening — 2026-11-04

**Branch:** `develop-v8` only. Starting HEAD `95dfb4863832b66695c1c1f6aebd7b50567c5b4a`, prior push Windows Actions [41828717755](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41828717755) SUCCESS for that previous SHA, not this batch.

**Code** `2234f8ff9c15219d74f4d745a015fff6cf5fd6f3`: fail closed on nonprintable barcode identifiers in deterministic, rollback-only sale planning. This blocks embedded newline, tab, NUL and terminal escape characters from being accepted as transaction identity, preventing ambiguous printed/audited item identifiers. Existing normal printable barcodes remain valid.

**Tests** `43f1e39eb6c4e955343a06f15b514da9b8df9e15`: four new adversarial inputs added to existing invalid-line regression; all still test-only. No real checkout or posting enabled.

**Verification:** exact-head Windows push Actions and test count for this checkpoint still need inspection; do not inherit the preceding 226-test PASS result. Gate A/B/C/D/E remain blocked. No production DB, private signing keys, V7 services or main touched.

**Next priority:** verify this checkpoint exact-head Windows CI and `run_v8_checks.py` no-skip result; then service-bound identity/shift/branch authorization, persistent idempotency and atomic transaction recovery in disposable schema before any financial writes.


## Fast Commercial Core Batch #16 — tender declaration + return stock-ledger rehearsal (2026-11-04)

**Base:** `develop-v8` exact SHA
`95dfb4863832b66695c1c1f6aebd7b50567c5b4a`, verified Windows
[41828717755](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41828717755)
**226/226 PASS, 0 skips/failures + compileall PASS**.

**Branch:** `feature/v8-integrated-tenders-and-return-ledger`.
The pure immutable `PreviewTenderPlan` validates split Cash, Card, QR
and Credit declarations with exact-cent amounts, cash-only change,
underpayment and excess-noncash denial. Card/QR references and credit
customer IDs are explicitly UNVERIFIED, and `can_settle=False` always.
The rollback-only sale simulation can bind those declarations into
its idempotency fingerprint without collecting or persisting funds.

`RollbackOnlyReturnRehearsal` now stages matching, positive synthetic
stock movements for each restored barcode under the same BEGIN IMMEDIATE
as return lines and journal. Return line rounding uses HALF_UP and
duplicate sale-item quantities are bounded. Same-claim replay and
new failure injections after ledger and journal completion are checked
before unconditional rollback even on apparent success.

Six model tests + five isolated integration tests added:
`tests/test_v8_tender_plan.py` and
`tests/test_v8_integrated_tender_return.py`.
Contract and explicit commercial blockers:
`docs/V8_INTEGRATED_TENDER_RETURN_ACCEPTANCE.md`.

**Verification pending:** exact PR-head Windows compileall + all
`python run_v8_checks.py` with no skipped or failed tests;
post-merge CI on exact merged head before acceptance.
Stable `main`, real V7 customer data and payment provider are untouched.
All commercial Gates A/B/C/D/E remain BLOCKED/INCOMPLETE.


**Concurrent branch repair:** the existing `develop-v8` barcode hardening at `fc59ad3` contained an accidental literal `\n` in Python source that broke Windows compileall. On this successor feature branch it is repaired to an actual line break, and four barcode test inputs now contain real escaped control-character literals rather than double-backslash printable text. The original barcode safety check is preserved. This checkpoint needs exact feature-head Windows CI and post-merge verification.


## Exact-head Windows CI reconciliation — 2026-11-04

Read master roadmap, commercial release gates, durable progress and GitHub push Actions. Current develop-v8 head at inspection: `06a936dc4eb9a6f0f4a512a01cbcec3d2ea9bb8e` (integrated tender declaration / rollback-only return stock-ledger rehearsal plus barcode syntax repair).

**Verified exact-head CI:** Windows push Actions [41834115875](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41834115875), completed **SUCCESS**. The job reports successful compileall and combined no-skip test-suite steps. Commit message reports 237/237 tests for an earlier head; do **not** attribute that count to this exact-head run without inspecting the run log. Exact-head pass/fail status is verified; exact-head numerical count is not independently verified here. Earlier barcode checkpoint `fc59ad3` had FAILED CI [41831836646](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41831836646); the later repair passed at `06a936d`.

**This checkpoint batch:** CI evidence and next-task documentation only; no code or regression tests executed locally and no claim of new tests. All real transaction actions remain disabled; Gate A/B/C/D/E are still not commercially accepted.

**Next highest-priority substantive batch:** inspect canonical session, branch, shift and license checks in `velopos_qt/atomic_sale_boundary.py` and original `velopos.services` entry points. Implement service-bound authorization and persistent transaction idempotency with disposable SQLite tests, including cross-branch, demotion, crash and retry cases; keep all production checkout/payment/stock mutations disabled. Require exact-head Windows CI after each code batch. Do not change main or V7 production data.


## Integrated atomic return readiness diagnostic — November 4, 2026

Merged PR #18 to `develop-v8`: `PreviewAtomicReturnBoundary` inspects persisted session/role, cashier shift, canonical branch membership, signed return entitlement, activation chain, original invoice eligibility and cumulative returnable quantities under one caller-owned SQLite transaction. It reports a rounded return amount as diagnostic evidence only. No refund, payment, stock, idempotency, or legacy service writes are made; owned transactions always roll back and `require()` always denies.

Disposable Windows regressions cover partial returns, duplicate return quantities, invalid and void invoices, forged session and activation status, revoked branch membership, closed shifts, malformed input, caller-owned transaction safety, and production-like path refusal. The first exact-head run failed only because the production-path test reused a fixture initialized in preview mode. The test setup was separated and rerun.

Exact PR head `efe4b3f511f9cb42e8cbd95c5d20928202b72afc`: Windows CI run [41844487031](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41844487031) **SUCCESS**, **242 tests PASS**, compileall PASS. Merged as `6ff51bf74c39b76386f89a0cae07c61732561b56`; post-merge Windows push CI run [41845037558](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41845037558) also **SUCCESS**, **242 tests PASS**, compileall PASS.

No financial return or checkout was enabled. Commercial Gates A/B/C/D/E remain unapproved; the diagnostic is not a production service. Stable `main`, V7 data, and signing keys remain untouched. Next substantive priority: service-bound authorization/idempotency architecture for a separately reviewed commercial engine; keep legacy direct services unchanged until compatibility and transaction ownership can be safely refactored.


## V8 preview transaction coverage and legacy-service isolation — November 4, 2026

Merged PR #19 as `e19232a5098fdf5fc19b236f2d29dfc8746f59e1`. The preview deny gate and persisted-session policy now include 17 actions: sale, return, purchase, sale/purchase void, supplier/credit payment, points redemption, shift open/close, receipt print, cash movement, expense add/delete, stock adjustment, stock-take finalization, and batch receipt. Every gateway method routes through the mandatory deny gate.

Added `tests/test_v8_legacy_service_boundary.py`, which checks policy/gateway action parity and scans V8 Qt modules for imports/calls to legacy financial mutation methods. The current source scan found no direct V8 Qt call to those legacy transaction methods. This is an architecture regression guard; it does not secure the legacy V7 service functions themselves.

Exact PR head `236d312c8671df5d768805b0a3a7125bf0cc6b59`: Windows Actions [41847315485](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41847315485) **SUCCESS**, **245 tests PASS**, compileall PASS. Post-merge head `e19232a5098fdf5fc19b236f2d29dfc8746f59e1`: Windows push Actions [41847710848](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41847710848) **SUCCESS**, **245 tests PASS**, compileall PASS.

All transaction writes remain hard-denied in the V8 preview. Gate A remains blocked until a reviewed commercial service owns and revalidates the same database transaction, and committed idempotency is integrated with that path. V7 behavior and customer data were not changed.


## Idempotency fingerprint JSON key collision hardening — 2026-11-04

Read master roadmap, release gates, progress history and exact develop-v8 head. Previous exact merged code head `e19232a5098fdf5fc19b236f2d29dfc8746f59e1` had Windows push CI [41847710848](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41847710848) SUCCESS (245 tests and compileall), as recorded above. Current documentation head before this batch: `6db3ffae75d50982b02975acc7360435db00f5a4`; the connector's PR-filtered workflow lookup returned no runs for it, which does not establish push CI.

**Code:** `9db977176cce9447461c678a5240dd2a8abfabe6` changes only isolated V8 preview `idempotency_ledger.request_fingerprint`. JSON encoding silently coerces non-string object keys, allowing distinct request payloads such as `{1: "sale"}` and `{"1": "sale"}` to hash identically. The function now rejects non-string dictionary keys recursively, including keys inside list/tuple containers, before hashing. Canonical string-key payloads remain unchanged.

**Regression:** `50c4d07d0cd47db9db256d07c6736bffeed20f89` adds `tests/test_v8_idempotency_key_canonicalization.py` covering integer/string collision, nested numeric/null/boolean keys, nested canonical key ordering, and non-object top-level payload. **Verification pending:** no tests were executed in this connector session; exact-head Windows push CI and no-skip test count must be checked. Do not inherit 245 PASS from the earlier SHA.

**Commercial scope:** only a preview journal fingerprint primitive changed. No real service transaction path is authorized, no financial writes enabled, and Gate A/B/C/D/E remain blocked. V7, production data, signing keys and `main` were not modified.

**Next highest priority:** inspect exact-head Windows push Actions run (the available workflow lookup only sees PR events), repair any regression, then implement durable transaction idempotency and crash recovery in a separately reviewed, service-owned isolated SQLite contract with verified session, branch, shift and license checks. Do not connect it to production V7 services or checkout until Gate A/B evidence is complete.


## Idempotency hostile-container hardening — 2026-11-04

Read roadmap, release gates, prior checkpoint and isolated idempotency source.
Code commit `669c2ee48471dff4077dffe28fb2ab6d98da4d48` rejects cyclic
list/dict/tuple request payloads and container nesting deeper than 64 before
canonical JSON serialization, instead of allowing uncontrolled recursion.
Shared but acyclic nested objects remain valid. Regression commit
`a7b239a57be441fc684a31cfb484daf949f043a6` adds three tests for
cycles, excessive nesting, and shared acyclic references.

**Verification:** No local test runner executed in this connector session;
the PR-filtered workflow lookup cannot prove push-triggered Windows CI.
Exact-head Windows compileall and no-skip combined suite are still pending.
No new verified test count is claimed. No live transaction/stock/financial
posting is enabled. Gate A/B/C/D/E remain blocked.

**Next priority:** verify exact-head push Windows CI, then implement and test
service-owned persistent transaction journal recovery and branch/session/shift
authorization on disposable V8 storage, preserving V7 production isolation.
