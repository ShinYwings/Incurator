# Incurator - System Behavior (v0.36.0)

This document represents the most concrete layer (`spec`) of the documentation hierarchy (`philosophy` -> `guides` -> `spec`). It is the absolute behavior source of truth. It defines how the backend, plugin, MCP tools, and workspace agents interact. Schema details live in `docs/specs/curator_schema/SCHEMA.md`.

Implementation plans under `.agents/plans/` are transient and strictly subordinate to this document. If a plan conflicts with this behavior contract, update the plan or bring the conflict back to review before coding.

Sections 1-22 below define the behavior contract. The system uses DB-native search, query expansion, chunk vectors, RRF, configured reranking, and durable query traces. Historical behavior definitions are tracked via git history.

The current path is the only supported behavior contract. It has no
prompt-function wrappers, legacy-query fallback path, `curate.yml`
persona-to-KRS auto-mapping, or external search runtime fallback.

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

- repo-cache `state.sqlite`
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

The plugin must not mutate repo-cache `state.sqlite` or `.curator/Collections/`
directly. The only v0.2.2 exception is `.cache/config/devices.json`, which the
plugin may refresh on startup as sync-friendly device metadata. All durable DAG,
source registry, ingest, and backpropagation writes must go through backend code.
For read-only dashboard synchronization, the preferred boundary is a backend-owned
local JSON snapshot under repo-cache `runtime/`: the backend is the only writer,
and the plugin is a read-only consumer.

### 2.3 Workspace Agent Authority

Workspace agents may:

- read MCP tool results
- call `check_source_status`, `fetch_document_section`, `curator_query`, and
  `get_available_models`
- request promotion of generated knowledge through explicit tools

Workspace agents must not silently edit `03_Notes/`, `04_Resources/`, or
`.curator/` by filesystem writes.

### 2.4 Transport Module Ownership

The CLI, MCP server, and same-device plugin command layer are transport
adapters over shared backend services. Refactoring their Python module layout
must preserve these public import and runtime surfaces:

- `curator.cli` remains the `wiki` entrypoint and owns the root Typer `app`.
  Extracted command-group modules may define isolated sub-apps, but the root
  facade wires the CLI tree top-down with `app.add_typer()`.
- `curator.mcp_server.build_server()` remains the MCP construction entrypoint.
  Extracted MCP modules register tools through `register_*_tools(mcp)` functions
  that receive the dynamic FastMCP instance created by `build_server()`.
- `curator.plugin_api` remains the backend-local function API used by hidden
  `wiki plugin ...` commands and selected MCP handlers. It is not an HTTP API
  contract.

This ownership rule is architecture-only. It must not change command names,
option names, hidden-command visibility, MCP tool names/schemas, or plugin JSON
payloads.

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
   and stores portable identity only. Zotero-backed PDFs persist the effective
   attachment key as `logical_source_id=zotero:<key>` and resolve through the
   current device's Zotero DB. Generic external PDFs persist
   `@<root_key>/<relative-path>` in `sources.external_ref`; the absolute root is
   read from repo-local `.cache/config/config.yml`.
   Generated stubs must not embed absolute `target_path` values by default,
   because `04_Resources/` may synchronize across devices whose external PDF
   libraries use different local paths. For Zotero-backed PDFs, the stub must
   include portable Zotero identity such as `reference_kind: zotero`,
   `zotero_attachment_key`, `logical_source_id: zotero:<key>`, and a
   `zotero://open-pdf/library/items/<key>` link.
   PDF lookup acceleration must keep the same boundary: portable identity may
   live in the `04_Resources` stub, while page text caches, page-label caches,
   and per-device absolute path hints stay in backend-owned state/cache keyed by
   content hash or logical source identity. Synced stubs must not become a cache
   dump for extracted page text or local filesystem paths.

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

If a registered Reference Mode source cannot be resolved from its Zotero key or
portable `external_ref`, backend status reports drift. It never falls back to a
persisted absolute path. Generic-source rebind requires human approval; Zotero
path movement is resolved by Zotero DB without rewriting source identity.

Normal commands, including `wiki status`, do not inspect or convert retired
absolute-path source schemas. There is no `wiki paths` command. A device-local
DB from before the portable-reference contract is unsupported and must be
rebuilt from current source/sync state before running this release.

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
L1 is complete but L2/L3 are still pending. The global L3 stage automatically
attempts shared L4 Synthesis after community reports settle; L4 is not a manual
post-build step.

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
- L2 is `done` only when at least one authoritative verified serving unit exists
  for the source; an exception-free extraction with no serving unit is
  terminal `skipped`.
- Without `--wait`, jobs are queued to the persistent `ingest_jobs` table and
  processed by the MCP server's IngestWorker or `wiki jobs run`.
- Recovering a job left `running` by a crashed worker resets both the job to
  `queued` and its source `l2_status` to `pending`; status surfaces must not show
  a permanently running source after recovery.
- After global L3 completes, sources whose L2 is done must receive a terminal
  `l3_status`: `done` only when a live community report is grounded in that
  source's spans, or `skipped` when no eligible L3 output exists. Returning
  without an exception is not sufficient for L3 completion.
- Community-report provenance lookups used by global L3 and projection re-emit
  must query span ids in batches of at most 900 parameters, remaining below
  SQLite's common 999-variable limit even for reports grounded in thousands of
  spans.
- Sources whose L2 is done must also receive a terminal `l4_status`: `done` only
  when current shared synthesis nodes are grounded in L3 reports that cite that
  source's spans, `skipped` when that source has no eligible L4 contribution, or
  `error` when report/synthesis generation fails. They must not remain
  indefinitely `pending` after a completed build.
- After processing, `wiki jobs run` (which `wiki build` spawns as a detached
  background daemon) **always refreshes the DB-native search index with
  embeddings** (`search.update_index(..., embed=True)`), **even when the queue was
  already empty**. This is required so a vault whose L2/L3 finished but whose
  vector embeddings never completed (interrupted daemon, or FTS-only `wiki add`)
  has an automatic path back to vector search instead of staying FTS5-only until
  a manual `wiki reindex --embed`. The embed refresh is idempotent: `update_index`
  fingerprints chunk input/dependency hashes, so already-current embeddings are
  not recomputed. The fast reuse path still validates that the currently
  configured embedding identity is available; otherwise it degrades explicitly to
  FTS5-only instead of reporting stale vectors as ready. `wiki build --wait`
  performs the same embed refresh inline.
- The `wiki build --wait` embed refresh runs **unconditionally** — it is no
  longer gated on `atoms_created or atoms_updated`. A `--wait` build that finds
  no pending sources (the global-L3 path) and a build that produces zero atom
  changes both still call the embedding-enabled native index refresh. Only the
  change-dependent side effects (persona reinforcement, sync-report
  invalidation) remain gated on real L2/L3 changes.

## 4.2 Source Management Commands

`wiki source rm <id>` removes backend tracking and generated derived records for
a source. It must keep the original source file by default. Deleting a file is a
separate destructive action that requires `--delete-file`, and even then only
vault raw/source directories may be unlinked.

`wiki source retry [id]` must consider both aggregate source failures
(`sources.status='error'`) and layer-scoped failures (`l1_status` through
`l4_status` or `layer_error`). L1-layer errors rerun L1 generation; L2/L3/L4
layer errors rerun the build path after resetting the failed downstream layer
state to pending.

## 4.3 `wiki update` Behavior

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

`curator_register_source` returns `warnings` on successful registration. If the
best-effort post-registration search refresh cannot run because the index or
database is temporarily unavailable, the MCP tool must keep the L1 registration
successful and report the skipped refresh in `warnings`; unexpected refresh
exceptions remain visible as tool failures.

For synchronous `curator_build_source`, an absent per-source ingest result is a
failure rather than a successful empty build. After a successful build, and
after `curator_add_knowledge` has durably written a Wiki page, a failed
best-effort search refresh is returned in `warnings` without rolling back the
completed primary operation.

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
- Generated CTX projections must not introduce lint-visible source-derived
  parser heading wikilinks such as `[[Paper#Section]]`. If a parser emits these
  links in generated CTX titles, previews, atom-candidate scaffolding, or source
  section projection text, the projection writer must convert them to plain text
  while leaving the original source file untouched.

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
  `wiki jobs rerun <id>`. Running the same command for an already queued job is
  an idempotent success/no-op; running jobs remain non-rerunnable while a worker
  owns them.
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
  active LLM client's `optimal_chunk_chars` cap, whether the client exposes that
  budget as a property or as a method, bounded by the system maximum, so
  CLI-backed models are not given oversized extraction prompts. Codex CLI is
  clone-safe for independent batch calls and uses a conservative chunk budget so
  large PDFs do not enter one long `codex exec` request. If a large-source L2
  batch fails prompt validation after the prompt runner's repair retry, the L2
  extractor must retry that batch as smaller provenance-preserving sub-batches
  before marking the source L2 layer failed.
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
2. **Recursive Batch Narrowing**: If an L2 knowledge-unit batch still fails
   validation after the prompt runner's repair retry, the extractor retries it
   as smaller batches while preserving the original source-span ids. Multi-span
   batches split by approximate character weight; a single very large span may
   split into overlapping text slices that still cite the same source span.
   Successfully validated retry slices are held in memory until the whole source
   extraction succeeds. If a top-level L2 batch returns an unrecoverable error,
   the extractor stops immediately instead of running later batches whose output
   cannot be published.
3. **No Partial L2 Publish**: L2 knowledge-unit rows and claim-support rows must
   be persisted only after every batch, including retry slices, validates. If any
   slice remains invalid, the source L2 layer is marked `error` with failed
   batch/span/trace context and no newly extracted units from that run are
   published. A fresh L2 extraction for a source must discard active
   generation-less knowledge units left by older failed runs before prompting,
   because those rows were never authoritative and must not block the new
   publish gate. Retired generation-less rows remain audit history.
4. **Closed Prompt Traces on Provider Exceptions**: Once a prompt run row is
   opened, any provider exception, timeout, capacity error, or repair-call
   exception must close that `PTR-` as `validator_status='failed'` with the
   exception class/message in `validator_errors`. L2 must not leave active
   `pending` prompt traces for failed provider calls.
5. **Deterministic L1-Candidate Fallback**: If batch extraction ultimately
   fails with an `LLMError`, the orchestrator may create low-confidence L2 Atoms
   directly from the English L1 `Atom Candidates` and `Source Guide` provenance.
   These fallback Atoms must include the closest section id/page when available
   and must use low confidence so later LLM-backed retries or human review can
   supersede them.
6. **Deterministic L3 Fallback Concepts**: If L3 clustering or L3 Concept
   drafting fails after L2 Atoms exist, the build may create low-confidence
   deterministic fallback Concepts that group related Atoms by source context.
   This keeps L3 coverage and provenance available while clearly marking the
   Concept as needing later LLM or human review.
7. **Legacy Sequential Fallback**: Older extraction paths may still attempt
   candidate-by-candidate LLM calls, but they must not be the only resilience
   mechanism for provider failures because they multiply the same failing LLM
   dependency.

L2 knowledge-unit extraction has an additional language contract: generated
fields (`canonical_name`, `statement`, and the ATM projection title/body derived
from them) must be English. Raw source spans may remain Korean or any other
source language. Non-English generated L2 output fails validation and triggers
the prompt runner's capped repair retry and recursive batch narrowing where
applicable; repeated failure marks the source L2 layer as `error` and publishes
no new ATM projection.

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

