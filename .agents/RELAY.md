# RELAY - v0.36.0 PL-1 Release

## Goal

Decompose the plugin god-files into cohesive internal modules while preserving
all public imports, persisted data contracts, command construction, and visible
Obsidian behavior.

## Plan Reference

- Implemented plan artifacts are deleted from the active workspace per project
  workflow; use Git history on `.agents/plans/` for the v0.36.0 PL-1 plan,
  Arena, domain analyses, and evidence ledger.

## Analysis & Reasoning

- Branch: `release/v0.36.0`, created fresh from merged `master` at PR #87 merge
  commit `9129908`.
- The v0.36 plan was approved before v0.35 and intentionally deferred; no PL-1
  implementation was mixed into the model-catalogue release.
- Facade-first extraction is locked. Existing imports from `chatSidebar.ts`,
  `llmClient.ts`, and `externalPdfView.ts` must remain valid.
- This is an internal refactor. UI, persistence schemas, backend commands, MCP
  behavior, providers, and models remain unchanged.
- Original import paths are one-line facades over owners in `ui/chat/`,
  `agent/llm/`, and `ui/pdf/`; `main.ts` required no import change.

## Progress Status

- [x] PR #87 merged and fresh v0.36 branch created from master.
- [x] Refreshed rollback anchors and file sizes from merged commit `9129908`.
- [x] P0 baseline: 65 plugin files / 678 tests; TypeScript and build passed.
- [x] Found stale KR-only absolute-path ExternalPdfView restart documentation;
  queued EN-first parity correction for P1.
- [x] P0: facade/export characterization tests added.
- [x] P1: internal ownership/facade contract and EN/KR guide parity documented.
- [x] P2: LLM client moved behind stable facade; pure message helpers extracted.
- [x] P3: external PDF view moved behind stable facade.
- [x] P4: chat sidebar moved behind stable facade.
- [x] P5: entrypoint verified unchanged against stable facades.
- [x] P6: 1218 backend tests, 683 plugin tests, Ruff, Mypy, TypeScript, build,
  and `gaussian_splatting` testbed passed. Autosync then dry-run was quiescent.
- [x] Branch pushed and PR #88 opened.
- [x] GitHub Backend Tests, Plugin Tests, and Version Consistency passed; PR #88
  marked ready for review.
- [x] Addressed all six lifecycle review findings: request-local abort ownership,
  guarded controller cleanup, PDF close render invalidation, optional child
  stdin, and missing MCP args. Plugin 688-test, TypeScript, build, and spec/docs
  checks passed locally; follow-up pushed to PR #88 for GitHub validation.
- [ ] Await human review/merge and address any actionable feedback on the same
  branch.

## Critical Context / Blockers

- No blockers.
- Stop if extraction requires changing persisted DTOs, public behavior, or broad
  `any` casts.
- Source-contract tests must follow the real owning module; inert facade strings
  are forbidden.

## Immediate Next Action

Await follow-up CI and human review/merge of ready PR #88. Address any new
actionable findings on the same branch.
