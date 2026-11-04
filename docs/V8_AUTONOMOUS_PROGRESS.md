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


## Durable journal crash-recovery triage — 2026-11-04

Branch: `develop-v8`. Reviewed roadmap, commercial gates, progress, journal
and rollback-only sale/return callers. Baseline Windows push CI run
[41847710848](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41847710848)
was successful for **older** SHA `e19232a5098fdf5fc19b236f2d29dfc8746f59e1`
(245 tests previously reported), **not** this batch.

**Code:** `f3c16db61961f0c44dc8c749a073256efd56b482` adds read-only
`PreviewIdempotencyLedger.inspect_request` to distinguish not-recorded,
persisted PENDING needing manual reconciliation, COMPLETED journal-only
unverified results and malformed legacy records. It checks immutable
payload conflicts. `claim` rejects corrupt completed refs; `complete`
requires printable nonpadded refs; newly created preview journal table
enforces pending/null and completed/nonempty constraints. Existing tables
remain compatible and are validated on replay. This does not validate any
real business invoice or authorize transactions, and deliberately never
auto-deletes/retries a stranded claim.

**Regression:** `4bed24ca854dbce8c73443491e4959c178bf8e54` and control-character
literal fix `b94819270b58b5579248dad1251821eab6f97a98` add six disposable
SQLite subprocess test methods covering durable replay, payload/branch
conflict, committed orphan PENDING, rollback, invalid refs, corrupt
legacy completion and new schema constraints. Five isolated local SQLite
schema smoke cases gave expected results; this is not a run of repo tests.

**CI:** Latest test SHA `b94819270b58b5579248dad1251821eab6f97a98`
returned no combined status entries or PR-triggered runs via the
available connector. Push-triggered Actions are not covered by the PR
lookup. Exact-head Windows `compileall` and no-skip `run_v8_checks.py`
remain **UNVERIFIED**; verified new regression count is zero.
Gates A/B BLOCKED; C/D/E outstanding. Production V7, real payments/stock,
license keys and `main` untouched.

**NEXT:** verify current checkpoint SHA against Windows push CI and fix
failures, then build service-owned persistent transaction authorization
(session, shift, canonical branch and signed license) with crash/retry
and concurrency evidence in disposable V8 storage. No live checkout.


## Bounded journal requests + crash/concurrency regressions — 2026-11-04

