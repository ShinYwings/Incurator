# Curation / Exhibition Persistence — Redesign Proposal

## Why this exists

The user clarified two things that invalidate the earlier
`2026-06_exhibitions_persistence_review.md` premise:

1. A **workspace can live outside the vault** (the reason external-agent support
   exists). Curation (Exhibition) is **workspace-scoped**, not chat-scoped.
2. `wiki query` and the Obsidian sidebar agent have **no workspace**, so they were
   shoe-horned into making *per-session ephemeral EXH* files that were meant to be
   deleted with the chat session. That conflation is the root problem.

Mandate: **keep the curation philosophy** (`docs/philosophy/ABOUT.md` §4: the
Curator stages a *Special Exhibition* per `curate.yml` so the Artist retrieves
pre-refined exhibits instead of raw data) — the storage form of EXH is otherwise
free to change.

## Core idea: separate the two concepts that EXH currently conflates

### Concept 1 — Workspace Curation (the Exhibition; the philosophy core)

- A workspace (its `curate.yml`, possibly an external directory) has **exactly one
  durable, maintained Exhibition**: the Special Exhibition tailored to its
  Knowledge Requirement Spec.
- Source of truth: the `exhibitions` data in the DB keyed by `workspace_id` +
  `curate_spec_hash`. Emitted as **one** markdown artifact per workspace
  (refreshed in place), placed where the workspace's agent can read it:
  - in-vault workspace → `.curator/Collections/04_Exhibitions/<workspace_id>.md`
  - external workspace → `<workspace>/.curator-exhibition.md` (or the workspace's
    `.agents/` context), so external MCP agents read it directly.
- **Refreshed in place** when stale (source/graph/`curate_spec_hash` changes) via
  `wiki curate` / `wiki refresh` / backprop. It never accumulates and is never
  GC'd. This is "curation."

### Concept 2 — Sessionless Q&A (`wiki query`, sidebar chat with no workspace)

- This is **not curation**. There is **no durable Exhibition and no vault markdown
  file**. The `QueryOrchestrator` returns the answer + `QTR` trace to the caller:
  - CLI prints it; the plugin renders it and stores the turn in `sessions.json`
    (the existing 1:1 chat-history store, PLUGIN_SCHEMA §2.2).
- Optional answer cache is a **DB table** (`query_cache`: `workspace_id`,
  `question_hash`, `output_language`, `answer`, `trace_json`, `created_at`) with a
  TTL — cleaned in the DB, never a vault file, never indexed by qmd.
- Deleting a chat session needs no backend cleanup (there is no EXH file). The
  user's original "delete session → delete EXH" intent is satisfied trivially.

## Why this is the best fit

- **Curation philosophy intact**: the workspace Exhibition is the durable, tailored
  Special Exhibition for the (possibly external) Artist.
- **No vault / qmd pollution**: sessionless answers never become indexed markdown,
  so the qmd corpus stays the *curated* DAG only.
- **No cross-process coupling**: the backend never tracks plugin session lifecycle.
- **The GC problem dissolves**: there are no ephemeral EXH markdown files to GC;
  the optional cache is DB-native with a TTL. `lint.gc_ephemeral_exhibitions`
  becomes obsolete and is removed.
- **Matches the v0.3.1 compile model**: DB = single source of truth; markdown is a
  derived corpus for *curated knowledge*, not chat caches.

## Concrete changes (no backward-compat shims, per locked decision)

Backend:
1. `query.py` / `plugin_api.curator_query`: when there is no workspace
   (`workspace_id == default`), STOP writing EXH markdown; return answer + trace.
   Add an optional DB `query_cache` lookup/store (replaces EXH cache).
2. `wiki curate` (workspace path): emit/refresh the **single** workspace Exhibition
   keyed by `workspace_id` (replace-in-place), not a new EXH per call.
3. Remove ephemeral-EXH cache + `lint.gc_ephemeral_exhibitions` (now obsolete).
   Re-enable nothing — the concept is gone.
4. `db.py`: add `query_cache` table + accessors (TTL GC by `created_at`).

Specs/guides (same commit):
5. SCHEMA §15 + SYSTEM_BEHAVIOR §9/§15/§22: redefine EXH as one-per-workspace
   durable curation; define sessionless Q&A (no EXH file) + `query_cache`.
6. USER/WORKFLOW/MCP/PLUGIN guides (EN+KR).

Tests:
7. workspace curate emits exactly one EXH per workspace (refresh-in-place);
   sessionless query writes NO EXH file; `query_cache` round-trip + TTL; plugin
   trace still renders from returned QTR fields.

## Alternatives considered (rejected)

- **Two-tier dirs** (sessions subfolder + promoted root): still files, still needs
  qmd exclusion + a retention policy; more structure for no real gain.
- **Session-bound EXH deletion** (plugin signals backend to delete EXH on session
  delete): couples backend EXH lifecycle to the plugin across processes, and the
  CLI has no session to bind — fragile.

## Status

PROPOSAL — awaiting user approval before implementation (per the /goal workflow:
plan → approve → docs/spec → TDD → implement).
