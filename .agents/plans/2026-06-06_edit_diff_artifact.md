# Plan — Item 20b: Persistent Diff Artifact File for Agent Code Edits

> Implemented 2026-06-06 (Claude Code). Mirror of the approved plan
> `~/.claude/plans/sprightly-weaving-breeze.md`, kept here per the CLAUDE.md
> `.agents/plans/` mandate.

## Context

User report **Item 20**: when the AI proposes code/Markdown edits it should not
dump full code into the chat, but write the changes cleanly as a **Diff-format
Markdown artifact file**, separate from the conversation.

First half (already shipped this session): the chat no longer floods with raw
`SEARCH/REPLACE` code (streaming collapses all edit blocks via
`collapseStreamingEditBlocks`; completed edits render as compact
`✏️ <file> · Review Diff` pills against the real file).

This plan added the second half: a persistent `.md` artifact recording proposed
edits as unified-diff blocks.

Confirmed decisions:
- Trigger: settings toggle `editArtifactEnabled`, **default ON**.
- Location: **fixed** `00_System/Agent Diffs/` (outside ingested `raw_dirs`).
- Apply flow: **additive** — keep inline Review-Diff/apply pills + add the
  artifact note and a chat link to it.

## What was implemented

1. **`plugin/src/context/editArtifact.ts`** (new, pure, unit-tested):
   - `ARTIFACT_DIR = "00_System/Agent Diffs"`.
   - `buildEditDiffBlock(search, replace)` → ```` ```diff ```` block
     (search `-`, replace `+`; empty/`<<< NEW FILE >>>` search → all `+`).
   - `buildEditArtifactMarkdown(proposals, meta)` → `agent-diff-artifact`
     frontmatter (`created`, `session`, deduped `files`), heading, one
     `## <filepath>` section per target grouping its diff blocks.
   - `buildEditArtifactFilename(proposals, created)` →
     `YYYY-MM-DD_HHmm_<slug>.md` (UTC; slug = first target basename, sanitized,
     fallback `edits`).
2. **`plugin/src/types.ts`**: `PluginSettings.editArtifactEnabled` (default
   `true`); `ChatMessage.editArtifactPath?`.
3. **`plugin/src/settings.ts`**: "Write edits as diff artifact" toggle.
4. **`plugin/src/ui/chatSidebar.ts`**:
   - `maybeWriteEditArtifact(msg)` — guarded by setting + idempotent via
     `editArtifactPath`; reuses `extractMultiEditProposals`; ensures the folder,
     picks a non-colliding path, `vault.create`. Called in the `sendMessage`
     `finally` before `renderMessages(false)`.
   - `renderEditArtifactPill(contentEl, msg)` — `📝 Open diff artifact` pill,
     additive to `renderInlineMultiDiff`.

## Docs / spec
- `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.3.2.md` — settings field,
  `ChatMessage.editArtifactPath`, edit-block + artifact behavior contract.
- `docs/guides/PLUGIN_GUIDE.md` + `_KR.md` — §3 Inline Edit artifact note.

## Tests
- `editArtifact.test.ts` (9), `settings.test.ts` (+1 default/toggle contract),
  `chatSidebarSource.test.ts` (+1 wiring contract), client test fixtures updated.

## Verification (done)
- `npx tsc --noEmit` clean; `npx vitest run` 272 passed (38 files);
  `npm run build` ok.
- Remaining manual check: testbed run confirming the artifact note appears under
  `00_System/Agent Diffs/` and `wiki add` does not ingest it.
