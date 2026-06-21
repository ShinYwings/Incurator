# Draft: Diff Viewer UI/UX & Edit Flow Stabilization

## 1. Core Problem Definition
The current code-editing flow (`ai-agent-edit`) and the built-in Diff Viewer suffer from several critical UX and reliability issues that degrade the editing experience. A previous review identified that the UI/UX work for the Diff Viewer grew substantial enough to require a dedicated milestone.

### Deep Code Analysis & Root Cause ("Why")
1. **`ai-agent-edit` SEARCH-Match Failures**: The search-and-replace algorithm often fails to find matches in the target markdown files due to whitespace normalization, invisible characters, or partial context truncation. When the agent attempts an edit, the failure is brittle and aborts the entire edit loop.
2. **Edit-Scope Bug**: The boundaries of what text gets replaced sometimes bleed or misalign, leading to corrupted markdown or duplicated sections.
3. **Immediate-Diff Rendering**: The diff is not surfaced to the user cleanly or immediately, leaving them blind to what the agent actually changed until they manually inspect the file.
4. **Hunk Navigation**: The current Diff Viewer lacks intuitive hunk-by-hunk navigation (next/prev changes, approve/reject individual hunks), making large file reviews painful.
5. **`00_System/Agent Diffs/` Cleanup**: Temporary diff artifacts and review files are lingering in `00_System/Agent Diffs/`, polluting the vault. The cleanup lifecycle for these ephemeral review artifacts is broken or missing.

## 2. Constraints & Success Criteria
- **Robust Search & Replace**: Refactor the matching algorithm to be more resilient to whitespace/newline discrepancies (e.g., fuzzier match or strict exact-block extraction).
- **Hunk Review UI**: Implement intuitive controls for navigating and accepting/rejecting diff hunks inline.
- **Ephemeral State**: Diff artifacts MUST NOT permanently pollute `00_System/Agent Diffs/`. They should either be stored in `.cache/`, in memory, or automatically cleaned up upon resolution (Approve/Reject).
- **Success Measure**: An agent edit successfully finds its target block, applies cleanly without duplicating text, immediately opens the Diff Viewer, and cleans up any backing artifacts when the user accepts the change.
