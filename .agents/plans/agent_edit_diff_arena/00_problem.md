# 00 — Problem Briefing: Agent Edit & Diff Viewer Reliability

Date: 2026-06-11 | Target: v0.5.0 | Branch: `feature/agent-edit-diff-reliability`
Source item: `.agents/drafts/agent_edit_diff_viewer.md` (ROADMAP To-Do #1, was #2)

## The user-reported pain (verbatim symptoms preserved)
1. `ai-agent-edit` "keeps failing SEARCH matching" → **no diff appears in the `.md` file**, no hover.
2. Inserting an image (`![alt](image.png)`) produces a stray heading + `>>>>` lines in rendered output.
3. **Edit-scope bug**: asked to add "section 4 of the chat answer" to Overall note 1.3; the agent appended the **entire** answer. Varies by model strength (weak model → no diff; strong model → diff but wrong scope).
4. Diff UX: "can't tell how many edits (e.g. 1/8), no moving arrows to the change".
5. Diff is gated behind a **"Review Diff"** button — wants it to render immediately.
6. Diffs are written into `00_System/Agent Diffs/` — wants this stopped; benchmark VSCodium's in-memory diff view.

## Repository reality (Evidence — what the code ACTUALLY does today)
Investigated 2026-06-11 on `master` @ e268809.

- **SEARCH matching is exact-only**, in three independent places:
  - `applyInlineEdit` (chatSidebar.ts ~2789/2814): `content.indexOf(prop.search)` / `content.includes(prop.search)`.
  - `reviewAssistantEdit` (chatSidebar.ts ~3040): `modifiedFullText.split(proposal.search)`.
  - `autoApplyProposals` (chatSidebar.ts ~2618): same pattern.
  → Any indentation/whitespace/newline drift, or LLM-normalized search text, fails with "Could not find the exact SEARCH block". **This is the headline bug and the upstream cause of symptoms 1 and 4** (no diff ever renders, so there is nothing to count or navigate).
- **Parsing** (`extractMultiEditProposals`, chatSidebar.ts ~3160): fenced ```` ```ai-agent-edit filepath="…" ```` with `<<<< SEARCH … ==== REPLACE … >>>>`, plus a bare-block fallback. Trailing-newline trimming only. Brittle to marker variations → leaks `>>>>` (symptom 2).
- **Streaming collapse** (`textUtils.collapseStreamingEditBlocks`): cuts from the first `` ```ai-agent-edit `` or `<<<< SEARCH`. Does NOT catch a bare/garbled `>>>>` closing marker if the opener was malformed → `>>>>` can survive into render.
- **Review gate**: `renderInlineMultiDiff` (chatSidebar.ts ~2552) renders a pill with a "🔍 Review Diff" button; the diff only opens on click via `reviewAssistantEdit` → `DiffViewer.show()`. (symptom 5)
- **On-disk artifact**: `maybeWriteEditArtifact` (chatSidebar.ts ~3083) writes a `.md` to `ARTIFACT_DIR = "00_System/Agent Diffs"` whenever `settings.editArtifactEnabled` (default **true**), plus `renderEditArtifactPill`. The helpers live in `context/editArtifact.ts`. (symptom 6)
- **DiffViewer is ALREADY an in-memory, VSCodium-style diff** (`ui/diffViewer.ts`, 530 lines): CodeMirror 6 decorations + `RemovedWidget`, a floating toolbar with **per-hunk Accept/Reject, Accept-All/Reject-All, an `n/total` hunk counter, ↑/↓ + Tab/Shift+Tab navigation, and Y/N/Enter/Esc shortcuts**. It writes NO file. → Symptom 4's counter/arrows **already exist** but are (a) hidden when `hunks.length <= 1` and (b) never seen because the diff didn't render. "Benchmark VSCodium in-memory diff" is therefore ~90% already met; the real ask is "make the diff actually show, immediately, without a separate on-disk file."
- **System prompt** (`context/systemPrompt.ts`): instructs "SEARCH text must EXACTLY match", "target a single file", "do not reduce the request to a copy command", selection handling. No explicit rule that REPLACE must be minimal/scoped → contributes to symptom 3.

## Reframed problem statement
The feature's *infrastructure* (in-memory DiffViewer with full hunk UX) is sound. The failures are concentrated at the **edges**: (a) the exact-match apply that aborts before any diff renders, (b) a brittle block parser that leaks markers, (c) an unnecessary click-gate + redundant on-disk artifact, and (d) under-constrained edit scope. Fix the edges; do not rebuild the DiffViewer.

## Out of scope (explicitly)
- Rewriting `DiffViewer` rendering/decoration engine (it works).
- PDF/image asset-path handling (that is ROADMAP #7, the PDF milestone).
- Multi-file transactional apply / undo-stack redesign (revertData exists; leave it).

## Success criteria
- A correct `ai-agent-edit` proposal whose SEARCH differs from the file only by leading/trailing whitespace or indentation still locates and renders a diff (no "could not find").
- The diff appears **without** clicking "Review Diff".
- No file is created under `00_System/Agent Diffs/` by default.
- A garbled/partial edit block never renders raw `<<<<`/`====`/`>>>>` markers as note text.
- A scoped request ("add section 4") produces a REPLACE limited to that section, not the whole answer.
- Hunk counter + nav remain visible/usable (including the single-hunk case).
- `npx vitest` green; new unit tests for the matcher + parser; testbed smoke for an apply.
