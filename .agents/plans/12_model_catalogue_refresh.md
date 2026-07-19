# v0.35.0 Master Implementation Plan

Date: 2026-07-19
Status: APPROVED - Arena debate concluded; v0.34.1 merged; implementation active.

## 1. Objective

Refresh the Claude Code and Codex CLI model catalogue and make the backend,
plugin, specs, and EN/KR guides enforce one executable model/effort contract.

Definition of done:

- Model dropdowns contain only the locked, CLI-verified Claude/Codex entries.
- Backend defaults and plugin defaults agree with the catalogue.
- Codex `max`/`ultra` and Claude model-specific effort support work end to end.
- Models with no effort dimension never receive an effort CLI argument.
- Settings, sidebar, dashboard, and load-time migration normalize effort using
  the same rule.
- Every model/effort statement in static specs and paired guides matches code.

## 2. Explicit Non-Goals

- No PL-1 god-file decomposition; it moves to v0.36.0.
- No provider authentication or billing changes.
- No API-key OpenAI/Anthropic backend.
- No speculative/limited-access models absent from the installed CLI contract.
- No tokenizer integration or broad context-packing redesign.
- No DB schema or persisted session format migration.

## 3. Strict Quality Conditions & Release Gates

- `models.json` remains the only model-list source.
- Provider model IDs are unique; defaults equal an available provider entry;
  every non-empty `default_effort` belongs to that model's `efforts`.
- Exact command vectors prove `ultra`, `max`, and empty-effort behavior.
- All three plugin model-selection surfaces and load migration share the same
  tested effort normalizer.
- Update English specs/guides first, then matching Korean guides.
- Full backend pytest/ruff/mypy, plugin vitest/TypeScript/build, version/spec
  consistency, testbed smoke, and `git diff --check` must pass.

## 4. Locked Design Decisions (Arena Consensus)

- Codex catalogue/order: `gpt-5.6-sol`, `gpt-5.6-terra`,
  `gpt-5.6-luna`, `gpt-5.5`; all use the CLI-effective 272K context.
- Codex default: `gpt-5.6-sol`, effort `low`.
- Claude catalogue/order: `claude-sonnet-4-6`, `claude-fable-5`,
  `claude-opus-4-8`, `claude-haiku-4-5`.
- Claude default: Sonnet 4.6, effort `high`. Fable 5 and Opus 4.8 default to
  `high`; Haiku has no efforts/default.
- A user-initiated model change resets to the new model's declared default.
  Load-time migration preserves a still-supported saved value, otherwise falls
  back to the declared default; a no-effort model clears the slot.
- `ModelOption.efforts`/`defaultEffort` are authoritative. Remove the fictional
  required `supportsThinking` field from the static plugin contract.
- `context_window` means provider/CLI token capacity. The current plugin
  per-document truncation remains a conservative character guard and must be
  documented as such until token-aware packing is separately designed.
- Merge v0.34.1 before implementing or rebasing the release branch.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: Antigravity/DeepSeek/Ollama catalogue refresh, PL-1 module
  moves, prompt redesign, token counter UI.
- **Stop Conditions**:
  - Stop if PR #86 is not merged or its merge introduces conflicts in model
    surfaces.
  - Stop if current CLI discovery no longer matches the locked model tables.
  - Stop if supporting a model requires changing authentication or persistence
    schema.
  - Stop if no-effort normalization cannot be added without touching unrelated
    chat/session behavior.

## 6. Evidence Ledger

- **Current Repository & Runtime Reality**: See
  `.agents/plans/12_roadmap_evidence.md`.
- **Current Dirty Worktree**: Preserve the pre-existing
  `plugin/package-lock.json` version edit.
- **Rollback Requirements**: Commit docs/tests before runtime code and keep the
  model contract change separate from PL-1.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 - Rebase and Measured Baseline**
  - Merge/update from v0.34.1 master only after PR #86 lands.
  - Recheck installed CLI versions/cache and capture backend/plugin baselines.
  - Verify: clean scoped diff plus preserved lockfile edit.

- **P1 - Contract Specification**
  - Update `SYSTEM_BEHAVIOR.md` and `PLUGIN_SCHEMA.md` for exact models,
    per-model efforts, `max`/`ultra`, optional effort fields, migration rules,
    and conservative character clipping.
  - Update USER/PLUGIN English guides, then `_KR.md` counterparts.
  - Verify: document parity searches and spec-sync tests after final bump.

- **P2 - Failing Catalogue and Command Tests**
  - Update backend catalogue/default/CLI command tests.
  - Add plugin catalogue, effort normalization, model migration, and command
    construction tests.
  - Include backend Claude text/image effort parity coverage.
  - Verify: new tests fail for the expected stale behavior.

- **P3 - Canonical Backend Catalogue**
  - Update `models.json`, constants, CLI examples/comments, and backend command
    construction only as required by tests.
  - Verify: focused backend tests plus `scripts/backend-check ruff`.

- **P4 - Plugin Effort Consistency**
  - Expand effort types, implement the pure normalizer, use it in settings,
    sidebar, dashboard, and load migration, and omit empty effort flags.
  - Keep catalogue-driven UI rendering; do not introduce hardcoded lists.
  - Verify: focused plugin tests, full vitest, and TypeScript check.

- **P5 - Integration and Testbed**
  - Build the production plugin and run the active custom testbed smoke.
  - Confirm config/provider commands serialize the selected model/effort and
    that a no-effort Claude model produces no unsupported flag.

- **P6 - Release Hygiene**
  - Run full local CI.
  - Bump backend/plugin manifests to `0.35.0`, update all four static spec titles
    to v0.35, and write `CHANGELOG.md`.
  - Update roadmap/relay, delete implemented plan artifacts after their history
    is committed, create `chore(release): v0.35.0`, push, and open the PR.
