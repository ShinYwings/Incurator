# v0.5.0 Master Implementation Plan — Agent Edit & Diff Viewer Reliability

Date: 2026-06-11
Status: **DRAFT — awaiting user approval before any code** (Universal Strict Workflow Step 4)
Branch: `feature/agent-edit-diff-reliability` (from `master` @ e268809)
Arena: `.agents/plans/agent_edit_diff_arena/` (00_problem, 01_proposal, 02_critique_redteam, 03_specialists)
Source: `.agents/drafts/agent_edit_diff_viewer.md`

## Strict quality condition
- A correct `ai-agent-edit` proposal that differs from the file only by leading/trailing whitespace or indentation level MUST locate its target and render a diff (no false "could not find").
- The matcher MUST NEVER apply a wrong/ambiguous edit: when ≥2 plausible spans exist, it returns null and the UI shows the honest "couldn't find" message (today's behavior) — silence is safer than corruption.
- "Copy as Markdown" output stays byte-faithful (marker stripping touches rendered HTML only, never stored `msg.content`).
- `npx vitest run -c ./plugin/vitest.config.ts` green; `npx tsc --noEmit` clean. New unit tests for matcher + parser/sanitizer.

## Locked design decisions (Arena Consensus)
1. **Do NOT rewrite `DiffViewer`.** It is already a VSCodium-style in-memory CM6 diff with per-hunk + global accept/reject, `n/total` counter, ↑/↓ + Tab nav, and Y/N/Enter/Esc. Scope = edge-hardening only.
2. **One unified matcher** `plugin/src/utils/editMatch.ts`, tiers: **exact → line-trim → anchored**. **Tier 2 (intra-line whitespace-normalize) REJECTED** (Markdown whitespace hazard, red_teamer V1). Anchored tier (search ≥3 lines) uses minimal non-overlapping spans; >1 candidate → null; reject span > 3× search line count (V3). Replacement always splices the **original** file span, never normalized text.
3. **All three apply/preview paths consume the one matcher** — `applyInlineEdit`, `autoApplyProposals`, and `reviewAssistantEdit` (the latter's whole-file `split/join` is replaced by matcher-driven splice so **preview == apply**, V7).
4. **Immediate diff**: auto-open the DiffViewer once per message, **hard-gated** (single resolvable target that is already the active `MarkdownView` or no focused MarkdownView; never force a new tab). `msg.diffAutoOpened` guard, reset on active-session switch (V2). Pill remains as a re-open affordance.
5. **Artifact off by default**: `DEFAULT_SETTINGS.editArtifactEnabled = false`; relabel setting "(legacy)"; keep helper + setting; never delete existing files (V4, schema_guardian). CHANGELOG tells existing users to toggle off.
6. **Faithful marker stripping**: new pure `stripDanglingEditMarkers` runs on the **rendered** pass only, code-fence-aware, exact marker grammar, own-line only (V5). Strengthen `collapseStreamingEditBlocks` for lone-opener variants.
7. **Scope**: prompt rule (minimal REPLACE; target only the referenced section; never paste the whole answer) in `systemPrompt.ts` + `editableSelectionInstruction`, PLUS a **non-blocking** "large replacement" warning Notice in the apply path as a model-independent net (V6).
8. **Counter always visible**: show `1/1` for single-hunk; arrows hidden/disabled when only one hunk.

## Contracts preserved
- `ai-agent-edit` block grammar (` ```ai-agent-edit filepath="…" ` + `<<<< SEARCH … ==== REPLACE … >>>>`) and the bare-block fallback remain valid; parsing only becomes MORE tolerant.
- `MultiEditProposal` shape, `revertData`/undo, and `EditArtifact*` helper signatures unchanged.
- `00_System/` non-`raw_dir` invariant preserved.

## Evidence Ledger
- **Rollback anchor**: `master` @ `e268809` (PR #16 merge). Branch `feature/agent-edit-diff-reliability` already cut from it.
- **Current repo reality (verified 2026-06-11)**: exact-match apply at chatSidebar.ts ~2789/2814/3040/2618; parser ~3160; review gate ~2552/2581; artifact writer ~3083 (`ARTIFACT_DIR="00_System/Agent Diffs"`, default flag `types.ts:174` = true); DiffViewer hunk UX present (`diffViewer.ts` 263–334); prompt rules `systemPrompt.ts` 33/42/94.
- **Dirty worktree**: only this plan's files + ROADMAP/RELAY edits on the feature branch. No user-uncommitted code in the touched modules.
- **Rollback requirement**: pure plugin/TS, no DB/destructive ops. Revert = `git revert` the PR merge. No migration.

## Execution Phases (TDD + `vitest`/`tsc` green at each gate)

- **P1 — Unified matcher (pure, TDD-first)**
  - New `plugin/src/utils/editMatch.ts` (`findSearchBlock`) + `editMatch.test.ts`.
  - Cases: exact; leading/trailing-trim; indentation-level drift; recurring-anchor → null; >3× span → null; not-found → null; CRLF/`\n`.
  - Gate: `vitest` + `tsc`. (No call-site change yet.)

- **P2 — Wire matcher into all three apply/preview paths**
  - `applyInlineEdit`, `autoApplyProposals`, `reviewAssistantEdit` (replace `indexOf`/`includes`/`split` with `findSearchBlock` splice). Preview == apply.
  - Add non-blocking "large replacement" warning.
  - Gate: `vitest` (extract any newly-pure helper for coverage) + `tsc` + manual reasoning trace in plan notes.

- **P3 — Parser + marker robustness**
  - Extend `extractMultiEditProposals` tolerance; add `stripDanglingEditMarkers` (pure, `textUtils.ts`) on render pass; strengthen `collapseStreamingEditBlocks`.
  - Tests: garbled-closer block, image-then-`>>>>` leak, code-fenced `>>>>` preserved, stored-content-untouched.
  - Gate: `vitest` + `tsc`.

- **P4 — UX: immediate diff + counter + artifact default**
  - Hard-gated auto-open in `renderInlineMultiDiff`; `msg.diffAutoOpened` (+ reset on session switch); pill relabel.
  - `buildToolbar`: always-visible counter.
  - `DEFAULT_SETTINGS.editArtifactEnabled = false` + setting relabel.
  - Gate: `vitest` + `tsc`.

- **P5 — Docs, testbed smoke, version, changelog**
  - Docs: `docs/guides/PLUGIN_GUIDE.md` (+ `_KR`) — agent-edit reliability, immediate diff, artifact now off-by-default, scope rule; `docs/specs/plugin_schema/PLUGIN_SCHEMA.md` if any contract noted. (English first, then KR.)
  - Testbed: `VAULT_ROOT=testbed` — open a Markdown note, run an indentation-drifted edit, confirm diff renders + applies, no `00_System/Agent Diffs/` file.
  - Version bump 0.4.4 → **0.5.0** (`pyproject.toml`, `package.json`, `manifest.json`, lockfile) + `CHANGELOG.md`.
  - Delete this plan + arena folder (Step 11), update `USER_REPORT`/ROADMAP, `chore(release): v0.5.0`, push, PR.

## Open questions for the user (answer before P1)
1. **Version**: this is plugin-behavior-only — bump **Minor `0.5.0`** (recommended, it's a behavior change set) or **Patch `0.4.5`** (treat as a bug-fix bundle)?
2. **Auto-open aggressiveness**: OK to auto-open the diff ONLY when the target is the already-active note / no note focused (never steal a tab)? Or do you want it to always force-open the target file in a new tab when edits arrive?
3. **Artifact default**: OK to flip `00_System/Agent Diffs/` to **off by default** (kept as an opt-in "legacy" toggle), or remove the feature entirely?
