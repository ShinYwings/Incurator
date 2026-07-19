# RELAY - Hotfix v0.34.1 Ready; v0.35.0 Model Refresh Planned

## Goal

Stop the Obsidian Knowledge Sync loop introduced/persisting in v0.34, then
refresh the Claude Code and Codex CLI model catalogue while prioritizing
code/document parity and model-selection bugs.

## Plan Reference

- Hotfix PR: https://github.com/ShinYwings/Incurator/pull/86
- v0.35 Master Plan: `.agents/plans/12_model_catalogue_refresh.md`
- v0.35 Evidence Ledger: `.agents/plans/12_roadmap_evidence.md`
- v0.35 Arena: `.agents/plans/12_model_catalogue_refresh_arena/`
- v0.35 Domain Analyses:
  - `.agents/plans/A_model_catalogue_domain_analysis.md`
  - `.agents/plans/B_model_effort_domain_analysis.md`
- Deferred PL-1 Plan (v0.36.0):
  `.agents/plans/11_pl1_plugin_decomposition.md`

## Analysis & Reasoning

- Hotfix branch: `hotfix/v0.34.1-knowledge-sync-loop`, head `1a71771`.
- Hotfix root causes:
  1. immutable/composite-PK snapshot rows were counted as updated on every new
     full-snapshot export even when content was equal;
  2. `--dry-run` ignored recorded peer export IDs;
  3. the plugin watcher did not exclude its known self snapshot.
- PR #86 is open, non-draft, mergeable, and all GitHub CI checks pass.
- Read-only production verification changed `would_export` from true with 6,650
  false updates to false with zero imports/updates after applying the hotfix
  logic. Production state was not mutated.
- Full hotfix validation passed: 1,214 backend tests, ruff, mypy, 670 plugin
  tests, production plugin build, spec/version sync, testbed ingest/reindex, and
  external Zotero-style Reference Mode without PDF hard-copying.
- Installed Codex cache exposes Sol/Terra/Luna/GPT-5.5 at an effective 272K
  context. Sol/Terra support `max`/`ultra`; Luna supports `max`.
- Installed Claude Code supports current Fable/Opus/Sonnet/Haiku aliases. The
  bounded full-ID update adds Fable 5 and Opus 4.8 while retaining verified
  Sonnet 4.6 and Haiku 4.5.
- Model triage found additional relevant mismatches: stale Codex effort unions,
  fictional `supportsThinking` in the plugin spec, divergent UI effort reset
  behavior, and unconditional effort flags for no-effort models.

## Progress Status

- [x] Reproduced the v0.34 Knowledge Sync loop against production state.
- [x] Implemented the v0.34.1 backend/plugin root-cause fix with docs/tests.
- [x] Completed full local CI, testbed, and Reference Mode validation.
- [x] Pushed v0.34.1 and opened ready-for-review PR #86; GitHub CI passed.
- [x] Ran the v0.35 model-refresh Arena and authored plan/evidence artifacts.
- [ ] Human merge of PR #86.
- [ ] Human approval of `.agents/plans/12_model_catalogue_refresh.md`.
- [ ] Update `release/v0.35.0` from merged master and execute P0-P6.

## Critical Context / Blockers

- Do not implement v0.35 until PR #86 is merged; release branches must be based
  on master and the sync regression must not be omitted from the next minor.
- Preserve the pre-existing user-owned `plugin/package-lock.json` version edit
  in the v0.35 worktree.
- Do not mix PL-1 extraction into v0.35. Its plan explicitly excludes
  provider/model behavior and is deferred to v0.36.0.
- Use installed CLI/cache values for executable catalogue context/effort, not
  broader API-only availability.

## Immediate Next Action

Merge PR #86 and approve `.agents/plans/12_model_catalogue_refresh.md`. Then
update `release/v0.35.0` from the merged master, revalidate the CLI catalogue,
and start P0 characterization tests.
