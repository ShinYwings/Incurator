# Incurator - Schema & Operating Conventions (v0.55.0)

Audience: Incurator backend, Obsidian plugin, MCP clients, and coding agents.

This document represents the most concrete layer (`spec`) of the documentation hierarchy (`philosophy` -> `guides` -> `spec`). It is the absolute schema source of truth.

Implementation plans under `.agents/plans/` are transient and strictly subordinate to this spec. They may explain sequencing and alternatives, but code must conform to this file when it writes `.curator/` state, Curator DAG pages, MCP payloads, or provider/model configuration.

Sections 1-17 below define the schema contract. The database engine internalizes search/query traces inside `state.sqlite`. Historical schema definitions are tracked via git history.

The shapes below are the only supported schema contract. There are no
prompt-function wrapper layers, legacy-query fallback path, `curate.yml`
persona-to-KRS auto-mapping, or external search runtime fallback.

## 1. Topology Additions

Current portable `.curator/` layout:

```text
.curator/
├── settings.yml              # vault-scoped portable settings (persona, sync policy, etc.)
├── sync/
│   └── dev-<device-id>.jsonl # portable DB transport snapshots
├── sessions.json             # mergeable plugin chat history
├── zotero_profiles.json      # mergeable import profiles
└── Collections/
    ├── 01_Contexts/
    ├── 02_Atoms/
    ├── 03_Concepts/
    └── 04_Synthesis/            # SYN-*.md projection of the shared L4 Synthesis layer (§11.11)
```

Machine-local state is stored at the repository root:

```text
.cache/
├── config/                   # provider/external config and sync bookkeeping
└── vaults/<vault-key>/
    ├── state.sqlite          # authoritative local replica
    ├── runtime/              # status snapshots and conflict archive
    ├── staging/              # transient ingest workspace
    ├── dashboard.md
    ├── sync-report.json
    ├── log.md
    ├── pdf_pages/
    ├── pdf_crops/
    └── cli/
```

Rules:

- The resolved vault root is hashed into `vault-key`; a local marker beside the
  DB records the root for DB-only backend call sites.
- Machine-local files must never fall back into the synchronized vault. Storage
  isolation is structural and does not depend on `.stignore`.
- `state.sqlite` is the single source of truth. Generated dashboards and DAG
  Markdown pages under `.curator/Collections/` are disposable projections that
  may be regenerated from the database.
- `03_Notes/`, `04_Resources/`, and `06_Archives/` remain read-only for autonomous
  agents. `02_Wiki/` promotion requires an explicit promote/import operation.

## 2. Configuration Schema

### 2.1 Provider Selection

`llm.primary` and `llm.fallback` accept:

```yaml
llm:
  primary: ""              # "" | ollama | claude-code | antigravity-cli | codex-cli
  fallback: ""             # "" | ollama | claude-code | antigravity-cli | codex-cli
```

If a CLI provider fails due to network, quota, or capacity errors and
`llm.fallback` is configured, the FailoverClient retries the same request on the
fallback provider. Antigravity CLI print-mode calls are special-cased: when `agy`
returns exit code 0 with empty stdout but records `RESOURCE_EXHAUSTED`, `429`, or
equivalent capacity text in its CLI log, Incurator must treat the call as a
recoverable `AntigravityCliError` rather than as an empty model answer.

### 2.1.1 Search Provider Selection

Search engine configuration is specified separately in
`docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`. Curator schema only
requires that `search.backend` defaults to `native` and that search state remains
inside the repo-cache `state.sqlite`; embedding/query-expansion/reranker provider
fields, recovery-only expansion thresholds, FTS tables, chunk embeddings, and
query traces belong to the search-engine spec.

### 2.2 Antigravity Model Fields

```yaml
llm:
  antigravity_flash_model: gemini-3.5-flash
  antigravity_think_model: gemini-3.1-pro
```



### 2.3 Instant L1

```yaml
llm:
  instant_l1: true
```

Default: `true`.

When enabled, `wiki add` and backend registration paths create L1 Contexts from
parser structure without calling an LLM. CLI `wiki add` stops after L1; the
plugin's explicit Add Source registration queues L2/L3 background work.
When set to `false`, the legacy LLM-generated L1 summary path is allowed.

### 2.4 Shared Model Catalogue

Provider model choices are defined by the backend bundle:

```text
backend/src/curator/data/models.json
```

Rules:

- Backend and plugin must not maintain divergent hard-coded cloud model lists.
- The backend MCP tool `get_available_models` returns this catalogue to external
  MCP clients.
- The Obsidian plugin bundles this same JSON file at build time for its model
  controls; it must not maintain a separate handwritten model list.
- Local Ollama model discovery remains runtime-local and is excluded from the
  static shared catalogue.
- The canonical macOS/Linux Antigravity installer command is
  `curl -fsSL https://antigravity.google/cli/install.sh | bash`.
- The canonical Windows PowerShell Antigravity installer command is
  `irm https://antigravity.google/cli/install.ps1 | iex`.

### 2.5 Vision Extraction Models (v0.23.0)

Two optional, independently-selectable extraction models, decoupled from
`llm.primary`/`fallback`. See SYSTEM_BEHAVIOR §26.2a for behavior.

```yaml
llm:
  vision_model: ""          # "" = disabled (pymupdf4llm). provider::model — heavy,
                            #   full-page model for `add source` PDF ingest +
                            #   standalone/markdown image description.
  latex_extract_model: ""   # "" = fall back to vision_model. provider::model —
                            #   light region-OCR model for the plugin's interactive
                            #   surfaces (Cmd+Shift+X snip, Convert-to-LaTeX).
  vision_render_dpi: 170    # PyMuPDF get_pixmap target DPI (range ~150-200).
  vision_max_image_px: 1600 # hard cap on a rendered page's longest edge (downscale).
  vision_max_pages_per_run: 300  # total-spend rail for a single `add` run.
```

Rules:

- Both slots empty = pre-v0.22.0 behavior (pymupdf4llm ingest, main-model snip vision).
- Resolution: ingest uses `vision_model` ONLY; interactive surfaces resolve
  `latex_extract_model → vision_model → (main chat model if vision-capable)`. The
  chain advances ONLY on an empty slot; a configured-but-failing model raises and
  halts (no silent fall-through). (SYSTEM_BEHAVIOR §26.2a.)
- A configured model MUST be vision-capable; the value reuses the `provider::model`
  form parsed by `split_provider_model`.
- Cloud vision uses CLI **subscription** auth (no provider API keys): Ollama via
  in-memory base64; agentic CLIs (claude/agy/codex) via a temp PNG under
  `.cache/vision_render/<run-id>/` read by the CLI's vision tool, output normalized
  to clean LaTeX, transient `.cache/vision_render` Markdown link destinations
  sanitized before cache/persistence, temp files removed in `finally` (no leaks).
- Per-page transcription cache key = `(page_content_hash, resolved_vision_model)`;
  a model switch invalidates stale L1.

## 3. L1 Context Schema

v0.2.2 L1 Contexts preserve structural source recall in Markdown (including LaTeX math `$$...$$` and tables) for immediate RAG and section-aware extraction. Small and medium sources may inline raw source text in `Source Sections`. Large sources MUST use a compact on-demand policy: keep section markers, page/section previews, hashes, and provenance in L1, but fetch exact raw evidence from the original source through `fetch_document_section` or page-window parsing instead of duplicating the whole document into CTX.

### 3.1 Frontmatter

```yaml
id: CTX-[UUID8]
type: context
source_path: "[[relative/path/to/source]]"
source_hash: [source content SHA-256]
content_hash: [16-char SHA-256 prefix of normalized L1 body/source text]
domain: general
last_updated: YYYY-MM-DDThh:mm:ssZ
tags:
  - md | pdf | html | docx | txt | image
  - instant-l1
toc:
  - id: s1
    level: 1
    title: Introduction
    page: 1
source_page_count: 12          # PDF only, optional
source_sections_inline: true | false
source_text_policy: inline | on_demand
source_char_count: 12345
parser_used: pymupdf4llm       # v0.2.2: which parser produced L1 (pymupdf4llm | vlm | text)
                               # v0.22.0: "vlm" when a user-elected vision_model
                               # transcribed the rendered pages (SYSTEM_BEHAVIOR §26.2a).
source_pages:                  # PDF only, optional
  - page: 1
    hash: 16-char-page-hash
    chars: 1024
    words: 180
    parser_text: "…"           # v0.22.0, PDF+vlm only: the pymupdf4llm text-layer
                               # extraction for this page, retained for audit/cross-
                               # check even when the VLM transcription became L1. A
                               # transient per-page VLM failure falls back to this.
```

- When `parser_used: vlm`, L1 page text is the vision-model transcription, but each
  page's `parser_text` preserves the pymupdf4llm extraction so a VLM hallucination is
  auditable (formula token cross-check, §26.1) and a transient per-page VLM failure
  degrades to `parser_text` for that page (logged, never silent).

Rules:

- `id` must use the `CTX-` prefix.
- `source_hash` identifies the source content registered in `sources.content_hash`.
- `content_hash` identifies the generated CTX/source-section content and is used
  by incremental sync.
- `toc[].id` must be stable within one generated CTX and use the `sN` shape.
- `toc[].page` is 1-based. For non-PDF text sources, page defaults to `1`.
- PDF page hashes are provenance hints, not standalone canonical source records.

### 3.2 Body

Required sections:

```markdown
## Summary

...

## 1. Key Claims

...

## Source Guide

- Generated scaffold language: English.
- Source truth: original text under `Source Sections` for inline L1 pages, or original file text fetched on demand for large-document L1 pages; previews are retrieval hints.

### Section Previews
- `s1` p.1 — **Introduction**: compact source preview...

## 2. Atom Candidates

- [fact] Section Title: Extract ...

## Source Sections

<!-- section:s1 page:1 -->
## Introduction

source text...

<!-- section:s2 page:42 -->
## Large Document Section

Raw source text is not duplicated in this L1 page because the source is large.
Fetch exact evidence on demand with `fetch_document_section(...)`.
Preview: compact source preview...
```

Rules:

- `## Summary`, `## 1. Key Claims`, `## Source Guide`, and `## 2. Atom
  Candidates` are required by L2 extraction and immediate source recall.
- Generated L1 scaffold text (`Summary`, `Key Claims`, `Source Guide`, Atom
  Candidate instructions) must be written in English.
- When `source_sections_inline=true`, the original source text remains
  unmodified under `Source Sections`, even when the source language is Korean or
  another non-English language.
- Parser-generated heading wikilinks such as `[[Paper#Section]]` are not
  generated DAG edges and must be rendered as plain text in generated CTX
  projections so lint does not see broken/malformed links. The original source
  file and DB source spans remain untouched.
- When `source_sections_inline=false`, `Source Sections` keeps durable section
  markers, headings, page numbers, and compact previews only. Exact raw evidence
  must be retrieved from the original source by `fetch_document_section`.
- L2 extraction readers must hydrate `source_text_policy: on_demand` CTX pages
  from the original source before calling the LLM; compact previews are not
  sufficient evidence for Atom extraction.
- Deterministic fallback Concepts are valid L3 pages when L3 clustering or
  concept drafting fails. They must use `type: concept`, preserve Atom relations
  under `## Relations`, and set a low `confidence_score` so later LLM or human
  review can distinguish them from richer Concepts.
- `Source Guide` previews are retrieval hints with section ids and page numbers;
  they must not replace raw evidence.
- `## Source Sections` is required for instant L1 CTX pages.
- Each source section begins with `<!-- section:{toc_id} page:{page} -->`.
- The section marker is the durable boundary used by batch splitting,
  `fetch_document_section`, and provenance assignment.
- L1 chunking MUST preserve math blocks (`$$...$$`). Chunks split at these boundaries rather than breaking them.
- L1 must preserve recall. It should not collapse multiple unrelated sections
  into one semantic summary before L2 extraction.

## 4. L2 Atom Schema Additions

v0.2.0 Atom fields remain required. v0.2.1 adds deterministic provenance fields
for section-aware extraction:

```yaml
id: ATM-[UUID8]
type: atom
parent_source: 01_Contexts/CTX-[UUID8]
source_path: relative/path/to/source.md
claim_type: fact | equation | theoretical_constraint | entity | technique | procedure | relationship
confidence_score: 0.0
contradicts: []
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: YYYY-MM-DDThh:mm:ssZ
content_hash: [16-char SHA-256 prefix of Atom body]
source_section_id: s3          # optional but required for section-aware L2 output
source_section_title: Method   # optional
source_page: 4                 # optional, 1-based
```

Rules:

- `content_hash` is generated from the Atom body, not from source bytes.
- `source_section_id` must match a CTX `toc[].id` when present.
- `source_page` is 1-based and should be copied from the section marker or PDF
  page fallback.
- L2 extraction may run in batches, but each Atom must be independently
  attributable to a CTX and preferably to a section.
- Section-aware L2 batches may run in parallel when each worker uses an
  independent LLM client clone. Shared non-thread-safe clients must fall back to
  sequential batch execution.
- If the LLM provider fails during L2 extraction, writers may create fallback
  Atoms from L1 `Atom Candidates`. These Atoms must retain `parent_source`,
  `source_section_id`/`source_page` when available, and a low
  `confidence_score` so they are searchable but clearly weaker than LLM- or
  human-verified extraction.
- Generated L2 text fields must be English. Non-English `canonical_name` or
  `statement` output fails contract validation, triggers the capped repair retry,
  and is not persisted if the repair also fails.

## 5. L3 Concept Schema Additions (Frozen L4 Artifacts Removed)

v0.2.0 Concept contracts remain valid. L3 clustering is embedding-first in
v0.2.1+. Implementations may add local embedding dependencies such as
`scikit-learn` and may fall back to the legacy LLM cluster-planning call when
embeddings are unavailable.

> **v0.3.1 redesign — frozen L4 artifacts removed.** The v0.2.x query-generated
> and promoted lifecycle (`exhibition_origin`, `ephemeral`,
> `cache_key`, answer cache) is **removed** (see §15). Queries are
> **sessionless**: they return an answer + `QTR-` trace and write **no** vault
> file. The L4 layer is now the shared **Synthesis** layer (`SYN-`, §11.11), and
> curation is a dynamic query-time lens.

Rules:

- `workspace_id` is derived from the active workspace slug (basename of the
  workspace path); outside a workspace it defaults to `default`. A plain chat turn
  whose active note is not inside a workspace folder resolves to `default`; the
  plugin must not bind an arbitrary workspace (e.g. the first `curate.yml` found in
  the vault) to a conversational chat.
- The language bridge fields (`input_language`, `english_query`,
  `final_output_language`) are response/trace-only and returned in the query JSON;
  no file persists them.
- Durable human artifacts come only from an explicit promotion to `02_Wiki/`
  (insight candidate → `02_Wiki/`).

