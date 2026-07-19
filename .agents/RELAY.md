# RELAY - Active Milestone: v0.35.0 Model Catalogue Refresh

## Goal

Refresh the Claude Code and Codex CLI model catalogue and eliminate the
code/spec/UI mismatches exposed by model-specific effort handling.

## Plan Reference

- Master Plan: `.agents/plans/12_model_catalogue_refresh.md`
- Evidence Ledger: `.agents/plans/12_roadmap_evidence.md`
- Arena: `.agents/plans/12_model_catalogue_refresh_arena/`
- Domain Analyses:
  - `.agents/plans/A_model_catalogue_domain_analysis.md`
  - `.agents/plans/B_model_effort_domain_analysis.md`
- Deferred PL-1 Plan (v0.36.0):
  `.agents/plans/11_pl1_plugin_decomposition.md`

## Analysis & Reasoning

- Branch: `release/v0.35.0`.
- PR #86 merged to `master` at `34636fd`; its Knowledge Sync regression fix and
  review follow-ups are now the release baseline.
- The user's "merged. next" authorizes the approved v0.35 plan to enter
  implementation.
- Installed Codex CLI/cache exposes Sol/Terra/Luna/GPT-5.5 at an effective 272K
  context. Sol/Terra support `max`/`ultra`; Luna supports `max`.
- Installed Claude Code supports current Fable/Opus/Sonnet/Haiku aliases. The
  bounded full-ID update adds Fable 5 and Opus 4.8 while retaining verified
  Sonnet 4.6 and Haiku 4.5.
- Relevant bugs in scope: stale Codex effort unions; fictional
  `supportsThinking` in the plugin spec; divergent settings/sidebar/dashboard
  effort reset rules; unconditional effort flags for no-effort models; backend
  Claude text/image effort parity.
- The pre-existing user-owned `plugin/package-lock.json` version edit was saved
  in a named stash before merging master and must be restored immediately after
  the merge commit.

## Progress Status

- [x] v0.34.1 hotfix merged to master.
- [x] v0.35 Arena/master plan authored and approved.
- [ ] Complete master merge and restore the user-owned lockfile edit.
- [ ] P0: revalidate CLI catalogue and capture test baselines.
- [ ] P1: update specs and EN/KR guides.
- [ ] P2: write failing model/effort regression tests.
- [ ] P3-P4: implement backend catalogue and plugin effort consistency.
- [ ] P5-P6: full CI, testbed, version/spec sync, release PR.

## Critical Context / Blockers

- Do not mix PL-1 module extraction into v0.35; it is deferred to v0.36.
- Use installed CLI/cache values for executable Codex context/effort, not
  broader API-only availability.
- Preserve the user-owned package-lock change through the branch update and
  reconcile it deliberately in the v0.35 version bump.
- Stop and re-plan if live CLI discovery no longer matches the locked tables.

## Immediate Next Action

Finish the master merge, restore the named lockfile stash, revalidate the live
CLI catalogue, and capture P0 backend/plugin baselines before editing behavior.
