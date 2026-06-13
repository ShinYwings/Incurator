# Incurator - System Behavior (v0.7.0)

This document represents the most concrete layer (`spec`) of the documentation hierarchy (`philosophy` -> `guides` -> `spec`). It is the absolute behavior source of truth. It defines how the backend, plugin, MCP tools, and workspace agents interact. Schema details live in `docs/specs/curator_schema/SCHEMA.md`.

Implementation plans under `.agents/plans/` are transient and strictly subordinate to this document. If a plan conflicts with this behavior contract, update the plan or bring the conflict back to review before coding.

Sections 1-22 below define the behavior contract. The system retires qmd as an external search backend and replaces it with DB-native search, query expansion, chunk vectors, RRF, configured reranking, and durable query traces. Historical behavior definitions are tracked via git history.

The current path is the only supported behavior contract. It has no
prompt-function wrappers, legacy-query fallback path, `curate.yml`
persona-to-KRS auto-mapping, or qmd runtime fallback.

## 1. System Goal

v0.2.2 changes Incurator from a blocking eager DAG compiler into a two-track
RAG/DAG system:

1. **Immediate reading path**: create or expose structural L1 context quickly so
   an agent can answer sidebar-style document questions right after a PDF or
   markdown file is opened or registered.
2. **Complete compilation path**: extract L2 Atoms, cluster L3 Concepts, and
   synthesize shared L4 Synthesis asynchronously so the long-running DAG compiler does
   not block the client UI.

The target user experience is comparable to an "Ask Gemini sidebar" reading a
PDF, while preserving Incurator's durable L1-L4 knowledge graph.

## 2. Authority Boundaries

### 2.1 Backend Authority

The Incurator backend owns:

- `.curator/state.sqlite`
- source registration and content hashes
- Reference Mode source identity and provenance
- L1-L4 derived inspection projections under `.curator/Collections/`
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
- rendering progress/status/trace returned by backend tools or backend-owned
  shared status snapshots

The plugin must not mutate `.curator/state.sqlite` or `.curator/Collections/`
directly. The only v0.2.2 exception is `.cache/config/devices.json`, which the
plugin may refresh on startup as sync-friendly device metadata. All durable DAG,
source registry, ingest, and backpropagation writes must go through backend code.
For read-only dashboard synchronization, the preferred boundary is a backend-owned
shared JSON snapshot under `.curator/runtime/`: the backend is the only writer,
and the plugin is a read-only consumer.

### 2.3 Workspace Agent Authority

Workspace agents may:

- read MCP tool results
- call `check_source_status`, `fetch_document_section`, `curator_query`, and
  `get_available_models`
- request promotion of generated knowledge through explicit tools

Workspace agents must not silently edit `03_Notes/`, `04_Resources/`, or
`.curator/` by filesystem writes.

## 3. Source Status And Adaptive Routing

When local viewer context is sufficient, the same-device Obsidian plugin answers
without waiting for backend status. When backend PDF context is needed, or when
an Add/status action explicitly requests it, the plugin computes the available
source identity and calls `wiki plugin source status ... --json`. External
workspace agents use the equivalent MCP `check_source_status` tool.

### 3.1 Unregistered Source

Expected behavior:

1. Backend returns `registered=false`.
2. Plugin may build an ephemeral L1 from PDF.js or viewer text.
3. Agent answers from local PDF.js/viewer context first. If local context is
   unavailable, a read-only backend PDF parse may provide ephemeral page/outline
   context without creating durable state.
4. Plugin shows an explicit "Add to Incurator" action.
5. Durable backend source registration only happens after human approval or an
   explicit tool call. For external PDFs, the default action is Reference Mode:
   the backend creates a lightweight markdown stub under `04_Resources/`, keeps
   the PDF in its original location, stores the stub relpath in `sources.relpath`,
   and stores the actual PDF path in device-local `sources.external_path`.
   Generated stubs must not embed absolute `target_path` values by default,
   because `04_Resources/` may synchronize across devices whose external PDF
   libraries use different local paths. For Zotero-backed PDFs, the stub must
   include portable Zotero identity such as `reference_kind: zotero`,
   `zotero_attachment_key`, `logical_source_id: zotero:<key>`, and a
   `zotero://open-pdf/library/items/<key>` link.

The backend must not create a source row from passive viewing alone. Provider
context assembly must never call source import/register as a side effect.

### 3.2 Registered, L1 Complete, L2/L3 Pending

Expected behavior:

1. Backend returns `registered=true`, `l1_complete=true`, and pending L2/L3 state.
2. Missing-local-context and `toc_id` requests use the registered durable L1 CTX
   projection. The response identifies `context_source=durable_l1_projection`.
   If that derived projection is missing, stale, or contains previews rather
   than exact source text, the backend may visibly degrade to a read-only
   original-source parse without mutating durable state.
3. `curator_query` may report that the document is not fully compiled yet if it
   requires L3 Concepts.
4. Background worker, **Incurator Dashboard > Jobs > Run queued**, or
   `wiki jobs run` continues L2/L3 extraction.

This is the normal fast path after plugin Add Source, or after CLI `wiki add`
followed by `wiki build`.

PDF viewer questions and durable PDF knowledge refinement are separate user
flows. Viewer questions should answer from local PDF/page/selection/crop context
without requiring ingestion. Purple PDF chips and Add-to-Incurator actions start
durable refinement by registering the source, producing instant L1, and queueing
L2/L3 jobs; they must not block until L2/L3 or L4 completes.

Adaptive routing is priority-based rather than a forced backend round trip:
explicit/local viewer context → registered durable L1 projection → read-only
ephemeral parse fallback. `curator_query` is an L3/workspace operation and must
not be presented as concept-grounded for a PDF-focused turn whose relevant
source is unregistered or L3-incomplete.

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

Default v0.2.2 behavior:

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

- `wiki build` uses the configured LLM client for high-quality extraction. If
  the LLM fails during L2 batch extraction, the backend may create low-confidence
  deterministic fallback Atoms from L1 `Atom Candidates` so the build remains
  searchable and provenance-preserving instead of leaving the source completely
  unusable.
- `wiki build --wait` runs L2/L3 synchronously before returning.
- Without `--wait`, jobs are queued to the persistent `ingest_jobs` table and
  processed by the MCP server's IngestWorker or `wiki jobs run`.
- After processing, `wiki jobs run` (which `wiki build` spawns as a detached
  background daemon) **always refreshes the DB-native search index with
  embeddings** (`search.update_index(..., embed=True)`), **even when the queue was
  already empty**. This is required so a vault whose L2/L3 finished but whose
  vector embeddings never completed (interrupted daemon, or FTS-only `wiki add`)
  has an automatic path back to vector search instead of staying FTS5-only until
  a manual `wiki reindex --embed`. The embed refresh is idempotent: `update_index`
  fingerprints chunk input/dependency hashes, so already-current embeddings are
  not recomputed. `wiki build --wait` performs the same embed refresh inline.
- The `wiki build --wait` embed refresh runs **unconditionally** — it is no
  longer gated on `atoms_created or atoms_updated`. A `--wait` build that finds
  no pending sources (the global-L3 path) and a build that produces zero atom
  changes both still call the embedding-enabled native index refresh. Only the
  change-dependent side effects (persona reinforcement, sync-report
  invalidation) remain gated on real L2/L3 changes.

## 4.2 `wiki update` Behavior

`wiki update` is the one-shot ingest pipeline. It runs the full sequence
**synchronously** so the vault is fully current when the command returns:

```text
wiki update [--force] [--no-sync]
  -> add  (discover + register + instant L1; no LLM)
  -> build --wait  (L2/L3 extraction + unconditional embed refresh)
  -> sync  (deductive verification + routing rebuild; skipped with --no-sync)
```

Rules:

- `wiki update` orchestrates the existing `add` / `build` / `sync` behaviors;
  it adds no new ingest logic. `add` and `build` run with verification deferred,
  and a single `sync` runs at the end (non-interactively).
- `--force` rebuilds existing L1/L2/L3; `--no-sync` skips the final verification.
- The granular `wiki add` / `wiki build` / `wiki reindex` / `wiki sync` commands
  remain for fine-grained control; `wiki update` is the recommended common path.
- The `jobs` command group (`wiki jobs run/list/cancel/rerun`) stays functional
  for the background worker and the Obsidian dashboard but is **hidden** from
  `wiki --help`, because the synchronous `update`/`build --wait` path drains the
  queue without a manual `jobs run`.

### MCP Tool Mapping

| CLI command | MCP tool |
|---|---|
| `wiki add` | `curator_register_source` |
| `wiki add` with no path | `curator_add_all` |
| `wiki build` | `curator_build_source` |
| `wiki build` for pending sources | `curator_build_all` |
| (legacy) | `curator_ingest_source` (deprecated — calls register + build internally) |

## 5. Instant L1 Generation

The backend parser must generate a CTX with:

- source hash
- content hash
- ToC entries when available
- PDF page provenance when available
- stable section markers
- an English `## Source Guide` with section/page previews for immediate search
  and MCP recall
- `## 2. Atom Candidates` compatible with L2 extraction
- `## Source Sections` preserving text recall inline for small/medium sources,
  or preserving section markers/previews with on-demand raw-source fetch for
  large sources

Parser priority:

1. PDF: PyMuPDF outline/ToC when available, with page fallback.
2. Markdown/text: markdown heading structure.

When an L1 CTX has `source_text_policy: on_demand`, L2 extraction must hydrate
the extraction body from the original source file before calling the LLM. The
compact L1 previews are useful retrieval hints, but they are not enough evidence
for Atom extraction.
3. HTML: heading structure from parser output when available, otherwise text fallback.
4. Other supported formats: one document section if no better structure exists.