## 6. SQLite State Schema Additions

### 6.1 `sources`

The v0.2.1 source row has per-layer status columns:

```sql
l1_status TEXT NOT NULL DEFAULT 'pending';
l2_status TEXT NOT NULL DEFAULT 'pending';
l3_status TEXT NOT NULL DEFAULT 'pending';
l4_status TEXT NOT NULL DEFAULT 'pending';
layer_error TEXT;
domain TEXT;
tags TEXT;
import_origin_ref TEXT;
import_policy TEXT;
external_ref TEXT;
is_reference INTEGER NOT NULL DEFAULT 0;
logical_source_id TEXT;
error_reason TEXT;
updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
```

Allowed layer states:

```text
pending | running | done | error | skipped
```

Rules:

- `status='curated'` is not the source of truth for L1 completion.
- `wiki status` must count L1 completion from `l1_status='done'`.
- `updated_at` is the source-row LWW revision. Every local source mutation,
  including a layer-status-only update, advances it. `last_ingested` remains
  ingest metadata and is not a general revision.
- `context_id` is set when L1 completes.
- L2/L3 may remain `pending` while a source is already usable for section RAG.
- `l4_status='done'` is the source-level signal that shared L4 Synthesis has been
  produced from L3 reports grounded in that source's spans. L2/L3 completion, or
  unrelated corpus-wide synthesis, must not be labelled as L4-ready for a source
  that did not contribute to the L4 evidence chain.
- `l4_status='skipped'` is a terminal non-error state after global L3 when no
  eligible community reports/syntheses exist for the current corpus. It must be
  shown distinctly from `pending`, not treated as still-running L4 work.
- Layer `error` states must remain visible until retried or reset; later layers
  must not mask an earlier failed layer with a healthy color.
- The `moved` and `hash_drift` states are dynamically computed and returned over MCP. They are NOT stored in the `status` column enum in SQLite to avoid destructive mutations.

### 6.2 `source_pdf_pages`

```sql
source_id INTEGER NOT NULL;
relpath TEXT NOT NULL;
page_number INTEGER NOT NULL;
content_hash TEXT NOT NULL;
char_count INTEGER NOT NULL DEFAULT 0;
word_count INTEGER NOT NULL DEFAULT 0;
metadata TEXT;
extracted_at TEXT NOT NULL;
PRIMARY KEY (source_id, page_number);
```

Rules:

- This table stores page provenance metadata. It does not need to store full page
  text if the backend can re-parse the source to serve page text.
- `metadata` may include PDF parser-specific data, but clients must not depend
  on undocumented keys.

### 6.3 `ingest_jobs`

```sql
id INTEGER PRIMARY KEY AUTOINCREMENT;
source_id INTEGER NOT NULL;
job_type TEXT NOT NULL DEFAULT 'l2_atoms';
trigger TEXT NOT NULL DEFAULT 'wiki_add';
node_id TEXT;
state TEXT NOT NULL DEFAULT 'queued';
phase TEXT;
progress REAL DEFAULT 0.0;
progress_current INTEGER DEFAULT 0;
progress_total INTEGER DEFAULT 0;
source_name TEXT DEFAULT '';
pages_created INTEGER DEFAULT 0;
pages_updated INTEGER DEFAULT 0;
error TEXT;
created_at TEXT NOT NULL;
started_at TEXT;
finished_at TEXT;
```

Allowed job states:

```text
queued | running | done | failed | interrupted
```

Rules:

- Plugin Add Source registration queues L2/L3 work. CLI `wiki build` queues the
  same work unless `--wait` requests foreground processing; CLI `wiki add` stops
  after instant L1.
- MCP server workers and `wiki jobs run` consume the same queue.
- Job state must survive UI tab close and process restart.

### 6.4 `job_events`

```sql
job_id INTEGER NOT NULL;
seq INTEGER NOT NULL;
kind TEXT NOT NULL;
data TEXT NOT NULL;
at TEXT NOT NULL;
```

Rules:

- `seq` is monotonic per job.
- `data` is JSON.
- Events support dashboard rendering and client rejoin.

### 6.5 `dag_edges`

```sql
id TEXT PRIMARY KEY;
from_id TEXT NOT NULL;
to_id TEXT NOT NULL;
edge_type TEXT NOT NULL;
source_id INTEGER;
created_at TEXT NOT NULL;
```

Allowed edge types:

```text
extracted_from   # CTX -> ATM
clustered_to     # ATM -> CON
synthesized_to   # CON -> EXH
```

Rules:

- `dag_edges` is an index for traversal and observability.
- File frontmatter/body links remain valid, but incremental sync may use this SQL
  edge index to expand downstream impact without scanning every markdown page.

### 6.6 `page_hashes`

`page_hashes` records generated page content hashes for incremental sync.

Rules:

- A body/content hash change in an L1/L2/L3 node invalidates downstream nodes.
- `wiki sync` default mode is incremental. Full verification requires `--full`.

## 7. MCP Payload Contracts

### 7.1 `check_source_status`

Input:

```json
{"file_hash": "sha256", "workspace_path": ""}
```

Output:

```json
{
  "registered": true,
  "source_id": 1,
  "relpath": "04_Resources/paper.pdf",
  "source_path": "04_Resources/paper.pdf",
  "l1_complete": true,
  "l2_complete": false,
  "l3_complete": false,
  "l4_complete": false,
  "jobs_pending": [
    {"id": 3, "type": "l2_atoms", "state": "queued", "phase": "queued"}
  ],
  "source": {}
}
```

`relpath` and `source_path` carry the same vault-relative value; `source_path`
is retained for older clients. `l4_complete` is reported alongside the other
layer flags. `source` is the full source record (`_source_dict`), so a client
that needs more than the layer flags does not have to make a second call. An
unregistered hash returns the same keys with `registered: false`, a null
`source_id`, all four layer flags `false`, and an empty `jobs_pending` — it
carries neither `relpath`/`source_path` nor `source`.

Looking a source up by `source_id` / `relpath` instead of `file_hash` returns a
different shape — `{"stats": …, "source": …}`, or
`{"state": "untracked", "error": …, "source_path": …, "stats": …}` when the row
does not exist — and the no-argument list form returns `{"stats": …, "sources": …}`.

### 7.2 `fetch_document_section`

Input:

```json
{
  "source_key": "hash-or-source-path-or-logical-id",
  "toc_id": "s3",
  "page_start": 4,
  "page_end": 5,
  "workspace_path": ""
}
```

Output:

```json
{
  "ok": true,
  "source_id": 1,
  "toc_id": "s3",
  "title": "Method",
  "page_start": 4,
  "page_end": 5,
  "text": "...",
  "provenance": {
    "source_path": "04_Resources/paper.pdf",
    "context_id": "CTX-12345678"
  }
}
```

Rules:

- If the source is unregistered, the plugin may serve an ephemeral in-memory
  section instead of calling the backend.
- If L1 is complete and L2/L3 are pending, the backend may serve CTX `Source Sections`.
- If no `toc_id` matches, page range fallback is allowed for PDFs.

### 7.3 `get_available_models`

Output:

```json
{
  "ok": true,
  "providers": {
    "antigravity": [],
    "claude": [],
    "openai": [],
    "deepseek": [],
    "ollama": []
  }
}
```

Rules:

- The response is generated from the backend shared model catalogue.
- Local model discovery remains provider-specific and may be served separately.
- Each provider maps to a list of model entries with the keys `id`, `label`,
  `context_window`, `supports_vision`, `supports_thinking`, `efforts`, and
  `default_effort`. An empty `efforts` list means the model exposes no
  selectable reasoning-effort dimension.

## 8. Synced Device Registry

v0.2.1 defines a sync-friendly device registry at `.cache/config/devices.json`.
This file is shared vault metadata, not a SQLite index, and may be synchronized
by Syncthing.

The registry records:

- Syncthing folder metadata for the active vault, including folder id, label,
  and participating device ids.
- Folder roles for the active vault and configured Zotero roots when Syncthing
  shares those paths. UI readers use these roles to show which devices sync the
  Vault and Zotero without inventing unsupported platform/backend facts.
- Known device display names from Syncthing.
- Per-device backend launcher hints. The supported local launcher is the
  repository-root virtual environment binary, for example
  `/Users/<user>/Workspace/Incurator/.venv/bin/wiki`.
- Platform hints for the device that last updated its own entry.

Each device must only update its own launcher entry. Entries learned from other
devices must be preserved so backend path differences can be inspected and
shared without synchronizing Obsidian plugin `data.json`.

## 9. Compatibility Rules

- v0.2.1 readers must accept v0.2.0 L1 pages that lack `toc` and `Source Sections`.
- v0.2.1 writers should emit instant L1 format by default.
- The legacy `gemini-cli` and related config aliases have been fully removed in v0.2.1. All systems must use `antigravity-cli`.
- Tests must cover schema-affecting helpers before implementation is considered
  complete.

## 10. External Resources (Reference Mode)

Files in `04_Resources/` or other root directories may be "Markdown Stubs" that
point to external files (e.g. PDFs in a Zotero library) without copying them
into the vault. This is called Reference Mode.

When an external PDF is added to Incurator from the Obsidian plugin, Reference
Mode is the default behavior. The PDF remains in its original location, while
the backend creates a lightweight `04_Resources/*.md` reference stub and records
the original PDF path in device-local backend state.

### 10.1 Markdown Stub Frontmatter

```yaml
type: reference
logical_source_id: zotero:ABCDEF12
zotero_attachment_key: ABCDEF12
```

Rules:
- The `type` must be `reference`.
- `sources.relpath` must point to the vault-relative markdown stub, not the
  external PDF's absolute path.
- Zotero-backed sources store only `logical_source_id:
  zotero:<effective-attachment-key>`. `external_ref` and `import_origin_ref`
  remain `NULL`; the backend resolves the key through the current device's
  Zotero database whenever it needs the PDF. A resolved absolute path supplied
  alongside the Zotero key is a device-local import hint and does not change
  this locator form or require a generic `external.path_roots` entry.
- Other external sources store `external_ref` as
  `@<root_key>/<relative-posix-path>`. The matching absolute root exists only in
  repo-local `.cache/config/config.yml` under `external.path_roots`.
- The backend accepts only the current source-table columns and locator forms.
  It does not retain an `external_path` / `import_origin` table converter,
  automatic absolute-path migration in `db.connect()`, or a user-facing
  `wiki paths` command.
- For Zotero-backed references, UI/source summaries should use
  `zotero://open-pdf/library/items/<attachment-key>` as the portable display
  path instead of copying the device-local absolute PDF path into `source_path`.
- Automatically generated stubs never write `target_path`.
- If `zotero_key` is present, the backend RAG pipeline must resolve the absolute path using the active `ZOTERO_BASE_PATH` (or Zotero integration logic).
- A manual absolute `target_path` is invalid; generic external files use
  `external_ref`.
- The Curator backend (`ingest_raw.py` and MCP tools) must transparently redirect read/parse operations to the resolved external file, ignoring the stub's body content.
- Zotero-backed references must use `logical_source_id:
  zotero:<attachment-key>` and deduplicate by that id before creating a new
  stub. The stub should include portable open links, including an Obsidian PDF
  viewer link when available and `zotero://open-pdf/library/items/<key>`.
- The linked attachment root resolves Zotero DB `attachments:` paths only; it is
  not required for ordinary Zotero `storage/<KEY>/...` attachments.

---

# v0.3.2 Curation-Native Schema Contract

The sections above (1–10) define the inherited v0.2.2 contract. The sections
below define the schema introduced by the v0.3.1 curation-native rebuild and
amended by v0.3.2 search internalization.
These records turn the Curator from a search-plus-synthesis pipeline into a
curation-native graph/memory compiler: every generated artifact is traceable to
source spans and to the prompt run that produced it, and `curate.yml` compiles
into a runtime policy that drives retrieval and synthesis.

The companion behavior contract is
`docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`; the plugin contract is
`docs/specs/plugin_schema/PLUGIN_SCHEMA.md`. All three must stay
version-synchronized.

### Storage model: DB is the single source of truth; markdown is a derived projection

v0.3.2 keeps the compiler storage model and removes the last search dependency
on emitted markdown:

- **`state.sqlite` is the single source of truth.** All curation knowledge —
  `source_spans`, `knowledge_units`, `graph_entities`/`graph_relations`,
  `community_reports`, `memory_paths`, dependencies, and backprop state — lives
  in the DB. This is the compiler's intermediate representation (IR).
- **The `.curator/Collections/` L1–L4 markdown pages (`CTX-`, `ATM-`, `CON-`,
  `SYN-`) are a DERIVED, disposable projection of the DB ("object code").** They
  are emitted from DB records and are NOT authoritative. As of v0.3.2 they are
  not the search corpus. Search indexes authoritative DB records directly through
  the internal `search_documents`, FTS5, chunk embedding, and query trace tables
  defined below. Projection pages may be deleted and re-emitted from the DB at
  any time. Because they are emitted (never edited as truth), there is no DB↔file
  drift.
- **Human-facing durable knowledge is promoted to `02_Wiki/`.** Generated L4
  Synthesis nodes remain DB-owned projections; query answers are sessionless and
  traceable.
- Consequently the per-page frontmatter shapes in §12–§15 describe the **emitted
  projection** of the DB records, not an independent source of truth. When an
  approved backend mutation changes a DB record, the authoritative DB
  row, search document/chunk rows, FTS5 rows, and embedding freshness state update
  in the same backend write path. Projection re-emission is an Obsidian
  convenience step, not a retrieval prerequisite.

## 11. SQLite State Schema (`SCHEMA_VERSION = 13`)

v0.4.0 set `db.SCHEMA_VERSION` to `7`; v0.8.0 (Plan B) bumps it to `8`; v0.9.0
(Plan C — Graph Quality) bumps it to `9`. The v0.3.2 tables remain in use.
v0.4.0 added the cross-device sync tombstone table (`deleted_records`, §11.17)
and the `wiki db export/import` pipeline. v0.8.0 adds the claim-level support /
formula-lifecycle / compiler-generation schema (§20), strictly additive over v7.
v0.9.0 adds the entity/relation resolution, independent relation support, and
hierarchical-community-quality schema (§21), strictly additive over v8. All ids
use typed string prefixes so they are self-describing in traces and frontmatter.

