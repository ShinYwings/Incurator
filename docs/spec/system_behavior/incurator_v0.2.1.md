# Incurator - System Behavior (v0.2.1)

This document is the behavior source of truth for the v0.2.1 line. It defines
how the backend, plugin, MCP tools, and workspace agents interact. Schema details
live in `docs/spec/curator_schema/SCHEMA_v0.2.1.md`.

Implementation plans under `docs/plans/update_plan/` are subordinate to this
document. If a plan conflicts with this behavior contract, update the plan or
bring the conflict back to review before coding.

## 1. v0.2.1 Goal

v0.2.1 changes Incurator from a blocking eager DAG compiler into a two-track
RAG/DAG system:

1. **Immediate reading path**: create or expose structural L1 context quickly so
   an agent can answer sidebar-style document questions right after a PDF or
   markdown file is opened or registered.
2. **Complete compilation path**: extract L2 Atoms, cluster L3 Concepts, and
   synthesize L4 Exhibitions asynchronously so the long-running DAG compiler does
   not block the client UI.

The target user experience is comparable to an "Ask Gemini sidebar" reading a
PDF, while preserving Incurator's durable L1-L4 knowledge graph.

## 2. Authority Boundaries

### 2.1 Backend Authority

The Incurator backend owns:

- `.curator/state.sqlite`
- source registration and content hashes
- Reference Mode source identity and provenance
- L1-L4 generated pages under `.curator/Collections/`
- `dag_edges`
- background ingest job queue
- shared cloud model catalogue
- MCP tools that mutate or query durable Incurator state

### 2.2 Plugin Authority

The Obsidian plugin owns:

- viewer state
- transient PDF.js extraction for open documents
- chat UI
- human approval prompts for import, reference registration, rebind, and promotion
- rendering progress/status/trace returned by backend tools

The plugin must not mutate `.curator/state.sqlite` or `.curator/Collections/`
directly. The only v0.2.1 exception is `.curator/devices.json`, which the
plugin may refresh on startup as sync-friendly device metadata. All durable DAG,
source registry, ingest, and backpropagation writes must go through backend MCP
tools or CLI code.

### 2.3 Workspace Agent Authority

Workspace agents may:

- read MCP tool results
- call `check_source_status`, `fetch_document_section`, `curator_query`, and
  `get_available_models`
- request promotion of generated knowledge through explicit tools

Workspace agents must not silently edit `03_Notes/`, `04_Resources/`, or
`.curator/` by filesystem writes.

## 3. Source Status And Adaptive Routing

When a PDF or document is opened, the client computes a SHA-256 file hash and
calls `check_source_status(file_hash)`.

### 3.1 Unregistered Source

Expected behavior:

1. Backend returns `registered=false`.
2. Plugin may build an ephemeral L1 from PDF.js or viewer text.
3. Agent can answer using plugin-served `fetch_document_section` data.
4. Plugin shows an explicit "Add to Incurator" action.
5. Durable backend import only happens after human approval or an explicit tool call.

The backend must not create a source row from passive viewing alone.

### 3.2 Registered, L1 Complete, L2/L3 Pending

Expected behavior:

1. Backend returns `registered=true`, `l1_complete=true`, and pending L2/L3 state.
2. Agent may call `fetch_document_section` against backend CTX sections.
3. `curator_query` may report that the document is not fully compiled yet if it
   requires L3 Concepts.
4. Background worker or `wiki jobs run` continues L2/L3 extraction.

This is the normal fast path after `wiki add` in v0.2.1.

### 3.3 Registered, L3 Complete

Expected behavior:

1. Backend returns `l3_complete=true`.
2. Agent may use `curator_query` for concept-grounded answers.
3. The response should include trace/provenance sufficient for the plugin to show
   "Sources & Trace".

### 3.4 Missing Or Drifted Source

If a registered Reference Mode source cannot be found at its remembered
`external_path`, backend status must report drift instead of silently choosing a
different file. Any rebind requires human approval.

## 4. `wiki add` Behavior

Default v0.2.1 behavior:

```text
wiki add
  -> discover/register changed sources
  -> parse source structure
  -> write instant L1 CTX without LLM (always structural)
  -> set sources.context_id and l1_status='done'
  -> return
```

`wiki add` is the **registration + instant L1** command. It never requires an LLM
client and completes within seconds even when the LLM backend is offline.

