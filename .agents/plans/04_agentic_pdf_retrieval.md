# v0.41.0 Master Implementation Plan — Agentic PDF Retrieval (Local Closed-Set Tools)

Date: 2026-08-03
Status: APPROVED — Arena debate concluded (`agentic_pdf_retrieval_arena/`).
User approved scope, tool model, and CLI handling before planning; then
approved proceeding ("오케이 플랜대로 해").

## 1. Objective

Give the reading assistant an **actuator** for the ToC it already receives, so
that when a cross-reference cannot be resolved deterministically the model
fetches the target page itself and answers from it, instead of telling the user
to navigate there. Definition of done: on both Ask AI popover and Sidechat
(API providers), a question whose target is not covered by the v0.40.3
deterministic resolver — multi-hop, question-dependent, fail-closed residue, or
unnumbered/prose reference — is answered from actually-fetched page text; the
popover's real security properties are unchanged and now locked by behavioral
tests; all gates green; v0.41.0 shipped.

## 2. Explicit Non-Goals

- NOT a new search capability. ToC injection, BM25, caption index, outline
  range fetch, and printed-page mapping already exist and are not rebuilt.
- NO MCP tools added, and NO MCP exposure for the popover under any input.
- NO agentic path for CLI providers (`agy`/Claude/Codex) — locked user
  decision; the `shouldUseCli` branch and v0.23.0 sandbox contract are untouched.
- NO filesystem, vault, or script capability added to any surface.
- NO backend/DB changes; no schema migration.
- `search_pdf_anchor` is NOT a general search surface — it exists only for
  documents proven to have no embedded outline.

## 3. Strict Quality Conditions & Release Gates

- Full plugin `npx vitest run -c ./plugin/vitest.config.ts` green; `npx tsc --noEmit` clean.
- `scripts/backend-check pytest|ruff|mypy` green (backend untouched; CI parity).
- Behavioral security tests (not string assertions) prove: popover gets zero
  MCP tools for every `(hasMcpManager, useCli)` combination, and a popover tool
  array contains only `LOCAL_PDF_TOOL_NAMES`.
- Local tools absent when there is no active PDF, no known positive page count,
  or an unstable document identity.
- Version consistency at `0.41.0` across `backend/pyproject.toml`,
  `plugin/package.json`, `plugin/manifest.json`.
- **MINOR SPEC-LINE SYNC (mandatory)**: all four static spec titles bumped to
  the `v0.41` line — `docs/specs/curator_schema/SCHEMA.md`,
  `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`,
  `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`,
  `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`.
  `backend/tests/test_spec_sync.py` is the hard gate.

## 4. Locked Design Decisions (Arena Consensus)

- **Policy**: `ToolPolicy = "auto" | "none" | "local-only"`;
  `POPOVER_PROFILE.toolPolicy = "local-only"`. Two sibling predicates in
  `messageUtils.ts` (`shouldInjectMcpTools`, `shouldInjectLocalTools`) keep one
  decision point per family. Every consumer switches exhaustively with a
  `never` default so a future value is a compile error.
- **Tool definitions are pure data** in `plugin/src/agent/llm/localPdfTools.ts`:
  `buildLocalPdfTools(ctx)` and `parseLocalPdfToolCall(name, rawArgs, ctx)`.
  Bounds and typed errors live in the parser, not the call site.
- **Emission preconditions (fail closed)**: active PDF **and** known positive
  `pageCount` **and** stable `documentId`, else emit nothing.
  `search_pdf_anchor` additionally requires a document **proven** outline-less;
  "outline not yet parsed" counts as having an outline (withhold).
- **Execution** through a narrow injected `LocalPdfToolRunner` implemented in
  `main.ts` over the existing `fetchActivePdfPage` /
  `getActivePdfDocumentIndex`. No new transport or filesystem reach.
- **Per-request capture**: runner, context, and `documentId` captured into
  local consts at the top of `streamChat`, mirroring the existing `mcpManager`
  capture rationale (`LLMClient.ts:802-805`). A mid-flight identity change
  yields a typed `document_changed` tool error, never a cross-document read.
- **Budgets**: existing `MAX_RECURSION = 5` for rounds, plus a distinct
  `LOCAL_PDF_FETCH_BUDGET` capping total pages fetched per request; exhaustion
  returns a typed error so the model answers with what it has.
- **Prompt boundary**: `boundaryConstraints` gains a `"local-only"` branch
  stating no filesystem / no MCP / no scripts, plus the one read-only PDF
  reader. The prompt string is documentation; the **behavioral** tests are the
  security guarantee.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: CLI agentic path; general search surface; backend anchors;
  any vault/filesystem capability.
- **Stop Conditions**: any change that would grant the popover an MCP tool, or
  weaken a behavioral security test to pass; a DB/public-contract change proving
  necessary; the same gate failing three times without a new diagnosis.

## 6. Evidence Ledger

See `04_agentic_pdf_retrieval_evidence.md` (rollback anchor, worktree state,
current reality, pre/post validation).

## 7. Execution Phases (TDD and CI at each phase)

- **P0 — Baseline**: record green baseline for the touched suites
  (`promptRegistry.test.ts`, `llmClient.test.ts`, `mainSecurity.test.ts`).
- **P1 — Contract (docs-first)**: `PLUGIN_SCHEMA.md` local-tool contract
  (policy values, emission preconditions, typed errors, budgets, popover
  guarantees), then `PLUGIN_GUIDE.md` → faithful `PLUGIN_GUIDE_KR.md`.
- **P2 — DB Schema**: N/A.
- **P3 — Core Logic (TDD)**: failing tests for policy exhaustiveness, the two
  injection predicates, `buildLocalPdfTools` gating, `parseLocalPdfToolCall`
  bounds/typed errors, and the popover behavioral guarantees; then implement
  `localPdfTools.ts` + `promptRegistry.ts` + `messageUtils.ts` until green.
- **P4 — Integration**: `LLMClient.streamChat` capture + dispatch; `main.ts`
  runner; popover/sidechat call sites pass the runner. Verified by loop tests
  covering multi-hop, budget exhaustion, and identity change.
- **P5 — Release Gate**: full vitest + tsc + backend trio; v0.41.0 bump; four
  spec titles to v0.41; CHANGELOG `### Added`/`### Changed`; ROADMAP item 7
  closed; plan deletion; `chore(release): v0.41.0`; push + PR.
