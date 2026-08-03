# RELAY — v0.41.0 IMPLEMENTED, PR PENDING MERGE

## Goal

Agentic PDF retrieval for Ask AI and Sidechat (ROADMAP item 7) — shipped as a
local, non-MCP, read-only PDF page reader.

## Plan Reference

- Plan set implemented and deleted per workflow Step 11; recover via `git show`
  on `.agents/plans/04_agentic_pdf_retrieval.md`,
  `04_agentic_pdf_retrieval_evidence.md`, and
  `.agents/plans/agentic_pdf_retrieval_arena/` in this branch's history.
- Branch: `feature/agentic-pdf-retrieval`

## Analysis And Reasoning

- The gap was never ToC knowledge: `formatOutline` already injects the outline
  WITH page numbers into both surfaces. The model could reason its way to
  "Appendix 4, p.617" but had no actuator, so it told the user to navigate.
- Scope narrowed during planning after reading the code: `fetch_pdf_page` is
  first class; `search_pdf_anchor` is exposed ONLY for documents proven
  outline-less (BM25 + caption index + outline resolution already run
  deterministically, so a model-driven search is otherwise redundant).
- User decisions locked before planning: local-only closed toolset for the
  popover (not MCP), and CLI providers excluded from agentic recovery.
- Arena red-team hardening: fail closed without active PDF / known page count /
  stable document identity; per-request page-fetch budget separate from the
  recursion limit; typed tool errors instead of thrown turns; document identity
  pinned per request so a mid-flight swap cannot be read across.

## Progress Status

- Implemented: `plugin/src/agent/llm/localPdfTools.ts` (pure defs + gating +
  bounds), `promptRegistry.ts` (`ToolPolicy` gains `local-only`, exhaustive
  switches), `messageUtils.ts` (`shouldInjectLocalTools` beside
  `shouldInjectMcpTools`), `LLMClient.ts` (per-request capture + dispatch +
  `runLocalPdfTool`), `main.ts` (runner over existing page fetch/index).
- 36 new tests; full plugin suite 834 green; `tsc --noEmit` clean; backend
  ruff/mypy green; `test_spec_sync.py` green after the minor bump.
- Docs: PLUGIN_SCHEMA §13.7 (new) + §13.5 amendment; PLUGIN_GUIDE EN/KR.
- Version 0.41.0 across three manifests; all four spec titles on the v0.41
  line; CHANGELOG `### Added` / `### Changed`.

## Critical Context / Blockers

- The popover's zero-MCP guarantee is now enforced by BEHAVIORAL tests, not by
  the prompt string. Do not weaken `shouldInjectMcpTools("local-only", …)`
  tests — that assertion is the security contract.

## Immediate Next Action

Human: review and merge the PR for `feature/agentic-pdf-retrieval`. Next agent
session then starts the deep system-defect audit (documented scenario
conformance + regression-audit P9 folded into one sweep), whose findings feed
USER_REPORT and then ROADMAP items 1–2.
