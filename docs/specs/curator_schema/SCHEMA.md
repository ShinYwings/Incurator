# Incurator - Schema & Operating Conventions (v0.3.3)

Audience: Incurator backend, Obsidian plugin, MCP clients, and coding agents.

This document represents the most concrete layer (`spec`) of the documentation hierarchy (`philosophy` -> `guides` -> `spec`). It is the absolute schema source of truth.

Implementation plans under `.agents/plans/` are transient and strictly subordinate to this spec. They may explain sequencing and alternatives, but code must conform to this file when it writes `.curator/` state, Curator DAG pages, MCP payloads, or provider/model configuration.

Sections 1-17 below define the schema contract. The database engine retires qmd as a search backend and internalizes search/query traces inside `state.sqlite`. Historical schema definitions are tracked via git history.

**Clean-rebuild stance (no migration compatibility shims).** v0.3.2 continues the
curation-native rebuild that does **not** maintain backward-compatibility shims
for retired migration surfaces. There are no prompt-function wrapper layers, no
legacy-query fallback path, no `curate.yml` persona→KRS auto-mapping, and no qmd
runtime fallback path. The new shapes below are the only supported shapes; an
existing vault is expected to be rebuilt (`wiki reset` + `wiki add` + `wiki build`)
rather than silently migrated.
Working v0.2.2 capabilities that are not replaced (instant L1, background jobs,
Reference Mode, the device registry, runtime snapshots) continue unchanged — the
no-compat rule applies to the v0.3.1 migration surface, not to removing
still-current features.

## 1. Topology Additions

The v0.2.0 vault topology remains unchanged, with these `.curator/` additions:

```text
.curator/
├── config.yml
├── state.sqlite
├── dashboard.md              # generated observability dashboard, optional
├── sync-report.json
├── staging/                  # transient async ingest workspace
│   └── {job_id}-{source_id}-{phase}.{ext}
└── Collections/
    ├── 01_Contexts/
    ├── 02_Atoms/
    ├── 03_Concepts/
    └── 04_Synthesis/            # SYN-*.md projection of the shared L4 Synthesis layer (§11.11)
```

Rules:

- `.curator/staging/` is transient. It may be deleted and rebuilt.
- `.curator/staging/`, `state.sqlite`, `state.sqlite-wal`, and `state.sqlite-shm`
  must be ignored by sync tools that cannot safely merge SQLite state.
- Generated dashboards must never become the source of truth. The source of
  truth is `state.sqlite` plus DAG page frontmatter/body content.
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
inside `.curator/state.sqlite`; embedding/query-expansion/reranker provider
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

When enabled, `wiki add` and backend import paths create L1 Contexts from parser
structure without calling an LLM. L2/L3 extraction is queued as background work.
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
parser_used: pymupdf4llm       # v0.2.2: specifies which parser (e.g. pymupdf4llm, vlm, text)
source_pages:                  # PDF only, optional
  - page: 1
    hash: 16-char-page-hash
    chars: 1024
    words: 180
```

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
  Candidates` are required for compatibility with existing L2 extraction and
  immediate source recall.
- Generated L1 scaffold text (`Summary`, `Key Claims`, `Source Guide`, Atom
  Candidate instructions) must be written in English.
- When `source_sections_inline=true`, the original source text remains
  unmodified under `Source Sections`, even when the source language is Korean or
  another non-English language.
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
import_origin TEXT;
import_policy TEXT;
external_path TEXT;
is_reference INTEGER NOT NULL DEFAULT 0;
logical_source_id TEXT;
error_reason TEXT;
```

Allowed layer states:

```text
pending | running | done | error | skipped
```

Rules:

- `status='curated'` is not the source of truth for L1 completion.
- `wiki status` must count L1 completion from `l1_status='done'`.
- `context_id` is set when L1 completes.
- L2/L3 may remain `pending` while a source is already usable for section RAG.
- `l4_status='done'` is the source-level signal that an L4 Exhibition has been
  produced. L2/L3 completion must not be labelled as fully curated in user-facing
  status surfaces.
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

- `wiki add` queues L2/L3 work unless `--wait` requests foreground processing.
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
  "source_path": "04_Resources/paper.pdf",
  "l1_complete": true,
  "l2_complete": false,
  "l3_complete": false,
  "jobs_pending": [
    {"id": 3, "type": "l2_atoms", "state": "queued", "phase": "queued"}
  ]
}
```

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
  "providers": {
    "antigravity": [],
    "claude": [],
    "openai": []
  }
}
```

Rules:

- The response is generated from the backend shared model catalogue.
- Local model discovery remains provider-specific and may be served separately.

## 8. Synced Device Registry

v0.2.1 defines a sync-friendly device registry at `.curator/devices.json`.
This file is shared vault metadata, not a SQLite index, and may be synchronized
by Syncthing.

The registry records:

- Syncthing folder metadata for the active vault, including folder id, label,
  and participating device ids.
- Folder roles for the active vault and configured Zotero roots when Syncthing
  shares those paths. UI readers use these roles to show which devices sync the
  Vault and Zotero without inventing unsupported platform/backend facts.
- Known device display names from Syncthing.
- Per-device backend launcher hints, such as `wiki` on Linux or
  `uv --directory /Users/<user>/Workspace/Incurator/backend run wiki` on macOS.
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
zotero_key: ABCDEF12
target_path: /absolute/path/to/external.pdf   # Optional fallback or alternative
```