Rules:

- `wiki add` must not require an LLM to complete.
- `wiki add` does **not** queue or run L2/L3 extraction. Use `wiki build` for that.
- L1 completion and full DAG compilation are different states. Status output must
  show layer statuses separately.

## 4.1 `wiki build` Behavior

`wiki build` triggers L2 (Atoms) and L3 (Concepts) extraction for sources whose
L1 is complete but L2/L3 are still pending.

```text
wiki build [path]
  -> find sources with l1_status='done' and l2_status='pending'
  -> enqueue L2/L3 jobs to the background worker
  -> return immediately (default) or block until done (--wait)
```

Rules:

- `wiki build` requires an LLM client.
- `wiki build --wait` runs L2/L3 synchronously before returning.
- Without `--wait`, jobs are queued to the persistent `ingest_jobs` table and
  processed by the MCP server's IngestWorker or `wiki jobs run`.

### MCP Tool Mapping

| CLI command | MCP tool |
|---|---|
| `wiki add` | `curator_register_source` |
| `wiki build` | `curator_build_source` |
| (legacy) | `curator_ingest_source` (deprecated — calls register + build internally) |

## 5. Instant L1 Generation

The backend parser must generate a CTX with:

- source hash
- content hash
- ToC entries when available
- PDF page provenance when available
- stable section markers
- `## 2. Atom Candidates` compatible with L2 extraction
- `## Source Sections` preserving text recall

Parser priority:

1. PDF: PyMuPDF outline/ToC when available, with page fallback.
2. Markdown/text: markdown heading structure.
3. HTML: heading structure from parser output when available, otherwise text fallback.
4. Other supported formats: one document section if no better structure exists.

The backend must not use plugin ephemeral payloads to write durable CTX pages.
Durable CTX pages are generated from backend-accessible source files.

## 6. Background L2/L3 Orchestration

Heavy extraction is queued in `ingest_jobs`.

Workers:

- MCP server may run an embedded background worker.
- CLI users may run `wiki jobs run`.
- Both consume the same persistent queue.

Job behavior:

- Queued jobs must survive process restart.
- Running jobs should publish phase/progress in `ingest_jobs` and `job_events`.
- Failed jobs should mark the relevant layer status as `error` and record
  `layer_error`.
- Retrying must not duplicate already valid CTX pages unless source content changed
  or the user forces regeneration.

Sub-agent model:

- L1 sub-agent is structural and parser-first.
- L2 sub-agent extracts Atoms section-by-section or batch-by-batch. When a CTX
  exceeds one section-aware batch and the client can be cloned safely, batches may
  run in parallel with independent client instances.
- L3 sub-agent clusters Atoms into Concepts. It should prefer local embedding
  clustering (Ollama embeddings first, sentence-transformers/sklearn when
  available) and use the LLM clustering-plan call only as a fallback.
- The orchestrator owns ordering, retries, progress, and downstream invalidation.

## 7. Section-Aware Extraction

L2 extraction should split CTX body by `<!-- section:... -->` markers.

Rules:

- Split at section boundaries when possible.
- Do not split unmarked text arbitrarily unless the implementation has a
  provenance-preserving fallback.
- Each extracted Atom should include `source_section_id`, `source_section_title`,
  and `source_page` when available.
- Extraction should preserve recall first, then deduplicate exact or near-exact
  Atoms at controlled stages.

## 7.1 Embedding-Based L3 Clustering

v0.2.1 includes embedding-first L3 clustering.

Rules:

- If embeddings are available, L3 clustering should not call an LLM to decide
  Atom group membership.
- Ollama local embeddings are preferred when an Ollama host is active.
- `sentence-transformers`/`scikit-learn` may be used as local CPU fallback.
- If no embedding path is available, the legacy LLM clustering planner remains
  valid.
- Concept page drafting may still use an LLM after clusters have been chosen.

## 8. Incremental Sync And Backprop

Default `wiki sync` behavior in v0.2.1 is incremental:

```text
wiki sync
  -> scan generated page hashes
  -> identify changed nodes
  -> expand downstream through dag_edges
  -> invalidate affected caches/jobs
  -> rebuild routing tables/report
```

Rules:

