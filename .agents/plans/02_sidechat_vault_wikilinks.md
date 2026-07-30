# v0.38.0 Sidechat Vault-Page Wikilinks Master Implementation Plan

Date: 2026-07-30
Status: APPROVED — implementation authorized by the user.

## 1. Objective

An Obsidian Agent Sidechat answer can cite a known existing vault note as
`[[vault/relative/path|label]]`. Clicking the rendered link opens that exact
note, heading, or block. Definition of done:

- all Sidechat providers receive the same grounded-wikilink contract;
- open/pinned context and ContextService evidence retain exact usable paths;
- the model never receives a full-vault filename dump and is told not to invent;
- native Obsidian navigation opens page/heading/block links;
- hidden Curator, PDF, edit-loop, and ordinary external-link behavior does not
  regress.

## 2. Explicit Non-Goals

- Compiling authored note topology into the backend graph (Failure Atlas F9).
- Making hidden Curator nodes appear in native Graph/Backlinks.
- Adding a vault-wide filename inventory, fuzzy note recommender, or new search
  subsystem.
- Auto-linking arbitrary plain text after model generation.
- Adding a setting, DB schema, MCP field, or backend API.
- Changing Quick Query behavior; this slice is the main Obsidian Agent Sidechat.

## 3. Strict Quality Conditions & Release Gates

- Formatter fails closed for stale/unavailable/external/ambiguous locators.
- Markdown `.md` is omitted; non-Markdown suffixes are preserved.
- Block id takes precedence over heading when both exist.
- Every changed behavior has EN then KR guide/spec updates.
- Full `scripts/backend-check {pytest,ruff,mypy}` and plugin Vitest pass.
- Plugin production build and `npm audit` pass.
- Existing Curator/PDF/link/navigation focused tests stay green.
- Real Obsidian smoke opens an existing page, heading, and block from a Sidechat
  answer; at least two provider families are exercised when available.

## 4. Locked Design Decisions (Arena Consensus)

- **Grounding source**: only exact paths already present in included
  open/pinned context, usable ContextService locators, or provider tool results.
- **Prompt owner**: `buildBaseSystemPrompt`, so model selection does not change
  the wikilink rule.
- **Identity preservation**: `contextPromptLabel` converts a safe
  `ContextRef.filePath` into one completed `vault_link_target` literal (and
  leaves external paths plain); `formatCuratorContextPack` retains usable
  locator targets.
- **Navigation owner**: native Obsidian MarkdownRenderer for visible vault notes.
  Existing special handlers remain scoped to hidden Curator nodes, PDFs, and
  explicit block locators.
- **No workaround**: do not regex-rewrite plain answer prose into links.
- **Version**: v0.38.0 Minor because this adds a user-facing answer capability.
- **Schema/API**: unchanged; no migration.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: Failure Atlas F9 compiler topology, whole-vault discovery,
  Graph/Backlinks changes, Quick Query, settings, and backend schema.
- **Stop Conditions**:
  - stop if live Obsidian proves ordinary MarkdownRenderer links are not
    clickable; document the baseline before proposing a custom handler;
  - stop if exact paths require exposing unrelated vault filenames;
  - stop if ContextService needs a public-contract/schema change;
  - stop if three consecutive live provider attempts cannot validate output
    because of authentication/capacity.

## 6. Evidence Ledger

- Detailed ledger:
  `.agents/plans/02_sidechat_vault_wikilinks_evidence.md`.
- Rollback anchor: clean `master` at `979bfe41`.
- Existing v0.17 hidden-link implementation is preserved.
- Existing F9 baseline and 31 focused prompt/link tests pass.
- No uncommitted user changes existed when the branch was created.

## 7. Execution Phases

- **P0 — Characterization And Native-Link Smoke**
  - Add no code.
  - Identify two existing visible Markdown notes with a heading and block.
  - Confirm current native `[[path]]` rendering/click behavior in Sidechat.
  - Verify focused prompt/link tests remain green.

- **P1 — Contract Specification**
  - Update `PLUGIN_SCHEMA.md` and relevant `SYSTEM_BEHAVIOR.md` sections.
  - Update `PLUGIN_GUIDE.md` first, then `PLUGIN_GUIDE_KR.md`.
  - Bump all static spec title lines to v0.38 for the Minor release.
  - Verify docs/spec sync.

- **P2 — Prompt And Locator TDD**
  - Add failing tests for the shared grounded-wikilink instruction,
    `ContextRef.filePath` preservation, valid locator formatting, suffix/
    heading/block handling, and fail-closed statuses.
  - Verify the new tests fail for the intended reasons.

- **P3 — Minimal Implementation**
  - Extend the shared base prompt.
  - Preserve context file paths through the existing prompt-label helper.
  - Add one pure locator-to-wikilink formatter and use it in the existing
    ContextService provider formatter.
  - Do not add generic render-time rewriting.
  - Verify focused Vitest and TypeScript/build.

- **P4 — Cross-Surface Regression**
  - Confirm Curator hidden links, PDF links, explicit block navigation, math copy,
    and edit-loop markers retain existing behavior.
  - Run full plugin tests and backend static/full gates.

- **P5 — Real Obsidian And Provider Smoke**
  - Deploy/reload the built plugin.
  - Ask a question whose grounded context contains a known related note.
  - Validate visible `[[...]]` output and page/heading/block click-through.
  - Exercise one CLI provider and one other available provider; record any
    authentication/capacity gap explicitly.

- **P6 — Minor Release**
  - Bump backend/plugin manifests and lockfile to v0.38.0.
  - Add CHANGELOG, clean ROADMAP/RELAY, record validation, delete completed plan
    artifacts, commit `chore(release): v0.38.0`, push, and open a detailed PR.