> **Version history.** `SCHEMA_VERSION = 4` introduced the v0.3.1 curation-native
> tables. `SCHEMA_VERSION = 5` adds the shared L4 `synthesis_nodes` table (§11.11)
> for the corpus-wide synthesis layer. The bump is forward-only; old vaults
> self-heal via `executescript(SCHEMA_SQL)` (every table is `IF NOT EXISTS`).
> `SCHEMA_VERSION = 6` adds DB-native search documents/chunks, FTS5 tables,
> chunk embeddings, search index metadata, and durable query traces (§11.12-§11.16).
> `SCHEMA_VERSION = 7` adds `deleted_records` tombstone table for cross-device
> knowledge synchronization (§11.17).
> `SCHEMA_VERSION = 8` adds the Plan B Evidence Compiler Integrity schema —
> `claim_supports`, `compiler_generations`, and the `knowledge_units`
> support/formula/generation columns (§20).
> `SCHEMA_VERSION = 9` adds the Plan C Graph Quality schema — `entity_aliases`,
> `entity_merge_proposals`, `entity_resolution_lineage`, `graph_relation_supports`,
> and the `graph_entities` redirect / `graph_relations` lifecycle-edge-class /
> `community_reports` identity columns (§21). Forward-only and additive over v8;
> indexes are created after their columns exist, `deleted_records`'s CHECK list
> is rebuilt to admit the four new tables, and the backfill infers nothing
> (legacy relations become `provisional`, never auto-`active`).
> `SCHEMA_VERSION = 10` removes absolute-path source columns. It replaces
> `sources.external_path` / `sources.import_origin` with portable
> `external_ref` / `import_origin_ref`, enforces vault-relative `relpath`, and
> makes Zotero attachment identity key-only.
> `SCHEMA_VERSION = 11` adds `sources.updated_at` as the source-row LWW clock.
> `SCHEMA_VERSION = 12` adds `sources.sync_key`, a portable transport identity,
> and `compiler_generations.updated_at`.
> `SCHEMA_VERSION = 13` adds the versioned composite-primary-key tombstone
> transport contract. The SQLite table shape is unchanged: existing scalar
> tombstones remain valid, while composite tombstones use validated canonical
> JSON and source-scoped keys use `sources.sync_key`.
>
> **v0.33.0 strict state-schema policy:** runtime DB initialization no longer
> carries pre-v12 automatic migration shims. Current databases are created from
> the full `SCHEMA_SQL`; unsupported legacy `state.sqlite` files must be rebuilt
> or regenerated from a current JSONL export.

| Record | Id prefix | Purpose |
| --- | --- | --- |
| source span | `SPAN-` | A precise, hashed region of a source (heading section, paragraph, page, equation block, code block). The atomic citation unit. |
| knowledge unit | `KNU-` | A typed L2 claim/definition/equation/etc., each citing ≥1 source span. |
| graph entity | `ENT-` | A named graph node (concept, method, dataset, person, system, …). |
| graph relation | `REL-` | A typed, directed, confidence-scored edge between two entities. |
| community report | `REP-` | A GraphRAG-style summary of a graph community, used for global reasoning. |
| synthesis node | `SYN-` | A shared, corpus-wide cross-cutting synthesized insight distilled from community reports (the durable L4 Synthesis layer). |
| memory path | `MPATH-` | A scored associative walk over the graph, used for explore retrieval. |
| prompt run | `PTR-` | One LLM prompt invocation with input/output hashes, validator status, and provenance. |
| curation plan | `PLAN-` | The compiled plan for one workspace curation/query (route, source policy, retrieval policy, prompt profile). |
| insight candidate | `INS-` | A provisional derived insight, correction, contradiction, or promotion request awaiting human review. |
| query trace | `QTR-` | The top-level trace for one query/curate/explore run, linking route, evidence, and prompt runs. |
| artifact dependency | (composite) | A directed dependency edge `(artifact, depends_on)` with a dependency hash for staleness detection. |

### 11.1 `source_spans`

```sql
CREATE TABLE IF NOT EXISTS source_spans (
    id TEXT PRIMARY KEY,               -- SPAN-<UUID8>
    source_id INTEGER NOT NULL,
    relpath TEXT NOT NULL,
    span_type TEXT NOT NULL,           -- heading_section | paragraph | page | equation | code | table | figure_caption
    page_number INTEGER,               -- 1-based, PDF
    section_title TEXT,
    toc_id TEXT,                       -- matches CTX toc[].id (sN) when available
    start_char INTEGER,                -- char offset within the source/section, when known
    end_char INTEGER,
    content_hash TEXT NOT NULL,        -- hash of the exact span text
    text_preview TEXT NOT NULL DEFAULT '',
    metadata TEXT,                     -- JSON
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_source_spans_source ON source_spans(source_id);
CREATE INDEX IF NOT EXISTS idx_source_spans_hash ON source_spans(content_hash);
```

Rules:

- A source span is the atomic citation unit in v0.3.1. Every generated knowledge
  unit, entity, relation, and community report cites source spans by id.
- `content_hash` is the hash of the exact span text, not of the whole source.
  When a source is re-parsed and a span's text is unchanged, its `id` and
  `content_hash` are stable so downstream citations survive a rebuild.
- `span_type` distinguishes structural spans (`heading_section`, `paragraph`,
  `page`) from preserved special blocks (`equation`, `code`, `table`,
  `figure_caption`). Equation and code spans must preserve their exact source
  text and delimiters.
- `toc_id` links a span to the CTX `toc[].id` so `fetch_document_section` and
  span citations share one provenance space.
- Source spans are derived from source truth only. They are never authored from
  derived insight or workspace conversation.

### 11.2 `knowledge_units`

```sql
CREATE TABLE IF NOT EXISTS knowledge_units (
    id TEXT PRIMARY KEY,               -- KNU-<UUID8>
    unit_type TEXT NOT NULL,           -- claim | definition | equation | procedure | method | result | observation | constraint | entity | relationship
    canonical_name TEXT NOT NULL,
    statement TEXT NOT NULL,
    source_span_ids TEXT NOT NULL,     -- JSON array of SPAN- ids (non-empty)
    source_id INTEGER,
    confidence REAL NOT NULL DEFAULT 0.0,
    truth_status TEXT NOT NULL DEFAULT 'source_supported',
                                       -- source_supported | derived_insight | contradiction | promoted_human_truth
    atom_node_id TEXT,                 -- linked ATM- page when one is written
    prompt_run_id TEXT,                -- PTR- of the extraction run
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_knowledge_units_source ON knowledge_units(source_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_units_type ON knowledge_units(unit_type);
```

Rules:

- **No span, no unit.** `source_span_ids` must be a non-empty JSON array of real
  `SPAN-` ids for `truth_status='source_supported'`. The extraction validator
  rejects any unit that cites an invented span id.
- `truth_status` separates source-authored knowledge (`source_supported`) from
  later interpretation (`derived_insight`), conflicts (`contradiction`), and
  human-promoted knowledge (`promoted_human_truth`). A source-supported unit must
  never be silently rewritten to carry a derived insight.
- A knowledge unit is the v0.3.1 typed form of an L2 Atom. When an ATM- page is
  written for a unit, `atom_node_id` links them and the page frontmatter carries
  `knowledge_unit_ids`, `source_span_ids`, and `prompt_trace_ids` (see §15).

### 11.3 `graph_entities`

```sql
CREATE TABLE IF NOT EXISTS graph_entities (
    id TEXT PRIMARY KEY,               -- ENT-<UUID8>
    canonical_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,         -- concept | method | dataset | metric | system | person | organization | other
    description TEXT NOT NULL DEFAULT '',
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    knowledge_unit_ids TEXT NOT NULL DEFAULT '[]',
    prompt_run_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_entities_name ON graph_entities(canonical_name, entity_type);
```

Rules:

- Entities are graph entry points for local and explore retrieval. They are
  deduplicated by `(canonical_name, entity_type)`; re-extraction merges spans and
  knowledge-unit references into the existing entity rather than duplicating it.
- `description` is a generated retrieval aid, not human truth. It must remain
  backed by `source_span_ids`.
- **(v9, §21.1/§21.4)** Exact `(canonical_name, entity_type)` dedup is candidate
  generation only; synonym/abbreviation/homonym resolution, accepted merges
  (with reversible lineage), and `resolution_state` redirects are governed by
  §21. Reads that build authoritative topology resolve `redirected` rows to
  their canonical survivor.

### 11.4 `graph_relations`

```sql
CREATE TABLE IF NOT EXISTS graph_relations (
    id TEXT PRIMARY KEY,               -- REL-<UUID8>
    source_entity_id TEXT NOT NULL,    -- ENT-
    target_entity_id TEXT NOT NULL,    -- ENT-
    relation_type TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    assertion_source TEXT NOT NULL DEFAULT 'source_states',
                                       -- source_states | system_infers | workspace_derives
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.0,
    prompt_run_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_graph_relations_src ON graph_relations(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_graph_relations_tgt ON graph_relations(target_entity_id);
```

Rules:

- Both `source_entity_id` and `target_entity_id` must reference declared
  `graph_entities` rows. The extraction validator rejects relations whose
  endpoints are not declared entities.
- `confidence` must be in `[0.0, 1.0]`.
- `assertion_source` distinguishes what a source literally states
  (`source_states`) from what the Curator infers (`system_infers`) and what a
  workspace derives (`workspace_derives`). `source_states` is necessary but not
  sufficient for factual evidence: an `authored` link records exact
  human-written structure, while only eligible `extracted` support rows may
  ground a factual report finding (§21.5/§21.6).
- **(v9, §21.5/§21.6)** A relation is a proposition with **independent**
  claim-level supports (`graph_relation_supports`); re-extraction adds support
  rows rather than overwriting. `lifecycle_status` (active/provisional/
  quarantined/retired), `edge_class` (authored/extracted), and lineage-based
  support independence are governed by §21. Only `active` relations enter
  authoritative communities. `confidence` is NOT a calibrated noise threshold
  (§21.9).

### 11.5 `community_reports`

```sql
CREATE TABLE IF NOT EXISTS community_reports (
    id TEXT PRIMARY KEY,               -- REP-<UUID8>
    community_key TEXT NOT NULL,       -- stable key for the detected community
    level INTEGER NOT NULL DEFAULT 0,  -- hierarchy level (0 = leaf)
    title TEXT NOT NULL,
    summary TEXT NOT NULL,             -- short global summary
    full_content TEXT NOT NULL,        -- full report body
    finding_json TEXT NOT NULL DEFAULT '[]',  -- JSON list of rated findings
    entity_ids TEXT NOT NULL DEFAULT '[]',
    relation_ids TEXT NOT NULL DEFAULT '[]',
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    rank REAL NOT NULL DEFAULT 0.0,
    prompt_run_id TEXT,
    dependency_hash TEXT NOT NULL,     -- hash of inputs; used for staleness
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_community_reports_key ON community_reports(community_key);
```

Rules:

- Community reports are **generated retrieval aids, not human verification**.
  Their confidence/rank must never be presented as human-verified truth.
- Each report must cite representative `entity_ids`, `relation_ids`, and
  `source_span_ids`, and should record contradictions and "not enough evidence"
  where appropriate.
- `dependency_hash` is computed from the report's input entities/relations/spans.
  When an input changes, the report is stale (see §11.10) and must be regenerated
  before it is used as global evidence.
- **(v9, §21.7)** Community identity is content/config-derived
  (`level`, `member_hash`, `support_hash`, `config_hash`); stale communities
  retire (`retired_at`) rather than being frozen for id stability. Reports are
  built only from `active` relations over canonical entities and MUST cite exact
  eligible claim support — the broad community-span fallback is removed (§21.8).

### 11.6 `memory_paths`

```sql
CREATE TABLE IF NOT EXISTS memory_paths (
    id TEXT PRIMARY KEY,               -- MPATH-<UUID8>
    query_hash TEXT NOT NULL,
    route TEXT NOT NULL,
    start_node_id TEXT NOT NULL DEFAULT '',
    path_json TEXT NOT NULL,           -- ordered JSON list of {entity_id, relation_id} hops
    score REAL NOT NULL DEFAULT 0.0,
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_paths_query ON memory_paths(query_hash);
```

Rules:

- A memory path is a HippoRAG-style associative walk over `graph_entities`/
  `graph_relations`, recorded so explore answers can show *why* two ideas are
  connected.
- `path_json` is an ordered list of hops; each hop names the relation traversed
  so the path is fully auditable.
- v0.3.1 scoring is the explicit linear combination defined in the behavior spec
  (lexical/entity seed, relation confidence, source-span support, recency/
  promoted status, `curate.yml` domain fit). Full Personalized PageRank is out of
  scope for v0.3.1 unless path-trace fidelity is proven by tests first.

### 11.7 `prompt_runs`

```sql
CREATE TABLE IF NOT EXISTS prompt_runs (
    trace_id TEXT PRIMARY KEY,         -- PTR-<UUID8>
    prompt_id TEXT NOT NULL,           -- e.g. curator.knowledge_unit_extract
    prompt_version TEXT NOT NULL,      -- e.g. v1
    family TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',     -- extractor | synthesizer | router | diagnoser | ...
    model_provider TEXT NOT NULL DEFAULT '',
    model_name TEXT NOT NULL DEFAULT '',
    input_hash TEXT NOT NULL,
    output_hash TEXT NOT NULL DEFAULT '',
    validator_status TEXT NOT NULL DEFAULT 'pending',  -- pending | ok | repaired | failed
    validator_errors TEXT NOT NULL DEFAULT '[]',
    retry_count INTEGER NOT NULL DEFAULT 0,
    source_ids TEXT NOT NULL DEFAULT '[]',
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    curate_spec_hash TEXT NOT NULL DEFAULT '',
    query_trace_id TEXT,               -- QTR- that owns this run, when part of a query
    latency_ms INTEGER,
    created_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_prompt_runs_prompt ON prompt_runs(prompt_id, prompt_version);
CREATE INDEX IF NOT EXISTS idx_prompt_runs_query ON prompt_runs(query_trace_id);
```

Rules:

- **Every LLM prompt invocation in v0.3.1 produces a `prompt_runs` row.** A
  generated artifact that cannot name the `PTR-` that produced it is a defect.
- `input_hash`/`output_hash` make prompt regressions diagnosable and allow
  identical-input deduplication.
- `validator_status` records the outcome of the prompt's declared validators:
  `ok` (passed first try), `repaired` (passed after a JSON-repair retry),
  `failed` (no valid output). Failed runs must not silently write artifacts.
- `model_provider` and `model_name` are initialized when the row opens and
  finalized from an immutable provider/model snapshot bound to the response
  whose output hash is stored. A successful failover must not leave the row
  attributed to the failed primary, even if the primary recovers before
  validation finishes.
- If the provider call or JSON-repair call raises after the row is opened, the
  row must be closed as `validator_status='failed'`, with the exception
  class/message recorded in `validator_errors`, so production failures do not
  leave active `pending` traces.
- When a query synthesis call fails with an expected provider `LLMError`, the
  owning `QTR-` must recover every linked `PTR-` through
  `prompt_runs.query_trace_id`, retain the already-selected retrieval
  provenance, and record a failed `synthesis` child action. This is a
  relationship/finalization rule over the existing tables; it adds no column or
  schema migration.