The backend must not use plugin ephemeral payloads to write durable CTX pages.
Durable CTX pages are generated from backend-accessible source files.

## 6. Background L2/L3 Orchestration

Heavy extraction is queued in `ingest_jobs`.

Workers:

- MCP server may run an embedded background worker.
- CLI users may run `wiki jobs run`.
- CLI users may cancel a queued job with `wiki jobs cancel <id>` before a worker
  claims it.
- CLI users may requeue a completed, failed, or cancelled job with
  `wiki jobs rerun <id>`.
- Both consume the same persistent queue.

Job behavior:

- Queued jobs must survive process restart.
- Running jobs should publish phase/progress in `ingest_jobs` and `job_events`.
- Failed jobs should mark the relevant layer status as `error` and record
  `layer_error`.
- Cancelled jobs stay terminal until explicitly requeued. A running job is not
  cancelled by the foreground command because a worker may already own it.
- Retrying must not duplicate already valid CTX pages unless source content changed
  or the user forces regeneration.

Sub-agent model:

- L1 sub-agent is structural and parser-first.
- L2 sub-agent extracts Atoms section-by-section or batch-by-batch. When a CTX
  exceeds one section-aware batch and the client can be cloned safely, batches may
  run in parallel with independent client instances. Batch size must respect the
  active LLM client's `optimal_chunk_chars` cap, bounded by the system maximum,
  so CLI-backed models are not given oversized extraction prompts. Codex CLI is
  clone-safe for independent batch calls and uses a conservative chunk budget so
  large PDFs do not enter one long `codex exec` request.
- L3 sub-agent clusters Atoms into Concepts. It should prefer the configured
  local embedding provider when available (for v0.3.2 search this defaults to
  llama-cpp Qwen3 embedding; Ollama and sentence-transformers/sklearn remain
  valid fallback profiles) and use the LLM clustering-plan call only as a fallback. Concept
  plans must be filtered to real L2 Atom files from the active build before
  Concept pages and `dag_edges` are written, preventing hallucinated or stale
  Atom IDs from entering evidence traversal.
- The orchestrator owns ordering, retries, progress, and downstream invalidation.

### 6.1 LLM Resiliency and Extraction Fallbacks

Batch Atom extraction (`_extract_atoms_from_chunk`) relies on the LLM adhering to a strict JSON array schema. To prevent silent failures when using lightweight or unreliable models:

1. **Self-Correction Loop**: If the LLM generates malformed JSON, the orchestrator catches the `JSONDecodeError` (via `LLMError`) and automatically resubmits the request to the LLM up to 2 times, appending the exact error message to prompt self-correction.
2. **Deterministic L1-Candidate Fallback**: If batch extraction ultimately
   fails with an `LLMError`, the orchestrator may create low-confidence L2 Atoms
   directly from the English L1 `Atom Candidates` and `Source Guide` provenance.
   These fallback Atoms must include the closest section id/page when available
   and must use low confidence so later LLM-backed retries or human review can
   supersede them.
3. **Deterministic L3 Fallback Concepts**: If L3 clustering or L3 Concept
   drafting fails after L2 Atoms exist, the build may create low-confidence
   deterministic fallback Concepts that group related Atoms by source context.
   This keeps L3 coverage and provenance available while clearly marking the
   Concept as needing later LLM or human review.
4. **Legacy Sequential Fallback**: Older extraction paths may still attempt
   candidate-by-candidate LLM calls, but they must not be the only resilience
   mechanism for provider failures because they multiply the same failing LLM
   dependency.

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

v0.2.2 includes embedding-first L3 clustering.

Rules:

- If embeddings are available, L3 clustering should not call an LLM to decide
  Atom group membership.
- The configured local embedding provider is preferred; Ollama local embeddings
  remain a valid fallback profile when an Ollama host is active.
- `sentence-transformers`/`scikit-learn` may be used as local CPU fallback.
- If no embedding path is available, the legacy LLM clustering planner remains
  valid.
- Concept page drafting may still use an LLM after clusters have been chosen.

## 8. Incremental Sync And Backprop

Default `wiki sync` behavior is incremental:

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
- `wiki sync --backward` is disabled; reviewed corrections use
  `curator_propose_correction` and a separate approved follow-up workflow.
- Hash-only incremental sync must be fast on unchanged DAGs.
- Human-verified `02_Wiki/` promotions are protected from automatic destructive rewrite.
- `dag_edges` is the preferred downstream expansion index.
- MCP `curator_update_node` is disabled and must never overwrite a generated
  node. It returns a non-mutating error directing clients to
  `curator_propose_correction` or an explicit promotion tool.
- `curator_propose_correction` classifies the proposal, identifies affected
  generated nodes, and returns a recommended action. It does not directly patch
  generated nodes or source truth. Ambiguous or derived changes remain
  reviewable candidates until an explicit follow-up action is approved.

## 9. Sessionless Query Behavior (frozen Exhibitions removed)

`curator_query(question, workspace_path)` is the MCP entry point for sidebar-style
answers; `curator_fetch_context(question, workspace_path)` is the evidence-only
surface for reasoning agents; `wiki query` is the CLI surface. All are
**sessionless**: they return an answer (or evidence pack) plus a `QTR-` trace and
write **no** vault file. The v0.2.x query-generated/ephemeral Exhibition and its
answer-cache are removed (§15, SCHEMA §5/§15).

Expected behavior:

1. Resolve `workspace_id` from the active workspace basename when a workspace path
   is available, else `default`. A plain chat turn whose active note is **not**
   inside a workspace folder (no ancestor `curate.yml`) MUST resolve to `default`;
   the plugin must not bind an arbitrary workspace (e.g. the first `curate.yml`
   found in the vault) to a conversational chat.
2. If L3 Concepts do not exist yet, return `ok=true`, `fallback="l3_incomplete"`,
   `answer=""`, raw fallback hits when available, and `trace.l3_complete=false`.
3. Run the QueryOrchestrator: choose a route (local/global/explore/source-section),
   build the curated evidence pack (the dynamic Curation lens over L1–L4 incl. the
   shared Synthesis layer), and — for `curator_query`/`wiki query` — synthesize an
   answer. `curator_fetch_context` returns the evidence pack without synthesis.
4. Return answer/evidence plus trace. No Exhibition is created or cached.

The Obsidian sidechat uses `wiki plugin query` (JSON) for ordinary
workspace/domain questions; it must not wait for an external MCP server. If the
latest turn is centered on selected Markdown, a line-range edit, a PDF page
reference, or a selected PDF/image crop, sidechat treats that selected context as
primary.

For PDF selected-context turns, a selected phrase that is itself a pointer
(`Section A4.2`, `p580`, `Figure 19.1`, `Eq. (19.6)`, etc.) changes the target
of the turn: the system should resolve the referenced section/page/object from
the PDF outline and local page/window text, inject the resolved target context
ahead of generic page background, and answer about the referenced target. If the
pointer is detected but cannot be resolved, the answer must say so instead of
silently explaining the visible page or inventing external knowledge.
Printed page references should use the PDF's native PageLabels map when
available instead of assuming printed page `N` equals physical page `N`.

Trace must include:

- matched concept IDs and `synthesis_node_ids` / `community_report_ids`
- source IDs or paths; section/page provenance when available
- `trace_id` (`QTR-`) and `route`
- latency or timing fields when practical

Durable human artifacts come only from an explicit promotion of an **insight
candidate** to `02_Wiki/` (`curator_promote_insight`), after user approval.

Rules:

- Generated answers/insights are not automatically human truth.
- Promotion writes only `02_Wiki/`; it must not edit `03_Notes/`/`04_Resources/`.

## 10. MCP Tools

The Incurator MCP server exposes over 40 tools. The following list highlights the *newly introduced tools specific to v0.2.2 behavior*. For a complete and exhaustive list of all MCP tools and their descriptions, please see [MCP_USER_GUIDE.md](../../guides/MCP_USER_GUIDE.md).

v0.2.2 introduces these new core MCP tools:

- `check_source_status`
- `fetch_document_section`
- `curator_query` (sessionless: answer + trace, no Exhibition file)
- `curator_fetch_context` (curated evidence pack, no synthesis)
- `get_available_models`
- `curator_get_version` (Returns the backend version string to detect cross-platform mismatches)

Implemented tools may be released incrementally, but docs and UI must not present
an unimplemented mutating tool as fully available without a clear status note.

## 11. Model Provider Behavior

Antigravity replaces Gemini CLI as the canonical Gemini-family CLI provider.

Rules:

- New config and docs use `antigravity-cli`.
- Legacy `gemini-cli` aliases and environment variables have been completely removed.
- The executable command for Antigravity is `agy`.
- Backend model choices come from the shared model catalogue.
- Plugin UI must use the backend model catalogue without duplicating cloud model
  lists. For the Obsidian plugin, this catalogue is bundled from
  `backend/src/curator/data/models.json` at plugin build time so model controls
  do not depend on MCP startup.

### 11.1 Model Catalogue and Reasoning Effort

The shared catalogue (`backend/src/curator/data/models.json`, the single source of
truth) is `schema_version: 2`. It must only list models the corresponding CLI
actually exposes — phantom entries (models the installed `agy`/`claude`/`codex`
or the configured API provider does not offer) are a defect. Each cloud/API model may declare a reasoning/effort
dimension:

- `efforts`: ordered list of effort levels the CLI accepts for that model
  (empty/absent = no effort dimension).
- `default_effort`: the level used when none is explicitly selected.

`curator.models` and external-agent `get_available_models` must surface
`efforts` and `default_effort` so clients render an effort picker without
hardcoding levels. The Obsidian plugin reads the same fields from the bundled
backend `models.json` artifact.