Synthesized answers must cite the **original source documents outside `.curator/`**,
not only the hidden DAG node. For each retrieved hit, the synthesis prompt resolves
the forward provenance trace `hit.source_span_ids → source_spans.source_id →
sources.relpath` (via `db.sources_for_spans`) and surfaces every distinct source
document as a resolvable wikilink (`[[04_Resources/…]]`, `.md` suffix stripped,
other extensions kept). High-level abstraction hits (concepts, synthesis nodes,
community reports) aggregate spans from one or MORE sources, so the trace returns
ALL distinct origin documents — not just the first. The model is instructed to
cite that source-document link alongside the curator-node link wherever a claim
derives from a hit that lists `Source document(s)`. When a hit has no resolvable
source span, the answer falls back to the curator-node citation only.

The Obsidian sidechat uses `wiki plugin context fetch` (JSON) for ordinary
workspace/domain questions; it must not wait for an external MCP server. The
provider is grounded with the returned evidence pack, not a backend synthesized
answer. `wiki plugin query` remains available only for explicit backend
synthesis. If the latest turn is centered on selected Markdown, a line-range
edit, a PDF page reference, or a selected PDF/image crop, sidechat treats that
selected context as primary.

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
- When promotion is given the answer's `source_span_ids` (from the query trace),
  the written `02_Wiki/` page appends a deterministic `## Sources` section listing
  the distinct original source documents (`[[04_Resources/…]]`, resolved via
  `db.sources_for_spans`). Because the `02_Wiki/` note is a visible vault file,
  these links make the sources appear in Obsidian's native Graph view and
  Backlinks pane — the hidden `.curator/` DAG cannot contribute such edges, so this
  visible-promotion path is the only place native source graph/backlinks exist
  (the c3 hybrid). Promotions without provenance still write the answer verbatim
  (any inline source citations it already carries remain).

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
- `codex-cli` → `codex -c model_reasoning_effort=<level>`
  (`low|medium|high|xhigh|max|ultra`; availability is model-specific). Codex
  `ultra` is not merely a deeper scalar level: the CLI may automatically
  delegate tasks while it is selected.
- `antigravity-cli` → Antigravity CLI 1.1.5+ receives
  `agy --model <base-slug> --effort <level>`. Base slugs such as
  `gemini-3.6-flash` require an explicit supported effort (`low|medium|high`);
  models whose catalogue entry has no selectable effort omit the flag.
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

The v0.35 CLI-backed catalogue is locked to the installed runtime contract:

| Provider | Model | Context | Efforts | Default |
| --- | --- | ---: | --- | --- |
| Claude Code | `claude-sonnet-4-6` | 1,000,000 | `low`, `medium`, `high`, `max` | `high` |
| Claude Code | `claude-fable-5` | 1,000,000 | `low`, `medium`, `high`, `xhigh`, `max` | `high` |
| Claude Code | `claude-opus-4-8` | 1,000,000 | `low`, `medium`, `high`, `xhigh`, `max` | `high` |
| Claude Code | `claude-haiku-4-5` | 200,000 | none | none |
| Codex CLI | `gpt-5.6-sol` | 272,000 | `low`, `medium`, `high`, `xhigh`, `max`, `ultra` | `low` |
| Codex CLI | `gpt-5.6-terra` | 272,000 | `low`, `medium`, `high`, `xhigh`, `max`, `ultra` | `medium` |
| Codex CLI | `gpt-5.6-luna` | 272,000 | `low`, `medium`, `high`, `xhigh`, `max` | `medium` |
| Codex CLI | `gpt-5.5` | 272,000 | `low`, `medium`, `high`, `xhigh` | `medium` |

These Codex context values are the installed CLI's effective window, not the
larger public API limit. A deliberate model change resets to the target model's
default. Loading existing settings preserves a still-supported effort, falls
back to the model default when invalid, and clears the stored effort for a model
with no effort dimension. Clients MUST omit the provider effort argument when
the normalized value is empty.

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