### 11.8 `curation_plans`

```sql
CREATE TABLE IF NOT EXISTS curation_plans (
    id TEXT PRIMARY KEY,               -- PLAN-<UUID8>
    workspace_id TEXT NOT NULL,
    workspace_path TEXT NOT NULL DEFAULT '',
    project TEXT NOT NULL DEFAULT '',
    curate_spec_hash TEXT NOT NULL,
    route TEXT NOT NULL,               -- planned default route for this curation
    source_policy_json TEXT NOT NULL,  -- compiled include/exclude/reference policy
    retrieval_policy_json TEXT NOT NULL,  -- allowed routes, exploration depth, verification
    prompt_profile TEXT NOT NULL DEFAULT '',
    evidence_plan_json TEXT NOT NULL DEFAULT '{}',  -- target concepts/communities/gaps
    prompt_run_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_curation_plans_ws ON curation_plans(workspace_id);
```

Rules:

- A curation plan is the compiled, inspectable bridge between `curate.yml` and a
  curation/query run. It records which sources were selected and excluded (and
  why), the retrieval policy, the prompt profile, and known gaps.
- `curate_spec_hash` ties the plan to the exact `curate.yml` content that produced
  it (see §16). A plan is stale when the spec hash changes.
- Plans are inspectable through the hidden plugin command
  `wiki plugin curate plan --workspace-path PATH` and the MCP
  `curator_plan_workspace` tool.

### 11.9 `insight_candidates`

```sql
CREATE TABLE IF NOT EXISTS insight_candidates (
    id TEXT PRIMARY KEY,               -- INS-<UUID8>
    workspace_id TEXT NOT NULL DEFAULT '',
    source_event_id TEXT NOT NULL DEFAULT '',  -- originating EXH/query/backprop event
    classification TEXT NOT NULL,      -- correction | contradiction | derived_insight | style_only | promotion_request | ambiguous
    statement TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',  -- supporting/missing source spans and nodes
    affected_node_ids TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | accepted | rejected | promoted | needs_review
    prompt_run_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_insight_candidates_ws ON insight_candidates(workspace_id);
CREATE INDEX IF NOT EXISTS idx_insight_candidates_status ON insight_candidates(status);
```

Rules:

- **Insight candidates are provisional, never human truth.** They record what the
  Curator believes a piece of feedback or a discovered connection means, pending
  explicit human action.
- `classification` follows the backprop lifecycle in
  `SYSTEM_BEHAVIOR.md`. A `derived_insight` candidate must never be written
  back into the originating source's L1 context; it lives as a candidate until
  promoted to `02_Wiki/` or attached to a generated/conversational artifact.
- `status='promoted'` is set only by an explicit promotion that writes `02_Wiki/`.

### 11.10 `artifact_dependencies`

```sql
CREATE TABLE IF NOT EXISTS artifact_dependencies (
    artifact_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,       -- knowledge_unit | entity | relation | community_report | synthesis_node | curation_plan
    depends_on_id TEXT NOT NULL,
    depends_on_type TEXT NOT NULL,     -- source_span | knowledge_unit | entity | relation | community_report
    dependency_hash TEXT NOT NULL,     -- hash of the depended-on content at link time
    created_at TEXT NOT NULL,
    PRIMARY KEY (artifact_id, depends_on_id, depends_on_type)
);
CREATE INDEX IF NOT EXISTS idx_artifact_deps_dependson ON artifact_dependencies(depends_on_id);
```

Rules:

- This table is the staleness/invalidation index for generated artifacts. When a
  depended-on record (e.g. a source span, after a re-parse changed its
  `content_hash`) changes, every artifact that depends on it is stale and must be
  regenerated or flagged before it is used as evidence.
- `dependency_hash` records the depended-on content hash at link time so
  staleness is detected by comparison, not by guesswork.
- This index complements `dag_edges` (which indexes file-level CTX→ATM→CON→EXH
  links). `artifact_dependencies` operates at the finer source-span/knowledge-unit
  granularity that v0.3.1 introduces.
- `synthesis_node` (§11.11) is a valid `artifact_type`; each synthesis node records
  a `(synthesis_node → source_span)` dependency so it is invalidated when its
  cited spans change.

### 11.11 `synthesis_nodes`

```sql
CREATE TABLE IF NOT EXISTS synthesis_nodes (
    id TEXT PRIMARY KEY,                        -- SYN-<UUID8>
    title TEXT NOT NULL,
    statement TEXT NOT NULL,                    -- the cross-cutting insight
    full_content TEXT NOT NULL DEFAULT '',      -- supporting explanation
    community_report_ids TEXT NOT NULL DEFAULT '[]',
    concept_ids TEXT NOT NULL DEFAULT '[]',
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.0,
    prompt_run_id TEXT,
    dependency_hash TEXT NOT NULL,              -- hash of the report corpus; staleness
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_synthesis_nodes_confidence ON synthesis_nodes(confidence);
```

Rules:

- Synthesis nodes are the **shared L4 Synthesis layer**: durable,
  workspace-INDEPENDENT, corpus-wide cross-cutting insights distilled from the
  community reports (L3). They are the analogue of the "synthesis"/"permanent
  note" tier in Zettelkasten and other LLM wiki repos — one level above community
  reports, one level below the dynamic per-workspace **Curation lens** (which
  selects/recombines them at query time and is never stored; see
  `SYSTEM_BEHAVIOR.md`).
- Like community reports, synthesis nodes are **generated retrieval aids, not
  human verification**. They must reflect uncertainty and never be presented as
  human-verified truth.
- Each node must cite only allowed `source_span_ids` (the
  `curator.synthesis_write` contract enforces the span-id and confidence
  validators) and records the originating community reports in
  `community_report_ids`.
- `dependency_hash` is the content-addressed hash of the **entire community-report
  corpus**, suffixed with the layer's intended node count — see §20.4b, which
  defines the exact format and why the cardinality is carried here. The synthesis
  layer is regenerated **wholesale**: when the hash AND the node count match the
  layer is skipped (no LLM cost); when any report changes, or the layer is
  incomplete, the whole layer is cleared and rewritten.
- Synthesis nodes are authoritative in the DB and **projected** to
  `.curator/Collections/04_Synthesis/SYN-*.md` as a disposable Obsidian
  projection (`type: synthesis`); the markdown is emitted, never edited as truth
  (§10 storage model).

### 11.11.1 Synthesis Audit Payload

Synthesis audit reports are returned JSON payloads, not persisted tables. They
hydrate existing rows from `synthesis_nodes`, `community_reports`,
`graph_entities`, `graph_relations`, `knowledge_units`, `source_spans`,
`prompt_runs`, `artifact_dependencies`, and `query_traces`.

The JSON shape is additive and stable enough for CLI/plugin consumers:

```json
{
  "ok": true,
  "kind": "synthesis",
  "id": "SYN-12345678",
  "synthesis": {
    "id": "SYN-12345678",
    "title": "Cross-community insight",
    "statement": "...",
    "confidence": 0.84,
    "community_report_ids": ["REP-..."],
    "source_span_ids": ["SPAN-..."],
    "prompt_run_id": "PTR-..."
  },
  "community_reports": [],
  "entities": [],
  "relations": [],
  "knowledge_units": [],
  "source_spans": [],
  "prompt_runs": [],
  "query_trace": null,
  "dependency_warnings": [],
  "warnings": []
}
```

For `kind="report"` the `synthesis` field is omitted and the audited report is
returned in `community_reports`. For `kind="answer"` the `query_trace` field is
required and the evidence lists are hydrated from the `QTR-` row.

Rules:

- Audit payloads must not create new ids or mutate the DB.
- Missing references are represented as warning strings with the missing id.
- `source_spans` entries expose `id`, `source_id`, `relpath`, `span_type`,
  `page_number`, `section_title`, `toc_id`, `content_hash`, `text_preview`, and
  parsed `metadata`.
- `prompt_runs` entries expose trace metadata and hashes, not raw prompt bodies.
- Dependency checks compare `artifact_dependencies.dependency_hash` with the
  depended-on row's current hash when the row type has one. A mismatch becomes a
  warning and must not silently remove the artifact from the report.

### 11.12 Search Engine Tables

Search engine tables are specified separately in
`docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`:

- `search_documents`
- `search_chunks`
- `search_documents_fts`
- `search_documents_fts_tri`
- `search_embeddings`
- `search_index_meta`
- `query_traces`

Curator records remain the authoritative source. Search tables are derived
retrieval state in repo-cache `state.sqlite` and must be rebuilt from Curator
records by `wiki reindex`.

## 12. Upgraded L1 Source Map

v0.3.1 keeps the v0.2.2 L1 CTX page contract (§3) and adds a source-span index.
When `wiki add` writes an instant L1 CTX, it also extracts `source_spans` for the
source (markdown headings/paragraphs/equations/code, or PDF pages/sections) and
records them in the schema. The CTX page gains an optional frontmatter list:

```yaml
source_span_ids:
  - SPAN-1a2b3c4d
  - SPAN-5e6f7a8b
```

Rules:

- Source-span extraction is deterministic and parser-first; it must not require an
  LLM (it runs inside the instant-L1 path).
- The CTX `## Source Sections` markers and the `source_spans` rows describe the
  same regions. `SPAN-` ids are the durable citation handles; CTX section markers
  remain the human-readable boundaries.
- L1 still preserves source recall and math blocks (§3). Spans do not replace the
  inline/on-demand source text policy; they index it.

## 13. Typed L2 Knowledge Units

The v0.3.1 L2 layer is the typed `knowledge_units` table (§11.2). When the
Curator writes ATM- pages, they represent knowledge units and their frontmatter
extends the v0.2.2 Atom schema (§4) with span/unit/trace provenance:

```yaml
id: ATM-[UUID8]
type: atom
unit_type: claim            # claim | definition | equation | procedure | method | result | observation | constraint
knowledge_unit_ids:
  - KNU-[UUID8]
source_span_ids:
  - SPAN-[UUID8]
prompt_trace_ids:
  - PTR-[UUID8]
truth_status: source_supported
confidence_score: 0.0
```

Rules:

- An ATM- page without at least one `source_span_ids` entry is invalid for
  `truth_status: source_supported`.
- `unit_type` mirrors `knowledge_units.unit_type` and supersedes the looser
  v0.2.2 `claim_type` for v0.3.1 extraction (v0.2.2 `claim_type` values remain
  readable on archived pages).
- ATM titles and bodies are projected from English `knowledge_units.canonical_name`
  and `knowledge_units.statement`; source-span evidence may remain in the original
  source language.

## 14. L3 Concept, Entity, And Community Layer

v0.3.1 keeps human-inspectable Concepts (CON- pages) and adds the entity/
relation graph and community reports as backend-owned records (§11.3–§11.5).

- Concepts remain clusters of knowledge units, written as CON- pages.
- Entities/relations live in SQL only by default; they do not each require a
  markdown page.
- Community reports live in SQL (`community_reports`). A markdown rendering under
  `.curator/Collections/` is optional and may be added later for Obsidian
  inspection; the SQL record is the source of truth.

## 15. L4 Synthesis Layer And The Dynamic Curation Lens

> **v0.3.1 redesign.** The per-workspace frozen L4 artifact (`curator.exhibition_write`,
> the answer-cache, and the markdown
> reverse-parse backprop path) is **removed**. It was the wrong abstraction: a
> frozen per-workspace package under-recalls (turn-N needs unstaged knowledge),
> goes stale against the live DAG, and duplicates the DAG (projection pollution + GC
> pain). There is **no backward compatibility**.

The L4 layer is now the **shared Synthesis layer** (`synthesis_nodes` / `SYN-`,
§11.11) — durable, workspace-independent, source-grounded cross-cutting insights
distilled from the community reports.

**Curation is a dynamic query-time lens**, never a stored file:

- `fetch_context(query, workspace)` (MCP `curator_fetch_context`) returns the
  workspace-KRS-biased **evidence pack** (synthesis nodes + community reports +
  entities/spans + memory paths), with NO synthesized answer — for reasoning
  agents that run their own LLM.
- `answer(query, workspace)` (`wiki query`, MCP `curator_query`, plugin) returns
  evidence + a synthesized answer. Both are **sessionless**: they return an
  answer + a `QTR-` trace and write **no** vault file.
- If answer synthesis fails because the configured provider returns no usable
  output or raises an expected `LLMError`, the result contains `error` instead
  of `answer` and preserves the existing `QTR-`, linked `PTR-` ids, warnings,
  and retrieval provenance. Unexpected programming or storage exceptions are
  not converted into provider failures.
- The lens is biased by `curate.yml` (the Knowledge Requirement Spec) and
  accumulated insight candidates — additive bias over the full DAG, never a frozen
  subset.

Durable human artifacts come only from an explicit **promotion to `02_Wiki/`**
(insight candidate -> `02_Wiki/`), never from a generated query artifact.

Backprop is **correction-driven and generated-artifact-independent**:
`curator_propose_correction` classifies proposals and may create provisional
insight candidates; it never patches generated DB nodes automatically. Any
approved follow-up mutation must protect source truth.

## 16. `curate.yml` Knowledge Requirement Specification

v0.3.1 makes `curate.yml` the full Knowledge Requirement Specification. The
canonical shape adds structured sections; the authoritative field-by-field
semantics live in `SYSTEM_BEHAVIOR.md` §16 and the user guides.

```yaml
project: "resnet-dynamics-lab"
description: "Workspace purpose."

goal:
  primary: "Explain and extend residual-network knowledge through a dynamics lens."
  audience: "researcher"        # researcher | engineer | learner | writer | generalist
  deliverables: ["curated-context", "research-note-context"]
  success_criteria:
    - "Every mathematical claim cites a source span."

sources:
  include: ["03_Notes/**", "04_Resources/**"]
  exclude: ["03_Notes/private/**"]
  reference_mode:
    allow_external: true
    require_rebind_approval: true

knowledge:
  domains: ["machine-learning", "dynamical-systems"]
  topics: ["residual learning", "Euler discretization"]
  disambiguation_keywords: ["ResNet", "Neural ODE"]
  avoid_merges:
    - "original ResNet claim != later ODE interpretation"

output:
  format: "context-pack"
  style: "dense-technical"
  citation_style: "curator-source-spans"
  include_sections: ["Evidence Map", "Conceptual Synthesis", "Unresolved Gaps", "Agent Directives"]

reasoning:
  default_mode: "auto"            # auto | local | global | explore | source-section
  allowed_modes: ["local", "global", "explore"]
  exploration_enabled: true
  max_followups: 5
  require_insight_candidates: false

verification:
  min_confidence: 0.70
  high_threshold: 0.85
  require_source_spans: true
  allow_general_knowledge: false
  contradiction_policy: "surface-and-flag"  # surface-and-flag | merge-allowed | needs-review

backprop:
  enabled: true
  source_truth_policy: "never_rewrite_original_source"
  derived_insight_policy: "record_then_promote_or_patch_generated"
  ambiguous_merge_policy: "needs_review"

prompts:
  profile: "default"
  output_language: "same_as_latest_request"
  prompt_overrides: {}
```

