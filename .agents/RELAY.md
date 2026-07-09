# RELAY - Active Milestone: v0.35.0 (PL-1 Plugin God-file Decomposition)

## Goal

Decompose plugin god-files into cohesive modules without changing user-visible
behavior, Obsidian lifecycle hooks, backend command contracts, provider
semantics, chat/session persistence, or external PDF state persistence.

Target files:

- `plugin/src/ui/chatSidebar.ts`
- `plugin/src/agent/llmClient.ts`
- `plugin/src/ui/externalPdfView.ts`
- `plugin/main.ts` only for import/coordinator hygiene after the three primary
  files are stable.

## Plan Reference

- Parent Master Plan: `.agents/plans/01_system_stability_overhaul.md`
- PM Draft Briefing: `.agents/drafts/11_pl1_plugin_decomposition.md`
- Target Implementation Plan: `.agents/plans/11_pl1_plugin_decomposition.md`
  (DRAFT; awaiting human approval before implementation)
- Evidence Ledger: `.agents/plans/11_roadmap_evidence.md`
- Domain Analyses:
  - `.agents/plans/A_pl1_chat_domain_analysis.md`
  - `.agents/plans/B_pl1_llm_domain_analysis.md`
  - `.agents/plans/C_pl1_pdf_domain_analysis.md`
  - `.agents/plans/D_pl1_entrypoint_domain_analysis.md`
- Arena Folder: `.agents/plans/11_pl1_plugin_decomposition_arena/`

## Analysis & Reasoning

- Current branch: `release/v0.35.0`.
- PR #85 / v0.34.0 merged into `master`; this branch starts from the post-merge
  IDLE reset.
- `USER_REPORT.md` is empty; no urgent inbox item supersedes PL-1.
- Baseline target file sizes:
  - `plugin/main.ts`: 2,224 LOC
  - `plugin/src/ui/chatSidebar.ts`: 4,895 LOC
  - `plugin/src/agent/llmClient.ts`: 2,382 LOC
  - `plugin/src/ui/externalPdfView.ts`: 1,909 LOC
- Baseline plugin tests passed on 2026-07-09:
  `npx vitest run -c ./plugin/vitest.config.ts` -> 65 files, 669 tests.
- Existing source-contract tests read `chatSidebar.ts`, `llmClient.ts`, and
  `externalPdfView.ts` directly; implementation must move those assertions to
  new owner modules instead of satisfying them with inert facade comments.

## Progress Status

- [x] Confirmed v0.34.0 PR #85 is merged.
- [x] Confirmed `release/v0.35.0` branch exists on top of post-merge master.
- [x] Read PL-1 draft briefing.
- [x] Ran Arena planning workflow and authored draft plan artifacts.
- [x] Updated roadmap with plan/evidence references.
- [ ] Human approval of `.agents/plans/11_pl1_plugin_decomposition.md`.
- [ ] Implementation through P0-P6 after approval.

## Critical Context / Blockers

- Do not implement until the PL-1 plan is approved.
- This is a structural TypeScript refactor only. UI, persistence, backend
  command envelopes, provider behavior, MCP behavior, and view type strings must
  remain unchanged.
- Keep current public import paths as facades:
  - `src/ui/chatSidebar`
  - `src/agent/llmClient`
  - `src/ui/externalPdfView`
- Avoid circular imports with one-way type/helper ownership.

## Immediate Next Action

Review `.agents/plans/11_pl1_plugin_decomposition.md`. If approved, start P0
characterization tests before moving code.