After `wiki config provider` and project-scoped `wiki config set --local`, the
CLI must make a best-effort attempt to refresh repo-cache `runtime/*.json` so the
plugin dashboard can reflect the change immediately. Because the config write has
already succeeded (and was confirmed to the user), expected local refresh
failures must not crash the command — not only file-system errors but also a
plugin-locked `state.sqlite` (the snapshot reads the job queue) or, for
`config set --local`, a malformed merged config. Every such failure must be
reported as a CLI warning rather than swallowed silently.

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
<repo>/.cache/vaults/<vault-key>/runtime/
```

Recommended files:

- `runtime/status.json` — vault health, source layer counts, active job
  counts, DB-native search readiness (`fts_ready`, embedded chunk counts,
  vector readiness, provider/model, degraded reason), backend version, and
  generated timestamp.
- `runtime/sources.json` — read-only source rows needed for dashboard
  and source chips.
- `runtime/jobs.json` — active/recent background jobs and errors.

Rules:

- Backend code is the single writer for repo-cache `runtime/*.json`.
- The plugin may read these files directly through the Obsidian vault adapter
  only after giving the local backend a chance to refresh them.
- The plugin must treat missing or stale snapshots as "unknown/waiting", not as
  proof that backend state is empty.
- Runtime snapshots must be derived from backend-owned state (`state.sqlite`,
  internal search metadata, job queue, config) and must not become a second
  source of truth.
- Runtime snapshot refresh is cache maintenance. If a mutating CLI command hits
  an expected local refresh failure (file-system error, a locked `state.sqlite`,
  or a malformed config during `config set --local`), the command should still
  complete and report a warning.
- Runtime snapshots and the live `wiki status --json` payload must not export
  local absolute paths. They use vault-relative/portable identifiers and blank
  machine-path fields; backend commands resolve machine-local paths only when a
  requested operation needs them.
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
  device's real file path from the Zotero attachment key or portable
  `sources.external_ref`.
- Source import commands used by the plugin may also accept Zotero attachment
  keys. Backend resolves the key, imports the resolved PDF as a Reference Mode
  source, and stores a stable logical source id such as
  `zotero:<attachmentKey>` in the local source registry.
- Dashboard source summaries for Zotero-backed references should expose the
  portable `zotero://open-pdf/library/items/<attachmentKey>` identity for
  display/opening. The local absolute PDF path remains a device-local
  transient resolved path and must not treat it as a portable source id or
  serialize it into DB/plugin state.
- Snapshot writes should be atomic: write a temporary file in the same
  repo-cache runtime directory and replace the target path.
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
  synced artifact. The command also always returns `build.backend_version`,
  `build.plugin_version`, `build.git_commit`, and `build.schema`; if the packaged
  `build_manifest.json` is absent, these fields fall back to the installed
  backend version and current schema constants rather than an empty object.
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

During `wiki init`, local MCP client configuration sync for known Gemini,
Antigravity, and vault-local Claude settings is best-effort. Expected
file-system, decoding, malformed-JSON, and wrong-shaped-config failures (e.g. a
non-object top-level document or a non-object `mcpServers` value) for one target
must not abort vault initialization or prevent other targets from being updated,
but each skipped target must be surfaced as a CLI warning.

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
- `wiki jobs rerun <id>` requeues a completed, failed, or cancelled job and is
  a success/no-op for an already queued job.
- Repo-cache `dashboard.md` may summarize job and DAG state for local diagnostics.

Status rules:

- "Sources summarized (L1)" means `sources.l1_status='done'`.
- It must not be derived from `sources.status='curated'`.
- L1 complete does not imply L2/L3 complete.
- Source health must be derived from per-layer statuses. Any `error` layer must
  be surfaced as unhealthy even if another layer is complete.
- Dashboard L1-L4 density counts come from authoritative serving DB records, not
  disposable files under `.curator/Collections/`.
- User-facing source state names are progressive and layer-explicit:
  `l1_ready`, `l2_ready`, `l3_ready` for Concept readiness, and `l4_ready`
  only when shared L4 Synthesis status is done.

## 12.1 Reset Behavior

`wiki reset` preserves `.curator/settings.yml`, sessions, Zotero profiles,
overview, correction ledger, and source folders, but clears
generated and device-local Curator state that can make a fresh vault run appear
stale:

- repo-cache `state.sqlite*`
- generated L1-L4 Collections
- generated index plus repo-cache dashboard/log/sync report
- repo-cache staging/runtime
- root-level legacy `build_trace_*.canvas` files
- `.cache/config/devices.json`
- internal DB-native search index rows stored in `state.sqlite`

Build trace canvases are diagnostics and must not be written at `.curator/`
root during normal background builds. If generated, they live under repo-cache
`staging/canvas/` so reset can treat them as transient state.

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
`search_chunks`, FTS5 rows, and missing/stale chunk embeddings. Rebuilding the
derived corpus MUST preserve ready embeddings for chunks that rematerialize with
the same chunk id and input hash, so unchanged vaults do not pay a full
re-embedding cost. It reports counts for FTS rows, chunks, embedded chunks,
skipped unchanged chunks, failures, provider/model, and degraded state. It does
not shell out to an external search binary.

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

Incurator supports P2P synchronization between repo-cache `state.sqlite`
replicas without a central server. SQLite never enters the vault; knowledge
crosses devices through synchronized JSONL snapshot files.

**Topology — one writer per file.** Each device exports only its own snapshot to
`.curator/sync/dev-<device_id>.jsonl` and imports every *other* device's file.
Because no two devices ever write the same file, Syncthing produces no
write-write conflicts under normal operation. `device_id` is generated once and
stored with peer high-water marks in the backend-local cache (see §13.3), never
inside the synchronized vault. The exported file is a **full snapshot** (not a
delta) so a late-joining peer always receives the complete view that device
holds.

**Conflict resolution — portable identity + LWW + tombstones.** `sources.id` is
replica-local. Source import resolves `sources.sync_key`, preserves the local
integer id, remaps child `source_id` values, then applies row-level LWW and
tombstones. There is **no whole-file replace**, so concurrent reads and edits to
disjoint source records remain safe.
If the same logical row is edited on both devices, the row with the newer
timestamp wins; a delete wins only when its `deleted_at` is newer than the
competing edit. Import preserves the source row's timestamp and never stamps
`now()`.

`sources.updated_at` is the source-row LWW clock. Every local source mutation,
including layer-status-only changes, advances it. `last_ingested` remains ingest
metadata and is never used as an import revision fallback. v0.33.0 accepts only
current-schema source rows: every imported `sources` row must carry a non-empty
`sync_key` and a valid `updated_at`; malformed source rows are rejected rather
than stamped with `now()`. Export-gate timestamp comparison is chronological
rather than a raw mixed-format string comparison, and non-string values are
treated as invalid rather than raising. Source and compiler-generation revision
triggers always advance beyond the previous row revision even if the current
device wall clock is behind.

**Snapshot identity and loop prevention are structural.** Every export header
has a fresh `export_id`; peer high-water state records that id, so a replaced
snapshot with the same mtime is imported. There is no whole-snapshot content-hash
guard. (An earlier `sync_meta.json` `last_exported_hash`/`last_imported_hash`
design was removed: it silently skipped legitimate imports and reported 0
changes.) Import resolves the actual SQLite primary-key columns, including every
column of a composite key. A row with the same key and equal/older LWW revision is
`skipped`, not rewritten or counted as updated. Immutable rows without a revision
clock compare full row content; equal content is skipped, while a malformed
same-key disagreement uses a deterministic canonical-payload tie-break so both
peers converge instead of alternating. Current-schema rows that omit a primary-key
column are rejected rather than blindly replaced. Loops cannot form because:
(a) row import is content-idempotent; (b) a device never imports its own file;
and (c) `wiki db autosync` exports this device's file only when something actually
changed (`local_has_unexported_changes()` compares the DB's newest timestamp
against the recorded `last_export_ts`). Receiving a fresh `export_id` for an
equivalent full snapshot is therefore not a reason to re-export.

**Triggers.** The Obsidian plugin runs `wiki db autosync` (a) once when the
vault loads, (b) when a `fs.watch` on `.curator/sync/` observes a peer file (once
the backend reports this device's exported filename, the watcher filters that
self snapshot; a debounced/coalesced scheduler collapses Syncthing's chunked
delivery into one pass and prevents overlapping runs), (c) on a 60-second fallback poll for
platforms where `fs.watch` is unavailable or misses events, and (d) from a manual
"Sync Knowledge DB" ribbon action. The plugin never triggers export on
`Vault.on('modify')` (a markdown-note save is not a DB mutation). Note that
`incuratorEnabled: false` turns off ALL plugin-side triggers on that device —
CLI-primary devices are covered by the CLI export hook below. All heavy JSONL
work runs in the backend subprocess, never on the Obsidian UI thread.

**CLI export hook (default-on since v0.30.0).** `auto_sync.enabled` defaults to
`true`; every mutating CLI command — `wiki add`, `wiki build`, `wiki sync`
(including the default incremental path, not just `--full`), and `wiki update`
— writes this device's snapshot at the end of the command via the best-effort
`_maybe_auto_export` hook (an export failure is printed but never breaks the
host command). Setting `auto_sync.enabled: false` in `.curator/settings.yml`
disables the hook; the explicit `wiki db autosync` command works regardless of
the flag. Without Syncthing the export is a harmless device-local file.
Rationale (v0.30.0 incident): the hook used to be opt-in and wired only into
`wiki update`, so a CLI-primary device with the plugin disabled silently never
exported — peers converged on a stale snapshot (the "Dashboard shows 5 sources
instead of 31" failure). A sync transport whose every trigger is opt-in fails
silently; the flag is now opt-out.

**Export gate semantics.** The hook is gated by
`local_has_unexported_changes()`: the newest LWW timestamp across all
`SYNC_TABLES` — **including `deleted_records`**, so a delete-only change (a
tombstone) still publishes — compared against `last_export_ts` with `>=`, not
strict `>`. Timestamps have second precision, so a mutation stamped in the same
second as the last export is indistinguishable from one already exported; `>=`
errs toward one redundant re-export (idempotent under row-level LWW, and
self-terminating because the extra export stamps a later `last_export_ts`)
instead of stranding the mutation until an unrelated later change.

**Dry-run observability.** `wiki db autosync --dry-run` honors recorded peer
`last_export_id` high-water marks, reports the changes a real pass would apply,
and reports whether an export would run (`would_export`) so a stale-snapshot
condition is visible without mutating anything.

**Syncthing conflict files.** If a `*.sync-conflict-*` file appears in
`.curator/sync/` (e.g. a duplicated `device_id`), `wiki db autosync` imports it
as an ordinary LWW peer — which is always data-safe — then moves it out of the
synced tree into repo-cache `runtime/sync_conflicts/` and surfaces a UI notice.
The conflict is reported as successfully merged only after both import and
archive complete. A peer import or archive failure makes the autosync pass fail
visibly and leaves the conflict file available for retry; it must never be
counted or displayed as merged. Earlier peer files may already have committed
before a later file fails because imports are transactional per file. Retrying
the pass is safe and content-idempotent.

## 13.3 Device-Local Sync State (Backend Cache)

The device id, `last_export_ts`, and per-peer `last_export_id` high-water
marks live at:

```text
.cache/config/sync_state/<vault-root-hash>.json
```

The hash namespaces multiple vaults without exposing their absolute paths in a
filename. This state is structurally outside the synchronized vault, so
correctness does not depend on every existing `.stignore` having received a
new pattern. A vault-local `.curator/sync_state.json` is unsupported and is not
read. The `.curator/sync/` directory remains synchronized because its JSONL
files are the transport.

Only an absent device-local sync-state file is an initialization case. If the
file exists but cannot be read, decoded, or validated as an object with correctly
shaped identity/high-water fields, autosync fails without rewriting it. In
particular, an existing state object with a missing, null, empty, or non-string
`device_id` is invalid. Corruption must never be converted to `{}` and must never
generate a replacement identity or discard peer high-water marks.

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
`.curator/settings.yml` because each device can have different local paths and
model availability.

`.curator/settings.yml` remains vault-scoped and portable. It may hold values such
as `version`, `paths`, `persona`, `sync`, `auto_sync`, and `curate`.

When a backend loads a vault config that still contains `llm`, `search`, or
`external`, it must migrate those blocks into `.cache/config/config.yml` and
remove them from the vault config while preserving the effective merged values.

All device-local runtime/temp/cache byproducts stay under
`<incurator-repo>/.cache/`; there is no vault fallback. Portable settings, JSONL
snapshots, sessions, profiles, and Collections projections remain under
`.curator/`. Backend and plugin CLI subprocesses set `TMPDIR`/`TEMP`/`TMP` under
the repo cache.

`wiki reset` resets the local DB/cache and generated projections but must not
delete shared `.curator/sessions.json` or `.curator/zotero_profiles.json`.

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

### 16.0 Workspace Provisioning Contract

- `wiki workspace init` and MCP `curator_workspace_init` create a workspace
  `curate.yml` with a `vault_root` that anchors the vault-relative
  `sources.include` and `sources.exclude` patterns.
- **`vault_root` is device-portable.** `curate.yml` is a synced workspace
  artifact, so `vault_root` is written **relative to the workspace directory**
  (e.g. `../..` for a workspace under `01_Workspaces/<proj>/`) via
  `os.path.relpath`, falling back to an absolute path only when no relative path
  exists (e.g. a different Windows drive). A workspace **outside** the vault gets
  the corresponding `../…` hop. This keeps the file valid across devices whose
  vault is mounted at different absolute paths.
- **Resolution precedence (unchanged authority, portable fallback).** The
  `VAULT_ROOT` env var the MCP server is started with is authoritative and always
  wins. `curate.yml.vault_root` is consulted only when `VAULT_ROOT` is absent
  (standalone tool calls); a relative value is resolved against the workspace
  directory that holds the `curate.yml`, never the process CWD. An absolute
  `vault_root` is still honoured.
- **Healing is non-destructive.** Re-running provisioning over an existing
  `curate.yml` rewrites `vault_root` to the portable relative form only when the
  current value does not resolve to the active vault; a value (relative or
  absolute) that already resolves to this vault is preserved untouched.
- Provisioning installs Curator-owned runtime files under `.agents/curator/` and
  one selected top-level agent rule file: `CLAUDE.md` for `claude-code`, or
  `AGENTS.md` for `codex` / `antigravity-cli`. Codex uses the workspace-agent
  slug `codex`; the LLM provider slug `codex-cli` is only an accepted alias.
- The managed top-level block is limited to Curator navigation, workspace check,
  query fallback, and session-closeout rules. It must not reference Incurator
  repository development workflow files such as `.agents/USER_REPORT.md`,
  `.agents/ROADMAP.md`, `.agents/drafts/`, release plans, or changelog/version
  procedures.

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
- Empty workspace context, or an explicit workspace directory with no
  `curate.yml`, uses the documented `default` policy. If `curate.yml` exists,
  read/parse/root-shape/source-scope-shape/semantic/hash failures are fatal to
  policy resolution and occur before retrieval, trace creation, or synthesis.
  This boundary applies equally to human `wiki query --workspace`, MCP
  `curator_query`, and hidden plugin query calls; no surface may discard the
  selected workspace path or warn-and-continue with unrestricted defaults.
  In particular,
  `sources` must be a mapping and its `include`/`exclude` values must be a string
  or list of strings. Each explicit pattern must remain non-empty after trimming;
  malformed or whitespace-only values cannot become an empty unrestricted scope.

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
Both surfaces validate the existing KRS before calling
`record_curation_plan()`. Missing or invalid input returns failure, the hidden
plugin command exits non-zero, and `curation_plans` remains unchanged. The
validation-only tool may return errors and a non-persisted policy preview.

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
- For ContextService-backed answer routes, plugin and MCP query JSON also
  return the selected `pack_id`, `snapshot`, and `budget` used for synthesis;
  degraded routes that have not migrated to ContextService return `null` or omit
  those fields instead of fabricating empty placeholders.
- The `fetch_context` surfaces (MCP `curator_fetch_context` and hidden
  `wiki plugin context fetch`) return the same curated evidence pack — including
  `synthesis` items and `synthesis_node_ids` — WITHOUT a synthesized answer, for
  reasoning agents and the Obsidian provider path that have their own LLM.
- For Obsidian sidechat, the fetched pack is retained on the local trace payload
  as `context_pack`. Sources & Trace renders this exact pack's route, pack id,
  snapshot id, budget, coverage/degraded state, evidence item summaries,
  locators, expansion handles, verification handles, and omitted `next[]`
  handles instead of reconstructing provenance from ids alone.
- Sources & Trace locator rows are actionable: vault locators open the target
  `relpath` plus heading or block anchor when present, and external locators open
  `external_uri`. Desktop clients open local external files through the system
  handler (Electron `shell.openPath`) rather than browser `window.open`.
  Expansion and verification buttons call hidden plugin JSON operations
  (`wiki plugin context expand` / `wiki plugin context verify`) with the
  displayed pack id and snapshot id. Successful verification replaces the
  matching displayed item in the retained context pack before re-render.
  Snapshot conflicts remain visible as degraded/refetch-required state. The
  plugin preserves the conflict metadata, offers a refetch action, and replaces
  the displayed pack with a fresh
  `context_fetch` result for the original question; it must not merge evidence
  from different snapshots.
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
`insight_candidate_ids`, and the existing `answer`/`trace`. Under the Plan F
ContextService contract, L3-complete synthesized answers also expose the exact
ContextService `pack_id`, `snapshot`, and `budget` used for synthesis inside the
returned trace, while the root `QTR-*` stores the same pack/snapshot and a
`synthesis` child action. As of v0.20.0 every served route — including `explore`
(§31.8) — grounds on the ContextService pack path, so `pack_id`, `snapshot`, and
`budget` are always populated; the `null`-metadata path for un-migrated routes is
retired.
For successful synthesized answers, result-level and query-trace
`source_span_ids` are the spans the validated prompt output reports as cited by
the answer. The full retrieved ContextService pack remains available under
`retrieval_trace.context_service` and, for plugin-backed calls, `context_pack`.

If answer synthesis fails validation after a ContextService pack is selected, the
result-level and root query-trace **retrieval provenance arrays are preserved**
(the evidence was retrieved and packed), exactly as the `explore` route preserves
them on its own synthesis failure. Only the answer itself is absent. The failure
is recorded on the `synthesis` child action as `synthesis_status=failed` with
empty `cited_source_span_ids` (the answer cited nothing), so evaluation can
distinguish a synthesis failure from a recall=0 retrieval failure without the
retrieval provenance being erased.

### 20.1 Synthesis Audit Reports

A synthesis audit report is a deterministic inspection payload for proving how a
generated L4 synthesis node, L3 community report, or query answer is grounded.
It is an export/inspection surface only: building an audit report must not call an
LLM, mutate repo-cache `state.sqlite`, rewrite projection markdown, or mark any
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
The optional local query-expansion GGUF provider uses structured
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
edit repo-cache `state.sqlite`, `.curator/Collections/`, `03_Notes/`,
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
     or altered relative to the span. Recorded with a reason and excluded from
     serving.
  3. `uncertain` — structurally plausible but ambiguous (heavy paraphrase or
     logical deduction). Escalated to secondary calibrated model validation,
     recorded with a `PTR-` validator trace; left `unchecked` when no model is
     available rather than promoted.
  A valid span id alone NEVER proves support (the F6 anti-pattern), and a
  semantic-similarity/NLI score alone NEVER verifies a formula.
- Formula structural rule (deterministic, no CAS): a claim's LaTeX formula —
  unescaped inline `$...$` or display `$$...$$` — is "present" in a span iff,
  after normalization (strip whitespace and spacing macros such as
  `\,`/`\!`/`\;`, while preserving grouping braces and non-alphabetic
  backslash escapes), its ordered token sequence is an exact contiguous
  subsequence of some formula in the span. This admits a faithful extracted
  sub-formula (`M` from `M = \int \rho dV`) while preserving operation
  direction, binding, and escaped-token distinctions: `a^b` ≠ `b^a`, `a-b` ≠
  `b-a`, `\frac{a}{b}` ≠ `\frac{b}{a}`, and `\{x\}` ≠ `{x}`. No commutative
  reordering is inferred without an AST/CAS. A central formula present in no cited span is
  `formula_status='missing'`; a structurally altered one is a `failed` support,
  never silently accepted. For a formula-only atomic unit with no prose terms,
  an ordered structural match is sufficient support; prose overlap is not
  required when there is no prose to score. If its formula is absent or altered,
  it routes to `uncertain` for P5 selective recovery rather than failing the
  prose-overlap gate. A claim with neither salient prose nor a formula fails as
  invalid/empty. Escaped currency/literal dollars (`\$`) are never formula
  delimiters. When multiple spans are cited, the verified `primary` support is
  the span with the highest `(matched claim formulas, prose term coverage)`
  score; this prevents a formula-only claim from binding to an arbitrary
  non-formula span. Textual support thresholds are evaluated independently
  against the maximum prose term coverage of every cited span, so a formula
  primary does not hide valid prose support in a contextual span. Claim support
  and formula preservation are independent status axes: an F6
  textual-grounding failure may still carry `formula_status='preserved_in_text'`
  when the cited span structurally contains the formula. Such a formula must not
  be mislabeled `missing` or routed to P5 recovery.
- A claim whose cited spans fail minimal-support validation is marked
  `support_status='failed'` with a reason; it is excluded from downstream
  compile stages and flagged by the compiler audit. Wrong-real-span citations
  remain audit telemetry and gold-fixture quality gates, but they do not create
  user-facing sync review items when the failed claim is already excluded from
  the served DAG.
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
  search materialization is removed. In particular, graph prompt batching may
  truncate oversized prose-only units, but never a formula-bearing statement.
- Community-report synthesis and query-answer prompts MUST preserve central
  equations, formulas, and code expressions exactly when they are needed for a
  finding, explanation, or answer; they may abstract prose, but not silently
  rewrite or drop the mathematical/code expression that carries the claim.
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
  every-page VLM processing is rejected **as an automatic recovery action**: the
  selective-recovery mechanism MUST NOT escalate to blanket page-VLM; it recovers
  only measured-loss regions. This constraint scopes the *recovery* path and does
  NOT govern a user-elected `vision_model` L1 extractor, which is a separate,
  upstream, opt-in extraction choice (§26.2a). Recovery output is additive
  (`source_spans.metadata.formula_recovery`, SCHEMA §20.4), labeled with full
  lineage, and lifecycle-gated (`candidate | reviewed | rejected`) — parseable
  LaTeX alone verifies nothing. The provider-free classifier emits no loss
  verdict from an expected formula alone: it requires measured corruption,
  parser/raw-text omission, or a rendered formula-region signal.
- The default recovery acceptance threshold is `0.80`. Below-threshold
  confidence, a missing validator trace, or a recovered formula that does not
  exactly match an owning-claim formula keeps the claim's
  `formula_status='uncertain'` and out of served formulas. An accepted reviewed
  candidate must re-run claim support against hydrated full raw-span text for
  every cited span plus additive recovered evidence before it can create linked
  formula evidence. Every hydrated text must match its cited span's content
  hash; stored previews are insufficient. A changed page hash invalidates
  exactly that page's candidates.

### 26.2a User-Elected Vision Extraction — `vision_model` / `latex_extract_model` (v0.23.0)

This is an **upstream, opt-in L1 extraction** path, distinct from §26.2's downstream
measured-loss recovery. It exists because pymupdf4llm text-layer extraction cannot
reliably reconstruct LaTeX for math; a user may elect a vision model to read the
rendered page instead.

- **Two optional config slots** (`llm`, `provider::model`, empty = disabled):
  - `vision_model` — heavy, layout-aware full-page model. Used by `add source` PDF
    ingest and standalone/markdown-linked image description.
  - `latex_extract_model` — light region-OCR model for the plugin's right-click
    **Convert-to-LaTeX** action. Resolution is
    `latex_extract_model → vision_model → (main chat model if vision-capable)`.
    (v0.28.0: the Cmd+Shift+X **chat snip** no longer routes here when the main
    chat model is vision-capable — see Interactive routing below.)
  - Both empty = pre-v0.22.0 behavior (pymupdf4llm ingest, main-model snip vision).
- **No implicit host OCR.** pymupdf4llm calls set `use_ocr=false`; missing
  Tesseract language data must not fail a text-layer PDF. OCR/vision work runs
  only through the explicitly configured slots above.
- **Interactive routing (v0.28.0).** The split depends on the surface:
  - **Right-click Convert-to-LaTeX** MUST call the backend `plugin pdf transcribe`
    resolver (it wants a clean LaTeX artifact, not a chat answer). The interactive
    transcribe prompt asks for exactly one `<transcription>...</transcription>`
    block; the backend normalizes the result by extracting that block when present
    and stripping common explanatory prose, labels, and fences before returning
    JSON to the plugin.
  - **Cmd+Shift+X "Snip PDF Region to Chat"** routes by the *main chat model's*
    vision capability (`modelSupportsVision`):
    - **Vision-capable main model** (antigravity / claude / codex CLI, or a vision
      Ollama model): the crop image is passed DIRECTLY to that same model through
      the chat CLI's scoped-Read image channel (see PLUGIN_SCHEMA "Interactive chat
      image channel") — there is NO separate `plugin pdf transcribe` round-trip.
      Rationale: in the default config the resolver's `main-if-vision` tail is the
      same provider CLI the chat already uses, so transcribing first is the same
      model invoked twice. The pymupdf text-layer `regionText` rides along as a
      caption so a weak/non-vision turn still has text. This intentionally reverses
      the pre-v0.28.0 rule that forbade attaching the crop image to the main chat
      model.
    - **Non-vision main model** (e.g. text-only Ollama): falls back to the
      `plugin pdf transcribe` resolver; the transcription text enters the chat
      context (image dropped), exactly as before v0.28.0.
  - The deferred transcription/image work runs AFTER the chat's "Thinking…"
    indicator is rendered, never blocking the Send action (fixes the v0.27.9
    residual freeze where the VLM `await` ran before any UI feedback).
- **Chat image channel & scoped Read (v0.28.0).** When a chat turn carries an image
  (Cmd+Shift+X crop, pasted image, or PDF-page capture) and the provider runs via
  CLI (`shouldUseCli`: antigravity/claude/codex), the image is written to
  `<repo>/.cache/cli/chat_images/<run-id>/` when a repo path is configured, or
  and the operation fails when the repo path is unavailable; the CLI is invoked with `Read`
  removed from its denylist plus `--add-dir <that dir>`, so the same model reads it —
  mirroring the backend transcribe path (`ClaudeCodeClient._run_with_image_path`).
  This grants the model scoped `Read` over the existing add-dir set (vault + Zotero +
  image dir) **for image-bearing turns ONLY**; text-only turns keep the hardened
  no-`Read` denylist verbatim. DB-scoped MCP curator tools remain available (denylist
  mode, not `--allowedTools`). All invocations stay inside the OS sandbox (§ v0.23.0
  CLI Provider Tool-Scope Sandbox). Temp PNGs are removed in a `finally`
  (guaranteed on success, error, and abort); stale `chat_images/*` dirs are swept on
  startup. No temp image survives a completed send.
- **Always-on when configured (per source).** When `vision_model` is set, each
  `add source` PDF page is rendered (PyMuPDF `get_pixmap`, bounded `vision_render_dpi`
  default 170 + `vision_max_image_px` default 1600 longest-edge with downscale) and
  transcribed to Markdown+LaTeX by the vision model; that becomes L1, recorded with
  `parser_used="vlm"` (SCHEMA). This is NOT a heuristic gate and NOT the §26.2
  recovery mechanism. Ingest uses `vision_model` ONLY — never `latex_extract_model`.
- **Resolver discipline (fallback only on empty, raise on failure).** The resolution
  chain advances ONLY when a slot is empty/unconfigured. A *configured* slot whose
  model is non-vision / unreachable / auth-failing **RAISES and HALTS** — it MUST NOT
  silently fall through to a heavier model (which would spike latency/cost and mask
  broken config). A configured-but-broken `vision_model` raises upfront and halts the
  `add` run (the user fixes config); it does not silently degrade the whole document
  to pymupdf4llm.
- **VLM L1 is not unconditional ground truth.** Per page, the pymupdf4llm text is
  retained as `parser_text` for audit, and a *transient* per-page VLM failure/timeout
  falls back to that page's parser text (logged + provenance-visible, never silent).
  The formula token cross-check (§26.1) still applies to VLM-authored L1; a VLM-only
  formula is never auto-promoted to `verified` outside the §26.2 evidence gate.
- **Cloud vision uses CLI subscription auth — NO provider API keys.** Transport:
  Ollama sends in-memory base64 (no disk); the agentic CLIs (claude, agy, codex —
  all live-verified) transcribe a temp PNG written under
  `.cache/vision_render/<run-id>/` and referenced by path to the CLI's vision-capable
  Read tool, then the output is normalized to clean LaTeX (strip `$$` wrappers, CLI
  banners, fences, commentary). Before any VLM transcription is cached or
  persisted as page/source text, Markdown image/link destinations that point to
  `.cache/vision_render` temp files are sanitized away while valid external URLs
  and vault-relative asset links are preserved. Temp PNGs are removed in a
  `finally` (guaranteed on success, exception, and timeout; per-run subdir wiped;
  stale dirs swept on startup; no leaks). Unsafe auto-approve CLI flags MUST NOT
  be passed.
- **Cost rail.** `vision_max_pages_per_run` (default ~300) bounds a single `add`
  run; beyond it requires explicit opt-in, with the remainder logged
  `vision_skipped` (never silently truncated).
- **Cache invalidation.** Per-page transcription is cached by
  `(page_content_hash, resolved_vision_model)`; switching the model in the Dashboard
  invalidates stale extractions and forces re-extraction on the next `add`/build.
- The §26.2 selective formula-recovery mechanism still runs on top of whichever L1
  was produced (VLM or pymupdf4llm) and still never performs blanket whole-corpus VLM
  as a recovery action.

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
- **Visibility is gated at write/materialization time, not read time.** A
  staged generation's `knowledge_units` carry TEMPORARY ids and are never
  emitted as ATM projections, upserted into the graph, or materialized into
  search while staged. Query, evidence, and search surfaces therefore read only
  authoritative-generation rows by construction (they read what is
  materialized, and only authoritative generations are ever materialized).
  Served = authoritative-generation ∧ `support_status='verified'` ∧
  `retired_at IS NULL`; an authoritative generation MAY contain non-verified
  (unchecked/uncertain/failed/stale) units — they are stored and audited but
  never served (visibility no longer keys on `support_status` alone).
- **Copy-on-stage.** Graph extraction (LLM) runs during staging, but its
  entities/relations are NOT upserted then — they are serialized and persisted
  only inside the publish transaction (the `graph_*` tables carry no
  generation id, so an in-staging upsert would bypass the gate and dangle on
  discard). Stable-id reconciliation is DEFERRED to the publish transaction:
  the DB cannot hold both the authoritative `KU-1` and a staged `KU-1` (the id
  is the primary key), so staged units use temporary ids and the publish
  transaction merges each unchanged temp unit into its stable id, rewrites
  every downstream reference (graph entity/relation `knowledge_unit_ids`,
  `claim_supports`, `artifact_dependencies`, `dag_edges`) from the temp id to
  the stable id, and deletes the temp row.
- **Atomic publish order (single DB transaction):** temp→stable reconcile +
  downstream-reference rewrite → upsert the serialized graph against the final
  stable ids → flip `gen_S` to `authoritative` and the prior generation to
  `discarded` (retiring its unmatched units). ONLY after the DB commits are ATM
  projections re-emitted and search re-materialized from the authoritative DB;
  projections are disposable, so a materialization/filesystem failure re-emits
  from the authoritative DB rather than leaving a partial publish.
- **No zero-unit publish guard.** A SUCCESSFUL extraction that yields zero
  units is the correct, deterministic representation of an emptied or
  non-claim-bearing source and MUST publish — retiring the prior authoritative
  units so the index never serves deleted claims. A FAILED extraction returns
  an error and never reaches publish, so this introduces no silent loss; a
  zero-unit publish that retires one or more prior units is recorded as a
  non-blocking audit note.
- **Gate audits the to-be-published state.** For the DB-level re-publish
  (`recompile_source`), re-validation and the publish gate run together in ONE
  transaction: the gate's compiler audit reads the uncommitted re-validated
  rows, so it checks exactly the state about to be committed, never a
  pre-validation snapshot. This lets a re-validation HEAL a transiently-dangling
  support — it is re-written against the live span before the gate sees it,
  rather than blocking the republish — while a genuine structural break (an
  orphaned support no re-validation can fix) still raises and rolls the whole
  transaction back, leaving the prior authoritative generation byte-identical.

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
  Formula token arrays are structurally serialized in the normalized hash
  input, so adjacent tokens or separate formulas cannot collapse into a
  different formula structure.
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
  so CI and the testbed can gate on it. Release-blocking assertions are
  structural breaks in the served DAG: dangling support references,
  formula-status inconsistencies, or multiple authoritative generations for one
  source scope. Failed/stale/unchecked claims are excluded from serving and are
  reported as informational compiler telemetry, not sync review blockers.
  Existing lint checks are unchanged.
- Surface scope: CLI only in v0.8.0. No MCP tool schema changes and no plugin
  contract changes (PLUGIN_SCHEMA.md is intentionally untouched apart from the
  synchronized version title). MCP/plugin clients observe Plan B only through
  better evidence: full-span hydration (SEARCH_ENGINE_SCHEMA §10) and
  support/formula labels already carried on returned records.

### 26.6 Current-Schema State DB Boundary

As of v0.33.0, runtime DB initialization no longer carries the historical v8/v9
automatic migration rehearsal path. `init_db()` and `connect()` create or open
the current schema directly and stamp the current `SCHEMA_VERSION`; unsupported
pre-v12 `state.sqlite` files are not upgraded in place. The supported recovery
path is to rebuild/regenerate from source truth or import a current-schema JSONL
snapshot. Clean rebuild remains available: source truth under `03_Notes/` /
`04_Resources/` is never modified by DB initialization, compile, or rollback.

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

## 27. Graph Quality: Resolution, Support, Hierarchy, And Grounded Reports (Plan C, v0.9.0)

v0.9.0 is the second Evidence Compiler Integrity release. It compiles the
trusted claim generation published by Plan B (§26) into a reversible,
support-aware entity/relation graph and a measured deterministic community
hierarchy whose reports stay claim-level grounded and incrementally
maintainable. The frozen schema names live in SCHEMA.md §21; this section
freezes the behavior. Owned failure-atlas cases: **F8** (graph resolution /
unsupported topology) and **F9** (hierarchy quality / report grounding),
explicitly deferred to Plan C by §26. Query-serving algorithms (PPR, DRIFT,
global serving, retrieval tuning) remain Program 3 work. Vault quota, storage
meters, admission limits, and auto-cleanup are out of scope (plan Non-Goals).

Plan C consumes ONLY one fully published B claim generation (`GEN-`,
SCHEMA §20.3) and its approved support-eligibility states. Reading mixed or
unchecked claim generations into graph construction is a stop condition. Graph
heuristics never compensate for unchecked or broadly grounded claims.

### 27.1 Entity Resolution Lifecycle And Reversible Merges

- **Similarity is candidate generation only (Arena decision 3).** Deterministic
  normalization (`alias_normalized`) and similarity signals may PROPOSE that two
  surface forms are the same entity; they may NEVER auto-create an `accepted`
  alias or auto-fuse two entities. A normalization match creates at most an
  `ambiguous_candidate` (homonym risk) or, when the §21.6 guards pass, a
  `merge_proposed` row routed through `entity_merge_proposals`.
- **Homonyms stay unresolved.** When the same normalized form plausibly maps to
  more than one distinct entity (e.g. "Mercury" the planet vs. the element vs.
  the mission), the alias stays `ambiguous_candidate` until an approved decision.
  The strict quality condition is **0 homonym false merges** on the adversarial
  gold fixtures; an ambiguous candidate that silently fused entities is a
  release-blocking defect.
- **Homonyms are stored as separate rows per entity.** A confirmed homonym is not
  a single ambiguous record — once each meaning is approved, it is its OWN
  `entity_aliases` row sharing one `alias_normalized` but carrying a distinct
  `entity_id`. The surrogate primary key (`ALI-`, SCHEMA §21.1) is what makes
  this representable: the surface form is deliberately not part of the key, so
  "Mercury → planet" and "Mercury → element" coexist as distinct resolved rows.
  A surface-form composite key would have collapsed them into one slot — silently
  overwriting the first resolution and re-introducing the very false merge this
  lifecycle exists to prevent.
- **Exact/high-certainty aliasing still requires guards (Arena decision 4).**
  Even an exact normalized match is only accepted as an `alias`/merge when ALL of
  these pass and are recorded in `evidence_json`: entity-type match, context
  overlap (shared spans/claims/neighbourhood above threshold), no contradicting
  claim, and the pair is not on the workspace `avoid_merges` list. Any guard
  failure downgrades the candidate to `ambiguous_candidate` or `rejected`.
- **Accepted merges preserve origin identity (Arena decision 5).** An accepted
  merge does NOT delete the origin entity. The origin `graph_entities` row is set
  `resolution_state='redirected'`, `redirect_to_entity_id` → the surviving
  canonical entity, and `decision_id` → the accepting `DEC-`. The merge writes a
  complete `entity_resolution_lineage` row whose `rewrite_json` captures the exact
  pre-merge entity row plus every relation/community/report/synthesis reference
  the merge re-pointed. A merge that cannot be represented losslessly there MUST
  NOT be accepted.
- **Reversal reconstructs the prior graph.** Reversing an accepted merge replays
  `rewrite_json` in reverse — restoring the origin entity to `canonical`,
  re-pointing every rewritten reference, and regenerating the affected
  relations/communities/reports/synthesis. The reversed decision row is retained
  (`resolution_status='reversed'` / `decision='reversed'`) as durable audit, never
  hard-deleted. The acceptance test: reversal yields endpoints and provenance
  byte-identical to the pre-merge state.
- **Rejected decisions are durable negative knowledge.** A `rejected` pair is not
  auto-re-proposed unless new evidence changes its candidate signals, preventing
  proposal churn.
- **Authoritative reads resolve redirects.** Every read that builds topology,
  community input, reports, search materialization, or synthesis resolves
  `redirected` rows through `redirect_to_entity_id` to the canonical entity. No
  authoritative artifact may reference a redirected entity directly (the §27.6
  audit asserts 0 such references).

### 27.2 Independent Claim-Level Relation Support

- **A relation is a proposition with independent supports (Arena decision 6).**
  Re-extracting the same `(src, tgt, relation_type)` triple ADDS
  `graph_relation_supports` rows; it never overwrites them. This replaces the
  current destructive `upsert_graph_relation` overwrite (SCHEMA §11.4 reality),
  which loses every prior support on the latest write.
- **Independence is by source lineage, not row count.** A relation's independent
  support count = the number of DISTINCT `source_lineage_hash` among its
  `verified` supports. Copied/duplicated/forked sources share a
  `source_lineage_hash` and therefore count exactly once. The strict quality
  condition is **0 copied-source rows counted as independent support**.
- **Corroboration threshold = 2 independent source lineages.** A relation
  becomes `active` only when this count is **≥ 2** (two genuinely independent
  sources assert the same proposition). A count of exactly **1** is a single
  uncorroborated source — however many copied/forked support rows it contributes,
  they collapse to one lineage — and quarantines as `copied_source_only` (§27.3),
  never `active`. A count of **0** is `unsupported`. Raising the bar to ≥2 is what
  makes `copied_source_only` and `active` mutually exclusive: a single-lineage
  relation can never satisfy `active`, and an `active` relation always carries
  independent corroboration.
- **Support eligibility mirrors the B claim lifecycle.** A support is `verified`
  only when its `knowledge_unit_id` is itself eligible (B `support_status =
  'verified'`, `retired_at IS NULL`, §26.1/§20.1) AND its cited spans are fresh
  (the support's evidence hash still matches the span `content_hash`; a drift
  marks the support `stale`). Only supports derived from the authoritative B
  generation may be `verified`; a mixed-generation support is a stop condition.
- **No broad-span fallback (F9).** No graph or report path may substitute an
  all-upstream-span set for missing claim-level support. The broad-community-span
  fallback that B's compiler audit measured and handed to Plan C (§26.1) is
  removed here, not merely reported.

### 27.3 Relation Lifecycle, Edge Classes, And Quarantine

- **Lifecycle (Arena decision 7).** Every relation carries `lifecycle_status ∈
  {active, provisional, quarantined, retired}`:
  - `active` — has **≥2 independent source lineages** of `verified` support (§27.2
    corroboration threshold), both endpoints resolve to canonical entities, and it
    passed all quarantine checks. **Only `active`, non-retired relations enter
    authoritative community construction.**
  - `provisional` — exists but not yet promotable (unrevalidated after migration,
    or support still pending). The v9 backfill marks every legacy relation
    `provisional`; none is auto-promoted.
  - `quarantined` — flagged OUT of authoritative topology with a frozen
    `quarantine_reason` code AND a `reeval_trigger` describing what would re-admit
    it. Quarantine is inspectable and re-evaluable — never an opaque discard pile
    (Arena decision 8).
  - `retired` — superseded by source edit/delete/split reconciliation; retained
    as a tombstone, never an authoritative input.
- **Frozen quarantine reason codes** (SCHEMA §21.6): `unsupported` (no eligible
  support — 0 independent source lineages), `self_loop`, `contradiction`,
  `copied_source_only` (exactly 1 independent source lineage — a single,
  uncorroborated source, below the ≥2 corroboration threshold of §27.2),
  `bridge_risk` (a single low-confidence edge joining otherwise
  separate dense components), `endpoint_unresolved`. Detection of self-loops,
  unsupported edges, contradictions, and bridge-risk candidates runs at compile
  time; each routes the relation to `quarantined` with the matching code rather
  than silently dropping or silently admitting it.
- **A relation is never a "duplicate" (no `duplicate_proposition` code).** The
  relation's identity IS its canonical proposition — `(resolved source, resolved
  target, relation_type)` after endpoint resolution (§27.1). Re-asserting that
  proposition aggregates supports onto the SAME relation (§27.2); it does not
  produce a second relation row to quarantine. Quarantining a re-assertion as a
  "duplicate" would suppress its supports and corrupt the independent-support
  count — the inverse of the aggregation contract — so the state cannot exist by
  construction. A relation's support-side state is therefore a total partition by
  independent-source-lineage count: **0** → `unsupported`; **exactly 1** →
  `copied_source_only` (a single, uncorroborated source); **≥2** → `active`. If
  two physical rows are ever found for the same canonical proposition,
  reconciliation (§27.8) merges their supports onto the canonical relation; it
  never quarantines one as a duplicate.
- **Edge classes stay distinct (Arena decision 9).** `edge_class ∈ {authored,
  extracted}` separates links/topology a human or workspace wrote (wikilinks,
  explicit structure) from LLM-extracted semantic relations. The two classes stay
  distinct through weighting, hierarchy, audit, and reports. `topology_weight` is
  computed per edge class; authored edges are NEVER silently treated as extracted
  factual evidence, and extracted relations never inherit authored structural
  weight. This preserves the existing `assertion_source` distinction (§11.4) at
  the topology layer.
- **Endpoint normalization.** Endpoints are normalized through ACCEPTED
  resolution only (§27.1) before lifecycle evaluation; an unresolved endpoint
  quarantines the relation with `endpoint_unresolved` rather than entering
  topology with a redirected node.

### 27.4 Deterministic Hierarchical Community Construction

- **Benchmark-driven, multi-metric selection (Arena decision 10).** The hierarchy
  algorithm is chosen by the frozen multi-metric benchmark (P0 Evidence Ledger
  "Hierarchy Benchmark Freeze"), not assumed. Filtered connected components is the
  EXPLICIT degraded fallback; seeded weighted Leiden (or an approved alternative)
  is a CANDIDATE that is adopted only if it improves the approved metric gates
  WITHOUT any homonym, provenance, report-support, or stability regression.
  Modularity alone is insufficient.
- **Deterministic under fixed inputs.** Construction takes a stable sorted input
  (relations ordered by a deterministic key), an explicit seed, and an explicit
  threshold/config set. The triple `(graph content, config, seed)` produces an
  IDENTICAL hierarchy — same members, same levels, same identities — on repeat
  runs. `config_hash` pins the algorithm + seed + thresholds that produced each
  community.
- **Real hierarchy levels.** The existing `community_reports.level` column now
  carries the real depth (0 = leaf); `parent_community_key` records the hierarchy
  edge. The current level-0-only behavior (SCHEMA §11.5 reality) is replaced.
- **No unexplained giant component.** A single component spanning more than the
  approved threshold of the graph is a benchmark failure unless explained by the
  authored-topology structure; it blocks hierarchy adoption.
- **Active-canonical input only.** A community built from anything other than
  `active` (§27.3) relations over canonical (§27.1) entities is invalid. The
  fallback never silently changes serving mode: when the degraded
  filtered-connected-components path runs, it is recorded in `config_hash` and
  surfaced by the audit, not hidden.

### 27.5 Claim-Grounded Community Reports

- **Content/config-derived identity (Arena decision 11).** `community_key` is a
  function of `(level, member_hash, support_hash, config_hash)`. When the active
  membership or eligible support set changes, the identity changes — a correct
  restructuring is preferred over artificial id stability. The superseded
  community/report is set `retired_at` BEFORE synthesis (§ L4) consumes it, so no
  stale report feeds a downstream artifact.
- **Exact eligible claim support, no fallback (Arena decision 12, F9).** Every
  report finding cites exact eligible claim support drawn from the `active`
  relations over canonical entities in the community. The whole-community-span
  fallback is removed: a finding that cannot cite eligible claim-level support is
  not emitted. 100% of served report findings carry eligible active claim
  support; 0 broad-span findings.
- **Fresh dependencies.** A report records precise dependency hashes over its
  input entities/relations/spans (the existing `dependency_hash`, §11.5, now
  computed over the active-canonical-support closure). When an input changes the
  report is stale and is regenerated before it is used as global evidence; a stale
  or retired report never serves.

### 27.6 Graph Audit Surface (`wiki lint` Extension)

- The graph audit is READ-ONLY and runs (a) as the graph/report publish gate
  inside the publish transaction and (b) on demand via `wiki lint`, which gains a
  **Graph Quality** section alongside the Plan B Compiler Integrity section
  (§26.5). The audit asserts the schema-level invariants frozen in SCHEMA §21.8:
  - 0 authoritative references to `redirected` entities;
  - 0 `active` relations with fewer than 2 independent source lineages of `verified` support;
  - 0 relation endpoints that are not canonical entities;
  - every `quarantined` relation has a reason code AND a re-eval trigger;
  - every served report finding cites eligible active claim support;
  - 0 stale/retired aliases, supports, communities, or reports feeding an
    authoritative artifact;
  - 0 mixed claim generations in graph/report input;
  - resolution safety: 0 homonym false merges; every accepted alias/merge has a
    reason, evidence, source/claim lineage, and reversible rewrite lineage;
  - 100% provisional/quarantined edges have a reason and re-evaluation trigger.
- `wiki lint` exits non-zero when a release-blocking graph-audit assertion fails,
  so CI and the testbed gate on it. Existing lint checks and the Plan B Compiler
  Integrity section are unchanged.
- **Surface scope: CLI only in v0.9.0.** No MCP tool schema changes and no plugin
  contract changes (PLUGIN_SCHEMA.md is intentionally untouched apart from the
  synchronized version title). MCP/plugin clients observe Plan C only through
  better evidence on already-returned records (canonical entities, active
  relations, claim-grounded reports).

### 27.7 v9 Migration Rehearsal And Rollback Acceptance Criteria

The v9 migration (SCHEMA §21.8) is forward-only and additive and ships only with
a rehearsed rollback path. Acceptance criteria — ALL must pass before the
migration may touch a real vault DB, encoded as tests in P3:

1. Rehearsal runs on a disposable copy of the pre-implementation backup
   (`state.sqlite.C-baseline.bak`, P0 Evidence Ledger) — never first on the live
   testbed DB.
2. Post-migration: `PRAGMA integrity_check` = ok; `schema_version` row = 9; all
   pre-existing row counts unchanged; every legacy `graph_entities` row reads
   `resolution_state='canonical'`, `redirect_to_entity_id IS NULL`; every legacy
   `graph_relations` row reads `lifecycle_status='provisional'`,
   `edge_class='extracted'`, `generation_id IS NULL`; zero `entity_aliases`,
   `entity_merge_proposals`, `entity_resolution_lineage`, and
   `graph_relation_supports` rows exist (the migration INFERS nothing).
3. Idempotency: running the migration twice is a no-op the second time.
4. Round-trip: `wiki db export` → `wiki db import` on a migrated DB preserves the
   four new tables and the new columns; the `deleted_records` CHECK list and
   tombstone deletion-before-upsert (§13.1) cover the four new tables.
5. Restore drill: replacing the migrated DB with the backup and re-running the
   migration reproduces an identical schema fingerprint (SHA-256 over ordered
   `sqlite_master` DDL).
6. Failure rollback: if migration, the post-migration graph audit, or a hierarchy
   gate fails, restore the DB backup, discard the staged graph/report generation,
   re-emit projections/search from the prior authoritative graph generation, and
   (after three repeated QA failures) return to planning via the rollback
   strategist.
7. Old graph/report generation and merge/rewrite lineage are preserved until the
   new graph audit passes; source truth under `03_Notes/` / `04_Resources/` is
   never modified by migration, compile, or rollback.

### 27.8 Source Edit/Delete Reconciliation And Idempotent Rebuild

- **Unchanged rebuild is idempotent (compiler integrity).** Re-running graph
  construction on the same authoritative B generation + same config/seed reuses
  the existing entity/relation/community/report identities, hashes, and counts —
  **no entity/relation/report count amplification**. Duplicate amplification is
  the measured artifact-growth signal (quota stays out of scope).
- **One-source mutation changes only its closure.** A source edit/delete/split
  reconciles exactly the measured downstream graph/report/synthesis closure (via
  `artifact_dependencies`, extending §26.4): supports whose source basis
  disappeared are retired, relations that drop below 2 independent verified
  source lineages drop out of `active`, communities whose active membership/support
  changed retire and regenerate, and dependent reports/synthesis are invalidated
  and regenerated or retired. The closure is measured and asserted by tests, not
  assumed.
- **Atomic graph/report publish.** Graph resolution, support aggregation,
  community construction, and report generation for a scope publish together or
  not at all, inside the publish transaction (extending §26.3). A failed graph
  audit discards the staged graph/report generation; the prior authoritative
  graph generation, its projections, and its search materialization remain
  untouched and continue serving. Disposable projections/search re-emit from the
  authoritative DB after commit. Re-emitting unchanged L4 synthesis concept links
  is a no-op for `synthesis_nodes.updated_at`; only real concept-link changes
  advance the LWW revision clock.

### 27.9 GQ07 Relation-Confidence Calibration Gate

- Plan E P7 measured production relation `confidence` as non-discriminative (all
  1,180 values in `0.9–1.0`, mean `0.966`). Therefore
  `graph_relations.confidence` and `graph_relation_supports.confidence` are **NOT
  a calibrated noise threshold** and MUST NOT be used as a serving-time filter
  until per-relation-type quality labels prove separation (P0 Evidence Ledger
  GQ07; SCHEMA §21.9).
- Quarantine and active-promotion decisions (§27.3) gate on support ELIGIBILITY
  and STRUCTURAL signals (independent verified support, endpoint resolution,
  self-loop/bridge/duplicate detection), never on a raw-confidence cutoff. The
  P7 holdout showed a fixed `0.5` filter simultaneously blocked a noisy bridge
  AND lost a true `0.25`-confidence edge — a rejected default.
- Any calibrated-confidence mechanism is `benchmark-later`: no calibrated column
  is frozen until P5 produces labeled relation-quality evidence. Changing the
  partition algorithm cannot repair untrustworthy edge scores, so hierarchy
  benchmarking compares raw connected components, confidence-denoised components,
  authored topology, and seeded Leiden ONLY after relation-quality labels exist.

### 27.10 Testbed Validation (Plan C)

- The confirmed active scenario (`gaussian_splatting`, P0 Evidence Ledger) is
  initialized and exercised with `VAULT_ROOT=testbed wiki status|add|update|lint`,
  plus the approved graph-audit, resolution, relation-support, hierarchy, and
  report scenario commands.
- DB-native graph adversarial fixtures (synonyms, homonyms, abbreviations,
  multilingual aliases, copied-source support, contradictions, self-loops, noisy
  bridges, ambiguous aliases, merge reversal, edit/delete) are added and run.
- Local Markdown/PDF and Reference Mode external sources are all validated.
  Hierarchy/report generation runs with the configured provider where available;
  otherwise every deterministic/local-simulator gate runs and the exact provider
  blocker is documented (the only accepted gap).
- Graph metrics are reported separately; no quota UI, limits, admission control,
  or auto-deletion is implemented. No source or reference file is autonomously
  edited at any point.

---

## 28. Retrieval Policy Enforcement (Plan A, v0.10.0)

### 28.1 CurationPolicy Forwarded To Evidence Building

`build_evidence(paths, request, route, *, policy)` receives the resolved
`CurationPolicy` from the orchestrator.  The orchestrator already resolves the
policy before routing; it MUST forward the same policy object to `build_evidence`
rather than letting evidence construction apply defaults independently.

**Source-scope enforcement (glob-based)** — `CurationPolicy` carries
`source_include` / `source_exclude` **glob patterns** (compiled from the
workspace `curate.yml`; there is no `source_ids` field). A source relpath is
*in scope* when it matches `source_include` (an empty `source_include` means "all
sources") and does **not** match `source_exclude` (exclusion always wins). The
same matcher used by `CurateSpec.matches_sources` applies, exposed as
`CurationPolicy.allows_source(relpath)`.

Evidence assembly MUST drop out-of-scope records on every route before they reach
the pack, using a **strict all-spans rule**: an evidence item is kept only when
**every** backing span is in scope. A single out-of-scope span excludes the whole
item.

- **Single-source items** (`source_span`, `search_hit`): included only when their
  source relpath is in scope.
- **Multi-source items** (`community_report`, `synthesis`) and **entity items**:
  these aggregate spans from several sources, and their rendered *text* already
  commingles content from all of them. They are **excluded entirely if ANY backing
  span is out of scope** — keeping a partially-in-scope artifact would leak
  excluded source content through its text, and trimming `source_span_ids` would
  corrupt provenance (the consumer would cite an in-scope source for
  out-of-scope-derived claims). `source_span_ids` is therefore **never mutated**
  by scope enforcement: an item is kept whole or dropped whole.

Out-of-scope spans MUST NOT appear in `EvidencePack.source_span_ids` or any
surviving `EvidenceItem.source_span_ids`. The number of items dropped by scope
enforcement is recorded in `EvidencePack.omitted_counts["policy_excluded"]` so the
retrieval trace's `candidate_count` conserves the full candidate set (§30.2).

When `source_include` is empty and `source_exclude` is empty (the default open
policy), every record is in scope and behavior is unchanged.

**Oracle**: `test_f3_oracle_build_evidence_filters_out_of_scope_sources` (F3, Plan A
P3) — seeds an in-scope source, an out-of-scope source, and a **mixed** report
backed by both, then asserts the out-of-scope source *and the mixed report* are
entirely absent from the pack (no partial inclusion, no span-id mutation).

### 28.2 Bounded Global Route

Global evidence MUST rank community reports by query relevance and select at
most `MAX_GLOBAL_REPORTS = 10` (configurable by policy in future; hard default
today).  Loading every report for every global query is a **rejected default**.

Query-relevance ranking: score each report by lexical overlap between the query
terms and the report `title + summary` text.  The top-N reports (by score, ties
broken by `rank DESC`) are selected; remaining reports are omitted with a count
recorded in `pack.omitted_counts["global_reports"]`.

L4 Synthesis nodes are similarly bounded to `MAX_GLOBAL_SYNTHESIS = 6` (current
limit is already in `_synthesis_items`; ensure it is also applied when policy is
present).

Two queries with different topics MUST select different report subsets.  The
baseline defect (F4) loads all reports query-independently; the oracle asserts
that two queries with non-overlapping topics produce non-overlapping top-10
selections and that each selection contains ≤ 10 items.

**Oracle**: `test_f4_oracle_global_evidence_bounded_and_query_dependent` (F4, Plan
A P3).

### 28.3 Explicit Evidence Omission Reporting

`EvidencePack.evidence_block(*, max_chars)` MUST append an omission summary line
when any items were excluded by the character budget.  The summary MUST contain
the word "omitted" and the count of excluded items, e.g.:

```
[2 items omitted — character budget reached]
```

Silent truncation is a **rejected default** (F5).  The omission line itself MUST
NOT cause `evidence_block` to exceed `max_chars`; it replaces the last partial
item if needed to fit.

**Oracle**: `test_f5_oracle_evidence_block_reports_explicit_omissions` (F5, Plan A
P3).

### 28.4 Route Candidate And Evidence Limits

Every route enforces explicit per-route limits:

| Route          | Candidate limit                          | Selected limit |
|----------------|------------------------------------------|---------------|
| `local`        | `limit` (default 8) search hits          | same as hits  |
| `global`       | all reports scored; top-N selected       | 10 reports + 6 synthesis |
| `explore`      | entity seed + memory paths               | per-policy    |
| `source-section` | all spans of that source               | unbounded (full source) |

Omissions for every route that drops candidates are recorded in
`pack.omitted_counts` (a new dict field on `EvidencePack`); Plan F exposes these
in the public context pack.

---

## 29. Structured Source Locators (Plan A, v0.10.0)

### 29.1 Purpose

A structured locator supplements (never replaces) the authoritative
`source_span_id` on an evidence item.  It encodes the precise sub-document
target — heading, block anchor, PDF page — needed by rendering clients and Plan F
navigation.  The locator is resolved at retrieval time and attached to every
`EvidenceItem`; rendering clients consume it at their own interface boundary.

### 29.2 StructuredLocator Schema

```python
@dataclass
class StructuredLocator:
    source_id: int | None          # FK to sources.id; None for external-only
    source_kind: str               # vault_markdown | vault_pdf | external_uri | promoted_wiki
    relpath: str | None            # vault-relative path (None for external_uri)
    heading: str | None            # nearest heading above the span (Markdown only)
    block_id: str | None           # Obsidian block anchor `^block-id` (Markdown)
    page_number: int | None        # verified printed page number (PDF only)
    toc_id: str | None             # PDF table-of-contents section id (PDF only)
    external_uri: str | None       # reference-mode external URI
    locator_status: str            # see §29.3
```

`source_kind` values:
- `vault_markdown` — a `.md` file in `03_Notes/`, `02_Wiki/`, or
  `.curator/Collections/`
- `vault_pdf` — a PDF source. This covers both a PDF copied into the vault and a
  Reference Mode PDF. For Reference Mode the PDF is *not* in the vault: `relpath`
  points to an in-vault markdown *stub* under `04_Resources/`, while
  `external_uri` carries the real file path. `external_uri` is therefore
  authoritative for opening — whenever it is present, clients MUST open the
  external file (a reference PDF in the client's PDF viewer at `page_number`),
  never the stub `relpath`. `relpath` is the open target only when `external_uri`
  is absent (a true in-vault PDF).
- `external_uri` — a URI-only external reference (no local copy)
- `promoted_wiki` — a note in `02_Wiki/` promoted from L4

### 29.3 Locator Resolution States

| Status              | Meaning |
|---------------------|---------|
| `exact`             | heading and/or block_id confirmed present in the file |
| `fallback_file`     | heading/block not found; locator resolves to the file root |
| `fallback_source`   | file not found; locator resolves to the source record only |
| `duplicate_anchor`  | block_id appears more than once in the file; not a unique target |
| `stale`             | file exists but content hash has changed since the span was stored |
| `unavailable`       | source record exists but the file cannot be read |

A locator MUST NOT be rendered as a clickable link unless its status is `exact` or
`fallback_file`.  Degraded statuses (`duplicate_anchor`, `stale`, `unavailable`,
`fallback_source`) MUST be surfaced as a warning.

### 29.4 Resolution Rules

1. Read `sources.relpath` and `source_spans.relpath` from the DB.
2. For Markdown: scan the file for the heading text (case-insensitive) and the
   block anchor `^block-id`.  Set `heading` / `block_id` when found; set
   `locator_status='exact'`.  If neither is found but the file exists, set
   `locator_status='fallback_file'`.  If the file does not exist, set
   `locator_status='unavailable'`.
3. For PDF: use `source_spans.metadata['page_number']` when stored; verify the
   page count via `source_pages` if the table is populated.
4. Duplicate anchor check: if the same `block_id` appears more than once in the
   file, set `locator_status='duplicate_anchor'` — do not guess the target row.
5. User notes in `03_Notes/` and `04_Resources/` are NEVER modified to add block
   anchors.  If an anchor is absent, the locator degrades to `fallback_file`.

### 29.5 EvidenceItem Extension

`EvidenceItem` gains one optional field:

```python
locator: StructuredLocator | None = None
```

The locator is populated by `_resolve_locator(db_path, item)` called inside
`build_evidence` for each item that has a backing `source_span_id`.  Items with no
backing span (community reports, synthesis nodes without spans) carry
`locator=None`.

### 29.6 AssetIdentity Resolution Authority (Plan G target, vNEXT)

A source asset — a PDF, a markdown note, or an external image attachment — is
referred to by up to five identifiers that the system currently converts between
ad hoc in many places (vault `relpath`, absolute filesystem path, Zotero
`attachment_key`, content `hash`, `logical_source_id`). The abstraction is named
`AssetIdentity` (not `PdfIdentity`) precisely because it resolves any source
asset, including the external-image-attachment routing folded into Plan G — not
PDFs alone. Plan G introduces **one resolution authority** so the conversion
happens once, at the boundary, and every flow (Reference Mode ingest, add-source,
external-image asset routing, locator building) consumes the same result.

```python
@dataclass(frozen=True)
class AssetIdentity:
    resolution_status: str         # resolved | path_unresolved | untracked
    source_id: int | None          # canonical sources.id when tracked
    abs_path: str | None           # resolved absolute path of the real file
    relpath: str | None            # in-vault path (the STUB for Reference Mode)
    logical_source_id: str | None  # e.g. "zotero:<key>" or "ref-<hash>"
    zotero_key: str | None
    content_hash: str | None
    is_reference: bool             # True when the file is external (not copied)
```

`resolution_status` values (mirrors `locator_status` discipline; callers branch
on status, never guess from `None`):
- `resolved` — a canonical row and a usable `abs_path` are both known.
- `path_unresolved` — the source is tracked (row/logical id known) but the real
  file path could not be resolved on this device (e.g. moved Zotero attachment).
- `untracked` — no `sources` row matches any provided identifier.

Resolution authority: `asset_identity.resolve(paths, *, relpath="", abs_path="",
zotero_key="", content_hash="", logical_source_id="") -> AssetIdentity`. It is the
ONLY place that:
1. expands a Reference Mode stub `.md` to its real external file (absorbs
   `_resolve_reference_source`);
2. resolves a Zotero attachment key via `zotero_tools.resolve_pdf` (the single
   backend Zotero resolver);
3. derives/looks up `logical_source_id` (absorbs `_default_logical_source_id`);
4. matches an existing `sources` row by id / relpath / portable external ref /
   Zotero logical id / hash.

**Open-target rule (consistent with §29.2):** when `is_reference` is true the
`abs_path` (external file) is authoritative for opening; the in-vault `relpath`
stub is never the open target. This is the contract the Sources & Trace locator
fix already honors; no other consumer opens by `relpath` (audited 2026-06-19:
`providerContextFormat` formats text only; the dashboard modal uses `relpath` as
a display label only).

This is a **resolution data structure and facade, not a DB schema change** — no
new tables or columns; `AssetIdentity` is computed from existing `sources` fields.

---

## 30. Retrieval Execution (RTR-*, Plan A, v0.10.0)

### 30.1 RTR-* Identifier

A retrieval execution identifier (`RTR-<8 hex chars>`) is generated once per
`build_evidence` call and attached to the returned `EvidencePack` as
`pack.retrieval_execution_id`.  The orchestrator records it in
`query_traces.retrieval_trace_json` alongside the existing route/ranking trace.

The RTR-* ID is the stable handle Plan F uses to reference the retrieval
execution without a second retrieval root.  It is transport-neutral and does not
create a new DB table; it is carried inside the existing `retrieval_trace_json`
JSONB column.

### 30.2 Retrieval Result Contract (Internal, Transport-Neutral)

The internal retrieval result carried on `EvidencePack` (and persisted in the QTR
trace) after Plan A:

```json
{
  "contract_version": "1",
  "retrieval_execution_id": "RTR-...",
  "route": {"selected": "local", "reason": "..."},
  "policy": {"source_include": [], "source_exclude": []},
  "selection": {
    "candidate_count": 12,
    "selected_count": 8,
    "omitted_counts": {}
  },
  "warnings": []
}
```

This is stored in `query_traces.retrieval_trace_json` and is the only
authoritative record of the retrieval execution for Plan F consumption.  It does
NOT expose MCP-format pack structures, plugin navigation handles, or progressive
context expansion — those are Plan F responsibilities.

### 30.3 Plan-F Handoff Contract

Plan F (`F_agent_context_service.md`) consumes the Plan A retrieval result
without a second retrieval operation.  The Plan F ContextService:

- MUST use the `EvidencePack` returned by Plan A's `build_evidence` as its
  primary evidence source.
- MUST NOT re-run retrieval to supplement or replace Plan A's selection.
- MUST NOT drop `source_span_ids`, `locator`, `evidence_status`, or
  `omitted_counts` fields when constructing the public context pack.
- MAY add progressive expansion handles, client budgeting metadata, and feedback
  lineage ATOP the Plan A result — it MUST NOT mutate the Plan A result object.

### 30.4 Diagnostic Retrieval (No Orphan QTR)

Diagnostic / raw-search surfaces that call `build_evidence` outside the
`QueryOrchestrator` (e.g. CLI `wiki query --context-only`, MCP
`curator_fetch_context`) MUST create an explicit parent QTR through
`db.insert_query_trace` before returning.  A retrieval execution MUST NOT produce
a disconnected `RTR-*` with no parent `QTR-*` in the trace record.

## 31. Unified Agent Context Service (Plan F target, v0.13.0)

Plan F introduces a single backend `ContextService` as the authoritative
transaction boundary for external MCP agents and the Obsidian agent. Existing
query, context, plugin, and MCP adapters remain transport surfaces only; when
they serve agent context, they delegate to this service instead of assembling a
second retrieval path.

### 31.1 Operations

The service exposes five logical operations:

| Operation | Purpose |
|---|---|
| `context_manifest` | Return a bounded summary of available context families and expansion handles. |
| `context_fetch` | Return the initial normalized evidence pack for a query/scope/budget. |
| `context_expand` | Expand a prior pack by handle within the same snapshot or return a typed conflict. |
| `context_verify` | Resolve an item/claim handle to exact source evidence, dependencies, locator state, and contradictions. |
| `context_feedback` | Append a reviewed or pending feedback event against a pack/item/claim without mutating source truth. |

`curator_fetch_context` maps to `context_fetch`. For ContextService-backed
routes, `curator_query` first obtains a pack through `context_fetch` and may
synthesize only over the full already-budgeted pack under the same root trace.
Raw search remains diagnostic; if a client uses it as agent context, it must
share the same policy, snapshot, trace, and provenance primitives.

`context_expand` budgets against the **cumulative** pack: the tokens already
consumed by the pack's selected items seed the budget, so a newly expanded item is
admitted only if it fits within `limit_tokens` alongside everything already
selected. Expansion never grants a fresh full budget — that would let the combined
pack overflow the model window. Items that no longer fit are returned as
`expansion_refused` with the `increase_limit_tokens_or_refetch` retry hint.

### 31.2 Request Contract

Every request carries an explicit purpose, route preference, scope, budget, and
freshness policy:

```json
{
  "contract_version": "1",
  "query": "How is residual learning interpreted?",
  "workspace_path": "/absolute/workspace",
  "purpose": "ground",
  "route": "auto",
  "scope": {"source_ids": [], "active_paths": []},
  "budget": {
    "max_tokens": 6000,
    "max_items": 12,
    "max_tokens_per_item": 700,
    "reserve_for_expansion": 1500
  },
  "detail": "index",
  "freshness_policy": "current_only",
  "expected_snapshot_id": null
}
```

Allowed `purpose` values are `ground`, `verify`, `synthesize`, and `discover`.
Allowed detail levels are `manifest`, `index`, `excerpt`, and `source`.

### 31.3 Root Trace And Snapshot Contract

Exactly one `QTR-*` root owns the logical context request. All retrieval,
packing, expansion, verification, synthesis, degradation, and feedback actions
are ordered child actions of that root. Plan A `RTR-*` retrieval executions are
attached to the caller-owned `QTR-*`; they must not create an orphan root.

The service resolves one immutable snapshot per request. The snapshot closure
includes source/corpus identity, DB epoch, search/index epoch, dependency or
derived-state epoch, `curate.yml` policy hash, model/tokenizer/config identity,
and creation time. The source/corpus epoch is represented as compact deterministic
counts plus ordered `(id, content_hash)` hashes, not as a serialized copy of all
source/span rows. `context_fetch` preallocates the root `QTR-*` id and persists
the completed root trace once. `context_expand` requires `pack_id`, expansion
handles, a new budget, and `expected_snapshot_id`; pack-only lookups are resolved
with a database-side ContextService pack-id query rather than a Python scan of
recent traces. If any snapshot component changed, the service returns a typed
conflict with `current_snapshot_id` and does not mix epochs silently.

### 31.4 Context Pack Contract

The normalized pack is versioned and budget bounded:

```json
{
  "contract_version": "1",
  "pack_id": "PACK-...",
  "trace_id": "QTR-...",
  "snapshot": {"snapshot_id": "SNAP-...", "created_at": "..."},
  "route": {"selected": "local", "reason": "...", "stop_reason": "sufficient"},
  "policy": {"applied_filters": [], "excluded": []},
  "budget": {
    "limit_tokens": 6000,
    "used_tokens": 4310,
    "reserved_tokens": 1500,
    "omitted_items": 7,
    "estimation_mode": "tokenizer"
  },
  "coverage": {
    "sufficiency": "sufficient",
    "contradictions_present": false,
    "omission_categories": []
  },
  "items": [],
  "next": [],
  "warnings": []
}
```

Budget enforcement covers total tokens, item count, per-item tokens, route caps,
and reserved expansion budget. Token accounting uses the selected model tokenizer
when available; otherwise it uses a conservative estimator and exposes
`estimation_mode`. The fallback estimator must be conservative for CJK and other
multi-byte text; it must not use an English-only characters-per-token divisor
that underestimates Korean, Chinese, or Japanese evidence. Truncation is never
silent: omitted items, omission categories, insufficiency warnings, and
expansion handles are explicit.

Selected provenance arrays preserve the selected pack order. Implementations
must deduplicate `source_span_ids`, report ids, synthesis ids, and memory-path
ids by first occurrence while iterating selected evidence items; they must not
sort those ids lexicographically after ranking.

### 31.5 Evidence Item Contract

Each selected evidence item carries stable identity and source validity:

- `item_id`, stable `record_id`, `record_hash`, `kind`, and DAG `layer`;
- compact `summary` or `claim` distinct from raw source text;
- authority, truth/support, and freshness state;
- ranking contributions and route/expansion reason;
- structured locator, locator status, and minimal supporting `source_span_ids`;
- immediate dependency ids;
- token cost and detail level;
- contradiction/uncertainty state;
- `expansion_handle` and `verification_handle`.

For source-supported items, all minimal support ids and locators must resolve or
the item is either excluded or returned with an explicit degraded/provisional
state. If an item still carries `source_span_ids` but no backing span/locator can
be resolved, it is returned as `truth_state=orphaned_support` with stale
freshness and an `unavailable` locator; it must not be labeled
`source_supported`. A working-looking link must never be fabricated.

`context_expand` consumes successfully expanded handles from the root pack state.
Repeating the same handle in the same snapshot returns no duplicate item and
does not append another expansion action. Handles requested under an insufficient
budget are returned in `expansion_refused` with `reason=budget_exhausted` and
are not requeued in `next`; clients must raise the budget or refetch rather than
looping over the same handle.

### 31.6 Feedback Contract

`context_feedback` records append-only events with one of these types:
`relevant`, `irrelevant`, `incorrect`, `stale`, `insufficient`, `duplicate`,
`new_insight`, `correction`, or `promotion_request`.

Every event stores the root trace, pack, snapshot, client/purpose, target item or
claim, reviewed evidence/source span ids, user statement, classification, review
status, review actor/time, and any resulting insight, correction, or promotion
lineage. Feedback requests MUST provide both the root `trace_id` (`QTR-*`) and
`pack_id` (`PACK-*`); the backend looks up the trace directly and verifies the
pack belongs to that trace before appending the event. Feedback cannot alter
ranking, truth status, source files, or generated records until a separate
reviewed policy explicitly applies it. The operation returns
`ranking_or_truth_mutated: false`; an unknown feedback type returns
`error_type: invalid_feedback_type` and appends nothing. Each `FBK-*` event is
stored append-only as an ordered `feedback` child action on the root `QTR-*`.

Lifecycle integration stays within the quarantine. A `new_insight` event records a
provisional `pending` insight candidate (the same review queue used by
`curator_propose_correction`) and reports its id in
`resulting_lineage.insight_candidate_id`; the candidate is never applied to
source, generated records, or ranking until a human promotes it. `correction`
patching of generated nodes and explicit `02_Wiki/` promotion remain behind their
existing human-approval tools (`curator_propose_correction`,
`curator_promote_insight` / `promote_answer`) and are not auto-applied by feedback.

### 31.7 Migration And Retention Plan

The physical implementation is additive. Existing `query_traces` remain readable.
New context roots may continue to use `query_traces` for the root row while child
actions, snapshots, packs, and feedback are stored in new versioned records or in
explicit JSON columns/tables chosen during the migration phase. The migration
must be forward/rollback rehearsed on a copied DB before release. No permanent
dual retrieval implementation is allowed: compatibility adapters may preserve old
transport shapes, but retrieval and packing logic live in `ContextService`.

### 31.8 Route Admission And Rollback

`ContextService` serves every Plan-A retrieval route whose evidence is mapped into
the progressive pack path: `local`, `source-section`, `global`, and `explore`.
`local` and `source-section` are always-available safe baselines.

**Explore unification (v0.23.0).** The `explore` route no longer keeps a divergent
associative pipeline. Its *grounding evidence* is built through the same
`context_fetch` pack path as every other route — it produces a `PACK-*`/`SNAP-*`
snapshot, enforces `limit_tokens` via the shared budget, and records ordered
`CTXA-*` actions on the one root `QTR-*`. The behavior unique to explore —
generating follow-up questions and provisional insight candidates — is a
**synthesis-phase consumer** of that normalized pack (`QueryOrchestrator`), not a
second retrieval path. `explore` is admitted into the pack path but is **not** a
safe baseline: it may be disabled for rollback like `global`, in which case it
degrades to `local`. Because explore is now a normal admitted route, the public
`fetch_context` (MCP grounding) surface returns explore-route grounding for
discovery-signal questions instead of silently degrading them to `local`; the
follow-up/insight synthesis still only runs through the answer path, never through
`fetch_context`.

After the router chooses a route, ContextService applies an admission gate
**before any retrieval runs**, so a rejected route never produces a second or
divergent retrieval execution:

- A route that is not in the admitted set degrades to `local`.
- An admitted experimental route (currently `global` and `explore`) may be
  independently disabled for rollback via the `INCURATOR_DISABLED_ROUTES`
  environment variable (comma-separated) or a programmatic `disabled_routes`
  argument; a disabled route degrades to `local`. Safe baseline routes
  (`local`, `source-section`) are never disabled.

The decision is recorded as `route_admission` on both the response and the root
trace's `context_service` payload: `{requested, served, admitted_routes,
disabled_routes, downgraded}`. Exactly one `RTR-*` retrieval execution attaches to
the one root `QTR-*`; admission changes which route runs, never how many.

## 32. Exception Boundaries And Observable Degradation (v0.36.1)

CLI commands, MCP tools, and hidden plugin APIs may catch an unexpected
exception at their outer transport boundary to preserve their established exit
or JSON result contract. Internal operations must not use an unexplained silent
`except Exception: pass` fallback.

When an internal operation can recover:

- deterministic parsing, filesystem, and conversion fallbacks catch the
  specific expected exception classes;
- optional LLM/provider/client and cleanup boundaries may retain a broad catch
  only when arbitrary implementations can raise unknown exceptions, with an
  explicit reason and module logging;
- a requested operation that succeeds with degraded maintenance, discovery, or
  indexing reports the degradation through an existing `warnings` field or CLI
  warning where that surface already defines one;
- MCP stdio diagnostics use logging and never write plain text to protocol
  stdout.

False success is forbidden. A response must not claim that a requested
maintenance/indexing action completed when it was skipped after an exception.
Optional classification or suggestion failures may preserve deterministic
fallback output, but the suppressed cause remains observable in logs.
