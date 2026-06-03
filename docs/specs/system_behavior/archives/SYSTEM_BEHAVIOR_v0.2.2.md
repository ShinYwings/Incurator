# Incurator - System Behavior (v0.2.2)

This document represents the most concrete layer (`spec`) of the documentation hierarchy (`philosophy` -> `guides` -> `spec`). It is the absolute behavior source of truth for the v0.2.2 line. It defines how the backend, plugin, MCP tools, and workspace agents interact. Schema details live in `docs/specs/curator_schema/SCHEMA_v0.2.2.md`.

Implementation plans under `.agents/plans/` are transient and strictly subordinate to this document. If a plan conflicts with this behavior contract, update the plan or bring the conflict back to review before coding.

## 1. v0.2.2 Goal

v0.2.2 changes Incurator from a blocking eager DAG compiler into a two-track
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
- rendering progress/status/trace returned by backend tools or backend-owned
  shared status snapshots

The plugin must not mutate `.curator/state.sqlite` or `.curator/Collections/`
directly. The only v0.2.2 exception is `.curator/devices.json`, which the
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

When a PDF or document is opened, the same-device Obsidian plugin computes a
SHA-256 file hash and calls `wiki plugin source status --file-hash ... --json`.
External workspace agents use the equivalent MCP `check_source_status` tool.

### 3.1 Unregistered Source

Expected behavior:

1. Backend returns `registered=false`.
2. Plugin may build an ephemeral L1 from PDF.js or viewer text.
3. Agent can answer using plugin-served `fetch_document_section` data.
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

The backend must not create a source row from passive viewing alone.

### 3.2 Registered, L1 Complete, L2/L3 Pending

Expected behavior:

1. Backend returns `registered=true`, `l1_complete=true`, and pending L2/L3 state.
2. Agent may call `fetch_document_section` against backend CTX sections.
3. `curator_query` may report that the document is not fully compiled yet if it
   requires L3 Concepts.
4. Background worker, **Incurator Dashboard > Jobs > Run queued**, or
   `wiki jobs run` continues L2/L3 extraction.

This is the normal fast path after `wiki add` in v0.2.2.

PDF viewer questions and durable PDF knowledge refinement are separate user
flows. Viewer questions should answer from local PDF/page/selection/crop context
without requiring ingestion. Purple PDF chips and Add-to-Incurator actions start
durable refinement by registering the source, producing instant L1, and queueing
L2/L3 jobs; they must not block until L2/L3 or L4 completes.

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
- L3 sub-agent clusters Atoms into Concepts. It should prefer local embedding
  clustering (Ollama embeddings first, sentence-transformers/sklearn when
  available) and use the LLM clustering-plan call only as a fallback. Concept
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
- Ollama local embeddings are preferred when an Ollama host is active.
- `sentence-transformers`/`scikit-learn` may be used as local CPU fallback.
- If no embedding path is available, the legacy LLM clustering planner remains
  valid.
- Concept page drafting may still use an LLM after clusters have been chosen.

## 8. Incremental Sync And Backprop

Default `wiki sync` behavior in v0.2.2 is incremental:

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
- MCP `curator_update_node` defaults to L4 -> L3 -> L2 -> L1 propagation.
  Insight backprop is expected to be rare, so graph consistency is prioritized
  over single-call latency. L1 updates must preserve original source truth while
  recording derived corrections separately. `propagate_sources=false` is reserved
  for explicit Concept-only diagnostic paths.
- For MCP updates where the previous Exhibition content is available, upstream
  propagation must target the Concepts most related to newly added/changed
  Exhibition text before invoking the LLM. Concept reconciliation should batch
  multiple targeted Concepts into one structured LLM call when the provider
  supports JSON output, and unchanged Concepts may be omitted from that response
  so model output is proportional to actual edits. Invalid batch output must use
  a safe fallback to per-Concept calls. Reconciled
  Concepts may then propagate to L2 and L1, but only when the upstream node
  actually changed. Propagation responses should expose `target_concepts`,
  `llm_calls`, and `timings_ms` so clients can diagnose latency without
  weakening backprop depth.
- Identical EXH submissions are no-ops. `curator_update_node` must return
  `noop=true`, `updated=false`, and `propagation.llm_calls=0` without invoking
  the LLM or rebuilding routing tables.

## 9. Query-Time Exhibition Behavior

`curator_query(question, workspace_id, force_new=false)` is the v0.2.2 MCP entry
point for sidebar-style concept-grounded answers after L3 exists.

Expected behavior:

1. Resolve `workspace_id`.
   - From active workspace basename if a workspace path is available.
   - Otherwise `default`.
   - A plain chat turn whose active note is **not** inside a workspace folder
     (no ancestor `curate.yml`) is treated as outside a workspace and MUST
     resolve to `default`. The plugin must not fall back to an arbitrary
     workspace (for example the first `curate.yml` found in the vault); binding
     an unrelated workspace to a conversational chat is a defect. The resulting
     ephemeral EXH therefore carries `workspace_id: default`, never an unrelated
     project workspace the user did not open.
