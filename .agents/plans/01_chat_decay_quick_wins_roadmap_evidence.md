# Evidence Ledger — v0.21.0 Chat Decay & Quick Wins

Date: 2026-06-21 | Branch: `feature/chat-decay-quick-wins`

## Rollback Anchor
- HEAD: `0339b63` (chore(project): update roadmap priorities). Worktree CLEAN at
  plan time (`git status --short` empty).
- Plugin-only change set → rollback = `git revert` the feature merge; no DB/vault
  state to restore.

## Current Repository Reality (verified by reading code, not docs)

| Claim | Evidence |
|---|---|
| Recency anchor exists (v0.19.0) | `plugin/src/context/promptRegistry.ts:78` `buildRecencyAnchor`; wired `plugin/src/ui/chatSidebar.ts:1356-1361` gated on `lastUserHasPrimaryContext`. |
| `Cmd+Shift+L` → `line-range` ref | `plugin/main.ts:383` command, `:1607` builds `type:"line-range"` ContextRef. |
| `line-range` is PRIMARY context | `plugin/src/context/chatContextPriority.ts:20`. |
| `line-range` is ALSO an editable ref (contradiction) | `plugin/src/ui/chatSidebar.ts:1175-1181`. |
| `editLoopLikely` latched by prior edit | `plugin/src/ui/chatSidebar.ts:1261-1275` (`priorAnswerOpenedEditLoop`). |
| `<editable_selection>` injected | `plugin/src/ui/chatSidebar.ts:1186-1192`. |
| LaTeX convert reuses main model | `plugin/src/ui/externalPdfView.ts:1294-1316`; no `latexModel` field in `settings.ts`/`types.ts`. |
| `complete()` has no model-override param | `plugin/src/agent/llmClient.ts:962` `complete(messages: LLMMessage[])`; model hardwired `this.settings.model` at `:974,:976,:997,:1003,:1006`. |
| Transient client blocked (auth private) | `plugin/src/agent/llmClient.ts:537` `private auth`. → Item B extends `complete()` signature instead. |
| `streamChat` already has opts pattern to mirror | `plugin/src/agent/llmClient.ts:663-668` `opts?: { toolPolicy?: ToolPolicy }`. |
| Zotero items already recent-first | `plugin/src/ui/zoteroWizardModal.ts:136-140` `prioritizeZoteroItems`. |
| Zotero profile dropdown NOT sorted | `plugin/src/ui/zoteroWizardModal.ts:211-226` iterates stored order; default `:195` `profiles[0]`. |
| Current version | `0.20.0` in `backend/pyproject.toml`, `plugin/package.json`, `plugin/manifest.json` (verified). |

## Draft Correction (important)
The draft `chat_context_decay.md` claims "no dynamic prompt weighting or recency
anchoring exists." This is STALE — v0.19.0 shipped exactly that. The real residual
root cause is a prompt-level contradiction (anchor says "don't edit," editable_
selection + edit_review_loop say "you may edit"), not missing anchoring. Plan is
scoped to the actual residual cause.

## Pre/Post Validation
- PRE: (to be filled at P0) capture current chatSidebar test suite green baseline.
- POST: (to be filled per phase) `vitest` green incl. new tests; spec_sync green;
  manifests + spec titles at `v0.21`.

## Open Investigations Before Coding (P0)
1. RESOLVED (human review): Item B extends `LLMClient.complete()` with
   `opts?: { model?: string }` (TS-only; no transient client). No longer a
   feasibility gate.
2. Single shared Zotero profile persistence/apply point for the `lastUsedAt` stamp.
3. Enumerate existing `complete()` callers to confirm the new optional param is
   backward-compatible.

## Human Review Corrections (2026-06-21)
- **Item A predicate**: removed `&& !priorAnswerOpenedEditLoop`. It disabled
  suppression in the exact reported scenario (prior assistant turn had edits →
  `!priorAnswerOpenedEditLoop` false → bug survives). Predicate is now
  `lastUserHasPrimaryContext && !latestIsMarkdownEditRequest`. Supersedes
  red-team A1 in `chat_decay_quick_wins_arena/02_critique_redteam.md`.
- **Item B**: changed from "defer if client can't override" to "extend the TS
  LLM client" — the no-backend rule applies only to the Python `backend/`.
