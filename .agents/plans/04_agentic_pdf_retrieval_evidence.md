# v0.41.0 Evidence Ledger — Agentic PDF Retrieval

Date: 2026-08-03

## Rollback Anchor

- Branch: `feature/agentic-pdf-retrieval` (from `master`)
- Anchor commit: `295e33fb6746f4f83a9825a0f74b2eaa01b77b45`
  (`chore(agents): reset relay after v0.40.3`)
- Rollback: `git checkout master` + delete branch. No DB/schema surface touched.

## Current Dirty Worktree (pre-plan)

- Clean at branch creation; only `.agents/plans/` additions belong to this plan.

## Current Repository Reality (fact-checked 2026-08-03)

- Versions agree at `0.40.3` (`backend/pyproject.toml:3`,
  `plugin/package.json:3`, `plugin/manifest.json:4`). Target: `0.41.0`.
- `ToolPolicy = "auto" | "none"` — `plugin/src/context/promptRegistry.ts:16`.
- `POPOVER_PROFILE.toolPolicy = "none"` — `promptRegistry.ts:37-41`.
- `boundaryConstraints` "none" branch returns "You have NO tools and NO
  filesystem access…" — `promptRegistry.ts:47-55`.
- Isolation locked by string assertion — `promptRegistry.test.ts:12`
  (`expect(text).toContain("NO tools and NO filesystem access")`). This must be
  replaced by behavioral guarantees per Arena consensus item 2.
- Single injection decision point — `messageUtils.ts:9-17`, consumed at
  `LLMClient.ts:811`.
- Tools sourced only from `mcpManager.getAllTools()` — `LLMClient.ts:823`.
- Tool loop `MAX_RECURSION = 5`, last turn drops tools — `LLMClient.ts:828-835`.
- `mcpManager` captured to a local const to avoid mid-flight drift —
  `LLMClient.ts:802-805` (precedent for the runner capture).
- Page fetch already exists — `plugin/main.ts:1759 fetchActivePdfPage`
  (backend `getPdfContext` first, PDF.js fallback).
- Document index accessors — `plugin/main.ts:1786-1795`.
- ToC already injected WITH page numbers, ≤80 entries —
  `providerContextFormat.ts:35-44`, used by `quickQueryContext.ts:97-101`.
- Popover call sites pass `toolPolicy: "none"` —
  `quickQueryPopover.ts:517,522`.

## Pre-Validation (P0 baseline)

- To record before P3: full plugin vitest + `tsc --noEmit` at the anchor.

## Post-Validation (P5 gate)

- Full plugin vitest + tsc green; `scripts/backend-check pytest|ruff|mypy`
  green; three manifests at `0.41.0`; four spec titles on the `v0.41` line;
  CHANGELOG entry present; `test_spec_sync.py` green.