Rules:

- `curate.yml` is compiled into a `CurationPolicy` (behavior spec §16) and a
  `curation_plans` row (§11.8). The compiled hash is `curate_spec_hash`.
- Per the clean-rebuild stance, v0.3.1 parses this shape directly. The old
  `persona.*` → KRS auto-mapping is **not** maintained; a workspace expressed only
  in the old persona shape must be re-authored in the v0.3.1 shape.
- `avoid_merges` entries are false-merge guards. The Curator must keep the named
  ideas distinguishable and must not collapse them into one entity/concept.

## 17. Id And Prefix Registry

v0.3.1 valid id prefixes are the active projection prefixes plus the new record
prefixes.

```text
CTX-   L1 Context page
ATM-   L2 Atom page (knowledge unit projection)
CON-   L3 Concept page
SYN-   L4 Synthesis page
SPAN-  source span
KNU-   knowledge unit
ENT-   graph entity
REL-   graph relation
REP-   community report
MPATH- memory path
PTR-   prompt run / prompt trace
PLAN-  curation plan
INS-   insight candidate
QTR-   query trace
GEN-   compiler generation (v0.8.0, §20)
```

All ids are generated backend-side. Generated content (knowledge units,
entities, relations, reports, paths, synthesis nodes) must reference only ids that
already exist; prompt validators reject invented ids.

## 11.17 `deleted_records` — Cross-Device Sync Tombstones (`SCHEMA_VERSION = 13`)

Records deleted on one device are propagated to other devices on the next `wiki db import`. The tombstone table stores the table name and the deleted record's primary key so the deletion can be applied without needing the original row.

```sql
CREATE TABLE IF NOT EXISTS deleted_records (
    table_name  TEXT NOT NULL,
    record_id   TEXT NOT NULL,
    deleted_at  TEXT NOT NULL,   -- ISO 8601 UTC
    PRIMARY KEY (table_name, record_id),
    CHECK (table_name IN (
        'sources','atoms','concepts','synthesis_nodes',
        'source_spans','knowledge_units','graph_entities','graph_relations',
        'community_reports','memory_paths','prompt_runs','dag_edges',
        'curation_plans','insight_candidates','artifact_dependencies',
        'synthesis','query_traces','source_pages','source_pdf_pages',
        'claim_supports','compiler_generations',
        'entity_aliases','entity_merge_proposals','entity_resolution_lineage',
        'graph_relation_supports'
    ))
);
```

**Invariants:**
- `record_tombstone(db_path, table_name, record_id)` must be called whenever a
  canonical row is hard-deleted. `record_id` is the portable transport-key token,
  not necessarily one physical SQLite column.
- A `sources` tombstone stores the portable `sources.sync_key`, never the
  replica-local integer `sources.id`.
- Scalar-primary-key tables keep their existing raw string token. Composite keys
  use compact, sorted JSON with no insignificant whitespace:
  `{"key":{...},"v":1}`. The accepted fields and scalar types are closed:

  | Table | Tombstone transport fields |
  | --- | --- |
  | `source_pages` | `source_sync_key: string`, `wiki_path: string`, `at: string` |
  | `source_pdf_pages` | `source_sync_key: string`, `page_number: integer` |
  | `claim_supports` | `knowledge_unit_id: string`, `source_span_id: string`, `support_role: string` |
  | `graph_relation_supports` | `relation_id: string`, `knowledge_unit_id: string`, `support_hash: string` |
  | `entity_resolution_lineage` | `decision_id: string`, `origin_entity_id: string` |
  | `artifact_dependencies` | `artifact_id: string`, `depends_on_id: string`, `depends_on_type: string` |

  Unknown, missing, extra, duplicate, or wrongly typed key fields and unsupported
  token versions fail closed. SQL table/column identifiers always come from this
  registry; JSONL input supplies bound values only.
- `source_pages` and `source_pdf_pages` tombstones never transmit the
  replica-local `source_id`. The receiver resolves `source_sync_key` against its
  own `sources` row. If that source is not present yet, the dependent row is
  already absent; the portable tombstone is still retained so a later stale row
  cannot resurrect it.
- During `wiki db import`, tombstones are applied **before** upserts. For a
  mutable row, `deleted_at >= row_revision` means the tombstone wins. A strictly
  newer row removes the older exact tombstone and proceeds through normal LWW.
  An explicit local reinsert of a mutable row likewise advances its revision
  strictly past the exact tombstone before clearing it; merely clearing a
  future-clock tombstone with an older local timestamp is forbidden. For an
  immutable row without a revision clock, an existing tombstone wins.
- Applying an imported tombstone is one SQLite transaction: the target `DELETE`
  must complete before the tombstone is recorded and the deleted counter is
  incremented. A `DELETE` exception aborts the input-file transaction, leaves
  the local row/tombstone state unchanged, and is surfaced to the caller. A
  zero-row delete is still valid when the target was already absent.
- Applying a `sources` tombstone performs the same non-cascading dependent
  cleanup as local source removal before deleting the source row. That cleanup
  is a single transaction over the complete measured ownership/dependency
  closure: source generations become `discarded`, source-owned knowledge units
  become retired, authored relations retire, extracted support rows from the
  source become stale and relation/report lifecycle is recompiled, synthesis
  nodes whose report/span closure changed are invalidated, and source-owned
  canonical rows that are hard-deleted receive their own portable tombstones.
  Shared graph rows remain only when another live source still supports them.
  Device-local jobs/search derivatives are hard-deleted or rematerialized and
  are never transported as canonical tombstones.
- A pre-v13 raw token stored for a composite table is ambiguous. Export or import
  reports its table and token and stops without rewriting or discarding it.
  v12/v13 JSONL snapshots do not interoperate; every device must upgrade and
  re-export before autosync resumes.
- Autosync skips only a well-formed peer header whose schema version is
  incompatible. An unreadable, empty, malformed, non-object, headerless, or
  current-schema snapshot without a valid `export_id` fails visibly and is not
  checkpointed.
- Device-local tables (`search_embeddings`, `ingest_jobs`, `job_events`, `page_hashes`, FTS5 virtual tables) are **never** listed as `table_name` in tombstones and are excluded from `wiki db export`.

**Portable source locators (`SCHEMA_VERSION = 11`):** `sources` has no
device-local path column. Zotero rows merge by stable `zotero:<attachment-key>`
identity. Generic `external_ref` values merge normally because they name a root
variable, not a device path. The receiving backend resolves that variable from
its own ignored `.cache/config/config.yml`. `_DEVICE_LOCAL_COLUMNS` must not
contain source locators.

Only `external.path_roots` and integration `root_keys` are accepted as
machine-local external-root configuration. The backend does not convert legacy
`external.roots` or `external.zotero.roots` arrays.
Machine-local config blocks (`llm`, `search`, `external`) are loaded only from
the repo-local `.cache/config/config.yml`. If those keys are present in the
synced vault `.curator/settings.yml`, they are ignored so macOS/Linux absolute
paths and model settings cannot clobber another device.

Schema v11 adds `sources.updated_at`. Current databases enforce a `NOT NULL`
expression default, and local source writes advance it monotonically. JSONL
import requires a valid remote `updated_at` value for every `sources` row; it
does not synthesize a revision from `last_ingested`, `added_at`, or the current
clock. Malformed source rows are rejected instead of partially imported.

**Portable source transport identity (`SCHEMA_VERSION = 12`):** every source has
a unique, non-empty `sync_key`. The key is derived from a portable integration
identity such as `zotero:<attachment-key>`, a portable external reference, or
`vault:<relpath>`. Absolute-path-derived fallback ids are not valid sync keys.
The integer `sources.id` remains replica-local. Import resolves/upserts a source
by `sync_key`, preserves the receiving replica's integer id, and remaps every
synchronized child `source_id` before applying child rows. JSONL import rejects
`sources` rows without a non-empty `sync_key`.

A `vault:<relpath>` key is normalized to forward slashes when it is derived, so
the same file yields the same key regardless of the operating system that
registered it. The derivation happens in the `sources_set_sync_key` trigger and
only when no key was supplied; an explicitly provided key (a `zotero:` or other
portable identity) is never rewritten.

**Existing `sync_key` values are never rewritten (v0.50.1).** A key that was
derived incorrectly — for instance by a historical trigger body that failed to
normalize separators — stays as it is. `sync_key` is the transport identity that
peers match on, so rewriting one retroactively would detach a row from whatever
its counterparts already agreed to call it, and a repair applied on one device
but not another would split the source rather than converge it. The trigger is
repaired on open; the rows are not. A vault suspected of holding malformed keys
should be inspected (`SELECT sync_key FROM sources WHERE sync_key LIKE '%\%'`)
and corrected deliberately across every replica at once, not silently by a
migration.

---

## 18. Source Truth Protection (Schema-Level)

The following are schema-level invariants enforced across all v0.3.1 records:

- `source_spans` are derived only from registered source files. No span is ever
  created from derived insight, conversation, or community-report text.
- A `knowledge_units` row with `truth_status='source_supported'` must cite ≥1
  real `SPAN-` id and must not be rewritten to encode a later derived insight.
  Derived interpretations are stored as separate rows with
  `truth_status='derived_insight'` and surfaced as `insight_candidates`.
- `03_Notes/`, `04_Resources/`, and `06_Archives/` remain read-only. v0.3.1 adds
  no path that mutates them. Promotion writes only to `02_Wiki/`.

## 19. Compatibility Note

Per the clean-rebuild stance stated at the top of this document, v0.3.1 does not
add migration shims. A vault built under v0.2.x should be rebuilt to populate the
v0.3.1 records (`wiki reset`, then `wiki add` and `wiki build`). Archived v0.2.2
pages remain readable, but new generated artifacts use the v0.3.1 schema.

## 20. Claim-Level Support, Formula Lifecycle, And Compiler Generations (`SCHEMA_VERSION = 8`, v0.8.0)

This section freezes the Plan B (Evidence Compiler Integrity) contract names
before any implementation code is written. It is strictly additive over
`SCHEMA_VERSION = 7`: no existing column, table, or id prefix changes meaning.
The owning failure-atlas cases are F6 (broad-span fallback), F7 (rebuild
idempotency / stale reconciliation / atomic publish), and F10 (preview-only
span evidence). F8 remains Plan C resolution scope; canonical F9 is the
authored-note topology contract implemented through §21.6.

### 20.1 `knowledge_units` Additive Columns

```sql
ALTER TABLE knowledge_units ADD COLUMN semantic_hash TEXT;
ALTER TABLE knowledge_units ADD COLUMN support_status TEXT NOT NULL DEFAULT 'unchecked';
ALTER TABLE knowledge_units ADD COLUMN support_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge_units ADD COLUMN formula_status TEXT NOT NULL DEFAULT 'not_applicable';
ALTER TABLE knowledge_units ADD COLUMN retired_at TEXT;
ALTER TABLE knowledge_units ADD COLUMN generation_id TEXT;
CREATE INDEX IF NOT EXISTS idx_knowledge_units_support ON knowledge_units(support_status);
CREATE INDEX IF NOT EXISTS idx_knowledge_units_generation ON knowledge_units(generation_id);
```

Column semantics (frozen enums):

- `semantic_hash` — deterministic fingerprint of the normalized claim
  statement (normalization algorithm versioned in the prompt contract). Used
  ONLY to propose reconciliation candidates across rebuilds. A matching
  `semantic_hash` never auto-merges two claims whose statement or equation
  content differs materially (Arena decision 6). Stable-id reuse additionally
  requires exact statement equality after whitespace normalization. Formula
  token arrays are structurally serialized in the hash input so adjacent tokens
  or separate formulas cannot collapse into a different formula structure.
- `support_status` ∈ `unchecked | verified | failed | stale`.
  - `unchecked` — no support validation has run (the migration backfill state).
  - `verified` — ≥1 minimal `claim_supports` row with `support_status='verified'`
    and a fresh `evidence_hash`.
  - `failed` — validation ran and the claim's cited spans do not minimally
    support it (wrong-real-span case). Excluded from downstream compile inputs
    and surfaced as informational audit telemetry rather than a sync review
    blocker.
  - `stale` — previously verified, but a cited span's content hash changed or
    the span was removed. Excluded from downstream compile inputs until
    re-validated; stale excluded claims are informational unless they leave a
    dangling served-DAG reference.
- `support_reason` — human/machine-readable verdict reason. Never empty when
  `support_status` is `failed` or `stale`.
- `formula_status` ∈ `not_applicable | preserved_in_text | linked_evidence |
  omitted_incidental | missing | uncertain`.
  - `preserved_in_text` — the central formula appears intact in `statement`.
  - `linked_evidence` — `statement` references an exact formula evidence record
    (a `claim_supports` row with `support_role='formula'`).
  - `omitted_incidental` — an incidental formula was omitted; `support_reason`
    carries an approved reason code (`incidental_omission:<code>`).
  - `missing` — a central formula could not be preserved or linked; the claim
    must not be served as formula-grounded.
  - `uncertain` — recovery produced a candidate below the acceptance
    threshold; excluded from served formulas.
- `retired_at` — ISO 8601 UTC. Non-NULL marks the row retired by source
  edit/delete/split reconciliation. Retired rows are never deleted by the
  compiler (tombstone-style audit trail) and never feed downstream stages,
  projections, or search materialization.
- `generation_id` — the `GEN-` compiler generation that produced or last
  revalidated this row (§20.3). NULL only for legacy rows backfilled by the
  v8 migration.

Eligibility rule (schema-level): a `truth_status='source_supported'` row may
feed downstream compile stages (graph input, reports, synthesis, projections,
search materialization) ONLY when `retired_at IS NULL`,
`support_status='verified'`, its generation is authoritative for the same
`source_id`, and that source row still exists. A generation row without its live
source is audit state, never serving authority. `unchecked` legacy rows are
read-only visible to humans/agents but are not valid downstream compiler inputs
after the v0.8.0 compiler ships.

### 20.2 `claim_supports`

```sql
CREATE TABLE IF NOT EXISTS claim_supports (
    knowledge_unit_id TEXT NOT NULL,
    source_span_id TEXT NOT NULL,
    support_role TEXT NOT NULL,        -- primary | contextual | formula
    support_status TEXT NOT NULL,      -- unchecked | verified | failed | stale
    support_reason TEXT NOT NULL DEFAULT '',
    evidence_hash TEXT NOT NULL,       -- content_hash of the span text at validation time
    validator_trace_id TEXT,           -- PTR- id of the model validation run, NULL for deterministic-only verdicts
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (knowledge_unit_id, source_span_id, support_role)
);
CREATE INDEX IF NOT EXISTS idx_claim_supports_span ON claim_supports(source_span_id);
CREATE INDEX IF NOT EXISTS idx_claim_supports_status ON claim_supports(support_status);
```