Effort is stored per failover slot in `llm.primary_effort` / `llm.fallback_effort`
(empty = the CLI's own default). The clients map a non-empty effort to the
provider-native control:

- `claude-code` → `claude --effort <level>` (`low|medium|high|xhigh|max`).
- `codex-cli` → `codex -c model_reasoning_effort=<level>` (`low|medium|high|xhigh`).
- `antigravity-cli` → `agy` has no effort flag, so the level is embedded as a
  prompt hint (best-effort only).
- `deepseek-api` → OpenAI-compatible `https://api.deepseek.com/chat/completions`
  with `DEEPSEEK_API_KEY`, `llm.deepseek-api.api_key_secret`, or the legacy
  plaintext `llm.deepseek-api.api_key`. Environment variables take precedence.
  `api_key_secret` points to a local encrypted secret outside the shared vault;
  shared/project config must not contain newly stored plaintext API keys.
  Current catalogue
  entries are `deepseek-v4-flash` and `deepseek-v4-pro`; legacy aliases
  `deepseek-chat` and `deepseek-reasoner` are not preferred because DeepSeek
  schedules them for deprecation on 2026-07-24.

The interactive `wiki config provider` wizard and the plugin dashboard LLM card
must offer only the efforts a chosen model declares, and changing the model must
reset its effort to that model's `default_effort`.

`wiki config provider` must be **non-interactive-safe** so callers like the
dashboard (which run it as a subprocess with no TTY) can persist a change:
1. The provider change is written to the project config **before** the optional
   tool/model install offer, so a skipped/failed offer never loses the change.
2. The install offer (`typer.confirm`) is **skipped entirely when stdin is not a
   TTY**, so the command never blocks on, or aborts at, a prompt.
The dashboard writes Primary via `config provider` and Fallback via
`config set --local`; both must target the **same project-scoped config**.
`config set` defaults to `--global`, and the project `llm` block shadows global
keys on load — so writing the fallback globally silently masked it. Mixing config
scopes for related `llm` keys is a defect.

Language handling is per request. Each query detects the latest user input
language, uses English as the internal/search working language, and then writes
the final answer in the detected latest input language unless that latest
request explicitly asks for another output language. Previous chat turns, saved
EXH metadata, Korean Markdown context, or workspace defaults must not force the
output language of a later English/Chinese/Korean question.

Input-language detection is a deterministic, logic-level step, not merely a
prompt instruction. The plugin classifies the latest request by Unicode script
ranges (Hangul → Korean; Han without Kana → Chinese; Hiragana/Katakana →
Japanese; Cyrillic → Russian; Arabic, Devanagari, Thai, Greek, Hebrew, …;
default Latin → English). Detection runs fresh on every request and a single
canonical detector is shared by both the curator-query path and the plain-chat
path so language behavior is identical everywhere. The detected language drives
the final answer language directly: the answering model generates in the
detected language rather than producing English and then translating in a
separate round-trip.

The three language fields (`input_language`, `english_query`,
`final_output_language`) are **response/trace-only**. They are returned in the
`wiki plugin query` JSON so the bridge is auditable, but they MUST NOT be
persisted as a generated query artifact or reused as a session-level language
preference. Each query derives them from the latest request and active
chat/workspace context.

### 11.2 Plugin Dashboard Runtime Snapshots

The Obsidian plugin dashboard reads backend status through backend-owned local
snapshot files rather than MCP tool discovery or a plugin-specific IPC process.
These files are generated caches for the current machine. They are not shared
truth and must not be synchronized across devices.

Canonical runtime snapshots live under:

```text
.curator/runtime/
```

Recommended files:

- `.curator/runtime/status.json` — vault health, source layer counts, active job
  counts, DB-native search readiness (`fts_ready`, embedded chunk counts,
  vector readiness, provider/model, degraded reason), backend version, and
  generated timestamp.
- `.curator/runtime/sources.json` — read-only source rows needed for dashboard
  and source chips.
- `.curator/runtime/jobs.json` — active/recent background jobs and errors.

Rules:

- Backend code is the single writer for `.curator/runtime/*.json`.
- The plugin may read these files directly through the Obsidian vault adapter
  only after giving the local backend a chance to refresh them.
- The plugin must treat missing or stale snapshots as "unknown/waiting", not as
  proof that backend state is empty.
- Runtime snapshots must be derived from backend-owned state (`state.sqlite`,
  internal search metadata, job queue, config) and must not become a second
  source of truth.
- Runtime snapshots may include local absolute paths such as the active vault
  root, backend executable, model cache, and Zotero roots. `.curator/runtime/`
  must therefore stay device-local in Syncthing and Git ignore rules.
- Mutating actions such as import, rebind, reset, query generation, and
  promotion must not be implemented by editing shared JSON files.
- Dashboard buttons that change backend state must invoke backend code. The
  plugin may launch an explicit backend command after a user action, but the
  backend command performs the write.
- Status bars and dashboard widgets should read runtime snapshots. They must not
  poll Incurator MCP tools for ordinary local status.
- Zotero plugin flows should call hidden backend plugin commands
  (`wiki plugin zotero ...`) that return JSON, rather than using MCP tools for
  local Zotero DB/path operations or exposing Zotero plumbing as normal human
  CLI commands.
- Backend Zotero commands must include status/init diagnostics so missing
  Zotero installs, moved data directories, and unreadable databases produce
  structured states instead of empty search results.
- Backend Zotero PDF resolution must distinguish missing database
  (`db_missing`), missing attachment key (`attachment_key_missing`), and missing
  attachment file (`attachment_file_missing`). It must resolve Zotero `storage:`
  paths under the active data directory and `attachments:` linked-file paths
  against configured linked attachment roots without mutating the Zotero DB.
  Linked attachment root discovery may use Zotero profile `prefs.js`
  `extensions.zotero.baseAttachmentPath` and ZotMoov
  `extensions.zotmoov.dst_dir` values as read-only candidates.
- PDF context commands should accept the richest available identity, not only a
  raw path: local file path, source id, vault relpath, file hash, or Zotero
  attachment key. For Reference Mode stubs, backend resolves the current
  device's real file path from `sources.external_path` or Zotero logic.
- Source import commands used by the plugin may also accept Zotero attachment
  keys. Backend resolves the key, imports the resolved PDF as a Reference Mode
  source, and stores a stable logical source id such as
  `zotero:<attachmentKey>` in the local source registry.
- Dashboard source summaries for Zotero-backed references should expose the
  portable `zotero://open-pdf/library/items/<attachmentKey>` identity for
  display/opening. The local absolute PDF path remains a device-local
  `sources.external_path` hint and must not be treated as a portable source id.
- Snapshot writes should be atomic: write a temporary file in `.curator/runtime/`
  and replace the target path.
- `wiki plugin version` MUST be vault-independent (it powers the update check
  before any vault is selected) and MUST report `repo_path`: the backend's own
  repo root when running from an editable/source checkout (both `setup.sh` and
  `plugin/manifest.json` present at the inferred root), or `null` for a regular
  site-packages install with no repo to update from. The plugin uses this so the
  user never has to configure a "Repository path" manually. The plugin's repo
  path precedence is: explicit `incuratorRepoPath` override → backend-reported
  `repo_path` → none. When none, the plugin hides the update banner instead of
  showing a dead button. `repo_path` is a machine-local value and must only be
  carried in vault-independent JSON / the device-local `devices.json`, never in a
  synced artifact.
- The plugin update action copies the freshly built `main.js` and
  `manifest.json` from `<repo>/plugin/` into the currently open vault's plugin
  directory only. It must not run `git pull` or `setup.sh`; building is the
  user's explicit `setup.sh` step. Other vaults update when next opened.

### 11.3 Agent Access Scenarios

There are two distinct agent scenarios in v0.2.2:

1. **Obsidian agent on the same device as the backend.**
   - Uses shared runtime snapshots for read-only status.
   - Uses hidden `wiki plugin ...` JSON commands for source, PDF, query,
     promotion, Zotero, and backend mutations.
   - Does not auto-start `wiki mcp`.
   - Does not require Incurator MCP tool discovery for model lists, dashboard
     status, source badges, Zotero, PDF context, or query/promotion.

2. **External workspace agents such as Claude Code, Claude Desktop, Antigravity,
   or other MCP-capable clients.**
   - Use `wiki mcp ...`.
   - Use MCP tools such as `curator_query`, `search_curator`,
     `fetch_document_section`, and workspace initialization/check tools.
   - May run with `VAULT_ROOT` or `WORKSPACE_PATH` to scope the server.

Do not mix the two paths. New same-device Obsidian plugin behavior belongs under
`wiki plugin ...` or runtime snapshots. New external-agent behavior belongs in
the MCP server and MCP guides.

Provider account ownership:

- CLI-backed providers (`antigravity-cli`, `claude-code`, `codex-cli`) use the
  account currently logged into the provider CLI on the backend machine. In a
  multi-account setup, users switch accounts through the CLI itself.
- API-key providers (`deepseek-api`) use the configured key. Account selection
  follows the key, not a browser-login CLI session.
- Quota/capacity/rate-limit errors must be surfaced as provider errors, not
  swallowed as empty LLM output; frontend sidechat should render them directly.

### 11.4 CLI Surface Policy

The normal human-facing `wiki --help` command surface should stay focused on the
daily workflow:

```text
init, status, add, build, query, sync, lint, reindex,
source, jobs, config, workspace, version
```

Advanced or integration-only command groups remain directly callable but should
be hidden from the default help listing:

- `wiki plugin ...` — JSON backend API for the local Obsidian plugin.
- `wiki mcp ...` — external workspace-agent server and installer.
- `wiki testbed ...` — development validation fixtures.
- `wiki devices ...` — synced-device/backend launcher diagnostics. Running
  `wiki devices` without a subcommand is equivalent to `wiki devices status`.

The frozen-staging command family is **removed** in v0.3.1: the L4 layer is the shared
Synthesis layer (built automatically by `wiki build`) and curation is a dynamic
query-time lens (`wiki query`). `wiki update` is not part of the public CLI.

Tracked source listing belongs to the source namespace: `wiki source ls`.
The legacy top-level `wiki ls` shorthand is not part of the v0.2.2 public
surface.

Plugin-local JSON commands must be added under `wiki plugin ...` rather than as
new top-level public command groups.

### 11.5 Persona Interview Behavior

The Curator persona interview used by `wiki init` and `wiki persona update`
must ask the first real question immediately after the opener; users must not
need to type a throwaway acknowledgement such as `yes` to begin. Each question
must label whether it accepts a single selection or multiple selections. The
vault verification-source question and artifact-type question accept
comma-separated numeric answers. When the LLM returns final `done=true` persona
JSON, the CLI must parse common JSON wrappers, save the persona, and terminate
the interview without accepting further chat turns.

## 12. Observability

Status surfaces:

- `wiki status` shows per-layer source status and active background jobs.
- `wiki jobs list` shows queued/running jobs.
- `wiki jobs run` drains queued jobs in foreground.
- `wiki jobs cancel <id>` cancels a queued job.
- `wiki jobs rerun <id>` requeues a completed, failed, or cancelled job.
- `.curator/dashboard.md` may summarize job and DAG state for Obsidian viewing.

Status rules:

- "Sources summarized (L1)" means `sources.l1_status='done'`.
- It must not be derived from `sources.status='curated'`.
- L1 complete does not imply L2/L3 complete.
- Source health must be derived from per-layer statuses. Any `error` layer must
  be surfaced as unhealthy even if another layer is complete.
- User-facing source state names are progressive and layer-explicit:
  `l1_ready`, `l2_ready`, `l3_ready` for Concept readiness, and `l4_ready`
  only when shared L4 Synthesis status is done.

## 12.1 Reset Behavior

`wiki reset` preserves `.curator/config.yml` and source folders, but clears
generated and device-local Curator state that can make a fresh vault run appear
stale:

- `.curator/state.sqlite*`
- generated L1-L4 Collections
- dashboard/index/overview/ledger/log files
- `.curator/sync-report.json`
- `.curator/staging/`
- root-level legacy `build_trace_*.canvas` files
- `.cache/config/devices.json`
- `.curator/sessions.json`
- internal DB-native search index rows stored in `state.sqlite`

Build trace canvases are diagnostics and must not be written at `.curator/`
root during normal background builds. If generated, they live under
`.curator/staging/canvas/` so reset and sync-ignore rules can treat them as
transient state.

## 12.2 Search Index Degradation

Search has internal stages:

1. FTS5/BM25 lexical retrieval over authoritative DB records. This is always
   available for a valid SQLite build with FTS5 support.
2. Chunked vector retrieval over `search_chunks` / `search_embeddings`.
3. Typed query expansion (`lex`, `vec`, `hyde`) from deterministic rules and,
   when configured, a search/query-expansion model. Tier-2 LLM/HyDE expansion is
   recovery-only by default: it engages when lexical recall is thin or raw vector
   confidence is below the configured floor, so expansion can add recall without
   perturbing already-confident rankings.
4. RRF fusion with traceable per-list contributions.
5. Configured reranking over best chunks for answer-producing routes.

If embeddings are missing or stale, Incurator must not treat search as failed.
It degrades to FTS5-only retrieval with `vector_unavailable` in the query trace
and runtime status. If the configured query expander is unavailable, deterministic
expansion still runs and `query_expander_unavailable` is recorded. If the
configured reranker is unavailable for `local` or `global` routes, retrieval
proceeds in RRF order and `reranker_unavailable` is recorded. These are degraded
modes, not the parity target.

`wiki reindex` rebuilds DB-native search state: `search_documents`,
`search_chunks`, FTS5 rows, and missing/stale chunk embeddings. It reports counts
for FTS rows, chunks, embedded chunks, skipped unchanged chunks, failures,
provider/model, and degraded state. It does not shell out to an external search
binary.

## 13. Syncthing Device Registry

When a vault is synchronized by Syncthing, Incurator may use the local
Syncthing `config.xml` as device discovery input. This discovery is limited to
facts Syncthing actually knows: device ids, device names, shared folder ids,
folder labels, and folder paths on the current machine.

Backend launch paths are not Syncthing facts. Incurator records those as
per-device declarations in `.cache/config/devices.json`. The Obsidian plugin performs
a best-effort refresh on startup by reading local Syncthing config files and the
current plugin MCP launcher settings. Running `wiki devices sync` remains a
manual repair/debug command, but normal plugin use should not require it.
Running `wiki devices` must inspect the current registry and list devices that
only have Syncthing metadata, even when no backend launcher hint has been
recorded yet.
The Obsidian dashboard follows the same rule: it must not hide a shared
Syncthing device merely because that device has no local backend command or
platform block. Device names come from Syncthing or registry metadata first.
Platform labels are shown only when explicit platform metadata exists; otherwise
the UI labels the platform as unknown instead of inferring unrelated text.
Existing entries for devices still present in the current Syncthing folder are
preserved, including backend launcher hints. Entries absent from the current
shared-folder snapshot are pruned so stale devices do not inflate the registry
or dashboard count. If the local device cannot be identified from Syncthing's
REST status or the configured device names, Incurator must not create a
synthetic `local` device when Syncthing already reports real shared devices.

The Obsidian plugin should keep `data.json` local when backend paths differ by
machine. Shared state, such as chat `sessions.json` and `.cache/config/devices.json`,
can synchronize independently from per-device plugin settings.

## 13.1 Syncthing Auto-Sync (One-Writer-Per-File)

Incurator supports P2P DB synchronization for `state.sqlite` via Syncthing
without a central server. `state.sqlite` itself is device-local (excluded in
`.stignore`); knowledge crosses devices through JSONL snapshot files that *are*
synced.

**Topology — one writer per file.** Each device exports only its own snapshot to
`.curator/sync/dev-<device_id>.jsonl` and imports every *other* device's file.
Because no two devices ever write the same file, Syncthing produces no
write-write conflicts under normal operation. `device_id` is generated once and
stored in `.curator/sync_state.json` (device-local; see §13.3). The exported file
is a **full snapshot** (not a delta) so a late-joining peer always receives the
complete view that device holds.

**Conflict resolution — LWW + tombstones.** Import is a row-level
Last-Write-Wins upsert keyed by each table's `updated_at`/`last_updated` column,
plus tombstone reconciliation via `deleted_records`. There is **no whole-file
replace**, so concurrent offline edits on two devices both survive: the row with
the newer timestamp wins, and a delete wins only when its `deleted_at` is newer
than the competing edit. Import preserves the source row's timestamp and never
stamps `now()`.

**Loop prevention is structural — there is no content-hash guard.** (An earlier
`sync_meta.json` `last_exported_hash`/`last_imported_hash` design was removed: it
silently skipped legitimate imports and reported 0 changes.) Loops cannot form
because: (a) LWW import is idempotent — re-importing a row at the same timestamp
is a no-op; (b) a device never imports its own file; and (c) `wiki db autosync`
exports this device's file only when something actually changed
(`local_has_unexported_changes()` compares the DB's newest timestamp against the
recorded `last_export_ts`). Importing peer data is therefore not, by itself, a
reason to re-export.

**Triggers.** The Obsidian plugin runs `wiki db autosync` (a) once when the
vault loads, (b) when a `fs.watch` on `.curator/sync/` observes a peer file (a
debounced/coalesced scheduler collapses Syncthing's chunked delivery into one
pass and prevents overlapping runs), (c) on a 60-second fallback poll for
platforms where `fs.watch` is unavailable or misses events, and (d) from a manual
"Sync Knowledge DB" ribbon action. The plugin never triggers export on
`Vault.on('modify')` (a markdown-note save is not a DB mutation). CLI users may
set `auto_sync.enabled` so `wiki update` exports this device's snapshot at the
end of a mutation. All heavy JSONL work runs in the backend subprocess, never on
the Obsidian UI thread.

**Syncthing conflict files.** If a `*.sync-conflict-*` file appears in
`.curator/sync/` (e.g. a duplicated `device_id`), `wiki db autosync` imports it
as an ordinary LWW peer — which is always data-safe — then moves it out of the
synced tree into `.curator/runtime/sync_conflicts/` and surfaces a UI notice.

## 13.3 Device-Local Sync State (`sync_state.json`)

`.curator/sync_state.json` holds this device's `device_id`, its `last_export_ts`,
and per-peer `last_imported_mtime` high-water marks (so a peer file is imported
exactly once per change and a late Syncthing delivery is never missed). It MUST
be excluded from Syncthing (`.stignore`); if it were synced, devices would
overwrite each other's marks and trigger re-import storms. The synced
`.curator/sync/` directory itself is NOT excluded — those files are the
transport.

## 13.4 Machine-Local Configuration

Machine-local runtime configuration lives in the project cache config:

```text
.cache/config/config.yml
```

The machine-local config blocks are:

- `llm`
- `search`
- `external`

These blocks may contain provider choices, model cache paths, Ollama/DeepSeek
connection settings, embedding/reranker model paths, external roots, and Zotero
data/attachment roots. They must not be persisted as shared vault truth in
`.curator/config.yml` because each device can have different local paths and
model availability.

`.curator/config.yml` remains vault-scoped and portable. It may hold values such
as `version`, `paths`, `persona`, `sync`, `auto_sync`, and `curate`.

When a backend loads a vault config that still contains `llm`, `search`, or
`external`, it must migrate those blocks into `.cache/config/config.yml` and
remove them from the vault config while preserving the effective merged values.

## 13.2 Chat Query Language And Trace

Plugin chat must use a structured English working-language bridge for every
user question. The plugin derives and passes `input_language`,
`english_query` when already known, and `final_output_language` to
`wiki plugin query`. Backend query code may compute `english_query` when the
plugin cannot, but it must return the resolved field in JSON. Search, intent
classification, MCP/tool arguments, and synthesis context use `english_query`
as the internal working query; the final answer targets
`final_output_language`.

The latest user request decides `final_output_language`; previous turns must not
create a persistent language preference. English latest requests receive English
final answers unless they explicitly ask for another language. `curator_query`
must expose `input_language`, `english_query`, and `final_output_language` in
its plugin JSON response so the language bridge is auditable rather than only a
prompt instruction. These fields are response/trace-only and are never written
into a generated query artifact. Queries do not reuse answer caches, so each
request must produce an answer in its freshly resolved `final_output_language`.

The plugin may compact visible MCP tool output before rendering it into the chat
transcript, but it must preserve parseable `trace` fields so the Sources & Trace
panel can link the evidence used by the sessionless answer.

## 14. Testbed Validation

Any v0.2.2 behavior change must be validated with:

```bash
wiki testbed init <active_scenario> --force
VAULT_ROOT=testbed wiki status
VAULT_ROOT=testbed wiki add
VAULT_ROOT=testbed wiki sync
VAULT_ROOT=testbed wiki lint
```

If LLM, embedding, query-expansion, or reranker dependencies are unavailable,
lower-level deterministic tests must still run and the blocker must be reported.

For instant L1 work, validation must show that `wiki add` can create CTX without
printing or requiring LLM readiness when `llm.instant_l1=true`.
Large-source validation must also show that L1 does not duplicate the full raw
document text while `fetch_document_section` can still return exact evidence
from the original source by `toc_id` or page range.

---

# Curation-Native Behavior

The sections below define the curation-native behavior. Schema records referenced here are defined in
`docs/specs/curator_schema/SCHEMA.md`.

The Curator is a curation-native graph/memory compiler. It
reads a workspace's `curate.yml`, compiles a curation plan, chooses a retrieval
route, builds an evidence pack from source spans / graph / community reports /
memory paths, runs registered and traced prompts, returns a sessionless answer, and
accepts human/agent feedback as a backprop signal.

## 15. Prompt Registry And Tracing

v0.3.1 makes prompts a versioned, contract-driven, traceable subsystem. Prompt
behavior is no longer scattered across `prompts.py`, `query.py`, `lint.py`, and
provisioning code.

### 15.1 Prompt Registry

- Every prompt is a `PromptContract` registered in a `PromptRegistry` with a
  unique `prompt_id`, a `version`, a `family`, a `role`, an input model, an
  optional output model (required for JSON families), system/user templates,
  declared validators, and a retry policy.
- Prompt ids are unique. Backend startup (or a registry self-check) asserts
  uniqueness; a duplicate prompt id is a defect.
- The minimum v0.3.1 prompt families and ids are:
  `curator.source_map`, `curator.knowledge_unit_extract`,
  `curator.entity_relation_extract`, `curator.community_report_write`,
  `curator.synthesis_write`,
  `curator.curation_plan`, `curator.query_router`,
  `curator.query_local_answer`, `curator.query_global_reduce`,
  `curator.query_explore_expand`, `curator.backprop_classify`,
  `curator.backprop_patch_plan`, and `curator.note_context_pack`.
- The clean-rebuild stance applies: prompt text currently in `prompts.py` and
  `query.py` moves into `backend/src/curator/prompting/families/*` and callers
  import the registered contracts directly. No compatibility wrapper functions are
  kept in `prompts.py`.

### 15.2 Prompt Trace

- Every prompt invocation records a `prompt_runs` row (`PTR-…`) with prompt id/
  version/family/role, model provider/name, input/output hashes, validator status
  and errors, retry count, source ids/spans, `curate_spec_hash`, and the owning
  query trace id when applicable.
- A generated artifact (knowledge unit, entity, relation, report, synthesis node)
  must record the `PTR-` that produced it. An artifact that cannot name its prompt
  run is a defect.
- Prompt traces are inspectable through `wiki prompt trace TRACE_ID`, the MCP
  `curator_get_prompt_trace` tool, and the plugin trace panel.

### 15.3 Prompt Validators

Prompt outputs are validated before they are persisted. Required validator
behaviors:

- valid JSON parsed into the declared output model for JSON families;
- only real Curator/source ids (invented `SPAN-`/`ENT-`/node ids are rejected);
- no invented wikilinks to non-existent targets;
- confidence values within `[0.0, 1.0]`;
- source-truth vs derived-insight separation respected;
- no instruction that mutates `03_Notes/`/`04_Resources/`;
- Obsidian-compatible math delimiters preserved.

On a JSON-schema failure, the declared retry policy (default
`json_repair_once`) re-prompts once with the validator error appended; a second
failure marks the run `failed` and must not write a partial artifact.

## 16. `curate.yml` Compilation And Curation Plan

### 16.1 Compilation

- `curate.yml` is parsed into a `CurateSpec` and compiled into a
  `CurationPolicy`: `source_include`/`source_exclude`, `allowed_routes`,
  `default_route`, `prompt_profile`, `require_source_spans`,
  `allow_general_knowledge`, `contradiction_policy`, `backprop_enabled`, and
  `max_explore_followups`.
- `curate_spec_hash` is a stable hash of the workspace's `curate.yml` content. It
  is recorded on curation plans and prompt runs so staleness is detectable.
- `curator_validate_curate_spec(workspace_path)` returns the parsed spec summary,
  the compiled policy, the spec hash, and any validation errors. Invalid specs
  (unknown route, contradictory policy) surface errors instead of silently using
  defaults.

### 16.2 Curation Plan Flow

Before a workspace curation run, the backend generates a `curation_plans` row
(`PLAN-…`):

1. Load and compile `curate.yml` into a `CurationPolicy`.
2. Inventory available sources, entities, concepts, and community reports.
3. Select in-scope sources (respecting `include`/`exclude` and Reference Mode)
   and record excluded sources with reasons.
4. Choose the retrieval mode mix, required community-report levels, target
   concepts/entities, output shape, verification policy, and prompt profile.
5. Record known gaps.

`wiki plugin curate plan --workspace-path PATH` and MCP
`curator_plan_workspace(workspace_path)` record and return the plan. They do not
write a frozen Exhibition.

## 17. Query Routing: local / global / explore / source-section

`wiki query` and `curator_query` route through a single `QueryOrchestrator`.
Routing is deterministic-first; an LLM router (`curator.query_router`) is used
only when deterministic signals are ambiguous.

Routes and selection rules:

- **source-section** — a question scoped to a known source/section id. Answers
  from source spans of that source.
- **local** — entity/fact questions. Resolve query entities (lexical + vector +
  graph), expand to related claims/concepts/spans, build a bounded context pack,
  answer with `curator.query_local_answer`.
- **global** — broad workspace/vault synthesis. Lead with the shared **L4
  Synthesis** nodes (the highest-level standing evidence; SCHEMA §11.11), back them
  with the community reports they distil, run map/reduce with rated intermediate
  points, backfill with source spans, answer with `curator.query_global_reduce`.
  This is the dynamic **Curation lens** in action: it selects/recombines L3+L4
  nodes per query and is never stored.
- **explore** — insight discovery ("what else", "find connections", "new
  insight"). Build a primer from L4 synthesis nodes + community reports, generate
  follow-up questions (`curator.query_explore_expand`), run local searches per
  follow-up, build a memory-path-backed exploration tree, return ranked **insight
  candidates** as provisional (not truth).
Rules:

- An explicit `--mode` wins when the policy allows it; a disallowed mode returns a
  clear error rather than silently downgrading.
- When the graph is incomplete (no entities/relations/reports yet), the
  orchestrator falls back to DB-native retrieval and records a warning in the
  trace. The fallback is FTS5 + available chunk vectors + RRF over authoritative
  DB records, not an external binary.
- Every query produces a `QTR-` query trace carrying `route`, `route_reason`,
  evidence (`source_span_ids`, `community_report_ids`, `synthesis_node_ids`,
  `memory_path_ids`), `prompt_trace_ids`, `insight_candidate_ids`, latency, and
  warnings. The trace is persisted in `query_traces` for every
  `QueryOrchestrator` run, including CLI, MCP, plugin query, plugin quick-query,
  and explore surfaces. These fields are returned in the query JSON (CLI
  `--trace`, plugin, MCP).
- The `fetch_context` surface (MCP `curator_fetch_context`) returns the same
  curated evidence pack — including `synthesis` items and `synthesis_node_ids` —
  WITHOUT a synthesized answer, for reasoning agents that have their own LLM.
- The v0.2.2 language bridge (§11 inherited) is unchanged: detect latest-input
  language, reason in English, answer in the detected language; bridge fields stay
  response/trace-only and are never persisted.

## 18. Backprop Classification And Insight Lifecycle

v0.3.1 routes feedback through an explicit classifier before any patch.

### 18.1 Classification

`curator.backprop_classify` classifies each feedback/change event into exactly
one of:

- `correction` — a generated artifact misread its evidence. Patch the generated
  knowledge unit/entity/relation/report/synthesis node, invalidate dependents,
  preserve source text.
- `contradiction` — two sources/artifacts conflict. Record it, flag both sides,
  surface it in query, inspection, and audit outputs, and require review before any merge that would erase the
  disagreement.
- `derived_insight` — a later interpretation not stated by the source. Create an
  `insight_candidates` row; never write it into the originating source's L1.
- `style_only` — presentation change, no claim change. Update the artifact if
  allowed; do not trigger graph rebuild.
- `promotion_request` — the human wants an artifact to become durable knowledge.
  Requires explicit approval; writes only `02_Wiki/`.
- `ambiguous` — set `status='needs_review'`; do not patch.

### 18.2 Proposal Classification And Review

- `curator_propose_correction(node_id, correction, workspace_path)` runs the
  classifier and returns the classification, recommended action, affected
  generated node ids, review requirement, trace id, and any provisional insight
  candidate.
- A proposal never overwrites source truth or generated nodes automatically.
  Any patching action requires a separate reviewed workflow.

### 18.3 Promotion

- Promotion writes only to `02_Wiki/` and sets `is_verified_by_human=true` for the
  promoted artifact only, never for every cited node.
- `insight_candidates.status='promoted'` is set only by an explicit promotion.

## 19. Source Truth Protection (Behavior-Level)

Enforced across every v0.3.1 flow (extraction, query, explore, backprop,
promotion):

- The Curator never edits `03_Notes/`, `04_Resources/`, or `06_Archives/`.
- A derived insight is never backfilled into the originating source's L1 context
  or into a `source_supported` knowledge unit. It lives as a `derived_insight`
  unit and an `insight_candidate` until explicitly promoted.
- Community-report confidence and memory-path scores are retrieval aids, not human
  verification.
- If a derived insight needs a durable source, it must come from a promoted
  `02_Wiki/` note, a conversation artifact, or an explicit human-created source —
  never from rewriting an existing source map.

## 20. CLI / MCP / Plugin Surface (v0.3.1)

The same backend service functions power CLI, MCP, and plugin JSON. MCP is the
external-agent interface; the plugin uses local `wiki plugin …` JSON commands and
runtime snapshots for same-device flows (the v0.2.2 separation in §11.3 is
retained).

New human CLI commands:

```text
wiki prompt list | show PROMPT_ID | trace TRACE_ID | eval
wiki query "..." --route auto|local|global|explore|source-section [--trace]
wiki inspect synthesis SYN-... [--json]
wiki inspect report REP-... [--json]
wiki inspect answer QTR-... [--json]
wiki insight list --workspace PATH | show INSIGHT_ID | promote INSIGHT_ID
```

New hidden plugin commands:

```text
wiki plugin curate plan --workspace-path PATH --json
wiki plugin prompt trace --trace-id ID --json
wiki plugin insight list --workspace-path PATH --json
wiki plugin insight promote --insight-id ID --workspace-path PATH --json
wiki plugin synthesis list --workspace-path PATH --limit N --json
wiki plugin synthesis show --synthesis-id SYN-... --workspace-path PATH --json
```

New/updated MCP tools (external-agent safe; they call shared services, not
duplicated logic):

```text
curator_plan_workspace(workspace_path)
curator_explore(query, workspace_path="")
curator_get_prompt_trace(trace_id, workspace_path="")
curator_list_insight_candidates(workspace_path="", status="pending")
curator_promote_insight(insight_id, workspace_path="")
curator_validate_curate_spec(workspace_path)
curator_propose_correction(node_id, correction, workspace_path="")
```

`curator_propose_correction` runs the backprop classification lifecycle and
returns a recommended action, affected node ids, and any provisional insight
candidate. `curator_update_node` is disabled and non-mutating. Neither endpoint
directly edits read-only source truth.

`curator_query` returns the v0.3.1 trace fields additively: `route`, `trace_id`,
`prompt_trace_ids`, `source_span_ids`, `community_report_ids`, `memory_path_ids`,
`insight_candidate_ids`, and the existing `answer`/`trace`.

### 20.1 Synthesis Audit Reports

A synthesis audit report is a deterministic inspection payload for proving how a
generated L4 synthesis node, L3 community report, or query answer is grounded.
It is an export/inspection surface only: building an audit report must not call an
LLM, mutate `.curator/state.sqlite`, rewrite projection markdown, or mark any
artifact as human verified.

Audit reports hydrate the evidence chain that already exists in the DB:

- L4 `synthesis_nodes` (`SYN-`) with title, statement, confidence,
  `prompt_run_id`, `community_report_ids`, and `source_span_ids`;
- L3 `community_reports` (`REP-`) with findings, entity ids, relation ids,
  prompt trace, dependency hash, and cited source spans;
- L3 graph entities and relations named by those reports;
- L2 `knowledge_units` (`KNU-`) whose `source_span_ids` intersect the audited
  source spans or whose ids are reachable from the audited entities;
- L1 `source_spans` (`SPAN-`) with source path, page/section metadata,
  `content_hash`, and text preview;
- prompt traces (`PTR-`) for synthesis/report/unit generation when present;
- query trace (`QTR-`) evidence when inspecting an answer.

The payload must include `warnings` instead of crashing when references are
missing or stale. Required warnings include missing synthesis/report/span rows,
missing prompt traces, unresolved graph endpoints, stale dependency hashes, and
weak grounding when a generated artifact has no cited source spans. Staleness is
computed from `artifact_dependencies.dependency_hash` where dependency rows
exist, and from `dependency_hash` fields on reports/synthesis nodes when the
audit cannot resolve a finer dependency edge.

Report selection remains conservative in this milestone. Global query answers
may continue to use the existing community-report set, but the persisted
`QTR-` must record the selected synthesis/report ids and any excluded stale
reports. Algorithmic upgrades such as modular community detection or DRIFT-like
exploration trees are deferred until audit/export surfaces prove the existing
pipeline.

## 21. Testbed Validation (v0.3.1)

The default scenario is `tests/scenarios/complex_math_backprop` (ResNet / Neural ODE).
Beyond the v0.2.2 smoke (§14), v0.3.1 validation must show:

- original ResNet source claims remain `source_supported` only;
- the later Neural ODE interpretation becomes a `derived_insight` / insight
  candidate, not a rewrite of the original ResNet L1;
- a global query uses a community report;
- an explore query returns a memory path between residual learning and Euler
  discretization;
- backprop classification does not rewrite the original L1;
- prompt traces are visible for generated artifacts.

If LLM, embedding, query-expansion, or reranker dependencies are unavailable,
deterministic tests, prompt validators, and the `local_slm_simulator` role still
run, and the exact blocker is documented; the scenario is not reported as passed.

## 22. Compile Model: DB Source Of Truth, Derived Markdown Projection

v0.3.1 makes the Curator a compiler whose intermediate representation is the DB
and whose L1–L3 markdown pages are a derived, disposable search corpus. This is
grounded in `docs/philosophy/ABOUT.md` (".curator/ = Database for search and
reasoning"; Curator = Knowledge Compiler; Forward/Backward pass).

### 22.1 Forward Compile Flow

```
Raw source
  └─ parse (deterministic, NO LLM, instant)
       → DB: source_spans                          (L1)
       → emit .curator/Collections/01_Contexts/CTX-*.md   (derived projection)
  └─ LLM refine (local SLM / non-reasoning model)
       → DB: knowledge_units                        (L2)
       → emit .curator/Collections/02_Atoms/ATM-*.md      (derived projection)
  └─ LLM + embeddings
       → DB: graph_entities, graph_relations, community_reports   (L3)
       → emit .curator/Collections/03_Concepts/CON-*.md   (derived projection)
  └─ LLM synthesize (cross-community, source-grounded)
       → DB: synthesis_nodes                        (L4 Synthesis, shared)
       → emit .curator/Collections/04_Synthesis/SYN-*.md (derived projection)
  └─ DB-native search index update
       → search_documents/search_chunks, FTS5, chunk embeddings
  └─ query/curate: typed expansion + FTS5 + chunk vectors + RRF + configured rerank
       plus DB graph traversal (HippoRAG)
       → dynamic Curation lens over L3/L4 (per workspace/query, never stored)
```

Rules:

- The DB is the single source of truth. L1–L4 markdown is emitted FROM the DB and
  is never edited as truth, so there is no DB↔file drift.
- **L4 Synthesis** (`synthesis_nodes` / `SYN-`) is a shared, workspace-INDEPENDENT
  layer distilled from all community reports (the "synthesis"/permanent-note tier
  of other LLM wiki repos). It is generated wholesale and content-addressed by the
  report-corpus hash, so it is skipped when nothing changed and regenerated
  entirely when any report changes (`compile_global_l3` → `generate_synthesis`).
  The per-workspace **Curation lens** sits ABOVE this layer: it selects and
  recombines L3/L4 nodes at query time and is never persisted (see SCHEMA §11.11).
- L1 (source_spans / CTX) is deterministic structure preservation, not
  refinement. It must not require an LLM (the v0.2.2 instant-L1 guarantee holds).
  Knowledge refinement happens at L2/L3 via the LLM prompt families.
- The emitted markdown is an Obsidian convenience projection, not the search
  corpus. Search reads DB-native `search_documents`, `search_chunks`, FTS5 rows,
  and chunk embeddings.
- Query expansion and reranking are v0.3.2 quality requirements. If a configured
  query-expansion model or reranker is unavailable, the query may proceed through
  deterministic expansion and RRF-only order, but the trace must explicitly record
  the degraded stage.

### 22.2 Backprop Re-emission (Loss Signal → Backward Pass)

- `curator_propose_correction` lets external agents submit correction proposals.
  It classifies each proposal (§18), returns the recommended action and affected
  node ids, and may create a provisional insight candidate. It does not patch
  generated nodes automatically; ambiguous changes require review.
- `curator_update_node` is disabled and non-mutating.
- Backprop is **correction-driven and independent of query artifacts**. Any
  approved follow-up patch must protect source truth and human-verified
  `02_Wiki/` promotions.

### 22.3 Directory Roles (Two-Track)

- `.curator/` — AI-Only Space: `state.sqlite` (source of truth), DB-native search
  indexes/traces, the derived `Collections/` Obsidian projection, and `runtime/`
  snapshots. Hidden; not a user concern.
- `02_Wiki/` — Human-Only Space: explicitly promoted human knowledge only.
- `wiki reset` may delete the entire derived `Collections/` projection because it
  is rebuildable from the DB (and the DB from source truth).

## 23. v0.3.2 DB-Native Search Providers, Traces, And Dashboard Actions

### 23.1 Provider Contracts

v0.3.2 introduces backend-owned providers for:

- **embeddings**: `embed(texts) -> list[float32_vector]`
- **query expansion**: plain question + route/context -> typed `lex` / `vec` /
  `hyde` expansions
- **reranking**: query + best candidate chunks -> relevance scores/order

The active provider, model, dimension, and degraded state must be recorded in
runtime status and query traces. Generic chat-model reranking is a degraded
fallback only; the parity target is a search reranker/cross-encoder or validated
search-fine-tuned local model. Query expansion and reranking are quality
requirements: when unavailable, the trace must say exactly what was skipped and
which deterministic fallback ran.

The default v0.3.2 search model profile is local-first and llama-cpp based:
`llama-cpp::qwen3-embedding-0.6b` for chunk embeddings and
`llama-cpp::qwen3-reranker-0.6b` for answer-path reranking. Implementations must
validate installed GGUFs with a live smoke check before using them for parity
claims; if validation fails, search degrades to FTS5/RRF with explicit warnings.
The optional local query-expansion GGUF provider uses qmd-compatible structured
lines (`lex:`, `vec:`, `hyde:`) and must remain fail-safe; if it is absent or too
slow, the chat-client expander or deterministic Tier-1 expansion remains valid.
Before loading llama-cpp search GGUFs, Incurator should issue a best-effort
Ollama `keep_alive=0` unload request for configured Incurator Ollama LLM models
to reduce VRAM contention. It must not unload arbitrary Ollama models belonging
to other applications by default.

### 23.2 Retrieval Trace Contents

Every `QTR-` trace must persist enough retrieval metadata for debugging and
dashboard display:

- deterministic and model-generated expansions
- rejected malformed expansions
- FTS candidate ids and ranks
- vector candidate chunk ids and scores
- RRF contribution list (`source`, `query_type`, rank, weight, contribution)
- reranker provider/model, best chunks, scores, and degraded reason if skipped
- selected evidence ids used by synthesis

Raw prompt bodies are not required in `query_traces`; prompt-level hashes and
validator status remain in `prompt_runs`.

### 23.3 Plugin Dashboard Click-To-Use Commands

The hidden same-device plugin command namespace gains:

```text
wiki plugin trace list --workspace-path PATH --limit N --json
wiki plugin trace show --trace-id QTR-... --workspace-path PATH --json
wiki plugin synthesis list --workspace-path PATH --limit N --json
wiki plugin synthesis show --synthesis-id SYN-... --workspace-path PATH --json
wiki plugin insight show --insight-id INS-... --workspace-path PATH --json
wiki plugin insight reject --insight-id INS-... --workspace-path PATH --reason TEXT --json
wiki plugin correction propose --node-id ID --correction TEXT --previous TEXT --workspace-path PATH --json
```

Dashboard trace/insight actions must call backend commands. The plugin must not
edit `.curator/state.sqlite`, `.curator/Collections/`, `03_Notes/`,
`04_Resources/`, `06_Archives/`, or runtime snapshots directly. Insight promotion
requires explicit confirmation and writes only to `02_Wiki/`.

Dashboard synthesis actions are read-only. The Synthesis/Graph view lists recent
L4 `SYN-` nodes and opens `wiki plugin synthesis show` details so the user can
inspect the L4→L1 evidence chain without manual SQLite access.

## 24. Git Integration (v0.5.3)

### 24.1 Local Git Only — No `gh` Dependency
The system uses the local `git` binary only. It has **no** GitHub CLI (`gh`)
dependency: `setup.sh` does not install `gh`, the plugin has no GitHub
sign-in/out UI, and `git_manager.status()` exposes no GitHub-account fields.
Authentication for pushing over HTTPS, if used, is handled by the user's normal
git credential helper, outside Incurator. The plugin **must not** store OAuth
tokens internally.

### 24.2 Status, History, And Push Workflow
The plugin UI **will not** expose manual `Commit` or `Push` buttons. Git
operations are mediated through sidechat and hidden backend JSON commands
implemented by `git_manager.py`.

The default workflow assumes the vault may already have scheduled commit jobs.
Therefore sidechat requests such as `push해줘` must push existing commits rather
than creating a new commit first. Explicit commit requests may call a guarded
commit primitive, but commit creation is not the default sync path.

The backend exposes:

```text
wiki plugin git status --json
wiki plugin git log --limit N --json
wiki plugin git diff --stat --json
wiki plugin git history --file-path PATH --query TEXT --limit N --json
wiki plugin git push --json
wiki plugin git commit --message TEXT --json
```

`git history` is used for Markdown selected-text/file history questions. It
searches the active file's history for the selected text or a normalized excerpt,
then returns matching commits and capped patch snippets. Paths outside the vault
root are rejected.

`git push` refuses unsafe states: no repository, no upstream, conflicted working
tree, branch behind/diverged from upstream, or missing `git`. It must not merge,
rebase, or commit implicitly.

### 24.3 State Exclusions
Git's own ignore rules are authoritative. Backend Git operations must stage or
inspect files according to `.gitignore`; ignored files are not added. The
`.curator/` directory and local SQLite/vector/search indexes should be excluded
from Git tracking. If `.curator/` is not ignored, status returns a warning rather
than silently editing `.gitignore`.

## 25. Failure Atlas Diagnostic Contract (v0.6.0)

v0.6.0 is a diagnostics-only release: it changes **no** runtime behavior,
schema, or API. It freezes the Program-1 truth contract for the RAG & Knowledge
Quality Stabilization program as a versioned Failure Atlas.

- The atlas contract, case records (F1–F13), evaluation baseline, frozen
  fixture corpus, and qrels live in `docs/specs/failure_atlas/`
  (`FAILURE_ATLAS.md` is the contract; `cases/F*.yml` are the authoritative
  machine-readable records).
- Every known end-to-end quality failure is classified
  (`reproduced`/`disproven`/`accepted`/`assigned`) with a minimal deterministic
  fixture, exact code boundary, capture-before-repair evidence, and a
  downstream owner (Plan D2, Program 2, or Program 3).
- Reproduction tests in `backend/tests/test_failure_atlas_repro.py` encode the
  contract mechanically: `*_baseline_*` tests assert the current defective
  behavior (they pass today and pin it), `*_oracle_*` tests assert the desired
  contract as strict xfail. Fixing a failure makes its oracle XPASS and fails
  CI until the fixer deliberately removes the marker and updates the atlas
  record in the same change — downstream programs cannot silently redefine an
  oracle.
- The deterministic retrieval baseline (lexical mode, frozen synthetic corpus)
  and the no-tuning holdout discipline are specified in
  `docs/specs/failure_atlas/EVALUATION_BASELINE.md` and enforced by
  `backend/tests/test_failure_atlas_eval.py`. Proposed thresholds in that
  document are not binding until user approval.

### 25.1 D2 Minimum Quality Observatory (v0.7.0)

- Search-hit evidence preserves the hydrated `source_span_ids` supplied by the
  DB-native engine.
- A query executed through `QueryOrchestrator` persists exactly one
  authoritative `QTR-`; the engine retrieval trace is embedded in that row
  rather than persisted as a disconnected second trace.
- Fine-grained retrieval evaluation reports Recall@k, MRR, top-1 citation
  correctness, citation completeness, provenance resolution, hard-negative
  outranks, indexed-character cost, and latency separately per query family.
- The frozen Failure Atlas holdout has one final valid no-tuning result after
  two transparently audit-invalidated methodology runs. CI validates the
  committed result and never reruns it.
- The tracked testbed template is the current-architecture F13 oracle and
  covers truth, DB-native retrieval, agent reuse, and incremental correctness.

## 26. Evidence Compiler Integrity (Plan B, v0.8.0)

v0.8.0 is the first Evidence Compiler Integrity release. It makes Markdown/PDF
source truth compile into stable, minimal, claim-level grounded L2 knowledge
without formula loss, unsupported broad-span grounding, duplicate
accumulation, stale records, or partial authoritative publishes. The frozen
schema names live in SCHEMA.md §20; this section freezes the behavior.
Owned failure-atlas cases: F6, F7, F10. F8/F9 (graph) stay with Plan C;
F3/F4/F5/F11/F12 stay with Program 3.

### 26.1 Claim-Level Minimal Support Lifecycle

- Extraction (the versioned knowledge-unit prompt contract) must declare, per
  claim, the minimal span set that entails it, with roles
  `primary | contextual | formula`. The compiler persists these as
  `claim_supports` rows in the `unchecked` state.
- Support validation runs a deterministic STRUCTURAL gate first, then a
  calibrated model only to adjudicate what the gate leaves uncertain. The gate
  operates on the cited span's full source text (hydrated — never the 200-char
  `text_preview`), so it generalizes to any production claim. It is NOT a lookup
  against the labeled gold fixtures: `plan_b_compiler_gold.yml` is the test-time
  release oracle that scores the gate's accuracy, never a runtime table (a
  fixture lookup would overfit CI and leave real vaults unprotected). The gate
  yields one of three verdicts per claim:
  1. `verified` — the cited span structurally supports the claim. For
     formula-bearing claims, every claim formula is structurally present in the
     span (formula rule below). For text claims, the claim's salient
     content/entity terms intersect the span above the support threshold.
  2. `failed` — no cited span structurally supports the claim: zero/low entity
     intersection (the F6 wrong-real-span case) OR a formula that is absent from
     or altered relative to the span. Recorded with a reason; release-blocking.
  3. `uncertain` — structurally plausible but ambiguous (heavy paraphrase or
     logical deduction). Escalated to secondary calibrated model validation,
     recorded with a `PTR-` validator trace; left `unchecked` when no model is
     available rather than promoted.
  A valid span id alone NEVER proves support (the F6 anti-pattern), and a
  semantic-similarity/NLI score alone NEVER verifies a formula.
- Formula structural rule (deterministic, no CAS): a claim's LaTeX formula —
  unescaped inline `$...$` or display `$$...$$` — is "present" in a span iff,
  after normalization (strip whitespace and spacing macros such as
  `\,`/`\!`/`\;`, while preserving grouping braces), its ordered token sequence is an exact
  contiguous subsequence of some formula in the span. This admits a faithful
  extracted sub-formula (`M` from `M = \int \rho dV`) while preserving
  operation direction and binding: `a^b` ≠ `b^a`, `a-b` ≠ `b-a`, and
  `\frac{a}{b}` ≠ `\frac{b}{a}`. No commutative reordering is inferred without
  an AST/CAS. A central formula present in no cited span is
  `formula_status='missing'`; a structurally altered one is a `failed` support,
  never silently accepted. For a formula-only atomic unit with no prose terms,
  an ordered structural match is sufficient support; prose overlap is not
  required when there is no prose to score. If its formula is absent or altered,
  it routes to `uncertain` for P5 selective recovery rather than failing the
  prose-overlap gate. A claim with neither salient prose nor a formula fails as
  invalid/empty. Escaped currency/literal dollars (`\$`) are never formula
  delimiters.
- A claim whose cited spans fail minimal-support validation is marked
  `support_status='failed'` with a reason; it is excluded from downstream
  compile stages and flagged by the compiler audit. Wrong-real-span citations
  are a release-blocking gate (0 accepted on gold fixtures).
- Evidence freshness: every audit pass re-compares `claim_supports.evidence_hash`
  against the cited span's current `content_hash`; a mismatch marks the
  support row and unit `stale`. Stale units leave downstream surfaces until
  re-validated against current source truth.
- Broad-fallback removal: no Plan-B-owned source-pair/L2 or non-graph
  generated-claim path may substitute an all-upstream-span set for missing
  claim-level support. Downstream compiler prompts receive claim-scoped
  evidence only. Graph/community-report fallback occurrences are measured,
  reported by the audit, and handed to Plan C explicitly.

### 26.2 Formula Lifecycle And Selective Recovery

- Formula-preserving distillation (adopted Plan E contract): every
  distillation stage carries an explicit preservation check — the formula set
  present in authoritative extraction must be a subset of
  distillation-visible evidence, or an explicit recorded exception
  (`omitted_incidental` with reason code) exists. Silent formula drops are a
  release-blocking defect. Visual recovery is NOT a substitute for this check.
- Central formulas survive in one of two valid forms (Arena decision 7):
  intact in the concise claim text (`formula_status='preserved_in_text'`), or
  exactly referenced formula evidence (`linked_evidence` + a `formula`
  support row). Destructive central-formula truncation in graph input and
  search materialization is removed.
- Selective recovery runs only after a measured loss verdict
  (`fragmented | image_only | parser_omitted`) where parser output, raw text,
  and current extraction all either miss the region OR yield a
  structurally-invalid (garbled) rendering of it — `fragmented` is the
  present-but-corrupt case (e.g. a parser that drops `\nabla`/superscripts or
  splits a `$$` block), distinct from total absence. A P4
  `formula_status='uncertain'` verdict on a central formula (a claim-vs-span
  ordered-token mismatch on a lossy source, §26.1) is the upstream signal that
  routes a region into this classification; validated recovery then re-validates
  the owning claim (`uncertain` → `verified` against the recovered evidence, or
  `missing` if unrecoverable), never a silent flip to verified. Whole-corpus/
  every-page VLM processing is rejected. Recovery output is additive
  (`source_spans.metadata.formula_recovery`, SCHEMA §20.4), labeled with full
  lineage, and lifecycle-gated (`candidate | reviewed | rejected`) — parseable
  LaTeX alone verifies nothing.
- Below-threshold confidence keeps a claim's `formula_status='uncertain'`
  and out of served formulas. A changed page hash invalidates exactly that
  page's candidates.

### 26.3 Staged Compile Generations And Atomic Publish

- Every Plan-B-owned compile runs inside a `GEN-` generation
  (SCHEMA §20.3). Rows, dependency records, markdown projections, and
  search-derived state for the scope publish together or not at all.
- Publish gate: the generation flips to `authoritative` only after the
  compiler audit validates required rows, dependencies, projections, and
  search materialization for its scope. Failed validation discards the staged
  generation; the prior authoritative generation, its projections, and its
  search state remain untouched and continue serving.
- Unchanged rebuild is idempotent: same source content + same prompt contract
  version reuses the authoritative generation's claim ids, hashes, dependency
  closure, and counts — no duplicate accumulation, no count amplification.
- Query, evidence, and search surfaces read only authoritative-generation
  rows. Staged rows are invisible everywhere outside the compiler.

### 26.4 Source Edit/Delete/Split Reconciliation

- A source edit/delete/split triggers reconciliation over the complete
  measured downstream dependency closure (via `artifact_dependencies`):
  - unchanged claims (per `semantic_hash` candidates + validation) keep their
    ids and verified supports;
  - changed claims are re-extracted and re-validated within the new staged
    generation;
  - claims whose source basis disappeared are retired (`retired_at` set),
    never silently deleted; their dependents are invalidated and regenerated
    or retired;
  - stale spans of the edited source are reconciled (removed or tombstoned)
    instead of lingering beside their replacements (F7).
- `semantic_hash` proposes reconciliation candidates only; materially
  different claims/equations are never auto-merged. Stable-id reuse additionally
  requires exact statement equality after whitespace normalization; the lossy
  semantic hash or term-set normalization alone can never authorize reuse.
- One-source mutation regenerates only the expected dependency closure —
  measured and asserted by tests, not assumed.

### 26.5 Compiler Audit Surface

- The audit is read-only and runs (a) as the staged-generation publish gate
  and (b) on demand via `wiki lint`, which gains a Compiler Integrity section
  reporting: unsupported/failed/stale claim counts, evidence-hash mismatches,
  broad-fallback findings (with Plan-C assignment for graph/report cases),
  orphan/staged leftovers, duplicate-claim candidates, and formula-status
  inconsistencies (SCHEMA §20.5 assertions).
- `wiki lint` exits non-zero when a release-blocking audit assertion fails,
  so CI and the testbed can gate on it. Existing lint checks are unchanged.
- Surface scope: CLI only in v0.8.0. No MCP tool schema changes and no plugin
  contract changes (PLUGIN_SCHEMA.md is intentionally untouched apart from the
  synchronized version title). MCP/plugin clients observe Plan B only through
  better evidence: full-span hydration (SEARCH_ENGINE_SCHEMA §10) and
  support/formula labels already carried on returned records.

### 26.6 Migration Rehearsal And Rollback Acceptance Criteria

The v8 migration (SCHEMA §20.6) ships only with a rehearsed rollback path.
Acceptance criteria — ALL must pass before the migration may touch a real
vault DB, and they are encoded as tests in P3:

1. Rehearsal runs on a disposable copy of the pre-implementation backup
   (`.agents/backups/b-pre-implementation-state.sqlite`) — never first on the
   live testbed DB.
2. Post-migration: `PRAGMA integrity_check` = ok; `schema_version` row = 8;
   all pre-existing row counts unchanged; every legacy `knowledge_units` row
   reads `support_status='unchecked'`, `formula_status='not_applicable'`,
   `retired_at IS NULL`, `generation_id IS NULL`; zero `claim_supports` and
   zero `compiler_generations` rows exist.
3. Idempotency: running the migration twice is a no-op the second time.
4. Round-trip: `wiki db export` → `wiki db import` on a migrated DB preserves
   the new tables/columns; tombstones for the two new tables apply
   deletion-before-upsert as in §13.1.
5. Restore drill: replacing the migrated DB with the backup and re-running
   the migration reproduces an identical schema fingerprint (SHA-256 over
   ordered `sqlite_master` DDL).
6. Failure rollback: if migration or the post-migration audit fails, restore
   the DB backup, discard staged generations, re-emit projections/search from
   the prior authoritative state, and (after three repeated QA failures)
   return to planning via the rollback strategist.
7. Clean rebuild remains available: source truth under `03_Notes/` /
   `04_Resources/` is never modified by migration, compile, or rollback.

### 26.7 Testbed Validation (Plan B)

- The confirmed active scenario is initialized and exercised with
  `VAULT_ROOT=testbed wiki status|add|update|lint`; the historical
  `complex_math_backprop` scenario is rewritten as the math-specific scenario
  against current DB-native L1-L4 and Reference Mode behavior rather than
  assumed to exist.
- Markdown, local PDF, and Reference Mode external PDF paths are all
  validated. Provider-backed extraction/recovery runs where available;
  otherwise every deterministic/local-simulator gate runs and the exact
  provider blocker is documented (this is the only accepted gap).
- No source or reference file is autonomously edited at any point.
