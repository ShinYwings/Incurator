# Draft: Diff Viewer Plugin Overhaul & Sync Fixes

## 1. Core Problem Definition
The user has reported 7 critical bugs in the Obsidian plugin's AI agent Diff Viewer:
1. Navigation arrows (↑/↓) in the diff viewer fail to scroll to the target hunk.
2. Multi-file edits only allow reviewing the first file; subsequent file diff buttons silently open the first file's diff.
3. Accepting a diff incorrectly teleports the editor cursor to the bottom of the document instead of remaining at the accepted hunk.
4. **Desync / Race Condition**: The backend agent operates on a different state than the user. The agent assumes its edits were applied immediately, but the user hasn't accepted them yet, causing the agent to hallucinate successful changes or edit stale context.
5. UI/UX is clunky. The user explicitly requests an inline unified diff view mirroring tools like `vscodium`.
6. **Premature Application**: "Could not find SEARCH text" errors appear, and edits are auto-applied to the disk *before* the user clicks Accept/Reject.
7. File Not Found errors on existing files (path resolution failure).
8. **Inconsistent reviewInEditor Output**: Output varies unpredictably by model. Sometimes changes are batched, sometimes split, and sometimes no reviewInEditor is generated at all, falling back to a raw diff.
9. **UI Selection Mismatch ("Not found search text")**: When multiple `reviewInEditor` items exist, selecting one incorrectly highlights all diffs. Fixing one causes the remaining buttons to fail with a "not found search text" error because the state is mismatched.
10. **Token Limit Truncation**: Models like Gemini hit output token limits when attempting to edit the entire document, resulting in abruptly truncated outputs.
11. **Hover Window Misplacement**: The Accept/Cancel hover window randomly positions itself at the top of the screen instead of anchoring correctly near the diff location.

## 2. Constraints & Success Criteria (User Approved via `/grill-me`)
- **UI/UX Paradigm (Bug 5 & 11)**: Implement an **Inline unified view**. Red/green lines must be inserted directly within the note (similar to GitHub unified diff or `vscodium`), avoiding side-by-side splits or floating modals. The Accept/Cancel hovering UI must be completely redesigned to anchor robustly or be integrated directly into the inline diff UI.
- **State Synchronization (Bugs 4, 6, & 9)**: Edits must be held **purely as UI proposals**. The file on disk MUST NOT be modified until the user explicitly clicks "Accept" in the Diff Viewer. Multi-item batching must maintain strict 1:1 mapping between the button clicked and the specific hunk rendered, eliminating "not found search text" errors.
- **Multi-File State (Bug 2)**: The state manager must correctly track multiple independent edit proposals in a single assistant message and map the correct proposal to its respective Diff Viewer instance when the user clicks the review button.
- **Navigation (Bug 1 & 3)**: Hunk navigation must accurately calculate CM6 line offsets. Cursor position must be restored or maintained cleanly after an Accept action.
- **Path Resolution (Bug 7)**: Ensure `getAbstractFileByPath` calls handle trailing spaces, URL encoding, or root slash inconsistencies robustly.
- **Token Limit Mitigation (Bug 10)**: The prompt architecture and file-edit workflow must strictly enforce minimal, scoped `ai-agent-edit` blocks. The system must prevent the model from attempting to rewrite the entire document in a single block, avoiding token truncation limits inherent to models like Gemini.
- **Model Output Consistency (Bug 8)**: The system prompt guiding the generation of `reviewInEditor` components must be tightened to ensure deterministic and consistent behavior across different provider models.
