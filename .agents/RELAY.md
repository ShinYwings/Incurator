# RELAY — ACTIVE

## Goal

Implement v0.37.1 Query Provider Failure UX so provider/repair failures preserve
diagnostics and prompt traces while CLI, MCP, and plugin surfaces return concise,
actionable errors instead of raw Rich tracebacks.

## Plan Reference

- Umbrella: `.agents/plans/01_system_stability_overhaul.md`
- Evidence: `.agents/plans/01_roadmap_evidence.md`
- Current branch: `release/v0.37.1`
- Slice plan: `.agents/plans/02_query_provider_failure_ux.md`
- Slice evidence: `.agents/plans/02_query_provider_failure_evidence.md`
- Arena: `.agents/plans/query_provider_failure_arena/`

## Analysis & Reasoning

- This is a backward-compatible bug fix/refactor and targets patch release
  v0.37.1; it adds no public fields or DB schema.
- The known production failure reached retrieval, then Antigravity returned no
  output during JSON repair; `wiki query` exposed an internal traceback.
- The slice must preserve the original provider failure and failed prompt trace,
  while keeping CLI non-zero exit semantics and MCP/plugin parity.
- Arena consensus reuses `LLMError` as the typed expected-provider boundary,
  rejects blank/non-zero provider output consistently, repairs Codex failover,
  recovers PTRs through the existing QTR index, and removes duplicated
  MCP/plugin query orchestration.

## Progress Status

- v0.37.0 merged in PR #98 and the release branch was cleaned.
- v0.37.1 branch was created from synchronized `master`.
- Repository/code/docs/test evidence, prior art, two domain analyses, Arena
  proposal/critique/defense, and the Master Plan are complete.
- A deterministic repair-failure reproduction produced one failed PTR
  (`retry_count=1`) but an empty QTR prompt list and zero synthesis actions.
- Existing prompt/query safety nets pass unchanged (`20 passed`).
- The user approved implementation on 2026-07-30.
- P1 docs-first contract synchronization is in progress; no application code
  has changed yet.

## Critical Context / Blockers

- Do not hide the original provider exception behind a generic repair error.
- Do not add a DB schema or new CLI/MCP/plugin capability in this patch.
- Do not catch arbitrary exceptions as provider failures.
- Keep cancellation, trace-storage outage recovery, malformed provider wire
  shapes, and prompt-provider attribution as separate follow-ups.
- Authored-wikilink validation remains a separate later release.

## Immediate Next Action

Complete P1 docs, then write the P2 provider/prompt regression tests before
changing application logic.
