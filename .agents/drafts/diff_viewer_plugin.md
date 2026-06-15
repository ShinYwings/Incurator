# Draft: Diff Viewer Plugin Overhaul & Sync Fixes

## 1. Core Problem Definition
The user has reported 7 critical bugs in the Obsidian plugin's AI agent Diff Viewer:
1. Navigation arrows (↑/↓) in the diff viewer fail to scroll to the target hunk.
2. Multi-file edits only allow reviewing the first file; subsequent file diff buttons silently open the first file's diff.
3. Accepting a diff incorrectly teleports the editor cursor to the bottom of the document instead of remaining at the accepted hunk.
4. **Desync / Race Condition**: The backend agent operates on a different state than the user. The agent assumes its edits were applied immediately, but the user hasn't accepted them yet, causing the agent to hallucinate successful changes or edit stale context.
5. UI/UX is clunky.
6. **Premature Application**: "Could not find SEARCH text" errors appear, and edits are auto-applied to the disk *before* the user clicks Accept/Reject.
7. File Not Found errors on existing files (path resolution failure).

## 2. Constraints & Success Criteria (User Approved via `/grill-me`)
- **UI/UX Paradigm (Bug 5)**: Implement an **Inline unified view**. Red/green lines must be inserted directly within the note (similar to GitHub unified diff), avoiding side-by-side splits or floating modals.
- **State Synchronization (Bugs 4 & 6)**: Edits must be held **purely as UI proposals**. The file on disk MUST NOT be modified until the user explicitly clicks "Accept" in the Diff Viewer. Auto-apply behavior (e.g., `autoApplyProposals`) must be completely disabled/removed. 
- **Multi-File State (Bug 2)**: The state manager must correctly track multiple independent edit proposals in a single assistant message and map the correct proposal to its respective Diff Viewer instance when the user clicks the review button.
- **Navigation (Bug 1 & 3)**: Hunk navigation must accurately calculate CM6 line offsets. Cursor position must be restored or maintained cleanly after an Accept action.
- **Path Resolution (Bug 7)**: Ensure `getAbstractFileByPath` calls handle trailing spaces, URL encoding, or root slash inconsistencies robustly.