Rules:

- A `claim_supports` row is a minimal support record: it asserts that this
  span is part of the smallest span set that entails the claim, in the given
  role. `support_role='primary'` rows carry the entailment; `contextual` rows
  disambiguate; `formula` rows bind a claim to exact formula evidence
  (an `equation` span or an accepted recovery candidate, §20.4).
- Real span ids are necessary but NOT sufficient: a `knowledge_units` row's
  `source_span_ids` array remains the citation surface, while `claim_supports`
  carries the verified minimal subset. Every `verified` unit has ≥1 `verified`
  `primary` support row.
- `evidence_hash` MUST equal the cited span's `content_hash` at validation
  time. The compiler audit (§20.5) marks the support row and its unit `stale`
  whenever the current span hash differs — freshness is re-checked, never
  assumed.
- Migration backfill creates NO `claim_supports` rows. Legacy units stay
  `unchecked` with an empty support set; nothing is silently verified.
- `claim_supports` is a canonical synced table: the v8 migration adds it to
  the `deleted_records` tombstone CHECK list and to `wiki db export`.

### 20.3 `compiler_generations`

```sql
CREATE TABLE IF NOT EXISTS compiler_generations (
    id TEXT PRIMARY KEY,               -- GEN-<UUID8>
    source_id INTEGER,                 -- per-source compile scope; NULL = corpus-wide stage set
    status TEXT NOT NULL DEFAULT 'staged',  -- staged | authoritative | discarded
    prompt_contract_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT,
    discarded_at TEXT,
    audit_json TEXT NOT NULL DEFAULT '{}',  -- publish-gate audit result snapshot
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_compiler_generations_source ON compiler_generations(source_id, status);
```

Rules (Arena decision 8 — staged atomic publish):

- Generation-owned Plan-B writes (knowledge units and claim supports) plus the
  serialized graph publish in one transaction. Stable projection identity,
  DAG, and artifact-dependency rows are completed deterministically in the
  recoverable post-publish phase. Markdown and search remain disposable
  projections derived from the authoritative generation.
- A generation becomes `authoritative` ONLY after every required canonical row,
  dependency, and serialized graph result for its scope validates. Until then
  its rows are `staged` and invisible to query/evidence/search surfaces.
  Invisibility is enforced at write/materialization time
  (SYSTEM_BEHAVIOR §26.3): staged units carry TEMPORARY ids and are never
  emitted as ATM projections, upserted into the graph, or materialized into
  search; only an authoritative generation's units reach those surfaces. An
  authoritative generation MAY contain non-verified units — served =
  authoritative ∧ `support_status='verified'` ∧ `retired_at IS NULL`.
- At most one `authoritative` generation exists per `source_id` scope. The
  prior authoritative generation is retained until the new one publishes, then
  retired per the reconciliation contract (SYSTEM_BEHAVIOR §26).
- A failed compile sets `status='discarded'`; discarded staged rows (including
  the temp-id knowledge units and their claim supports) are removed and the
  prior authoritative generation remains untouched. No graph entity/relation,
  ATM projection, or search doc is ever written for a staged generation, so a
  discard leaves no orphan downstream artifact. No partial authoritative
  publish is representable in this contract.
- The authoritative DB transaction and its disposable projection phase have
  distinct failure semantics. After DB publish, every serving knowledge unit
  has a persisted stable `atom_node_id` and dependency rows before filesystem
  output begins. The publish transaction also stores a pending projection
  marker. If the process stops before output begins, or ATM/CON/SYN emission or
  search materialization fails, the published generation remains authoritative
  and retry performs a deterministic full projection/search re-emit from that
  generation without another LLM call or a replacement generation. A partial
  filesystem projection is never treated as authority. Successful full re-emit
  also replaces the device-local ATM/CON/SYN page-hash baseline and removes only
  deleted orphan CTX hashes; it does not bless preserved CTX edits.
- Unchanged-rebuild idempotency: recompiling an unchanged source under the
  same prompt contract version MUST reuse the existing authoritative
  generation's claim ids, hashes, dependency closure, and counts (verified by
  the compiler audit; F7 oracle).
- `compiler_generations` is canonical and synced (tombstone CHECK +
  `wiki db export`), since authoritative-generation identity must agree across
  devices.
- `audit_json` contains the exact sorted `authored_relation_ids` owned by the
  generation in addition to claim/unit audit fields. The field is the
  membership authority during replica reconciliation: shared deterministic
  relation ids are reassigned to the winning generation, and only
  loser-exclusive ids retire. Missing, malformed, or non-list membership fails
  closed and cannot resurrect an authored row. The same exact membership is an
  admission requirement: an authored relation absent from its generation's
  valid membership cannot be `active`. For report invalidation, a winner-member
  relation counts as newly active when it is absent from any losing
  generation's valid membership.
- Reconciliation runs for every source scope, including a single remaining
  authoritative generation. If its source row is absent (for example, a source
  tombstone won), there is no eligible winner: every authoritative generation
  in that source scope is discarded and its authored relations retire.
- Every repair, discard, and retirement transition writes a valid LWW revision
  strictly newer than the current wall clock and every valid revision observed
  on the affected generation, relation, or report. Equal-clock repair is not a
  state change to a strict-greater LWW peer and is therefore forbidden. A stale
  `staged`/`discarded` snapshot cannot overwrite a newer authoritative row.

### 20.3.1 JSONL Import Boundary (`SCHEMA_VERSION = 13`)

- Export headers include a unique `export_id`; peer high-water state records
  this id rather than relying on filesystem mtime.
- Import accepts only frozen `SYNC_TABLES` entries and columns declared by the
  local table schema.
- Schema v12 snapshots are unsupported once v13 is active. v13 adds the
  composite tombstone token and convergence rules in §11.17; mixed-version peers
  must upgrade and re-export rather than partially applying a snapshot.

### 20.4 Formula Recovery Candidates (`source_spans.metadata.formula_recovery`)

Per the Arena consensus, recovery candidates are NOT normalized into a new
table unless Plan B measurements prove a multiple-attempt lifecycle or indexed
audit need. The frozen default is structured `source_spans.metadata` under the
reserved key `formula_recovery`:

```json
{
  "formula_recovery": [
    {
      "status": "candidate",            // candidate | reviewed | rejected
      "loss_verdict": "image_only",     // fragmented | image_only | parser_omitted
      "locator": {"source_id": 3, "page": 7, "region": [120, 410, 580, 470]},
      "page_hash": "<sha256 of the rendered page image>",
      "crop_hash": "<sha256 of the cropped region image>",
      "provider": "antigravity",
      "model": "gemini-3.5-flash",
      "confidence": 0.91,
      "latex": "\\\\nabla_W L = \\\\delta x^T",
      "validator_trace_id": "PTR-...",  // null until reviewed
      "created_at": "2026-06-13T00:00:00Z"
    }
  ]
}
```

Rules (Arena decisions 2-4; Plan E FR05 contract candidates):

- Raw parser/source span text is immutable. A recovery candidate never
  overwrites `text_preview`, `content_hash`, or any source file.
- Recovery may run ONLY on a region with a measured loss verdict where parser
  AND raw text AND current extraction all either (a) MISS the region entirely
  (`image_only`, `parser_omitted`) OR (b) yield a STRUCTURALLY-INVALID/garbled
  rendering of it (`fragmented` — present but corrupt, e.g. a dropped `\nabla`,
  a lost superscript, or a split `$$` block). `fragmented` is triggered by a
  structural-validation failure of the extracted formula against the rendered
  region, not by total absence. Whole-corpus/every-page VLM processing is
  rejected by contract.
- Parseable LaTeX alone cannot move a candidate to `reviewed`; a validator
  verdict (deterministic gold check or recorded human review) is required, and
  `validator_trace_id` records it. The default acceptance threshold is `0.80`,
  and the recovered ordered token sequence must exactly match a formula in the
  owning claim. Reviewed promotion also requires hydrated full raw-span text
  for every cited span; each SHA-256 must match `source_spans.content_hash`,
  and stored 200-character previews are never used for revalidation.
- `confidence` below the acceptance threshold, a missing validator trace, or a
  structural mismatch keeps the candidate out of served formulas; the owning
  claim's `formula_status` stays `uncertain`.
- An accepted reviewed candidate re-runs claim support against additive
  recovered evidence. Only a verified result may create a verified
  `support_role='formula'` row and move the claim to
  `formula_status='linked_evidence'`.
- A changed `page_hash` invalidates exactly that page's candidates: the audit
  marks them stale-by-hash, and they cannot be cited by `support_role='formula'`
  rows until refreshed.

### 20.3b `l2_checkpoints` Removed (v0.52.0)

The table and its helpers are gone. L2 extraction is all-or-nothing: staged
units from an interrupted run are discarded, then units accumulate in memory and
are bulk-persisted only on full success.

The checkpoint-resume mechanism it served was never reachable — its only writer
sat inside the branch that required checkpoints to already exist, so the table
stayed empty (verified: 0 rows across 36 sources and 2,799 units). Removing it
changed no behavior.

Existing vaults keep the table as an empty orphan. `SCHEMA_SQL` only issues
`CREATE TABLE IF NOT EXISTS` and this codebase has no migration path, so nothing
drops it here. Dropping it belongs to the batch that owns schema migration (B7);
until then an empty, unreferenced table is inert.

Resumable L2 remains worth building. It must be designed rather than re-enabled:
the removed branch returned the staged-unit list, which is empty after a
successful publish and would have attributed zero units to a fresh generation,
retiring the source's entire authoritative unit set under §26.3.

### 20.4a Span-Level Extraction Loss (`source_spans.metadata.loss`, v0.49.0)

Distinct from §20.4. `formula_recovery` records an *attempt to repair* a loss
against an owning claim. `loss` records that a region **could not be read at
all** — there is no text, and therefore no knowledge unit and no claim to
anchor to. Recording it requires no provider call and changes no
`formula_status`.

```json
{
  "loss": {
    "verdict": "image_only",
    "region": {"width": 221, "height": 18},
    "classified_at": "2026-08-08T00:00:00Z"
  }
}
```

- `verdict` — one of `image_only | fragmented | parser_omitted`, the same
  vocabulary as §20.4 and `formula_recovery.LOSS_VERDICTS`.
- `region` — whatever geometry the parser stated, and nothing more. A
  picture-omitted placeholder carries `width`/`height` only; it carries **no
  page coordinates**, so `region` is not a crop locator and must never be
  treated as one. Omit the key entirely when no geometry survived rather than
  writing zeros or nulls.
- `classified_at` — UTC ISO-8601, when the verdict was assigned.

Invariants:

- Additive and non-authoritative. `loss` never gates indexing, never changes
  `support_status` or `formula_status`, and never removes a span.
- Written at span creation, and only there. Because `upsert_source_span` returns
  the existing row for an unchanged `(source_id, content_hash)`, a re-parse does
  NOT refresh `loss`, so spans ingested before this field exists never acquire
  one. There is deliberately **no backfill and no migration**: re-ingesting to
  obtain the record would mean `wiki add --force`, which sets `l2_status` back
  to `pending` and lets the next default `wiki build` selection trigger a full,
  expensive L2/L3 rebuild across every source.
- Because of that, a reader MUST NOT treat a missing `loss` key as proof that
  nothing was lost. Reporting surfaces recognize a pre-existing loss by the
  parser placeholder still present in `source_spans.text_preview`, and the
  stored record is the authoritative signal only for spans written since this
  field existed. Both signals describe the same span and must be counted once.
- `page_number` on a span is a section index, not a physical page. It must not
  be used to locate the lost region in the source document.
- A `metadata` write must survive cross-device import; `source_spans` has no
  `updated_at`, so its LWW revision is derived rather than read from a column.
  See SYSTEM_BEHAVIOR §26.2c.

### 20.4b `synthesis_nodes.dependency_hash` Records Layer Cardinality (v0.50.3)

L4 is regenerated wholesale — the layer is cleared, then each node is written and
committed separately. The corpus hash alone therefore cannot tell a complete
layer from an interrupted one: a crash between the clear and the last write
leaves surviving nodes all carrying the *current* hash, and the idempotency
guard reads that as complete. The layer stays truncated until the corpus changes
enough to move the hash, and nothing reports it.

The stored value is therefore `<corpus-hash>#<intended-node-count>`, and a layer
counts as current only when every node carries the hash for the corpus AND the
count equals the number of nodes actually present.

- `#` cannot appear in a hex digest, so the format is unambiguous.
- A value with no `#` is a legacy row. It reads as **unknown, not current**, so a
  vault frozen by the earlier behavior regenerates exactly once and repairs
  itself. This is deliberate: there is no `ALTER TABLE` path in this codebase, so
  a new column could not reach an existing vault, and a silent migration of the
  column would erase the only evidence that the layer was ever suspect.
- `artifact_dependencies.dependency_hash` keeps the bare corpus hash. It is a
  per-edge record, not a per-layer one, and carries no cardinality claim.

This detects an interrupted write; it does not prevent one. Making the layer
rebuild atomic is separate and deferred.

### 20.5 Compiler Audit Contract (Schema-Level)

The compiler audit is the read-only traversal that proves the §20 invariants
on a live DB. Its schema-level assertions, all of which must hold for an
authoritative generation:

1. Every active (`retired_at IS NULL`) `source_supported` unit with
   `support_status='verified'` has ≥1 `verified` `primary` `claim_supports`
   row whose `evidence_hash` matches the cited span's current `content_hash`.
2. No active Plan-B-owned generated claim cites the broad all-upstream-span
   set in place of claim-level support (F6). Graph/community-report fallback
   findings are recorded and assigned to Plan C, not silently accepted.
3. No `claim_supports` row cites a missing span id, a retired unit, or a
   discarded generation.
4. Exactly one authoritative generation per compiled source scope; zero
   staged rows visible to query/search surfaces — no ATM projection, graph
   entity/relation, or search doc references a unit whose generation is not
   `authoritative` (staged/discarded rows are never materialized).
5. Every `formula_status` value is consistent with its evidence: rows with
   `linked_evidence` have a matching `formula` support row;
   `omitted_incidental` rows carry a reason code.

Re-validation preserves a recovered `formula` support row (the additive
`recover_formula` evidence link, §20.2) ONLY while it stays relevant: the claim
must still carry a formula AND the support's `source_span_id` must still be in
the unit's declared `source_span_ids`. A `formula` support whose claim lost its
formula, or whose span the claim no longer cites, is stale and is cleared by the
same re-validation pass — so it can never linger as a dangling row (assertion 3)
or a status inconsistency (assertion 5). Recovery always attaches to a cited
span, so a valid link is never dropped.

