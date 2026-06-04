# Exhibition Persistence & User Memory Architectural Review

## Goal Description
Analyze the transition of L4 Exhibitions from ephemeral, garbage-collected chat session caches to persistent "living documents." We evaluate the implementation of this transition, the reasoning behind it, and whether the current design is the most optimal architectural approach for establishing a long-term user profile and context alignment.

---

## Before vs. After Comparison

| Metric / Feature | Before (v0.2.x / early v0.3.0) | After (v0.3.1 Implementation) |
| :--- | :--- | :--- |
| **GC Behavior** | Stale ephemeral Exhibitions (>24 hours) were automatically deleted during `wiki lint`. | Ephemeral GC is disabled (`gc_ephemeral_exhibitions` returns `[]`). |
| **Persistence** | Chat sessions were treated as disposable, short-lived cache files. | All chat session files (`EXH-*.md`) are permanently preserved in the vault. |
| **Frontmatter** | Stamped with `ephemeral: true`. | Stamped with `ephemeral: false` (or flag deprecated). |
| **Purpose** | Temporary visualization of query traces and answers. | Persistent memory of user interactions, tendencies, corrections, and style preferences. |

---

## Rationale for the Change
1. **In-Context Personalization**: Chat sessions are not just search results; they contain rich signals about user intent, past corrections, preferred style (e.g., academic vs. engineering), and specific formatting preferences.
2. **Context Preservation**: If chat session files are deleted, the user loses their Obsidian chat history, which breaks the expected UX where a sidebar chat session corresponds 1:1 with an inspectable file.
3. **Referenceability**: L4 Exhibitions act as the bridge between user query context and the DAG. Persistent exhibitions allow future queries and agent runs to reference previous conversations as grounded context.

---

## Architectural Evaluation: Is this the best approach?

While preserving the files resolves the immediate problem of deleting chat history, keeping *every* chat session permanently in the main workspace file tree has significant trade-offs. We analyze three possible designs below:

### Option A: Direct Perpetual Storage (Current Implementation)
*Every chat session creates a permanent markdown file under `02_Wiki/04_Exhibitions/EXH-*.md`.*
* **Pros**:
  - Extremely simple to implement (just disable GC).
  - 1:1 mapping between the sidebar chat UI and the Obsidian file.
  - Files are indexable by default.
* **Cons**:
  - **Workspace Clutter**: A power user might initiate 10+ chat sessions a day. Within a few months, `04_Exhibitions/` will contain hundreds of fragmented files, bloating the vault.
  - **Context Fragmentation**: Having user preferences scattered across 50 separate chat logs makes it difficult for the LLM during context injection. The LLM must either search/RAG over all past chats, or load a large, redundant context window.
  - **Search Pollution**: General searches over the vault will be heavily polluted with old chat logs.

### Option B: Consolidated Memory File + Ephemeral Chats (Proposed Alternative)
*Chat sessions are kept in a separate cache directory (or remain ephemeral/cleanable), but any explicit user corrections, style preferences, or key decisions are compiled/synthesized into a single master memory file (e.g., `02_Wiki/memory.md` or `.curator/user_profile.md`).*
* **Pros**:
  - **High Density**: The LLM gets a single, highly synthesized file containing all learned user preferences (similar to Claude Code's `memory.md`).
  - **No Clutter**: Stale chat logs can be safely archived or deleted because their *value* (the learned memory) has already been extracted.
  - **User-Editable**: The user can open `memory.md` directly and clean up or edit their profile manually.
* **Cons**:
  - Requires a background "compilation" process that runs periodically or upon session close to extract preferences and update the memory file.

### Option C: Two-Tier Storage (Hybrid Model)
*Individual chat sessions are kept in a dedicated subdirectory (e.g., `02_Wiki/04_Exhibitions/Sessions/`) that has its own retention policy, while "Promoted" Exhibitions (which the user manually saves or the system flags as highly valuable) are placed in the root of `04_Exhibitions/`.*
* **Pros**:
  - Prevents main workspace clutter while preserving recent chat history.
  - Clearly separates temporary conversations from permanent curated exhibitions.
* **Cons**:
  - More complex directory structure.

---

## Verification Plan & Open Questions for the User

### Verification of Current Work
- Run `uv run pytest backend/tests/test_lint_ephemeral_gc.py` to confirm that GC is successfully bypassed.
- Verify `npm run build` in the plugin compiles without errors.

### Review Questions for the User
> [!IMPORTANT]
> Please review the options above and clarify:
> 1. **Do you prefer Option A (current: leave every chat file permanently in `04_Exhibitions/`) or Option B/C (consolidation into a single `memory.md` / moving chats to a subfolder)?**
> 2. **If we proceed with a consolidated `memory.md`, should the compilation/extraction run asynchronously in the background when a session ends, or should it run during `wiki build`/`wiki curate`?**

---

## Opus Review Decision (2026-06-03) — the premise is incorrect

The user clarified the architecture: **an Exhibition (EXH) is NOT a chat-session
cache.** A *workspace* can live OUTSIDE the vault (that is the whole reason
external-agent support exists), so it is decoupled from plugin chat sessions. EXH
was created specifically to **stage a curated context package for a workspace**
(possibly external) that external agents (Cursor, Claude Code) consume over MCP.
Chat history is a separate plugin concern stored in `sessions.json`
(PLUGIN_SCHEMA §2.2), not in EXH files.

**Therefore Options A/B/C above are moot** — they all rest on the false premise
that "EXH = persisted chat session." The v0.3.1 SCHEMA §15 already models EXH
correctly as a workspace-scoped staged context package (`workspace_id`,
`curate_spec_hash`, `route`).

### Correct model (two distinct kinds of EXH)

1. **Workspace EXH** — staged per `curate.yml` (`exhibition:` pointer),
   `exhibition_origin: promoted`/staged. This is the durable workspace context
   for (possibly external) agents → **persists; never GC'd.**
2. **Query-generated ephemeral EXH** — `ephemeral: true`,
   `exhibition_origin: query_gen`, produced as an answer cache for plain chat
   turns with no workspace (`workspace_id: default`). These ARE caches →
   **should remain GC-eligible.**

### Consequence for the GC change

Disabling ALL GC (`gc_ephemeral_exhibitions()` → `[]`) over-persists kind #2 (chat
answer caches), which contradicts the user's model and pollutes the qmd corpus.
The correct behavior: GC stale `ephemeral: true` + `exhibition_origin: query_gen`
EXH, while NEVER touching workspace/promoted Exhibitions. (User memory /
preferences belong to the insight-candidate lifecycle + sessions.json, not to
accumulating EXH files.)

**Status:** premise corrected by the user; no Option A/B/C consolidation needed.
Pending user sign-off to re-enable scoped GC for ephemeral query_gen EXH only
(reverses Antigravity's blanket GC-disable deliberately, so confirm before code).
