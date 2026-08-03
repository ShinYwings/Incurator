# Briefing: Agentic PDF Retrieval for Ask AI and Sidechat

Date: 2026-08-03 | Author: Main Agent (Claude) | Source: ROADMAP item 7 (deferred from v0.40.3)

## 1. What already exists (verified in code — do NOT rebuild)

A reviewer's first instinct is "isn't ToC navigation already there?" It is. The
following all ship today and are **not** the gap:

- **ToC is already injected into the prompt, with page numbers.**
  `formatOutline` (`plugin/src/context/providerContextFormat.ts:35-44`) emits
  `- Appendix 4 Matrix Properties p.617` lines, up to 80 entries, into both the
  popover background block (`quickQueryContext.ts:97-101`) and sidechat.
- **Deterministic cross-reference resolution** (hardened in v0.40.3):
  printed→physical page mapping, outline-bounded section range fetch
  (`outlineRangeForNumber`), caption/definition index, BM25 over seen pages,
  adjacent-equation probing, and fail-closed verification.
- **A page fetch capability**: `main.ts:1759 fetchActivePdfPage(pageNum)` —
  backend `getPdfContext` first, PDF.js viewer fallback.
- **A document BM25 index**: `getActivePdfDocumentIndex()` /
  `getActivePdfDocumentId()`.

## 2. The actual gap: knowledge without actuation

The model can already read the ToC and reason "that's Appendix 4, around
p.617". It has **no mechanism to act on that conclusion**. Its only move is to
tell the user to navigate there — the precise behavior the user rejected
("Ask AI 기능은 이런 것들을 사용자가 페이지를 바꾸지 않고서도 확인하기 위해
만든 목적"). The missing piece is an *actuator*, not a new search capability.

## 3. Residual cases the deterministic path cannot cover

1. **Multi-hop.** Fetched page 599 says "see Result A4.2 for the general
   case". The resolver already ran; it does not follow the second hop.
2. **Question-dependent targets.** The popover resolves from
   `capturedSelection` **before the question is known**
   (`quickQueryPopover.ts:472-488`). A question like "이 증명에서 쓴 SVD
   성질은 어디서 유도돼?" carries the real target, and the selection has no
   pointer token at all.
3. **Fail-closed residue.** v0.40.3 deliberately made resolution failure more
   common (correctly preferring no context to wrong context). Those cases now
   produce "could not locate" with no recovery path.
4. **Unnumbered / prose references.** "앞 장에서 보인 것처럼", "the Jacobi
   algorithm" — no pattern in the closed regex table matches.

## 4. Locked user decisions (asked and answered before planning)

- **Popover tool model**: local-only closed toolset executed by the plugin.
  Zero MCP exposure, zero filesystem/vault/script access. Requires refining
  the v0.19.0 isolation contract wording from "no tools at all" to "no MCP
  tools, no filesystem, no scripts" and updating its locking test.
- **CLI providers** (Antigravity `agy`, Claude, Codex): excluded from agentic
  recovery. They keep the v0.40.3 deterministic path only, so the
  `shouldUseCli` branch and the v0.23.0 sandbox contract stay untouched.

## 5. Scope narrowing (decided during briefing)

The originating draft proposed two tools. Code review of what already exists
narrows this:

- **`fetch_pdf_page(page_number)` — first class.** It is the actuator for all
  four residual cases and for the ToC the model already holds.
- **`search_pdf_anchor(query)` — conditional.** BM25, the caption index, and
  outline resolution already run deterministically, so a model-driven search
  is redundant **except when the PDF has no embedded outline** (common for
  arXiv papers; the test corpus uses `outline: []` frequently). Without a ToC
  the model has no map and cannot know which page to fetch. Expose it only as
  the no-map fallback, never as a general search surface.

## 6. Hard constraints

- Tool injection has exactly one decision point today:
  `shouldInjectMcpTools(toolPolicy, hasMcpManager, useCli)`
  (`plugin/src/agent/llm/messageUtils.ts:9-17`), consumed at
  `LLMClient.ts:811`. Any new path must not create a second, divergent one.
- Tools currently come **only** from `mcpManager.getAllTools()`
  (`LLMClient.ts:823`). There is no local-tool concept to extend.
- The isolation wording is locked by a test:
  `promptRegistry.test.ts:12` asserts
  `boundaryConstraints(POPOVER_PROFILE)` contains
  `"NO tools and NO filesystem access"`.
- The existing tool loop is bounded at `MAX_RECURSION = 5`
  (`LLMClient.ts:828`) and drops tools on the last turn to force an answer.
- Minor bump (v0.40.3 → v0.41.0) ⇒ **all four static spec titles must be
  bumped to the v0.41 line** (`backend/tests/test_spec_sync.py` hard-asserts
  this).