**Branch:** `develop-v8` only. At run start reread
`docs/V8_MASTER_ROADMAP.md`, `docs/V8_COMMERCIAL_RELEASE_GATES.md`,
this checkpoint, `velopos_qt/idempotency_ledger.py`,
`velopos_qt/service_authorization.py`, and journal regression tests.
Last confirmed historical Windows push CI job
[41847710848](https://github.com/rajithagaspeus-eng/VeloPOS-8.0/actions/runs/41847710848)
was SUCCESS at prior SHA `e19232a5098fdf5fc19b236f2d29dfc8746f59e1`,
NOT the current head. Exact-head status entries and PR-filtered workflow
runs for this batch returned empty; the available lookup does not cover
all push-triggered CI, so it cannot confirm pass/fail.

**Corrections & code:**
- `e7eedfe4240555350449cf34e77ec590f2a4e9c5` fixes escaping in
  `tests/test_v8_idempotency_recovery_triage.py`: the outer Python
  triple-quoted subprocess script now passes literal escapes for newline
  and NUL into the child interpreter. The previous single-backslash
  literals could expand to a syntactically malformed child script or NUL
  in subprocess arguments.
- `9c960c68a0840aa5472d326175d94750d6b418ab` caps canonical
  idempotency fingerprint serialization to 256 KiB and traversed
  request nodes to 10,000, avoiding excessively large attacker-supplied
  request payloads. Invalid Unicode surrogate encodings become a
  fail-closed ValueError rather than an uncaught UnicodeEncodeError.
  Existing canonical well-sized payload hashes are unchanged.
- `e8cf87018868dea009c089c87d6c2de7aea4c87b` adds three
  regression methods for payload size/node caps, invalid Unicode
  and ordinary deterministic hashing.
- `8102edb1bcf974da2475113b44e3dcf16cd3874c` adds two
  disposable SQLite integration regression methods: hard process
  exit after an uncommitted claim/completion must leave no durable
  journal, and competing connections must produce one committed
  completed row plus replay without a second reservation.

**Verification:** These five newly committed unittest methods were
NOT executed in this tool session, and exact-head Windows compileall
and `python run_v8_checks.py` remain **UNVERIFIED**. Do not reuse
the older 245-test PASS figure for this head. The source and tests
have been inspected; no fabricated passing count is asserted.

**All commercial blockers:** Gate A transaction authorization and
Gate B accounting reconciliation remain BLOCKED; cloud Gate C,
commercial licensing Gate D and final QA Gate E remain outstanding.
No transaction-capable V8 service, live sales, GRNs, returns, payments,
stock writes or shift mutations were enabled. No V7 production data,
keys or stable main changed.

**Next:** Obtain exact-head Windows push Actions result and repair any
failing test (especially the nested subprocess/Windows concurrency
regressions). Then implement strictly service-owned verified
session/role, canonical branch/shift and signed-license checks in the
same isolated DB transaction as durable journal and posting simulation;
never connect to real checkout while Gate A/B fail.


## Windows 263-test failure triage and surrogate fixture repair — 2026-11-04

**Actual user Windows evidence:** After fast-forwarding `develop-v8` from
`a76e230` to `ad1507d`, the local `python -m compileall -q velopos_qt
tests` completed without visible errors; `python run_v8_checks.py`
ran **263 tests** in 85.520 seconds, **FAILED (failures=1)**. The only
reported failure was
`tests.test_v8_idempotency_key_canonicalization.FingerprintKeySafetyTests.test_invalid_unicode_is_caught_as_request_validation_error`.
Earlier local `a76e230` had 212 tests, OK, but is an older code version.

**Root cause:** Test fixture used Python string `"\\\\ud800"` and
`"\\\\udfff"` (literal backslash-u text), which is valid JSON input,
rather than actual lone-surrogate Unicode code points. The production preview
fingerprint code's surrogate-to-ValueError conversion did not cause the failure.

**Fixes on `develop-v8`:**
`003d6d595c285ec6558284e84968d44e23efb300` replaces those
ambiguous literals with `chr(0xD800)` and `chr(0xDFFF)`, ensuring
genuinely malformed Unicode is rejected with a ValueError containing
"encoding". A positive control asserts legitimate literal backslash-u
barcode text remains valid. Follow-up
`6d006735c26b6f928f2113dd0fe750537e91c726` corrects that positive
control to contain one literal backslash rather than two.

**Verification:** An isolated independent local Python unittest exercising
the same json.dumps(ensure_ascii=False) -> UTF-8 encoding behavior passed
(1 test, OK); this is **not** an execution of the repository test suite.
Exact new GitHub SHA Windows CI / 263-test suite rerun is **PENDING**.
Do not claim all tests pass on the patched commit yet.

**Next priority:** Run the entire exact-head Windows preview suite and
compileall; if failed, fix remaining regressions. Then resume service-owned
canonical session/role, shift, signed entitlement, branch isolation and
persistent atomic idempotency. Gate A/B BLOCKED; C/D/E remain outstanding.
No production sale, payment, stock posting, V7 data, secrets or `main`
modified.


## Exact-head local Windows suite PASS — 2026-11-04

**User-provided Windows execution evidence (not GitHub-hosted CI):**
User fast-forwarded local `develop-v8` from `ad1507d` to the exact GitHub
code SHA `dd7ae38b4adfdfb53f0b23fe9690fd3d76f7ba70`.
`git rev-parse --short HEAD` printed `dd7ae38`.
`python -m compileall -q velopos_qt tests` returned without visible errors.
`python run_v8_checks.py` reported **Ran 263 tests in 88.806s — OK**.
The suite runner is configured to return failure on skipped tests; no skips
were reported. Therefore the 263-test Windows **local** suite PASSED for
exact code SHA `dd7ae38`, fixing the prior one-failure 263-test run at
`ad1507d`. PySide6 printed missing-font-directory and
`propagateSizeHints` warnings; neither failed this suite. The user also
reported an unrelated untracked local `VeloPOS-8.0/` folder in earlier
`git status`; no action was taken on it.

**GitHub status distinction:** GitHub connector compared `dd7ae38`
to `develop-v8` and returned identical before this documentation-only
checkpoint. Commit combined-status returned no status entries and
PR-filtered Actions run lookup returned no runs. This does **not** verify
the GitHub-hosted push Windows Actions run. Do not attribute these 263
passed tests to this later documentation commit.

**Commercial gates:** A/B still BLOCKED; C/D/E still outstanding.
No checkout/payment/return/GRN/stock posting authorized or enabled,
no V7 production data, signing secrets or `main` touched.

**Next strict priority:** independently inspect exact commit's GitHub-hosted
Windows push workflow; then continue trusted service-owned
session/role/branch/shift/signed-license authorization under the same
disposable SQLite transaction as persistent idempotency and crash recovery,
with cross-branch and concurrent-request regression tests. Retain
mandatory deny gate until all Gate A/B evidence is complete.


## Journal schema fail-closed completion constraints — 2026-11-04

**Previous verified evidence:** user-provided local Windows
`dd7ae38` run: **263 tests / OK / 88.806 seconds**, not current code.
Commercial gates reviewed: Gate A BLOCKED; B in progress but BLOCKED for
production; C/D/E not production-ready.

**New safe code batch on `develop-v8`:**
- `39d18c1a3953ae33a4704858cb51ba4b741ce019` tightens newly
  created SQLite preview request-journal constraints: a COMPLETED
  result_ref must be TEXT, length 1–128, trimmed, and free of ASCII
  newline, carriage return and tab. This narrows direct SQL bypasses
  around the existing Python-level reference validation.
  The `complete()` method now validates scope AND request ID using the
  same canonical identity contract as `claim()`.
- `414baed8cc4d3316c6ebd2b25253e8c0ee4e7d45` adds two disposable
  DB regressions for direct SQL malformed-completion insertion and
  invalid completion request IDs.
- An independent SQLite in-memory smoke exercise verified 7 malformed
  references rejected and a normal reference accepted. This is NOT
  a run of the repository's Windows tests. Existing legacy journal
  tables are not automatically migrated or represented as safe.

**Verification pending:** Exact-head Windows compileall and
`python run_v8_checks.py` have **not** run on these commits.
GitHub combined status and PR-filtered Actions lookup did not provide
a confirmed push-triggered Windows run for the previous checkpoint.
Do not reuse the prior 263-test PASS as evidence for this head.

**Next priority:** Verify new head on GitHub-hosted Windows Actions and
the combined Windows suite; fix any failures. Continue Gate A canonical
session/role/branch/shift/signed-entitlement checks and transactional
idempotency, with a dedicated posting simulation that ALWAYS rolls
back. No real financial mutations or V7 services may be unlocked.
`main`, V7 production data and signing secrets untouched.


## Integrated sale authorization + durable journal recovery snapshot — 2026-11-04

**Branch:** `develop-v8` only. Reviewed `docs/V8_MASTER_ROADMAP.md`,
`docs/V8_COMMERCIAL_RELEASE_GATES.md`, the last checkpoint, recent
`develop-v8` changes, `atomic_sale_boundary.py`,
`service_authorization.py`, `checkout_preflight.py`,
`sale_plan.py` and `idempotency_ledger.py`.
Discovered three intervening commits after `8cd01a4` that tightened
journal result-reference integrity and added regression cases; preserved
those changes.

**Code:** `1477caa24b52b030ccdf13de979b37d61352ade7` creates
`velopos_qt/atomic_sale_recovery.py`, a **read-only, rollback-only**
V8 test-data diagnostic that inspects canonical cashier/shift/branch,
signed license/activation observations, stock/price preflight AND durable
idempotency journal triage in the SAME caller-owned SQLite transaction.
The pure canonical request payload binds claimed branch, actor, shift,
license, machine, draft lines and day. These are untrusted request
identity fields, **not** authorization. Distinct request identity with
the same request id fails closed. Results remain frozen,
`can_checkout=False` and `can_execute=False`; `require()` always
raises `PermissionError`. No journal reservation, sale, payment or stock
movement is committed by this module.

**Tests:** `617a28499a06445fa53d47082862ac700a200442`,
test correction `a5a58a04280c53dd2ac160a60fd19d64daf21f84`,
and canonical Decimal replay test `2213e4e5d317eef145ca1bcc1883121ecc052bba`.
`tests/test_v8_atomic_sale_recovery.py` now has **six** disposable
subprocess/SQLite unittest methods: healthy policy still denied and no
writes; pending and completed journal states; immutable identity
conflicts for branch/device/actor/shift/draft; revocation plus closed
shift after a completed journal; caller-owned/foreign connection safety;
and numeric-equivalent immutable replay. An orphaned PENDING claim is
deliberately NOT auto-completed or retried; the completed-claim test uses
a **different** request id with claim and completion in one transaction.

**Verification:** Previous user-provided local Windows run on
`dd7ae38b4adfdfb53f0b23fe9690fd3d76f7ba70` passed **263
tests, 0 failures, 88.806s**, with compileall returning no errors;
that evidence is for an **older commit**, not the new code.
GitHub combined status for new test SHA `2213e4e` returned no
statuses; the connector's PR-event workflow lookup returned zero runs
and does not cover push Actions. New six test methods and exact-head
Windows compileall remain **UNVERIFIED**. Do not claim these tests pass
until executed; do not inherit 263/263 from the older SHA.

**Progress tracking:** Historical ~35% *subjective* development
estimate unchanged (not measured). **0/5 commercial release gates
accepted**: A/B hard BLOCKED, C/D/E incomplete. This batch does not
unlock any real transactions or remove a commercial gate.

**Next priority:** Verify the exact-head Windows push Actions + no-skip
`python run_v8_checks.py` and repair failures. Then build a separately
reviewed **service-owned** transaction boundary that revalidates
canonical persisted session/role, branch and shift, server-authenticated
signed licensing and immutable journal within the same disposable
DB transaction before any business posting. Add concurrent/crash and
cross-branch regression evidence; keep checkout and legacy V7 services
strictly disabled for V8 until Gates A/B actually pass. Do not touch
stable `main`, production data, private keys or customer licenses.


## Five-phase commercial execution adopted + Phase 1 immutable draft snapshot — 2026-11-04

**User decision:** Group the entire VeloPOS V8 mission into five ordered
acceptance phases rather than report subjective percentage increases.
`docs/V8_FIVE_PHASE_EXECUTION_PLAN.md` added in
`e052b9f47a915243bd681ad9f8ca53ef9d5cf4e3`; master roadmap linked
in `a784049a7798fc6b168e5624cdff1dd275a175ab`.
Phase 1: verified service-bound security, signed entitlement, shift and
branch identity, atomicity, persistent idempotency, crash recovery.
Phase 2: billing/purchasing/stock/returns and Gate A/B reconciliation.
Phase 3: optional offline-first multi-branch/cloud/owner dashboard.
Phase 4: production activation/trial/email recovery/installer.
Phase 5: premium UI, trilingual accessibility, Windows/hardware/final QA.
**Phase status:** Phase 1 in progress; none of the five phases accepted.
These are milestones, NOT claims of work finished in one run.

**Phase 1 code batch:** `63a86015eee013e56377e6e62187fb560a7e93b2`
makes `PreviewAtomicSaleRecovery.inspect_in_transaction()` validate and
canonicalize the caller's draft once, then pass the same frozen lines to
persisted session/branch/license/stock policy inspection and journal
fingerprinting. This addresses one-shot generator exhaustion and caller
mutation between the independent checks. `fc51ea10db39a479e2f118922d3e7a0841a81175`
pins an omitted calendar date to one resolved day across preflight and
immutable request identity (important at local midnight). All of these are
**read-only/rollback-only V8 TEST DATA** diagnostics; `require()` still
denies, `can_checkout=False`, and no production posting is enabled.

**Regression:** `f891a35741267077b5e9e50f744770d3a04f0454`
adds generator-consumption and hostile caller draft-mutation
subprocess tests. `ae8d3d82cd731bec2d7358329dfb3e0bf1cb2d8a`
adds date-pinning regression, making three new methods and nine total
in `tests/test_v8_atomic_sale_recovery.py`.

**Evidence:** Previously confirmed user Windows local `dd7ae38`
`run_v8_checks.py`: **263 tests / OK, 88.806 sec**, and compileall
with no errors. That SHA is older than these Phase 1 commits.
At `a784049`, GitHub branch comparison returned `identical` to
`develop-v8`; combined status entries and the connector's PR-filtered
workflow runs were empty. Neither is proof of push Actions result.
**Exact-head Windows CI and new test execution UNVERIFIED**; no
fresh passing count is claimed. No local test execution in this run.

**Gate status:** **0/5 commercial release gates accepted**. A/B hard
BLOCKED; C/D/E incomplete. The earlier ~35% figure is a subjective,
not independently computed estimate; do not advance it without
objective task/gate accounting. No real sales, returns, GRNs, supplier
or credit payments, shift mutations, stock posting, production V7
data, paid licenses, signing keys or `main` touched.

**Exactly next priority:** Inspect the latest exact-head Windows push
Actions and full no-skip preview suite; repair failing tests if present.
Then move Phase 1 into a separately reviewed service-owned canonical
session/role, branch/shift and signed-license enforcement boundary
that owns the SAME isolated SQLite transaction and idempotent ledger;
prove revoked sessions, concurrency, crash and cross-branch refusal
on disposable data. Real financial writes remain disabled until Gate A/B
are independently accepted.


## Phase 1 bounded sale-stream and Decimal exponent safety — 2026-11-04

**Branch and plan:** develop-v8 ONLY; five-phase execution contract is
`docs/V8_FIVE_PHASE_EXECUTION_PLAN.md`. Read master roadmap, commercial
gates, five-phase plan, earlier progress, sale plan, recovery boundary,
idempotency ledger and relevant regressions. Earlier user-verified
**Windows local** result remains `dd7ae38`: 263 tests / OK /
88.806 seconds, compileall with no visible errors; this DOES NOT
cover the later Phase 1 code commits.

**Source hardening:** `6e9d8907a6f456a0fc1cb9f96d78019aed133c13`
replaces unlimited `tuple(lines)` materialization in
`velopos_qt/sale_plan.py` with bounded `islice(iter(lines), 101)`;
invalid streams fail after at most 101 produced entries, respecting the
existing 100-line cap. This protects against unbounded/infinite generators
without altering normal 1–100-line arithmetic.
`1d9acad80bcaae493c0ce01779c17a985914d3a9` caps the raw numeric
string at 128 chars and rejects nonzero Decimal magnitude exponents outside
[-18,18] before canonical fixed-point expansion. This rejects hostile
input like 1E-999999999 which previously could cause huge allocation
in `canonical_decimal`, while retaining ordinary retail quantities,
prices and 1e-18 as a bounded precision lower limit.

**Regressions:** `11d2d6482b4fa3aa5594d6553a5db4467900871f`
adds guarded generator (101-entry cap) and exact 100-line arithmetic
tests; `13a5641fd86d3b782bc214bb887608858be0a76d` adds disposable
rollback-only atomic sale recovery rejection with unchanged finance
and journal snapshot. `bbe0ffe1cf1132643968635487a286284a4a6c5a`
adds extreme-exponent and overlength numeric representation rejection
tests. **Four** new test methods total in this batch. The tests were
committed but NOT executed in this tool session. New-head Windows
CI and combined no-skip regression count remain unverified.

**Gate evidence metadata:** `e603be8d7f3a093c604ffe8bd9ee17f22f963d42`
corrects `docs/V8_COMMERCIAL_RELEASE_GATES.md` from stale 121-test
historical wording to the exact earlier 263-test local Windows result,
while explicitly distinguishing it from a hosted CI result or current
head success. This is a documentation update, not a release approval.

**Remaining hard blocks:** Phase 1 IN PROGRESS; Phase 2–5 NOT ACCEPTED,
**0/5 commercial gates accepted**. Gate A/B block all actual checkout,
refunds, GRNs, supplier/customer payments, stock changes and shift
posting. V8 remains TEST-DATA ONLY. No stable main, V7 production data,
private keys or paid customer licenses touched.

**Next priority:** Get exact-head Windows-hosted push Actions evidence
and run `python run_v8_checks.py` with no skips on latest
`develop-v8`; fix any regression. Then implement reviewed,
service-owned identity/role/branch/shift/licensing authorization
and committed idempotency under a single canonical disposable SQLite
business transaction, preserving production and V7 isolation.


## Phase 1 single-snapshot identity binding and persisted revocation regressions — 2026-11-04

**Scope:** develop-v8 only. Reviewed five-phase plan, master roadmap,
commercial release gates, latest checkpoint, service authorization,
branch authorization, persisted session verifier, combined signed
entitlement, single-transaction sale/recovery diagnostic and existing
test fixtures. **No production service was opened** and no financial
posting, customer data or signing secrets touched.

**Code commit:** `6cb90bd28aec5f7a8d63a3b42e74cd0e93d07ab6`
updates `velopos_qt/atomic_sale_recovery.py` to snapshot caller-supplied
identity attributes (username, role, HMAC credential tag) once into a
frozen `PreviewIdentity` before performing service authorization and
durable journal fingerprint matching. Previously mutable identity
attributes could diverge between the policy inspection and journal
actor hint; this preserves one immutable set of claims per locked
SQLite diagnostic. **The copied identity is not authorization**:
the HMAC session token, current persisted user/role/password hash,
canonical shift and branch, signed license and activation chain are
still independently revalidated within the same caller-owned DB
transaction. Invalid, expired or revoked identities remain denied.
The preview `can_execute` / `can_checkout` fields remain always False,
and `require()` always raises.

**Regression commit:** `c9a1e1f645a64a9cec46c9861546d9e3852d9691`
adds four disposable SQLite subprocess tests to
`tests/test_v8_atomic_sale_recovery.py` (14 total in that module):
mutable identity tampered *during* boundary inspection cannot split
authorization from request identity, persisted role change invalidates
the session despite a prior COMPLETED journal, password-hash rotation
permanently invalidates a cached token even if hash is later restored,
and shift-branch rebinding denies the policy despite a completed
journal result. Completed journal is never evidence of actual posting.

**Verification:** GitHub connector compared test commit
`c9a1e1f` to `develop-v8` as identical, and fetched the new source
and all four test methods. Combined-status endpoint had no status
entries and PR-filtered workflow run lookup returned no runs; those
are insufficient to prove push-triggered Actions success. No new
tests were executed in this connector session. **Exact-head Windows
no-skip test suite and compileall UNVERIFIED.** The last user-verified
local Windows 263-test PASS was at older `dd7ae38`, not this head.

**Five-phase state:** Phase 1 still IN PROGRESS; Phases 2–5 not
accepted, commercial Gates A/B BLOCKED and C/D/E outstanding
(0/5 accepted). No checkout, refund, GRN, stock posting, payment,
shift mutation, or other commercial write enabled. Never touch
stable `main`, production V7 DB or paid customer keys.

**Next priority:** confirm exact-head Windows push CI and rerun
`python run_v8_checks.py` without skips; fix errors before advancing.
Then implement reviewed **service-owned** persisted-role, canonical
branch/shift and trusted signed-license authorization together with
durable idempotent write transaction and crash recovery in disposable
V8 storage. Do not bypass Gate A/B.


## Phase 1 fail-closed journal privacy and strict request-id agreement — 2026-11-04

**Branch and gate review:** develop-v8 ONLY. Reviewed five-phase plan,
commercial release gates, latest progress, atomic sale recovery,
service and branch authorization, signed entitlements, idempotency journal,
checkout preflight and disposable integrated regressions. V8 remains
TEST DATA ONLY; signed preview diagnostics do NOT grant commerce.

**Security vulnerability addressed:** Prior
`PreviewAtomicSaleRecovery.inspect_in_transaction()` could inspect
and return a prior journal result reference even if the current session,
branch binding, shift, license activation, price or stock validation
failed. Such references could reveal a prior transaction's existence to
an unauthorized/invalid caller. At
`cb0e4904109f10cbf4114ff88f67bda33d989a32`, journal inspection
is withheld entirely unless EVERY current preview diagnostic is
consistent: persisted session bound, branch verified, license bound,
signed activation chain valid, policy consistent AND checkout local
checks consistent. On denial it returns
`RecoveryInspection("withheld_authorization_required")` with no
result reference; no journal SELECT is attempted. This is information
minimization only, NOT a production authorization. The standard
`require()` continues to deny unconditionally.

**Contract alignment:** `c3e55a8a56188aa14845ce5861400cf0029b648c`
replaces the preview checkout preflight's old length-only request ID
validation with exactly the existing `PreviewIdempotencyLedger`
scope and request-id syntax. Invalid IDs now fail local checks and
cannot reach the recovery journal even when 8-128 characters long.

**Regressions:** `d3c46552f59743c26202b52349281ceea95dab26`
updates previous atomic recovery integration assertions for masked
unauthorized branch, identity, device, license and shift contexts,
while keeping immutable-draft idempotency conflict checks for
otherwise valid callers. `7353f367e6f6d3a7aaf520bb76ca8491f6514ade`
adds two disposable subprocess regressions: a forged role must not
query the journal at all; invalid price, license and request IDs
must mask journal references. `541e85ecb639c627f78d7507d80a9d26d00fcf52`
adds a third dedicated preflight regression for noncanonical
request IDs. The recovery test module now contains **17 unittest
methods** (three new this batch).

**Verification:** GitHub fetched the new source/test files, checked
strict preflight validator and masked state and compared latest code
commit `541e85ec` against `develop-v8`: identical. Combined commit
status had no status entries, PR-event workflow lookup had no
runs; neither verifies push-triggered Windows CI. **No new
full-suite test execution took place in this session**. Prior user
verified local Windows `dd7ae38` **263 tests, OK** remains an older
baseline, NOT a result for these latest commits. The current
exact-head Windows compileall and no-skip suite are UNVERIFIED.

**Five-phase acceptance:** Phase 1 IN PROGRESS, Phases 2–5
NOT ACCEPTED; commercial Gates A/B hard BLOCKED, C/D/E outstanding
(0/5 accepted). No real checkout, refund, GRN, credit/supplier
payment, shift posting, stock movement or transaction capability
enabled; main, V7 production data and license signing secrets untouched.

**Next:** Obtain exact-head Windows push Actions and a full
`python run_v8_checks.py` run with no skips; fix regressions.
Then implement a reviewed **service-owned** trusted signed-license,
canonical session/role/branch/shift and idempotent atomic business
write boundary in isolated V8 data, with crash/rollback tests.
Do NOT permit production financial posting until Gates A/B pass.


## Phase 1 service-owned, rollback-only signed sale journal probe — 2026-11-04

**Branch and source review:** `develop-v8` only. Reviewed the
five-phase execution plan, release gate contract, preceding security
checkpoint, `sale_rehearsal.py`, `atomic_sale_recovery.py`,
`idempotency_ledger.py`, immutable sale-plan math, signed activation
inspector and regression fixture. This batch addresses a gap between
previous read-only authorization diagnostics and the older
rollback-only rehearsal that did not include signed branch/license/
activation observations. Nothing was wired to Qt or original V7
commerce.

**Service-owned isolated simulation:**
`b6e2eb9ee5fc3fa7da47913667c4d61b915f4bb7` creates
`velopos_qt/rollback_sale_probe.py` with
`PreviewRollbackOnlySaleProbe.simulate()`. It takes its own
`BEGIN IMMEDIATE` lock against the canonical
`VeloPOS8PreviewData` SQLite database, snapshots submitted lines,
cashier identity and date once, and calls existing
`PreviewAtomicSaleRecovery.inspect_in_transaction()` in the same
transaction. This invokes persisted cashier session/role and assigned
shift, branch membership, signed Ed25519 license and signed server
activation chain diagnostics plus price, expiry and stock preflight.
The probe proceeds ONLY with all local policy evidence consistent and
an unused journal request key. It simulates claim → complete →
replay on the same connection, using a deterministic synthetic
`SIM-` reference. Finally it **ALWAYS rolls back**, on success,
denial and exceptions, leaving NO durable journal, invoice, payment,
stock change or shift write. There is no arbitrary delegate/callback,
commit, real sale/receipt, or public posting permission. Its frozen
return value explicitly has `persisted=False`,
`can_execute=False` and `can_checkout=False`, and `require()`
always raises. This is proof-of-internal-composition only, **not**
commercial authorization or a reliable business result.

**Further hardening:** `d78bb9524d209723f728ed8ced2116358d4f4e35`
validates canonical scope/request ID BEFORE opening the write
transaction and limits simulated failpoint names, to reject
malformed input without touching the journal.

**Regressions:** `2f6d4177ee6ebe5fa190df8f4c97f0e8c4633c60`
creates `tests/test_v8_rollback_sale_probe.py` with 6 disposable
subprocess/SQLite tests; `b3b8382f0054bd9d3448438356bc2299d28afcd5`
adds 2 more (**8 new tests total**). Cases cover valid signed
policy with guaranteed rollback and immutable denial return,
injected failure after claim/completion/replay, forged or revoked
identity/branch/shift/activation/license, stranded PENDING and
COMPLETED claims requiring reconciliation, mutable actor and
one-shot line generator, changed price/insufficient stock/expired
batch, malformed request ID and prohibited commit-style failpoint.
The module doesn't invoke live financial services. Completed journal
status is NEVER accepted as evidence of a posted invoice.

**Verification:** GitHub fetched the module and 8 test methods,
verified the explicit BEGIN IMMEDIATE/claim/rollback/hard-deny
source and compared test SHA `b3b8382` against `develop-v8`:
identical. Combined-status lookup returned no statuses and the
connector's PR-only workflow lookup returned no runs; neither
establishes push-triggered Windows CI. **No repository tests were
executed in this environment. Exact-head Windows compileall and
no-skip `run_v8_checks.py` remain UNVERIFIED.** The last owner
confirmed local 263-test PASS was older SHA `dd7ae38` and must
not be attributed to new code.

**Release position:** Five-phase Phase 1 IN PROGRESS, Phases 2–5
unaccepted, Gates A/B hard BLOCKED and C/D/E pending (0/5 accepted).
All V8 money, checkout, stock, returns, supplier/customer payments,
GRNs and shift posting stay disabled. Do not alter stable `main`,
V7 production records, signing keys or paid customer licenses.

**Next mandatory priority:** obtain the exact-head Windows push
Actions result and run the entire no-skip preview suite; repair
any failed tests. Continue toward a trusted, reviewed service-owned
commercial transaction boundary with persistent server-authoritative
licensing, complete accounting/stock invariants and recovery before
EVER enabling real posting; the rollback probe is NOT a shortcut
around Gates A/B.


## Owner-confirmed exact-code Windows 293-test PASS — 2026-11-04

**Owner-provided Windows local execution evidence:**
From an activated Python virtual environment in the VeloPOS 8.0 repo,
the owner ran `git fetch origin develop-v8`,
`git merge --ff-only origin/develop-v8`,
`git rev-parse --short HEAD`,
`python -m compileall -q velopos_qt tests` and
`python run_v8_checks.py`. Git fast-forwarded local develop-v8 from
`dd7ae38` to `9753c47`, and `git rev-parse` printed
`9753c47` (full code SHA
`9753c4727cc36addbcff73ea458ce44c837897cb`).
`compileall` returned without visible errors. The combined suite
printed **Ran 293 tests in 139.399s — OK**; **0 failures and no
skips reported** (the runner returns failure if any skipped test is
recorded). PySide6 font directory and `propagateSizeHints` warnings
did not fail these tests. This is the first owner-confirmed local
Windows execution of the rollback-only signed sale probe and its
accumulated prior security regressions. Previous 263-test local PASS
on `dd7ae38` is now superseded as the **latest locally verified
code commit**.

**Verification limitation:** This is **Windows local**, not proof of
the GitHub-hosted Windows Actions workflow. GitHub commit status
lookups for `9753c47` returned no status entries and the available
workflow lookup filters to PR-triggered runs, returning no results.
The release gates evidence document was updated in
`7828e10f9ecc6dc05fee9bccf92aa8a9ce011b30`.
The documentation-only checkpoint(s) following `9753c47`
were NOT individually tested on Windows; do not ascribe the 293
PASS to a later code SHA.

**Five-phase / commercial status:** Phase 1 IN PROGRESS;
Phases 2–5 not accepted; **0/5 release gates passed**. Gates A/B
remain hard BLOCKED while the app is isolated TEST DATA ONLY,
nontransactional; C/D/E outstanding. No commercial service,
checkout, stock postings, refund, GRN, payment or shift write
enabled. Preserve stable `main`, real V7 data, paid customer
entitlements and private signing keys.

**Next priority:** Independently verify GitHub-hosted Windows
push Actions on a future exact head and continue trusted
service-owned transaction enforcement with persistent
server-authoritative licensing, full stock/accounting invariants,
concurrent retry/crash tests and no V7 bypass. No commerce enablement
until Gate A and B evidence accepted.


## Phase 1 lossless Decimal request identity and deterministic sale rounding — 2026-11-04

**Scope:** `develop-v8` ONLY, using the five-phase plan and commercial
release gates as acceptance criteria. Reviewed last user-confirmed
`9753c4727cc36addbcff73ea458ce44c837897cb` Windows local
`run_v8_checks.py`: **293 tests, OK, 139.399s**, compileall no errors.
That proof is for the previous code SHA, NOT for this batch. GitHub
combined CI status at prior checkpoint had no available statuses;
hosted push Windows Actions remains separately unverified.

**Confirmed correctness flaw:** `velopos_qt/sale_plan.py` previously
called `Decimal.normalize()` when deriving canonical immutable sale
request items. It respects ambient `decimal.getcontext().prec`
(default 28) and can round distinct high-precision quantities such
as `0.123456789012345678901234567890123456` and
`0.123456789012345678901234567890123457` to the SAME canonical
string; thus two different requests with equal receipt cents could
share an idempotency hash. The Decimal behaviour was independently
reproduced and verified without use of customer data.

**Code fixes:**
- `d6f605e2857a0bf1bd260d97abebf8532d3a3546`: lossless
  `canonical_decimal` uses exact fixed-point `format(number, "f")`
  and strips only insignificant fractional trailing zeroes.
  No ambient precision-based rounding of identity values occurs.
  The existing bounded number length/exponent guard remains.
- `b6ec47dda45547f33325edd6b8b2873ef3601953`: subtotal,
  line-level `ROUND_HALF_UP` quantization and combined duplicate
  barcode quantities are calculated in a fixed private 512-digit
  Decimal context, not a caller's thread-local precision, rounding
  policy or Inexact trap setting. 512 exceeds the exact arithmetic
  needs of the bounded 100-line / 128-digit test-only draft contract.
  This is draft math, NOT certified tax, inventory, or checkout posting.

**Regressions:**
- `823c49d706d33954a80cd7b044489f5237845574`: different
  low-order decimal digits must produce unequal canonical payloads
  and fingerprints at precisions 6/28/50, even with equal cents;
  equivalent zeros and exponent forms remain canonical.
- `1c00259472501d052db76973b002d39fe47d1d16`: disposable
  integrated journal test must raise `IdempotencyConflict` if a
  previously completed request changes a deep-precision quantity,
  even though displayed line totals are unchanged.
- `448b6d24377df9bf745dc1d5d404f82f6bf15018`: use an
  adversarial ambient Decimal context (`prec=3`, `ROUND_UP`,
  `Inexact` trapped) and assert identical receipt cents,
  exact stock quantities and journal fingerprints.
  **Three new unittest methods** added across preexisting files.
- `4dbfa74e4f37ee212603af3459535ab6d0a7a138`: post-review
  fix adds the explicit sale-planner import inside the disposable
  integration test subprocess, avoiding a missing-name test failure.

**Verification limitations:** An independent local Python smoke
using the same built-in Decimal fixed-point arithmetic passed for
four contexts; this is NOT an execution of repository tests.
The newly committed test methods and exact-head Windows
`python run_v8_checks.py` remain **UNVERIFIED**. Do NOT copy the
older 293-test PASS claim onto the new code. The canonical hash
changes for certain unusually high-precision preview journal
requests that used the previously lossy format; a mismatch must
fail closed / require manual reconciliation, never auto-rewrite
or auto-replay stored journal rows. No production data migration
was performed.

**Commercial status:** Phase 1 IN PROGRESS, Phases 2–5 NOT
ACCEPTED, Gate A/B BLOCKED, C/D/E outstanding (0/5 accepted).
All V8 sale, payment, refund, stock, shift and GRN postings remain
disabled; no V7 production database, paid keys or `main` modified.

**Next strict priority:** Obtain exact-head Windows push Actions
and no-skip combined regression evidence; fix any failures.
Continue trusted service-owned, canonical session/branch/shift
and signed-license enforcement integrated with persistent
atomic ledger and crash-safe business mutation on disposable
V8 storage only, and reconcile complete accounting/stock invariants
before permitting any real posting.


## Owner-confirmed Windows 296/296 no-skip local PASS on da53500 — 2026-11-04

**Evidence from the owner's actual Windows PowerShell terminal:**
Local `develop-v8` had fast-forwarded to code SHA
`da535008b708511fbb8cf64529e5c9d2fc983ebd` (short `da53500`).
The first attempted combined run gave
**Ran 296 tests in 132.887s — OK (skipped=59)**, so it was NOT
accepted as a complete run. Re-running after explicitly activating
`C:\\Users\\user\\VeloPOS8\\.venv\\Scripts\\Activate.ps1`
confirmed that `python` resolved to the virtual environment
`C:\\Users\\user\\VeloPOS8\\.venv\\Scripts\\python.exe`
and imports `PySide6.QtWidgets` and `cryptography` succeeded.
`python -m compileall -q velopos_qt tests` produced no visible errors.
The corrected `python run_v8_checks.py` run printed
**Ran 296 tests in 121.843s — OK**, with **0 failures, 0 skips**,
and **Suite exit code: 0**. PySide6 font and
`propagateSizeHints()` warnings were nonfatal. The 59 skipped
tests issue is resolved on the explicitly verified virtual
environment run; do not mark the earlier skip-containing run green.

**Version and CI distinction:** This is **exact-code local Windows**
verification for `da53500` only, including the lossless Decimal
and deterministic rounding regressions. GitHub verified that
`da53500` equaled `develop-v8` *before* writing this
documentation checkpoint. The GitHub-hosted Windows push Actions
workflow remains **UNVERIFIED**; empty legacy commit statuses or
PR-filtered workflow runs cannot prove it passed. Subsequent
documentation-only SHAs are not independently executed on Windows.
Release-gates evidence was updated in
`07589b5b411e80c8a8d3b6fe33f6ec540e03f8f5`.

**Release gates:** Five-phase Phase 1 still IN PROGRESS;
Phases 2–5 not accepted; **0/5 commercial release gates
accepted**. Gates A/B remain BLOCKED and cloud/licensing/final
QA gates C/D/E outstanding. V8 remains isolated TEST DATA ONLY.
No checkout, financial posting, supplier payment, refunds, GRNs,
stock or shift business mutation enabled; stable `main`,
customer V7 production data and signing keys untouched.

**Next priority:** independently validate the exact-head GitHub
Actions Windows push job; move Phase 1 toward reviewed trusted
service-owned transaction enforcement with authoritative signed
activation, current session/role/branch/shift and persistent
idempotency + crash recovery on one disposable SQLite transaction.
Only after Gate A/B financial, stock and accounting invariants
are genuinely accepted may any production financial capability
be considered.


## Phase 1 hardening batch — canonical SQLite schema binding (2026-11-04)

**Code head before checkpoint:** `d38bb54ba5f7b2c182eefb83095b4dde52630cf4`.
This batch closes a specific *preview-only* SQLite name-resolution risk:
SQLite normally resolves unqualified table names against `TEMP` before
`main`. An already-open caller-owned connection to the canonical
disposable V8 database could therefore supply shadow `TEMP` tables
for users, shifts, products, batches, branch bindings or the request
journal. Checking only the `main` file path was not sufficient to
ensure that authorization, inventory and journal queries read
canonical persisted rows.

**Implemented on `develop-v8` only:**
- `velopos_qt/service_authorization.py`: persisted cashier and shift
  lookups now explicitly reference `main.users` and `main.shifts`.
- `velopos_qt/branch_authorization.py`: branch registry existence and
  membership/shift joins explicitly reference `main.sqlite_master`
  and `main.*` tables.
- `velopos_qt/checkout_preflight.py`: session, shift, inventory,
  batch-expiry and price checks explicitly use `main.*` tables.
- `velopos_qt/idempotency_ledger.py`: journal existence, creation,
  claim, replay and completion explicitly use `main.*`; a forged
  `TEMP` journal cannot shadow durable idempotency state.
- `tests/test_v8_atomic_sale_recovery.py`: added four isolated
  subprocess regressions for shadow users/shifts, stock/branch,
  completed journal and forged new-claim journal. They use disposable
  V8 data and no production business mutation.

**Verification status:** These four new tests and the entire
combined suite are **NOT YET VERIFIED** on Windows or GitHub Actions
for this new code head. Previous owner's exact-code `da53500`
Windows local milestone remains **296 tests, 0 skips, exit code 0**;
do not transfer that result to this batch. The intended combined
suite count is **300** (296 prior + four added), pending execution.
The GitHub connector's commit workflow-run lookup returned an empty
list for `d38bb54`, but that endpoint only exposes PR-triggered
runs; it does **not** establish success, failure or absence of
push-triggered Windows CI. Independently verify push Actions by
exact head SHA and inspect job logs before claiming CI success.

**Commercial gates:** Phase 1 IN PROGRESS, Phases 2–5 NOT ACCEPTED,
0/5 release gates accepted. Gate A/B remain BLOCKED, C/D/E outstanding.
All checkout, refund, purchasing, shift, stock and financial postings
remain disabled. No `main` branch, V7 production data, paid keys or
customer records touched.

**Exact next priority:** Execute new shadow-table regressions and
the complete no-skip Windows suite against the current exact code
SHA. Fix any failures. Then audit remaining unqualified SQL in
preview service-owned authorization and recovery, and advance
trusted service-owned license/session/branch/shift checks with
persistent idempotency and crash-safe accounting invariants on
disposable V8 storage only.


## Phase 1 canonical SQLite main-schema binding against TEMP shadowing — 2026-11-04

**Progress baseline:** The owner-requested rough overall development
estimate remains **~35% (unmeasured, not an acceptance score)**;
Phase 1 of five is still IN PROGRESS. Commercial release **gates
accepted: 0/5**; A/B BLOCKED, C/D/E outstanding. A verified Windows
local suite at `da535008b708511fbb8cf64529e5c9d2fc983ebd`
ran **296 tests / OK, 0 skipped, exit 0, 121.843 seconds** in
the correct `.venv`. That is an older exact code SHA; this newer
hardening batch has NOT been run on Windows yet.

**Security issue found:** SQLite resolves an unqualified table name to
a caller-created `TEMP` table before the persistent `main` table.
A caller-owned connection whose `main` path passed the preview DB
path check could therefore shadow `users`, `shifts`,
`products`, branch registry tables or
`v8_preview_request_journal`, potentially producing misleading
identity, branch, inventory or journal diagnostics. This is a
**transaction-boundary integrity problem**, not a production bypass
claim (V8 checkout remains hard disabled). A separate isolated
Python/SQLite smoke reproduced the TEMP-first resolution and
confirmed explicit `main.table` avoids it.

**Code commits on develop-v8 only:**
- `25c8e81480f12c8812518e9e112dca7729f6c582`: explicit
  `main.v8_preview_request_journal` in inspect, claim,
  insert, complete and `main.sqlite_master` lookup;
  no TEMP/ATTACH shadow can impersonate persisted idempotency rows.
- `7d6c178cd4d5316c809d7557a10c44a7842babd4`: current
  persisted cashier/shift policy reads from `main.users`,
  `main.shifts`, never TEMP overrides.
- `5a175322aafc2ace617d6eee9d0a75f73556db52`: branch
  registration, membership and shift assignments use `main`
  tables and main schema metadata.
- `712d0b8a29254c88f2e39f6d6d4be25e237aba15`: checkout
  preflight user, shift, product, batch and price rechecks read
  `main` tables explicitly.

**Regression methods:** `a306b466d1a3c78d2d7974c3af4fb9102a4c7da7`
adds 3 disposable V8 SQLite subprocess tests in
`tests/test_v8_atomic_sale_recovery.py`: TEMP user/shift copies must
not resurrect a main-database revoked role or closed shift;
TEMP product/branch copies must not mask main stock depletion or
membership revocation; and a TEMP shadow journal must not hide a
persisted completed request or permit a new claim.
`d38bb54ba5f7b2c182eefb83095b4dde52630cf4` adds a fourth
regression ensuring a forged TEMP completed record cannot block a
fresh canonical main journal claim; staged main table creation and
claim are rolled back. **4 new test methods**, 22 methods in
atomic-sale-recovery test module.

**Verification scope:** GitHub source and commits verified.
An independent SQLite namespace smoke passed and showed canonical
main queries override TEMP shadows; this does NOT establish repository
suite passing. **New-head compileall, Windows local no-skip suite and
GitHub-hosted push Actions remain UNVERIFIED**. No new passing test
count is claimed. Old `da53500` local 296-test result is not
inherited by this code. No implementation here authorizes real
sales, payments, stock deduction, return, GRN, shift or supplier
posting. No `main` branch, V7 production data, signing secrets or
paid customer licenses changed.

**Next strict priority:** Verify the new exact SHA in Windows
`python -m compileall -q velopos_qt tests` and
`python run_v8_checks.py` with the correct virtual environment
and 0 skips; address any failures. Continue comprehensive
service-owned canonical authorization plus signed-license and
crash-safe idempotent business write design in disposable V8
storage. Gate A/B must pass before financial posting is enabled.


## Delivery acceleration: automated Windows CI + visible Billing Draft receipt slice — 2026-11-04

**Owner constraint and correction:** The owner has rightly objected that
repeat claims of **~35%** alongside dozens of small security commits
and requests for manually rerunning Windows tests are too slow and
time-consuming. The ~35% is explicitly **an unmeasured rough estimate,
not an actual verified completion percentage**. No artificial
increase is claimed. Switch to acceptance-driven, user-visible
end-to-end feature slices, with actual Windows CI instead of repeatedly
requiring the owner to operate PowerShell. Full plan update:
`docs/V8_FIVE_PHASE_EXECUTION_PLAN.md` at
`22e6b3b2219919501da6daf1b6a8a68bc1145d96`.

**CI automation:**
`24c71d07d7e7a95168ccce46fcb698d005fe6f27`
creates `.github/workflows/v8-preview-windows.yml` for
pushes/PRs to `develop-v8`, plus manual dispatch. GitHub-hosted
Windows runner, Python 3.12, dependencies from `requirements.txt`
plus PySide6, ephemeral isolated `VELOPOS_HOME`, offscreen Qt,
`python -m compileall -q velopos_qt tests`, entire
`python run_v8_checks.py` with **any skipped tests causing failure**,
and logged tested SHA. No production keys or customer data. The
workflow file is in GitHub; the actual GitHub Actions run and
whether the repo permits push-triggered workflows remain
**UNVERIFIED**. A workflow commit is not evidence of CI success.

**Visible Billing Draft slice:**
- `0b5960831257fc99a88eec65761e44c5a19ad52c` adds
  `velopos_qt/draft_receipt.py`: a pure, nontransactional
  cart-to-receipt-style text view with itemized barcode/quantity/
  price, discount, optional existing read-only net estimator,
  typed cash amount, estimated change or shortfall, and prominent
  NOT A SALE / NOT A TAX INVOICE / NO PAYMENT notices. It does not
  generate invoices, mutate stock, access customer data, print
  receipts or call payment services.
- `f2cca878e75fdc61f6df98ea7ac00ddb278fa1e5` adds a real
  visible button/dialog in the Billing Draft UI showing
  scrollable read-only receipt text and copy-to-clipboard.
  Receipt button is disabled when cart is empty.
- `a00342bf62ec82979b752b725c26d1aa59eae92d` localizes the
  viewer/button/copy/close controls in English, Sinhala and Tamil.
- `537e986350532cf95a0e201469a0ec2d94621956` adds
  **six** `test_v8_draft_receipt.py` regression methods for
  estimated totals, discount/change/shortfall, rejecting invalid
  inputs/line injection, reuse of read-only Billing net estimates,
  translations, and an offscreen UI preview dialog.
  THESE TESTS WERE COMMITTED BUT NOT EXECUTED IN THIS SESSION.
  An in-memory draft is not a certified fiscal receipt.

**Latest independently verified code:** Owner's local Windows
`da535008b708511fbb8cf64529e5c9d2fc983ebd` had
**296/296 tests OK, zero skips, exit 0, 121.843 seconds** under
the correct `.venv`, compileall clean. This evidence is now
**older than the new CI and Billing Draft changes**. No Windows
Actions success or latest-head local test success is claimed.

**Phase gates unchanged:** Phase 1 in progress; Phases 2–5
unaccepted; **0/5 commercial release gates passed**. A/B hard
BLOCKED. The new screen is a UI/read-only preview milestone,
NOT commercial billing. All real checkout, taxes, returns,
supplier payments, GRNs, stock and shift posting remain
disabled. No V7 production files, paid keys, private signing
secrets or stable `main` touched.

**Next high-value delivery:** verify hosted push Windows Actions
and fix red jobs; then prioritize a true integrated service-owned
atomic sale/stock/receipt/tender vertical slice on disposable
V8 data, including trusted licensing, cancellation/replay,
crash recovery and financial/stock reconciliation, before
ever enabling real checkout. Report tangible acceptance milestones,
not unsupported percentages. Do not burden the owner with
every routine small batch's local testing.


## Phase 1/2 vertical slice: durable isolated sandbox invoice, stock and journal — 2026-11-04

**Delivery change:** Owner wants milestone-sized development without
repeatedly operating Windows terminals. This batch moved beyond
rollback-only scenarios to an explicitly **durable TEST-SANDBOX**
sale+stock+journal cycle. It is NOT V7 production posting,
NOT commercial checkout and NOT proof of trusted server-authoritative
entitlement. The app's checkout gate remains disabled.

**Source:** `b44f8e9ab8a0130bf2881fbb983cd99d1661f1c5`
adds `velopos_qt/sandbox_sale_ledger.py`, followed by source
cleanup `7907c6fbdc1313ac87d6e6b973da77eb2ae21257`.
`PreviewSandboxSaleLedger.simulate_commit()` on a canonical
`VeloPOS8PreviewData` database freezes identity/draft/date,
runs the existing persisted-session/open-shift/branch,
Ed25519-signed license and activation-chain, stock,
price and expiry preflight in ONE owned `BEGIN IMMEDIATE`
SQLite transaction. It uses the normal V8 preview
idempotency journal with the exact same immutable request
payload. Successful **sandbox** execution commits only
`v8_preview_sandbox_sales`,
`v8_preview_sandbox_sale_lines`,
`v8_preview_sandbox_stock`,
`v8_preview_sandbox_stock_moves` and the V8 preview
request-journal row. Stock is seeded from a READ-ONLY
original product opening balance and then decremented
ONLY in dedicated sandbox stock records. Real
`sales`, `sale_items`, `products`, `stock_moves`,
`returns`, `payments`, `shifts` or batch records
are NEVER modified by the sandbox service; no real receipt,
tender or payment is issued. Return evidence explicitly
marks `actual_invoice_posted=False`,
`payment_captured=False`, `can_checkout=False`,
`can_execute=False`. The production-facing
`require_commercial_sale()` fails closed.

**Atomic/retry behavior:** Duplicate request identity
must resolve to an existing MATCHING sandbox sale and
never duplicate invoice/stock rows. Changed quantity
with the same ID raises idempotency conflict. Pending,
orphaned or corrupt journal states are denied; a prior
COMPLETED journal alone is not trusted without the
matching durable sandbox invoice. Caller-selected
failpoints after claim/stock/invoice/completion cause
full rollback including sandbox table creation. Other
invalid sessions, closed shifts, branch mismatch,
expired license or activation status never create
sandbox ledger writes.

**Independent reconciliation:** `99d29348ffa410470e3f52a73d076ea300783edf`
adds `reconcile_sandbox()`, a read-only, locked audit
of invoice totals vs lines, each invoice vs COMPLETED
journal, current sandbox stock vs opening and ordered
movement chain and all orphaned result references.
`4e51fffa197d2eab3f1a5ce045690b86371c8fcd`
also reconciles invoice sold quantity per barcode
against stock move quantity. It FAILS CLOSED on
mismatches and does not self-repair. This is only
sandbox accounting, NOT the real Gate B/V7 financial
reconciliation of tax, cash, credit, COGS, refunds,
supplier payments, GRNs or loyalty.

**Test design:** `0a2616157c0fec9b4af953e2304b9baa2d9c525c`
adds seven disposable subprocess SQLite tests, then
`17e01172511a8dd7de4301c289962c1f2b1c760a`
adds two reconciliation/tamper regressions, and
`e58d46ccbf0857e313af8ce6359d96a4ce7d33fc`
adds stock-move/invoice-quantity discrepancy test.
**10 new test methods** cover persisted invoice and
stock journals, exact-once replay, immutable key
conflict, all four rollback failpoints, sequential
stock shortage without touching original inventory,
signed authority denials, orphan completed journal,
multi-sale integer-cent reconciliation, invoice and
stock tampering and movement/line quantity mismatches.
These were COMMITTED but have NOT yet been executed
on Windows or by hosted Actions. Do not label them
PASS from older evidence.

**Previously confirmed evidence:** Owner verified
`da535008b708511fbb8cf64529e5c9d2fc983ebd`
Windows local **296 tests, zero skips, exit 0**.
Subsequent Billing Draft receipt preview and sandbox
code are NOT covered by that historical local run.
The Windows GitHub Actions workflow was committed
earlier but its actual hosted run remains UNVERIFIED
through available connector status endpoints.

**Release position and next priority:** Still ~35%
unmeasured rough estimate (NOT measured completion),
Phase 1 in progress with a partial Phase 2 sandbox
vertical slice; **0/5 commercial gates accepted**.
Gate A/B financial service authorization, real tender,
stock/COGS/tax, returns, refund and ledger reconciliation
remain blockers. No production sale, payment, return,
GRN or receipt-print capability enabled, and no V7
customer data, private signing keys or stable `main`
were touched. Next priority: get evidence from hosted
Windows Actions (and fix failing jobs), then extend the
single service-owned sandbox lifecycle to validated
tender declarations, invoice settlement and
reconciliation, while refusing real commercial posting
until Gates A/B are accepted. Avoid asking the owner
to manually run routine tests.


## Phase 2 sandbox tender declaration, replay and settlement reconciliation — 2026-11-04

**Milestone delivery:** Extended the previously persisted
isolated TEST-only sandbox invoice + stock + request-journal transaction
into an integrated **declared tender / estimated settlement** slice.
Only `develop-v8` was changed. This is NOT a real POS checkout:
no payments were captured, card/QR confirmations verified, credit
limits checked, tax/COGS/returns posted, real receipts generated,
original `sales`, `products`, `stock_moves`, customer balances,
V7 data, signing keys or stable `main` touched.

**Core code**:
- `542a091c493471ef5dea9c8eb6e559b0c45c094e` upgrades
  `velopos_qt/sandbox_sale_ledger.py` to accept optional 1..10
  test-only tender declarations via the existing deterministic
  `plan_preview_tender()` validator. Supports Cash, Card, QR
  reference declarations; **Credit denied** until a verified
  customer-credit ledger exists. Cash/noncash allocation must
  cover exactly the amount due plus cash-only change.
  No payment capture or issuing processor action occurs.
- The *complete frozen tender allocation* and cash change become
  part of the immutable V8 request-journal fingerprint so same
  request ID with changed tenders conflicts. The locked authorization
  boundary is still revalidated before lookup. Replay verifies
  a persisted matching sandbox invoice, settlement totals and
  individual tender declarations. It does not deduct stock again.
  Existing tender-absent sandbox requests remain supported with
  explicit `declared=0`.
- Sandbox-only `v8_preview_sandbox_tenders` and
  `v8_preview_sandbox_settlements` tables are created, inserted
  and committed **in the same BEGIN IMMEDIATE transaction** as
  sandbox invoice, stock moves and request-journal completion.
  The immutable evidence carries `tender_declared` and
  `change_cents`, while `payment_captured=False`,
  `actual_invoice_posted=False` and `can_checkout=False`.
- `4bb9ff41ecc647947b9f3dc8843b4b9a220e0947`
  adds independent settlement audit: every sandbox invoice must
  have a linked allocation record; sums of cash/noncash tender
  declarations must match the ledger, and declared change must
  reconcile to amount due with no noncash overpayment. Orphans,
  inconsistencies and tampered amounts fail closed. The audit
  does NOT claim funds were received.
- `65f2e60b4d064e0543e9cdcf1f378888d488276a`
  explicitly refuses unimplemented Credit and requires manual
  reconciliation when older completed sandbox journal records
  lack the new tender tables. Never silently migrate, auto-credit,
  auto-approve or replay unverifiable old data.

**Regression coverage:** `79609de74f43347797926df51b2c466423581948`
adds 6 disposable subprocess SQLite tests: cash with change and
exact replay; mixed cash/card/QR declarations; changed tender key
conflict; insufficient, fractional, missing-reference and credit
denials; altered settlement amounts; tampered allocation on replay.
`e6087c6e98d9408d420c20c36f8436ebcc5b4062`
adds 2 tests for tender rollback after the journal-complete failpoint
and old tenderless sandbox tables requiring reconciliation.
**8 new test methods** in `tests/test_v8_sandbox_sale_ledger.py`,
now 18 in that module. All tests committed, NOT executed
on Windows in this run. An independent local sqlite3 SQL syntax
smoke showed creation and insertion of sandbox tender/settlement
tables succeeds in `BEGIN IMMEDIATE`, but is not repository
test evidence.

**Evidence / open gates:** The most recent owner-confirmed local
Windows suite remains code SHA `da535008b708511fbb8cf64529e5c9d2fc983ebd`,
296/296 OK, 0 skipped, exit 0. Do not attribute that result to
the new sandbox tender code. GitHub Actions workflow is committed
for Windows push CI, but hosted success not yet independently
verified by the available connector. Phase 1 remains IN PROGRESS,
Phase 2 only a partial disposable sandbox milestone,
**0/5 commercial gates accepted**. A/B require a trusted
server-authoritative commercial boundary, exact financial tax,
COGS, stock/batch, customer/credit, audit, payment and refund
invariants before real posting. C/D/E are outstanding.

**Next priority:** Independently get exact-head hosted Actions
status and remediate any red test. Continue integrated sandbox
customer-credit/returns/accounting workflows with original service
review, avoiding repeated owner PowerShell requests. Once the
end-to-end core is solid, seek actual acceptance against Gates A/B;
never enable commercial posting based on sandbox-only tests.


## Phase 2 sandbox partial-return/refund declarations with locked cumulative limits — 2026-11-04

**User-visible direction:** Continue milestone-scale
Billing → Tender → Invoice → Stock → Returns/Refunds →
Accounting. This change adds a durable but **non-restocking,
non-financial sandbox return declaration**. This is not real
customer refund or production stock/accounting. The original
sale/return/payments/customer-credit tables and V7 live data
are never modified. Only `develop-v8` was changed;
`main`, private signing keys and paid license records untouched.

**Implementation:** `4d4f011f662156bc3a0c3cdc6c425650d232f7af`
creates `velopos_qt/sandbox_return_ledger.py`.
`PreviewSandboxReturnLedger.simulate_return()` owns one
`BEGIN IMMEDIATE` write transaction in canonical isolated
`VeloPOS8PreviewData` and rechecks current persisted cashier,
role and open shift, canonical assigned branch, Ed25519 license
specifically entitled for **return** action, signed activation
continuity and claimed license/machine/branch binding. It
verifies an existing committed sandbox invoice and matching
completed original sale journal, then validates requested
original sale **line number + quantity**. Each line's
cumulative returned quantity cannot exceed original sold
quantity. Cumulative ROUND_HALF_UP cents are bounded by the
original item's line total; no repeated cents windfall from
partial-return rounding. A new return request key is bound to
original invoice, return quantities, actor, branch, date,
license/device and refund declaration type. Claim, return
header/line declarations and COMPLETED journal entry commit
or roll back together; all three injected failure points roll
back. Only standalone `v8_preview_sandbox_returns`,
`v8_preview_sandbox_return_lines` and the test-only
idempotency journal are written. Explicit **non-restock
policy** does not add product stock back to either real or
sandbox stock; no cash refund, card/QR reversal, customer
credit or fiscal credit note occurs. Return evidence is
frozen, labeled `actual_refund_posted=False` and
`stock_restocked=False`; `require_real_refund()`
always hard-denies. This is intentionally narrower than
Gate A/B commercial return requirements.

**Reconciliation:** `11106f5368cd148e1f3e197a8935bbb896ae7dde`
adds a read-only `reconcile_returns()` audit for
original invoice/branch linkage, original sale-line
quantity/barcode, cumulative total refund cents bounded
by original line amounts, return header-line totals,
one matching COMPLETED return journal and orphaned journal
or line detection. Any inconsistency returns `balanced=False`;
nothing is auto-repaired.

**Replay integrity:** `f2a848d0b17217baca8a4add00ef0c34550873d5`
requires a COMPLETED request's persisted deterministic
reference, current actor, branch, shift, original sale,
refund mode, exact line numbers/quantities and refund-cents
sum to match before returning sandbox replay evidence.
A journal row by itself is NEVER proof of a real refund.

**Regressions:** `0ddb4d912b7b03da3b57007ff5357cd8146fc756`
adds 8 disposable SQLite process tests in
`tests/test_v8_sandbox_returns.py`: signed partial return,
unchanged V7 stock/financial tables, exact-once replay and
changed-request conflicts, quantity/amount limits,
unauthorized session/branch/license/shift denial, rollback
failpoints, tamper-detecting audit, nonexistent invoice and
unsupported Credit/modes, hard commercial denial.
`e078ac34dd235c4ed1eac5bccd34c7c150e01daa`
adds 2 tests for tampered replayed quantities and
orphaned completed return journals. **10 new regression
methods written**, NOT yet executed by owner Windows or
confirmed hosted GitHub Actions.

**Verification/gates:** Latest verified owner Windows suite
remains `da535008b708511fbb8cf64529e5c9d2fc983ebd`
with 296/296 OK, zero skipped, exit 0. It is an older
code SHA and does NOT verify subsequent sandbox sale,
tender, or return commits. Github Actions workflow exists
for Windows `develop-v8` pushes but hosted results have
not been confirmed through available connectors. Phase 1
remains IN PROGRESS, Phase 2 partial sandbox vertical slices;
**0/5 commercial gates accepted**. A/B still require
trusted commercial service authorization, true tender capture
proof, verified customer credit, batch allocation/expiry,
COGS/tax, audited refunds/reversals and end-to-end financial
reconciliation. Cloud/licensing/final QA gates C/D/E
remain outstanding.

**Next feature direction:** Add test-only sandbox
customer-credit and full return stock disposition
policy, then reconcile refund declarations against
original tender allocation and eventual accounting
contra-revenue entries; keep all financial posting in
production off until independently accepted Gates A/B.
Do not request frequent owner PowerShell commands.


## Phase 2 integrated sandbox close-out and non-restocking return disposition — 2026-11-04

**Delivery:** Added a one-snapshot, test-only financial close-out that
reconciles sandbox invoices, item prices/quantities, stock consumption,
tender allocations, partial return declarations and immutable sale/return
journal references. Return lines now explicitly record non-restocking
`DAMAGED` or `DISCARDED` disposition with a database CHECK
`restocked=0`. **Customer credit remains disabled**; no customer
balance/credit limit/repayment ledger is yet implemented. These are
sandbox experiments and never constitute real revenue collection,
cash disbursement, certified profit or financial permission.

**New code:**
- `9bcbcc885f9b7b0632e18d58ca4f61a2503b4014` creates
  `velopos_qt/sandbox_accounting.py`. Its
  `PreviewSandboxAccounting.closeout()` owns one
  `BEGIN IMMEDIATE` canonical isolated SQLite transaction and
  **always rolls back**. It verifies exact invoice-line sums,
  journal/request links, tender declarations and cash-only change,
  barcode/quantity/ordered stock moves, total returned quantities
  versus original sale lines, per-item cumulative refund cents and
  return-journal links. Missing/partial schema or tampered records
  become `balanced=False` with diagnostic reasons; no auto-fixes
  or production data writes. Frozen `SandboxCloseout` includes
  gross invoice cents, refund-declaration contra revenue,
  indicative net after returns, declared cash/external/change,
  zero captured payment/refund cents and `certified_profit_cents=None`.
  `require_certified_accounting()` hard denies.
- `3b09f3c56428b4c31e598c853d77d4c8f98fc383` additionally
  validates *each* line's exact price × quantity rounded at
  currency cents, so changed unit prices do not hide behind
  unchanged invoice subtotals.
- `73430c541784a44d2a628f52f0f688763c00af46`
  adds explicit non-restocking `disposition` and `restocked=0`
  columns to sandbox return lines, includes disposition in
  idempotency fingerprints and replay integrity checks. This
  remains an unusable/damaged-goods TEST declaration; neither
  sandbox stock nor legacy product stock is restocked.
- `fc8188e23fa3e87b2c380180218cd2cfc2b708d2` extends
  close-out to flag disposition corruption, independently of
  the return-ledger audit.

**New regressions (written, not executed):**
- `01f48e1f03535306d8bd1e3c68b4644b41407037` creates
  `tests/test_v8_sandbox_accounting.py` with 7 disposable
  SQLite subprocess tests for no-schema fail closed, sale-only
  close-out, mixed cash/Card/QR plus partial refund net,
  two partial returns, invoice/tender/stock/refund tampering,
  orphan journal/over-return, and incomplete return schema.
- `f50bcea640d5b8c40aa48bbc75cad19afcf9d4c5` adds
  disposition-corruption close-out test.
- `5c963224cc88a366f0b1bcf991e8e59ff5d8b642` adds
  sale line price tamper test with unchanged invoice subtotal.
  **9 accounting regression methods** in this new module.
- `8962d2c248d629b8be6e525d2c04673b6f5bdabd`
  adds 3 new return tests for DISCARDED disposition, immutable
  idempotency replay, rejection of RESTOCK/unknown values and
  forced CHECK-constraint corruption. The return test module
  now contains 13 methods (previous 10).
  **12 new regression methods** across accounting/return tests.

**Verification and release position:** These new source and test
commits were saved on `develop-v8`, but repository full-suite
Windows or hosted Actions execution for this latest code is
**UNVERIFIED**. Attempting local `git clone` from this execution
environment failed due to no GitHub DNS/network access, so no
local test execution is claimed. The latest owner-confirmed local
Windows evidence is still **296/296 passed, 0 skips, exit 0**
at earlier SHA `da535008b708511fbb8cf64529e5c9d2fc983ebd`;
do not transfer its PASS to the new code. A GitHub Actions
workflow file was added previously, but available commit status
and PR-only workflow lookups cannot verify push-run success.

Phase 1 still IN PROGRESS, Phase 2 partial sandbox slices;
**0/5 commercial gates accepted**; Gates A/B blocked,
C/D/E outstanding. No V7 production financial records, private
signing secrets, paid entitlements or stable `main` modified.
No production sale, cash/Card/QR collection, customer credit,
refund disbursement, GRN, batch restocking or shift posting
enabled.

**Next significant milestone:** Build a verified, customer-scoped
sandbox credit limit/outstanding/repayment ledger with explicit
authority and exact-once original sale linkage, plus refund
allocation to original tender and real COGS/tax/batch policy
reconciliation on copied V8 data. Do not enable real financial
posting until independently accepted Gates A/B and current-code
Windows CI. Avoid routine owner PowerShell burden.


## Phase 2 sandbox stock movement cardinality hardening — 2026-11-04

**Code:** `c437b020c788649d250a79d04e924a4321ceed67` updates
`PreviewSandboxAccounting.closeout()` to explicitly reject duplicate
`(sale reference, barcode)` stock movement records with
`duplicate_sale_stock_movement`. Previously a set-based coverage check
discarded duplicate identities, potentially hiding corrupted extra movement
rows. The normal sandbox writer enforces a composite primary key, but the
independent auditor must still fail closed if a copied/corrupted schema loses
that constraint.

**Regression:** `30b02bf66d3b2cfd6707f088d17a3c313d1071b4`
adds a disposable-db subprocess test which creates a legitimate sale,
rebuilds only its test stock-movement table without the uniqueness constraint,
inserts a duplicate movement, and requires unbalanced close-out and
`can_checkout=False`.

**Verification:** Source and regression were committed on `develop-v8`;
no local Python or exact-head hosted Windows CI pass has been established
for these commits. The historical 296-test local Windows PASS belongs to
an earlier SHA, not this batch. No financial production code or V7 data
was changed. **0/5 commercial release gates accepted.**

**Next:** Confirm latest exact-head hosted Windows CI; inspect job logs and
repair regressions. Then audit stock movement cardinality and journal
cross-links in other sandbox reconciliation modules, followed by
customer-scoped credit/repayment modeling and true COGS/tax/batch
reconciliation on disposable data. Gates A/B block commercial posting;
C/D/E remain outstanding.


## Customer credit limits and repayments sandbox milestone — 2026-11-04

- Branch: `develop-v8` ONLY. New `velopos_qt/sandbox_credit_ledger.py` adds test-only customer accounts with immutable Admin-set limits, a single credit charge per *wholly unpaid* sandbox invoice, and exact-once Cash repayment **declarations**. Both charges and repayments use `BEGIN IMMEDIATE`, canonical `main.*` tables, SHA-256 request fingerprints and the existing SQLite idempotency journal. Replays verify stored rows, and injected exceptions roll back the entire transaction.
- `sandbox_return_ledger.py` now refuses credit-backed returns pending an approved credit-note and receivables policy; no hidden balance write or fictitious refund. `sandbox_accounting.py` closeout optionally includes sandbox credit charges, repayments and outstanding receivables and fails closed on partial schema / mismatched journal or limit.
- New `tests/test_v8_sandbox_credit.py` contains 10 disposable-database integration tests covering limits, replay, repayments, cross-customer protection, denial of already-tendered invoices, signed session / Admin checks, rollback failpoints, credit-backed returns and tamper evidence. **New test results are not yet verified on Windows GitHub Actions**. Do not count tests as passing until the workflow for the new commit completes successfully.
- All credit and repayment records are isolated sandbox declarations: **no payment captured**, no real V7 `customers.credit_balance` / `credit_logs` mutation, no real checkout, no commercial credit authority. `require_real_credit` hard-denies. No Cloud, AI, mobile dashboard or commercial release gates were completed by this milestone.
- Overall percentage remains an **unverified planning estimate**, not a test-derived acceptance score. 0/5 commercial release gates accepted. The next priority is fixing any Windows CI failures, hardening credit ledger reconciliation and then implementing explicit credit-note/refund policy in disposable sandbox only.


## Sandbox customer credit notes and receivable adjustment — 2026-11-04

**Development branch ONLY:** `develop-v8`. This milestone extends the
isolated V8 test credit ledger with item-scoped, non-restocking credit
notes linked to a previously journal-completed sandbox credit charge.
It NEVER makes a cash refund, captures real payments, changes the V7
`customers.credit_balance`, `credit_logs`, `sales`, `returns`,
`products`, or `stock_moves`, or permits commercial checkout.

**Implemented:**
- `9c4ec3e9da1e9b463931323f3f820786cd4bd159` adds the separate
  `credit_note` idempotency request scope.
- `0370d833b0fbe39ae3a8f5766a23e1720e389965` introduces
  `PreviewSandboxCreditLedger.declare_credit_note()`, along with
  `v8_preview_sandbox_credit_notes` recording original invoice,
  charge, customer, branch and original sale-line number/quantity,
  immutable non-restocking DAMAGED/DISCARDED disposition, zero
  restocking and exact cents. Cumulative credited quantities cannot
  exceed original sold quantities; cumulative HALF_UP cents cannot
  exceed the original line cents. Every new credit note must fit the
  remaining unpaid customer receivable, not create an unverified
  external refund. The saved claim, note and completed journal
  entry are committed in one owned `BEGIN IMMEDIATE`, with failpoints
  and exact-once replay. Evidence still marks
  `actual_payment_captured=False`, `can_checkout=False`.
- `e43b7ec2ddf551f22e5dd791e246454ed757ab95` updates the
  independent credit audit to reconcile note-to-charge-to-invoice
  linkage, cumulative per-line quantities/cents, completed
  idempotency journals, outstanding receivables and limits.
  `e08e5dc04f9f4d2efa1d2b72a64115a70cc607b9` avoids
  an auditor exception on tampered orphan notes and instead records
  an unbalanced result.
- `446e808be9c1e6192ed864d43b98766f16dda644` integrates
  optional sandbox notes into the existing one-snapshot gross-to-net
  accounting closeout. Credit notes decrease declared net revenue
  and credit outstanding, without incorrectly treating them as
  captured payments or actual disbursed refunds.
- `39d3d66578162e21a09530bfe87ad51e891ed494` explicitly
  denies **new** credit notes after any repayment has been
  declared for that customer until repayments can be allocated to
  specific invoice balances. Without this rule, a note on a
  previously repaid invoice could accidentally forgive another
  invoice's debt. Exact replay of an earlier completed note remains
  available after later repayments. Ordinary refund/return service
  remains closed to credit-backed invoices; this is a separate
  credit-note declaration, not fiscal return posting.

**Regression coverage (written, not yet verified by hosted CI):**
`b04c81579df104b8bacab523a317c04779477129`
adds 6 cases to `tests/test_v8_sandbox_credit.py` for
partial note + repayment + accounting closeout, immutable replay
and changed-key conflict, cumulative sold-quantity caps,
excess note after full repayment refusal, rollback failpoints,
tampering and closed debt accounting.
`c133631526d9172121f1362e1ba74d1223d5f27c`
adds 2 more cases: deny new notes on previously repaid accounts
without invoice allocations; permit strict replay of an existing
note after a subsequent repayment. Total sandbox credit test
methods now **18**. Do not claim these tests PASSED based on
older Windows screenshots or the older green CI run.

**Verification:** GitHub source/commit presence is verified via
the connector, but its available commit-status endpoint returns
no checks and the workflow-run endpoint exposes PR-only runs,
not push-triggered Actions runs. Thus exact-head hosted Windows
CI result and error logs are **UNVERIFIED**. Do not silently
equate empty check statuses with success. No new local V8 test
suite was executed from this session.

**Release:** Legacy rough planning estimate ~35% is NOT a
measured acceptance percentage. Phase 1 unfinished and only
sandbox Phase 2 slices are present; commercial gates **0/5
accepted**, real payment/credit refunds disabled. Next priorities:
verify exact-head Windows CI, reconcile credit-note edge cases
and then implement formally invoice-allocated repayments and
credit-note/fiscal refund workflows in isolated V8 environments,
followed by cloud sync, licensing, mobile dashboard and AI
milestones as commercial security gates permit.