Rules:
- The `type` must be `reference`.
- `sources.relpath` must point to the vault-relative markdown stub, not the
  external PDF's absolute path.
- `sources.external_path` stores the original absolute file path as a recoverable
  device-local location hint.
- Automatically generated stubs should not write `target_path` because
  `04_Resources/` may sync across devices whose external libraries live at
  different absolute paths. Use `target_path` only for explicit local/manual
  stubs where that portability tradeoff is accepted.
- If `zotero_key` is present, the backend RAG pipeline must resolve the absolute path using the active `ZOTERO_BASE_PATH` (or Zotero integration logic).
- If `target_path` is present (and `zotero_key` is missing or fails to resolve), the backend uses this absolute path.
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
  projection** of the DB records, not an independent source of truth. When a DB
  record changes (e.g. via `curator_propose_correction`), the authoritative DB
  row, search document/chunk rows, FTS5 rows, and embedding freshness state update
  in the same backend write path. Projection re-emission is an Obsidian
  convenience step, not a retrieval prerequisite.

## 11. SQLite State Schema (`SCHEMA_VERSION = 7`)

v0.4.0 sets `db.SCHEMA_VERSION` to `7`. The v0.3.2 tables remain in use.
v0.4.0 adds the cross-device sync tombstone table (`deleted_records`, §11.17)
and the `wiki db export/import` pipeline. All ids use typed string prefixes so
they are self-describing in traces and frontmatter.

> **Version history.** `SCHEMA_VERSION = 4` introduced the v0.3.1 curation-native
> tables. `SCHEMA_VERSION = 5` adds the shared L4 `synthesis_nodes` table (§11.11)
> for the corpus-wide synthesis layer. The bump is forward-only; old vaults
> self-heal via `executescript(SCHEMA_SQL)` (every table is `IF NOT EXISTS`).
> `SCHEMA_VERSION = 6` adds DB-native search documents/chunks, FTS5 tables,
> chunk embeddings, search index metadata, and durable query traces (§11.12-§11.16).
> `SCHEMA_VERSION = 7` adds `deleted_records` tombstone table for cross-device
> knowledge synchronization (§11.17).

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
  workspace derives (`workspace_derives`). Only `source_states` relations may be
  treated as source-grounded evidence.

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
  corpus**. The synthesis layer is regenerated **wholesale**: when the hash is
  unchanged the layer is skipped (no LLM cost); when any report changes the whole
  layer is cleared and rewritten.
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
retrieval state in `.curator/state.sqlite` and must be rebuilt from Curator
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
- The lens is biased by `curate.yml` (the Knowledge Requirement Spec) and
  accumulated insight candidates — additive bias over the full DAG, never a frozen
  subset.

Durable human artifacts come only from an explicit **promotion to `02_Wiki/`**
(insight candidate -> `02_Wiki/`), never from a generated query artifact.

Backprop is **correction-driven and generated-artifact-independent**: corrections from any
interaction (`curator_propose_correction`) are classified (§18) and patch the
generated DB nodes / create insight candidates, protecting source truth.

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
```

All ids are generated backend-side. Generated content (knowledge units,
entities, relations, reports, paths, exhibitions) must reference only ids that
already exist; prompt validators reject invented ids.

## 11.17 `deleted_records` — Cross-Device Sync Tombstones (`SCHEMA_VERSION = 7`)

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
        'synthesis','query_traces','source_pages','source_pdf_pages'
    ))
);
```

**Invariants:**
- `record_tombstone(db_path, table_name, record_id)` must be called whenever a canonical row is hard-deleted. It records the deletion and enables other devices to apply it on import.
- During `wiki db import`, tombstones are applied **before** upserts. A tombstone beats a concurrent update (deletion wins over modification).
- Device-local tables (`search_embeddings`, `ingest_jobs`, `job_events`, `page_hashes`, FTS5 virtual tables) are **never** listed as `table_name` in tombstones and are excluded from `wiki db export`.

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
