---
name: velopos-development
description: Safely continue VeloPOS 8.0 Windows POS engineering on develop-v8 from the verified GitHub project history, parity matrix, release gates and evidence ledger. Use for VeloPOS bug fixes, feature integration, regression analysis, Windows milestone preparation and progress updates.
---

# VeloPOS 8.0 development continuation

This skill is for the repository `rajithagaspeus-eng/VeloPOS-8.0`, branch
`develop-v8`. Follow root `AGENTS.md` first. Never infer full conversation
history from memory and never imply this skill can keep working after a session
ends.

## Enter a new session

1. Confirm current working directory is the repository root containing
   `AGENTS.md`, `run_v8_checks.py` and `velopos_qt/`.
2. Check `git branch --show-current` == `develop-v8` and review
   `git status --short` without discarding user changes. If wrong branch,
   stop before modifying anything.
3. Read, in order:
   - `docs/V8_CONSOLIDATED_PROJECT_HISTORY.md`
   - `docs/V8_FEATURE_PARITY_MATRIX.md`
   - `docs/V8_VERIFIED_EVIDENCE_LEDGER.md`
   - `docs/V8_MISSING_WORK_CHECKLIST.md`
   - `docs/V8_MASTER_ROADMAP.md`
   - `docs/V8_COMMERCIAL_RELEASE_GATES.md`
   - latest relevant `docs/V8_AUTONOMOUS_PROGRESS.md` entries
4. Check latest local and remote commit identity if Git remote access exists.
   Never silently overwrite divergent local work.
5. Identify the highest-priority safe integrated slice. Validate against
   existing code and actual tests rather than trusting old descriptions.

## Work cycle

- Plan briefly, then inspect target files and related tests.
- Make cohesive code changes in a disposable V8/test context. Preserve V7,
  main and all real data. Do not introduce Supabase/cloud requirements.
- Add regression tests and execute what the environment permits; never call
  a test written or a CI workflow triggered an executed PASS.
- Keep real checkout/payment/refund/stock posting hard-disabled until Gates
  A/B are independently accepted and the owner approves release. Preserve
  fail-closed service boundaries.
- Update the evidence ledger and checklist only after meaningful evidence;
  link exact SHA, environment, test counts, skips, failure details and logs.
- If the user authorizes commits, stage only intended files and commit to
  `develop-v8`; never push/merge `main` or force-push.
- Summarize completed, remaining and blocked work in Sinhala; finish
  "Continue කරන්නද?"

## Recovery when history is incomplete

The GitHub master documents and verified repository are the continuity source;
don't guess earlier task state. Show missing evidence explicitly. Test count,
commit count or subjective percentages are not proof of commercial readiness.
The last consolidated documents started at code snapshot
`3ed6d8f7866f95111d221f4d309938f1fc5fb4d5`; check HEAD, which can advance.

## Non-goals

This skill does NOT provide unattended background execution, ChatGPT-wide
persistent memory, production transaction authorization, privileged Windows
hardware access, paid licenses or Supabase integration.