- `wiki sync --full` performs full structural/logical verification.
- `wiki sync --backward` performs explicit backward repair where supported.
- Hash-only incremental sync must be fast on unchanged DAGs.
- Human-verified promoted Exhibitions are protected from automatic destructive rewrite.
- `dag_edges` is the preferred downstream expansion index.

## 9. Query-Time Exhibition Behavior

`curator_query(question, workspace_id, force_new=false)` is the v0.2.1 MCP entry
point for sidebar-style concept-grounded answers after L3 exists.

Expected behavior:

1. Resolve `workspace_id`.
   - From active workspace basename if a workspace path is available.
   - Otherwise `default`.
2. If L3 Concepts do not exist yet, return `ok=true`, `fallback="l3_incomplete"`,
   `answer=""`, raw fallback hits when available, and `trace.l3_complete=false`.
   The client must then use L1/source-section or local PDF context rather than
   pretending concept-grounded retrieval succeeded.
3. Retrieve relevant L3 Concepts and source provenance.
4. Synthesize or reuse a query-generated Exhibition.
5. Return answer content plus trace.

Trace must include:

- matched concept IDs
- source IDs or paths
- section/page provenance when available
- cache hit/miss
- generated Exhibition ID when one exists
- latency or timing fields when practical

`promote_exhibition(exh_id)` promotes a query-generated Exhibition into a durable
human-facing artifact under `02_Wiki/` after user approval.

Rules:

- Query-generated Exhibitions are not automatically human truth.
- Promotion sets `is_verified_by_human=true` only for the promoted artifact, not
  for every cited Atom/Concept.
- Promotion must not edit `03_Notes/`.

## 10. MCP Tools

v0.2.1 behavior requires these MCP tools:

- `check_source_status`
- `fetch_document_section`
- `curator_query`
- `promote_exhibition`
- `get_available_models`
- `curator_get_version` (Returns the backend version string to detect cross-platform mismatches)

Implemented tools may be released incrementally, but docs and UI must not present
an unimplemented mutating tool as fully available without a clear status note.

## 11. Model Provider Behavior

Antigravity replaces Gemini CLI as the canonical Gemini-family CLI provider.

Rules:

- New config and docs use `antigravity-cli`.
- `gemini-cli` may be read as a migration alias.
- The executable command for Antigravity is `agy`.
- Backend model choices come from the shared model catalogue.
- Plugin UI must request backend model metadata instead of duplicating cloud model
  lists, except for local runtime discovery.

## 12. Observability

Status surfaces:

- `wiki status` shows per-layer source status and active background jobs.
- `wiki jobs list` shows queued/running jobs.
- `wiki jobs run` drains queued jobs in foreground.
- `.curator/dashboard.md` may summarize job and DAG state for Obsidian viewing.

Status rules:

- "Sources summarized (L1)" means `sources.l1_status='done'`.
- It must not be derived from `sources.status='curated'`.
- L1 complete does not imply L2/L3 complete.

## 13. Syncthing Device Registry

When a vault is synchronized by Syncthing, Incurator may use the local
Syncthing `config.xml` as device discovery input. This discovery is limited to
facts Syncthing actually knows: device ids, device names, shared folder ids,
folder labels, and folder paths on the current machine.

Backend launch paths are not Syncthing facts. Incurator records those as
per-device declarations in `.curator/devices.json`. The Obsidian plugin performs
a best-effort refresh on startup by reading local Syncthing config files and the
current plugin MCP launcher settings. Running `wiki devices sync` remains a
manual repair/debug command, but normal plugin use should not require it.
Existing entries for other devices are preserved.

The Obsidian plugin should keep `data.json` local when backend paths differ by
machine. Shared state, such as chat `sessions.json` and `.curator/devices.json`,
can synchronize independently from per-device plugin settings.

## 14. Testbed Validation

Any v0.2.1 behavior change must be validated with:

```bash
wiki testbed init <active_scenario> --force
VAULT_ROOT=testbed wiki status
VAULT_ROOT=testbed wiki add
VAULT_ROOT=testbed wiki sync
VAULT_ROOT=testbed wiki lint
```

If LLM or qmd dependencies are unavailable, lower-level deterministic tests must
still run and the blocker must be reported.

For instant L1 work, validation must show that `wiki add` can create CTX without
printing or requiring LLM readiness when `llm.instant_l1=true`.