2. If L3 Concepts do not exist yet, return `ok=true`, `fallback="l3_incomplete"`,
   `answer=""`, raw fallback hits when available, and `trace.l3_complete=false`.
   The client must then use L1/source-section or local PDF context rather than
   pretending concept-grounded retrieval succeeded.
3. Retrieve relevant L3 Concepts and source provenance.
4. Synthesize or reuse a query-generated Exhibition. Workspace-scoped queries
   must still save an ephemeral query-generated EXH so repeated identical
   questions can return from cache without another LLM synthesis call.
5. Return answer content plus trace.

The Obsidian sidechat uses this behavior directly through the hidden
`wiki plugin query` JSON command for ordinary workspace/domain questions. It
must not wait for an external Incurator MCP server to be discovered before it
can create or reuse a query-generated Exhibition. If the latest user turn is
centered on selected Markdown, a line-range edit, a PDF page reference, or a
selected PDF/image crop, sidechat treats that selected context as primary and
does not start workspace-wide Exhibition generation for that turn.

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

The Incurator MCP server exposes over 40 tools. The following list highlights the *newly introduced tools specific to v0.2.2 behavior*. For a complete and exhaustive list of all MCP tools and their descriptions, please see [MCP_USER_GUIDE.md](file:///Users/shin/shinywings/Incurator/docs/guides/MCP_USER_GUIDE.md).

v0.2.2 introduces these new core MCP tools:

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
persisted into saved query-generated EXH frontmatter. Persisting them caused a
stale `final_output_language` to force later English/Chinese questions to keep
answering in the earlier language; saved EXH pages therefore omit them entirely.

Query-generated EXH pages remain valid cache/trace artifacts. Their
question/persona/context fields must be derived from the current query and
active chat/workspace context, not a stale session-level language or unrelated
workspace default.

### 11.2 Plugin Dashboard State Sharing

The Obsidian plugin dashboard should synchronize backend status through
backend-owned shared files rather than MCP tool discovery or a plugin-specific
IPC process.

Canonical runtime snapshots live under:

```text
.curator/runtime/
```

Recommended files:

- `.curator/runtime/status.json` — vault health, source layer counts, active job
  counts, qmd/BM25/vector readiness, backend version, and generated timestamp.
- `.curator/runtime/sources.json` — read-only source rows needed for dashboard
  and source chips.
- `.curator/runtime/jobs.json` — active/recent background jobs and errors.

Rules:

- Backend code is the single writer for `.curator/runtime/*.json`.
- The plugin may read these files directly through the Obsidian vault adapter.
- The plugin must treat missing or stale snapshots as "unknown/waiting", not as
  proof that backend state is empty.
- Runtime snapshots must be derived from backend-owned state (`state.sqlite`,
  qmd metadata, job queue, config) and must not become a second source of truth.
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
- Snapshot writes should be atomic: write a temporary file in `.curator/runtime/`
  and replace the target path.

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
- `wiki curate ...` — advanced/workspace-agent L4 Exhibition generation.

`wiki refresh` is the public forward-propagation command for refreshing L4
Exhibitions from changed L3 Concepts. `wiki update` is not part of the v0.2.2
public CLI.

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
  only when L4 Exhibition status is done.

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
- `.curator/devices.json`
- `.curator/sessions.json`
- qmd's generated index database

Build trace canvases are diagnostics and must not be written at `.curator/`
root during normal background builds. If generated, they live under
`.curator/staging/canvas/` so reset and sync-ignore rules can treat them as
transient state.

## 12.2 Search Index Degradation

qmd indexing has two layers: `qmd update` for lexical/BM25 search and `qmd embed`
for vector search. If `qmd update` succeeds but `qmd embed` fails, Incurator must
not treat the whole index rebuild as failed. It should report a degraded result:
BM25 search is current, vector search is stale, and the user can retry
`wiki reindex` after qmd embedding support is healthy.

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
machine. Shared state, such as chat `sessions.json` and `.curator/devices.json`,
can synchronize independently from per-device plugin settings.

## 13.1 Chat Query Language And Trace

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
into the saved EXH frontmatter.

The answer cache key incorporates the resolved output language so that the same
normalized question asked in different input languages does not collide. A
Korean-language cached answer must never be returned for an English query (or
vice versa); the cache key is derived from `(workspace_id, normalized_question,
final_output_language)`. This guarantees a freshly detected English request is
answered in English even when an earlier Korean turn cached the same question.

When `curator_query` creates or reuses a query-generated Exhibition, the plugin
may compact visible MCP tool output before rendering it into the chat transcript,
but it must preserve parseable `exhibition_id` and `trace` fields so the
Sources & Trace panel can link the generated L4 Exhibition.

## 14. Testbed Validation

Any v0.2.2 behavior change must be validated with:

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
Large-source validation must also show that L1 does not duplicate the full raw
document text while `fetch_document_section` can still return exact evidence
from the original source by `toc_id` or page range.