### 20.6 v8 Schema Columns And Tombstone Extension

- `SCHEMA_VERSION` 8 includes the §20.1 columns, the §20.2/§20.3 tables, and
  `deleted_records` CHECK coverage for `claim_supports` and
  `compiler_generations`.
- Current v0.33.0 initialization creates the complete current schema directly.
  Runtime pre-v12 migration/backfill shims are removed; unsupported legacy DBs
  must be rebuilt or regenerated from a current export.
- `wiki db export` / `wiki db import` include the two new tables; LWW and
  tombstone-first ordering apply unchanged. No device-local columns are added.

## 21. Entity/Relation Resolution And Hierarchical Community Quality (`SCHEMA_VERSION = 9`, v0.9.0)

This section freezes the Plan C (Program 2C — Graph Quality) contract names
before any implementation code is written. It is strictly additive over
`SCHEMA_VERSION = 8`: no existing column, table, or id prefix changes meaning,
and §11.3/§11.4/§11.5 remain valid (this section overlays a resolution/support/
lifecycle layer onto them). The owning Plan C failure-atlas case is **F8**
(graph resolution / unsupported topology). Hierarchy/report grounding is a
section-level Plan C gate, not Failure Atlas F9; canonical F9 is authored-note
topology in §21.6.

> **Target version note.** `v0.9.0` is this milestone's planned product version
> (minor bump after Plan B's `v0.8.0`); the binding bump across
> `pyproject.toml` / `package.json` / `manifest.json` happens at Plan C P10. The
> binding schema constant is `SCHEMA_VERSION = 9`.

Locked Arena consensus this section encodes: similarity is candidate generation
only (no automatic similarity merge); accepted merges preserve origin identity +
reversible rewrite lineage; relations are propositions with **independent**
claim-level supports keyed by source lineage (not row count); authored and
extracted edges stay separate classes; only `active` relations enter
authoritative communities; community identities are content/config-derived and
stale records retire; reports cite exact eligible claim support with no
broad-span fallback.

### 21.1 `entity_aliases`

```sql
CREATE TABLE IF NOT EXISTS entity_aliases (
    id TEXT PRIMARY KEY,               -- ALI-<UUID8> surrogate key; one surface form may resolve to MANY entities (homonyms)
    alias_normalized TEXT NOT NULL,    -- deterministic normalization of the surface form (candidate key, NOT unique alone)
    entity_id TEXT,                    -- ENT- this alias resolves to; NULL while only a candidate
    alias_display TEXT NOT NULL,       -- original surface form as written
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    knowledge_unit_ids TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.0,
    resolution_status TEXT NOT NULL,   -- alias | ambiguous_candidate | merge_proposed | accepted | rejected | reversed
    resolution_reason TEXT NOT NULL DEFAULT '',
    decision_id TEXT,                  -- entity_merge_proposals.id that decided this alias, when applicable
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity ON entity_aliases(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_normalized ON entity_aliases(alias_normalized);
-- A RESOLVED alias is unique per (surface form, entity, status) — this admits a single
-- normalized surface resolving to several distinct entities (homonyms) while still
-- blocking an exact duplicate resolved row. Unresolved candidates (entity_id IS NULL)
-- are keyed only by the surrogate `id` and are excluded from this constraint.
CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_aliases_resolved
    ON entity_aliases(alias_normalized, entity_id, resolution_status)
    WHERE entity_id IS NOT NULL;
```

`resolution_status` (frozen enum):

- `alias` — a confirmed alternate surface form of exactly one `entity_id`
  (synonym/abbreviation/translation) that passed the type/context/contradiction/
  `avoid_merges` guards (§21.6 rules). Resolvable at query/extraction time.
- `ambiguous_candidate` — a similarity- or normalization-generated candidate that
  is NOT auto-resolved. It stays unresolved (homonym risk) until an approved
  decision; it never silently fuses entities. Arena decision 3/4.
- `merge_proposed` — surfaced into an `entity_merge_proposals` row awaiting
  decision; `decision_id` is set.
- `accepted` — the alias/merge was accepted; `entity_id` is the surviving
  canonical entity and `decision_id` records the reversible decision.
- `rejected` — an explicit decision recorded that these surface forms are
  distinct entities (negative knowledge; prevents re-proposal churn).
- `reversed` — a previously `accepted` decision was reversed; the row is retained
  for audit and the rewrite is replayed from §21.3 lineage.

Rules:

- **Surrogate key (homonym support).** The primary key is the opaque surrogate
  `id` (`ALI-<UUID8>`), NOT a composite of the surface form. `alias_normalized`
  is deliberately NOT unique on its own: a single normalized surface form may
  legitimately resolve to several DISTINCT entities (homonyms — "Mercury" → the
  planet, the element, and the mission). The earlier composite key
  `(alias_normalized, alias_display, resolution_status)` could hold only ONE row
  per surface form per status, so a second entity claiming the same surface form
  collided on the key and silently overwrote the first — destroying homonym
  resolution. With the surrogate key, each `(surface form → entity)` resolution
  is its own row.
- **Resolved-row uniqueness.** `idx_entity_aliases_resolved` keys a RESOLVED
  alias by `(alias_normalized, entity_id, resolution_status)`. This still blocks
  an exact duplicate resolved row for the same entity, while allowing the same
  `alias_normalized` to appear once per distinct `entity_id`. Unresolved
  candidates (`entity_id IS NULL`) are outside the constraint and are
  distinguished only by their surrogate `id`.
- `alias_normalized` is candidate-generation input ONLY. A normalization match
  never auto-creates an `accepted` row; it may at most create an
  `ambiguous_candidate` (homonym-risk) or `merge_proposed` row.
- Every `accepted`/`alias`/`rejected`/`reversed` row MUST have a non-empty
  `resolution_reason` and (for accept/reverse) a `decision_id`.

### 21.2 `entity_merge_proposals`

```sql
CREATE TABLE IF NOT EXISTS entity_merge_proposals (
    id TEXT PRIMARY KEY,               -- DEC-<UUID8>
    source_entity_id TEXT NOT NULL,    -- ENT- being merged away (origin)
    target_entity_id TEXT NOT NULL,    -- ENT- surviving canonical
    decision TEXT NOT NULL,            -- proposed | accepted | rejected | reversed
    rationale TEXT NOT NULL,
    evidence_json TEXT NOT NULL,       -- JSON: candidate signals, guard checks, span/claim evidence
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entity_merge_proposals_src ON entity_merge_proposals(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_merge_proposals_tgt ON entity_merge_proposals(target_entity_id);
```

Rules:

- A merge is only authoritative when `decision='accepted'`. `proposed` proposals
  do not rewrite the graph.
- `evidence_json` MUST record which guards (type match, context overlap,
  contradiction check, `avoid_merges` list) were evaluated and their outcome, so
  every accepted merge is auditable (Strict Quality Condition).
- A `rejected` decision is durable negative knowledge: the same `(source,target)`
  pair is not auto-re-proposed unless new evidence changes the candidate
  signals.

### 21.3 `entity_resolution_lineage`

```sql
CREATE TABLE IF NOT EXISTS entity_resolution_lineage (
    decision_id TEXT NOT NULL,         -- entity_merge_proposals.id
    origin_entity_id TEXT NOT NULL,    -- ENT- as it existed before the merge
    canonical_entity_id TEXT NOT NULL, -- ENT- it was redirected into
    rewrite_json TEXT NOT NULL,        -- JSON: exact pre-merge entity row + every relation/report/synthesis rewrite applied
    PRIMARY KEY (decision_id, origin_entity_id)
);
```

Rules:

- This table is the **reversal contract**. `rewrite_json` MUST contain enough to
  reconstruct the origin entity row and re-point every relation/community/report/
  synthesis reference that the merge rewrote (Arena decision 5).
- Accepted-merge reversal replays `rewrite_json` in reverse and regenerates the
  affected relations/communities/reports/synthesis (SYSTEM_BEHAVIOR §27). A merge
  that cannot be represented losslessly here MUST NOT be accepted (plan Stop
  Condition).

### 21.4 `graph_entities` Additive Columns (Merge Redirects)

```sql
ALTER TABLE graph_entities ADD COLUMN resolution_state TEXT NOT NULL DEFAULT 'canonical';  -- canonical | redirected
ALTER TABLE graph_entities ADD COLUMN redirect_to_entity_id TEXT;  -- ENT- canonical survivor when redirected
ALTER TABLE graph_entities ADD COLUMN decision_id TEXT;            -- DEC- merge decision that redirected this row
```

Rules:

- Accepted merges **do not delete** the origin entity. The origin row is set
  `resolution_state='redirected'` with `redirect_to_entity_id` → canonical and
  `decision_id` → the accepting decision. Origin identity is preserved for
  reversal; the existing `(canonical_name, entity_type)` UNIQUE index is
  unaffected (merged forms have distinct names).
- Only `resolution_state='canonical'` rows are authoritative graph nodes. All
  reads that build topology, reports, search materialization, or synthesis MUST
  resolve `redirected` rows through `redirect_to_entity_id` to the canonical
  entity. No authoritative artifact may reference a redirected entity directly
  (graph audit, §21.8, asserts 0 such references).

### 21.5 `graph_relation_supports`

```sql
CREATE TABLE IF NOT EXISTS graph_relation_supports (
    relation_id TEXT NOT NULL,         -- REL-
    knowledge_unit_id TEXT NOT NULL,   -- KNU- asserting this relation
    source_span_ids TEXT NOT NULL,     -- JSON array of SPAN- ids carrying the assertion
    assertion_source TEXT NOT NULL,    -- source_states | system_infers | workspace_derives
    confidence REAL NOT NULL,
    support_status TEXT NOT NULL,      -- unchecked | verified | failed | stale
    support_hash TEXT NOT NULL,        -- content hash of (relation proposition + cited spans); dedup within a relation
    source_lineage_hash TEXT NOT NULL, -- hash of the logical source lineage; the INDEPENDENCE key
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (relation_id, knowledge_unit_id, support_hash)
);
CREATE INDEX IF NOT EXISTS idx_graph_relation_supports_rel ON graph_relation_supports(relation_id);
CREATE INDEX IF NOT EXISTS idx_graph_relation_supports_lineage ON graph_relation_supports(source_lineage_hash);
```

Rules:

- An extracted relation is a **proposition with independent supports** (Arena
  decision 6). The relation's identity IS its canonical proposition — the triple
  `(resolved source entity, resolved target entity, relation_type)` after
  endpoint resolution (§21.4). Re-extraction of that same triple maps to the
  SAME canonical relation and ADDS support rows; it never overwrites them and
  never spawns a parallel "duplicate" relation. This replaces today's
  destructive `upsert_graph_relation` overwrite (§11.4 reality). Because the same
  proposition aggregates onto one relation, there is no duplicate-proposition
  state to quarantine (§21.6).
- **Extracted independence is by source lineage, not row count.** The
  independent-support count of an extracted relation = number of DISTINCT
  `source_lineage_hash` among its
  `verified` supports. Copied/duplicated sources share a `source_lineage_hash`
  and therefore count once (Strict Quality Condition: 0 copied-source rows
  counted as independent support).
- **Extracted corroboration threshold = 1 independent source lineage.** An
  extracted relation is
  `active` when its independent-support count is **≥ 1** — at least one DISTINCT
  `source_lineage_hash`, i.e. at least one genuinely independent source asserts
  the proposition. A count of **0** is `unsupported`. Row count alone still never
  promotes: ten copies of one source collapse to one lineage and count once. The
  threshold was 2 until v0.43.0; because the lineage hash already collapses
  copies, requiring two excluded every single-source fact rather than any fraud,
  which emptied real vaults' graphs (SYSTEM_BEHAVIOR §27.2).
- `support_status` mirrors `claim_supports` (§20.2): a support is `verified`
  only when its `knowledge_unit_id` is itself eligible (`support_status='verified'`,
  `retired_at IS NULL`, §20.1 eligibility) and its cited spans are fresh.
- Only supports derived from the **authoritative** B claim generation (§20.3)
  may be `verified`. Mixed-generation supports are a stop condition.

### 21.6 `graph_relations` Additive Columns (Lifecycle, Edge Class, Topology)

```sql
ALTER TABLE graph_relations ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT 'provisional';  -- active | provisional | quarantined | retired
ALTER TABLE graph_relations ADD COLUMN quarantine_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE graph_relations ADD COLUMN edge_class TEXT NOT NULL DEFAULT 'extracted';          -- authored | extracted
ALTER TABLE graph_relations ADD COLUMN topology_weight REAL NOT NULL DEFAULT 0.0;
ALTER TABLE graph_relations ADD COLUMN reeval_trigger TEXT NOT NULL DEFAULT '';
ALTER TABLE graph_relations ADD COLUMN generation_id TEXT;                                     -- GEN- that produced/revalidated
CREATE INDEX IF NOT EXISTS idx_graph_relations_lifecycle ON graph_relations(lifecycle_status);
```

`lifecycle_status` (frozen enum, evaluated by `edge_class`):

- `active` — authoritative for its edge class and both endpoints resolve to
  canonical entities. An `extracted` relation requires **≥1 independent source
  lineage** of `verified` support (§21.5 corroboration threshold). An
  `authored` relation instead requires exact supported vault structure in a
  registered visible Markdown source and the source's current authoritative
  compiler `generation_id`; authored relations never require or create
  synthetic `graph_relation_supports`. **Only `active`, non-retired relations
  enter authoritative topology/community construction** (Arena decision 7).
- `provisional` — exists but not yet promotable to `active` (e.g., unrevalidated
  after migration, or support pending). The v9 backfill marks every legacy
  relation `provisional`.
- `quarantined` — flagged out of authoritative topology with a `quarantine_reason`
  (frozen reason codes below) and a `reeval_trigger` describing what would
  re-admit it. Quarantine is inspectable and re-evaluable, never an opaque
  discard (Arena decision 8).
- `retired` — superseded by source edit/delete/split reconciliation; retained as
  a tombstone, never an authoritative input.

`quarantine_reason` frozen codes: `unsupported` (no eligible support, i.e. 0
independent source lineages), `self_loop`, `contradiction`, `copied_source_only`
(RETIRED as an outcome in v0.43.0; kept frozen so historical rows stay decodable
and re-evaluable — §21.5), `bridge_risk` (single low-confidence
edge joining otherwise separate dense components), `endpoint_unresolved`.

**There is no `duplicate_proposition` reason code — a relation is never a
"duplicate."** A relation's identity IS its proposition: the canonical triple
`(resolved source entity, resolved target entity, relation_type)` after endpoint
resolution (§21.4). Re-asserting that proposition does NOT create a second
relation row to quarantine; it ADDS independent supports to the one canonical
relation (§21.5). Treating a re-assertion as a "duplicate" and quarantining it
would HIDE its supports from the independent-support count — the exact opposite
of the aggregation contract — so the state cannot exist by construction. For
`extracted` relations, support-side outcomes are therefore a total partition by
independent-source-lineage count: **0** → `unsupported`; **≥1** → `active`. This
partition does not apply to authored structural relations. If two physical rows
are ever found describing the same canonical
proposition, that is a compile-time defect (the support should have aggregated
onto one relation), and reconciliation merges their supports onto the canonical
relation rather than quarantining either row.

`edge_class` (frozen enum): `authored` (links/topology a human or workspace
wrote) vs `extracted` (LLM-extracted semantic relations). v0.39 compiles four
authored relation types: `links_to`, `embeds`, `tagged_with`, and
`property_ref`, with endpoint entity types `vault_note`, `vault_asset`, and
  `tag`. F9-created entity ids derive from `(entity_type, canonical portable vault
  key)` and relation ids derive from `(source entity id, target entity id,
  relation_type)`. Portable vault keys use Unicode NFC before hashing. After DB
  import, multiple authoritative generations for one portable source are
  reconciled to the generation matching the LWW source content fingerprint (then
  newest publication). Exact sorted authored membership comes from the winning
  generation's `audit_json`: shared deterministic relation ids are assigned to
  the winner and have lifecycle recompiled, while only loser-exclusive ids
  retire. Lifecycle admission also requires that the relation id occur in that
  exact valid membership. Missing/malformed membership fails closed. A
  tombstoned source has no eligible winning generation, even when only one
  authoritative generation remains. Unchanged builds and independent-device
  compilation therefore converge under id-based DB sync even when relation-row
  and generation LWW clocks disagree. Existing extracted ids are unchanged.

The two classes stay distinct through weighting, hierarchy, audit, and reports
(Arena decision 9). `topology_weight` is the partition-input weight and is
computed per edge class. Authored edges may shape topology but never create
`graph_relation_supports`, enter factual `community_reports.relation_ids`, or
serve as factual citations. Backlinks are derived from incoming traversal over
the stored forward edge, never persisted as a duplicate reverse relation.

### 21.7 Community Identity, Levels, And Config

```sql
ALTER TABLE community_reports ADD COLUMN parent_community_key TEXT;                    -- hierarchy parent; NULL at top level
ALTER TABLE community_reports ADD COLUMN config_hash TEXT NOT NULL DEFAULT '';         -- algorithm+seed+threshold config identity
ALTER TABLE community_reports ADD COLUMN member_hash TEXT NOT NULL DEFAULT '';         -- hash of sorted active member entity ids
ALTER TABLE community_reports ADD COLUMN support_hash TEXT NOT NULL DEFAULT '';        -- hash of the eligible active-support set
ALTER TABLE community_reports ADD COLUMN retired_at TEXT;                              -- ISO 8601 UTC; non-NULL = retired stale community
CREATE INDEX IF NOT EXISTS idx_community_reports_parent ON community_reports(parent_community_key);
```

Rules:

- **Community identity is content/config-derived**, not arbitrarily stable:
  `community_key` is a function of `(level, member_hash, support_hash,
  config_hash)`. When the active membership or eligible support set changes, the
  identity changes — a correct restructuring is preferred over artificial id
  stability, and the superseded community/report is set `retired_at` before
  synthesis consumes it (Arena decision 11).
- For this identity contract, `support_hash` covers the complete active topology
  dependency closure: eligible verified extracted supports plus the stable ids
  of active authored relations that shaped membership. Authored relation ids
  invalidate topology/report membership but never become factual report support.
- A newly active authored relation retires each live report whose `entity_ids`
  contains either endpoint unless that report already records the exact
  relation dependency. This endpoint rule closes the addition case where an
  older report cannot yet have an artifact dependency on the new relation while
  preserving a newer imported report already built from the winning topology.
  The retirement revision is a strict successor of the report and relation
  revisions, so invalidation never moves a LWW clock backward.
- `level` (existing column, §11.5) now carries the real hierarchy depth (0 =
  leaf). `parent_community_key` records the hierarchy edge.
- `config_hash` pins the partition algorithm, seed, and thresholds that produced
  the community. The **exact set of config inputs is frozen at P5** alongside the
  hierarchy benchmark (Evidence Ledger "Hierarchy Benchmark Freeze"); until then
  `config_hash` records the degraded filtered-connected-components fallback
  identity. No algorithm choice is locked by this schema section — only the
  identity/provenance contract is.
- A community built from anything other than `active` (§21.6) relations over
  canonical (§21.4) entities is invalid.

### 21.8 v9 Migration, Tombstones, And Graph Audit

- `SCHEMA_VERSION` 8 → 9 is forward-only and additive: the §21.1/§21.2/§21.3/
  §21.5 CREATEs, the §21.4/§21.6/§21.7 ALTERs, and extension of the
  `deleted_records` CHECK list + `wiki db export`/`import` with the four new
  tables (`entity_aliases`, `entity_merge_proposals`, `entity_resolution_lineage`,
  `graph_relation_supports`).
- Backfill (infers nothing): existing `graph_entities` →
  `resolution_state='canonical'`, no aliases. Existing `graph_relations` →
  `lifecycle_status='provisional'`, `edge_class='extracted'`,
  `generation_id=NULL`; **no** legacy relation is auto-promoted to `active` and
  **no** support rows are created — relations become `active` only after rebuild
  from the authoritative B claim generation. Existing `community_reports` keep
  their rows but are recomputed against active topology before being served.
- **Graph audit (schema-level invariants)** — the read-only audit asserts: 0
  authoritative references to `redirected` entities; 0 `active` **extracted**
  relations with zero independent source lineages of `verified` support (the
  threshold is >=1 since v0.43.0);
  0 `active` authored relations without exact current-generation source
  structure; 0 endpoints that are not canonical entities;
  every `quarantined` relation has a reason code + re-eval trigger; every served
  report finding cites eligible active claim support; 0 stale/retired
  aliases/supports/communities feeding authoritative artifacts; 0 mixed claim
  generations. Behavioral acceptance criteria, reconciliation closure, and
  rollback rehearsal live in SYSTEM_BEHAVIOR §27.

### 21.9 GQ07 — Relation-Confidence Calibration Gate (Schema-Level Note)

Plan E P7 measured production relation `confidence` as non-discriminative (all
1,180 values in `0.9–1.0`, mean `0.966`). Therefore the existing
`graph_relations.confidence` and `graph_relation_supports.confidence` columns are
**NOT** a calibrated noise filter and MUST NOT be used as a serving-time
threshold until per-relation-type quality labels prove separation (Evidence
Ledger GQ07). No calibrated-confidence column is frozen here yet; it is
`benchmark-later` and added only with the P5 labeled relation-quality evidence.
Quarantine decisions (§21.6) gate on support eligibility and structural signals,
NOT on a raw-confidence threshold.

---

## 22. Retrieval Contracts (Plan A, v0.10.0)

No schema migration — Plan A changes are transport-level (in-memory + JSONB
column) only.  `SCHEMA_VERSION` remains `9`.

### 22.1 Retrieval Execution Identity (RTR-*)

A `RTR-<8 hex chars>` retrieval execution identifier is generated once per
`build_evidence` call.  It is stored inside the existing
`query_traces.retrieval_trace_json` JSONB column under the key
`"retrieval_execution_id"`.  No new DB table is introduced.

Prefix `RTR-` is added to the Id And Prefix Registry (§17):

| Prefix | Owner | Table / location |
|--------|-------|-----------------|
| `RTR-` | `retrieval/evidence.py::build_evidence` | `query_traces.retrieval_trace_json` |

### 22.2 StructuredLocator (In-Memory Only)

`StructuredLocator` is a Python dataclass defined in
`retrieval/models.py` (§17 SYSTEM_BEHAVIOR).  It is NOT persisted as its own DB
row; it is computed at retrieval time and returned in `EvidenceItem.locator`.
Plan F may later choose to cache resolved locators; Plan A does not.

Fields and resolution states are defined in SYSTEM_BEHAVIOR §29.

### 22.3 EvidencePack Extended Fields

`EvidencePack` gains two new fields (no DB migration):

| Field | Type | Description |
|-------|------|-------------|
| `retrieval_execution_id` | `str` | `RTR-*` ID for this retrieval; empty string before Plan A ships |
| `omitted_counts` | `dict[str, int]` | route-specific omission counts (e.g. `{"global_reports": 5}`) |

`EvidenceItem` gains:

| Field | Type | Description |
|-------|------|-------------|
| `locator` | `StructuredLocator \| None` | resolved source locator; `None` when no backing span |

### 22.4 retrieval_trace_json Contract

After Plan A, `query_traces.retrieval_trace_json` stores:

```json
{
  "contract_version": "1",
  "retrieval_execution_id": "RTR-xxxxxxxx",
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

`selection.candidate_count` is `selected_count + sum(omitted_counts.values())`
(items considered before bounding/omission), and `selected_count` is the number
of items actually carried in the pack — the two MUST NOT be hardwired equal.
`policy` echoes the workspace source-scope globs (`source_include` /
`source_exclude`) that were enforced; there is no `source_ids` field.

Pre-Plan-A QTR rows retain their existing `retrieval_trace_json` shape; no
backfill or migration is performed.  Readers MUST handle both the pre-Plan-A
`{}` / engine-raw shape and the Plan-A contract shape by checking for
`"contract_version"`.

### 22.5 CurationPolicy Forwarding Contract

`build_evidence` MUST receive the `CurationPolicy` resolved by the orchestrator.
The policy is forwarded via the new `policy` keyword argument:

```python
def build_evidence(
    paths: cfg.WikiPaths,
    request: QueryRequest,
    route: str,
    *,
    policy: curate_yml.CurationPolicy | None = None,
    limit: int = 8,
) -> EvidencePack: ...
```

When `policy` is `None`, behavior defaults to the current open policy (no source
filter, no workspace-specific constraints) — this preserves backward compatibility
for existing callers that do not yet pass a policy.

Source scope is enforced via the policy's glob patterns
(`source_include` / `source_exclude`), tested with
`CurationPolicy.allows_source(relpath)`, using a **strict all-spans rule**: an
item is kept only when *every* backing span is in scope. Multi-source artifacts
(`community_report`, `synthesis`, entities) are excluded entirely if any backing
span is out of scope — their text commingles all sources, so partial inclusion
would leak excluded content and trimming `source_span_ids` would corrupt
provenance. `source_span_ids` is never mutated; items dropped by scope are counted
in `omitted_counts["policy_excluded"]`. See SYSTEM_BEHAVIOR §28.1.

### 22.6 Global Route Bounded Selection

`_report_items` is replaced by a query-aware variant that accepts the query text
and returns at most `MAX_GLOBAL_REPORTS` (default 10) reports ranked by lexical
overlap.  The exact ranking algorithm: compute a score for each report as
`|query_terms ∩ (title_terms ∪ summary_terms)| / |query_terms|`; select top-N by
score, break ties by `rank DESC`.  The omitted count is stored in
`pack.omitted_counts["global_reports"]`.

### 22.7 Evidence Block Omission Contract

`EvidencePack.evidence_block(*, max_chars)` appends an omission marker when
`len(items) > rendered_count`:

```
[N items omitted — character budget reached]
```

This line is appended AFTER the last fully-rendered item, ensuring `max_chars` is
respected by the rendered content + marker together.  The marker MUST contain the
word `"omitted"` (case-insensitive match used by tests).

## 23. Context Service Contracts (Plan F target, v0.13.0)

Plan F adds the schema contract for a unified `ContextService`. The initial
schema is additive; `SCHEMA_VERSION` remains unchanged until the physical
migration is implemented and rehearsed.

### 23.1 Prefix Registry Additions

The following logical ids are reserved for the context service:

| Prefix | Owner | Table / location |
|---|---|---|
| `PACK-` | ContextService pack assembler | context pack record or `query_traces` child payload |
| `SNAP-` | ContextService snapshot resolver | context snapshot record or root trace payload |
| `CTXA-` | ContextService child action recorder | ordered context action record |
| `EXP-` | ContextService expansion handle issuer | pack `next[]` handle payload |
| `VER-` | ContextService verification handle issuer | evidence item verification payload |
| `FBK-` | ContextService feedback recorder | append-only feedback record |

These prefixes do not replace existing `QTR-`, `RTR-`, `PTR-`, `SPAN-`, `ATM-`,
`CON-`, or `SYN-` ids. A `QTR-*` remains the root request id, and a Plan A
`RTR-*` remains the retrieval execution child id.

### 23.2 Logical Records

The physical migration may choose normalized tables or explicit JSON payload
columns, but it must preserve these logical records:

- **Context root**: one `QTR-*` root per logical context/query request, including
  request identity, workspace, purpose, policy hash, route decision, final pack,
  warnings, and optional synthesis references.
- **Context snapshot**: one `SNAP-*` closure per root request, including source
  epoch, DB epoch, search/index epoch, dependency epoch, policy hash,
  model/tokenizer/config hash, and creation time. The source epoch is a compact
  deterministic representation: source/span counts plus ordered
  `(id, content_hash)` hashes. It must not embed full `sources` or
  `source_spans` row payloads in each snapshot.
- **Context action**: ordered `CTXA-*` child actions for retrieval, pack assembly,
  budget decisions, omissions, expansion, verification, synthesis, degradation,
  and stop reason.
- **Context pack**: one or more `PACK-*` payloads containing version, snapshot,
  route, policy, budget, coverage, evidence items, expansion handles, and
  warnings. Pack-only operations such as expansion and verification resolve the
  owning `QTR-*` through a database-side ContextService pack-id lookup, not by
  decoding a bounded list of recent query traces in Python.
- **Context feedback**: append-only `FBK-*` events linked to `QTR-*`, `PACK-*`,
  `SNAP-*`, client, purpose, target item/record/claim, reviewed evidence, review
  status, and resulting lineage. Feedback calls use the explicit `(trace_id,
  pack_id)` pair: the service looks up the `QTR-*` directly and verifies the
  `PACK-*` belongs to that trace before appending an action.

### 23.3 Migration Rules

Existing `query_traces` rows remain readable without backfill. The migration must
be additive and must pass forward/rollback rehearsal on a copied DB before
release. Compatibility adapters may emit legacy transport fields, but the
canonical context record must not duplicate retrieval selection or create a
second source of truth.

### 23.4 Canonical Fixtures

The canonical JSON fixtures for this contract live under:

```text
docs/specs/system_behavior/context_service_fixtures/
```

They define the minimum wire shape for `context_manifest`, `context_fetch`,
successful `context_expand`, `context_expand` snapshot conflict responses,
`context_verify`, and `context_feedback`.
