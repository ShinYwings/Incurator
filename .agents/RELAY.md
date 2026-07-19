# RELAY - v0.36.0 PL-1 Plugin Decomposition

## Goal

Decompose the plugin god-files into cohesive internal modules while preserving
all public imports, persisted data contracts, command construction, and visible
Obsidian behavior.

## Plan Reference

- Master Plan: `.agents/plans/11_pl1_plugin_decomposition.md`
- Evidence Ledger: `.agents/plans/11_roadmap_evidence.md`
- Arena: `.agents/plans/11_pl1_plugin_decomposition_arena/`
- Domain Analyses:
  - `.agents/plans/A_pl1_chat_domain_analysis.md`
  - `.agents/plans/B_pl1_llm_domain_analysis.md`
  - `.agents/plans/C_pl1_pdf_domain_analysis.md`
  - `.agents/plans/D_pl1_entrypoint_domain_analysis.md`

## Analysis & Reasoning

- Branch: `release/v0.36.0`, created fresh from merged `master` at PR #87 merge
  commit `9129908`.
- The v0.36 plan was approved before v0.35 and intentionally deferred; no PL-1
  implementation was mixed into the model-catalogue release.
- Facade-first extraction is locked. Existing imports from `chatSidebar.ts`,
  `llmClient.ts`, and `externalPdfView.ts` must remain valid.
- This is an internal refactor: UI, persistence schemas, backend commands, MCP
  behavior, providers, and models must not change.

## Progress Status

- [x] PR #87 merged and fresh v0.36 branch created from master.
- [x] Refreshed rollback anchors and file sizes from merged commit `9129908`.
- [x] P0 baseline: 65 plugin files / 678 tests; TypeScript and build passed.
- [x] Found stale KR-only absolute-path ExternalPdfView restart documentation;
  queued EN-first parity correction for P1.
- [ ] P0: add facade/export characterization tests.
- [ ] P1: document internal ownership/facade contract.
- [ ] P2: extract LLM client modules incrementally.
- [ ] P3: extract external PDF modules incrementally.
- [ ] P4: extract chat sidebar modules incrementally.
- [ ] P5-P6: entrypoint hygiene, full CI, testbed, release publication.

## Critical Context / Blockers

- No blockers.
- Stop if extraction requires changing persisted DTOs, public behavior, or broad
  `any` casts.
- Source-contract tests must follow the real owning module; inert facade strings
  are forbidden.

## Immediate Next Action

Read the relevant PLUGIN_SCHEMA/guide contracts and domain analyses, refresh P0
evidence, then add failing facade/export characterization tests before moving
implementation code.
