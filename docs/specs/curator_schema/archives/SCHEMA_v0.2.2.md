# Incurator - Schema & Operating Conventions (v0.2.2)

Audience: Incurator backend, Obsidian plugin, MCP clients, and coding agents.

This document represents the most concrete layer (`spec`) of the documentation hierarchy (`philosophy` -> `guides` -> `spec`). It is the absolute schema source of truth for the v0.2.2 line. 

Implementation plans under `.agents/plans/` are transient and strictly subordinate to this spec. They may explain sequencing and alternatives, but code must conform to this file when it writes `.curator/` state, Curator DAG pages, MCP payloads, or provider/model configuration.

v0.2.2 extends v0.2.1. Any v0.2.1 field not contradicted here remains valid.

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
    └── 04_Exhibitions/
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

## 5. L3 Concept And L4 Exhibition Schema Additions

v0.2.0 Concept and Exhibition contracts remain valid. v0.2.1 adds query-time
Exhibition lifecycle metadata.

L3 clustering is embedding-first in v0.2.1. Implementations may add local
embedding dependencies such as `scikit-learn` and may fall back to the legacy LLM
cluster-planning call when embeddings are unavailable.

### 5.1 Query-Generated Exhibition

```yaml
id: EXH-[UUID8]
type: exhibition
core_concepts:
  - 03_Concepts/CON-[UUID8]
confidence_score: 0.0
last_updated: YYYY-MM-DDThh:mm:ssZ
workspace_id: default
workspace_path: /absolute/path/to/workspace   # optional
query_session: QRY-[UUID8]
exhibition_origin: query_gen
ephemeral: true
question: "original question"
cache_key: "sha256-or-prefix"
is_verified_by_human: false
```

### 5.2 Promoted Exhibition

```yaml
id: EXH-[UUID8]
type: exhibition
workspace_id: my-workspace
exhibition_origin: promoted
ephemeral: false
is_verified_by_human: true
promoted_to: 02_Wiki/path.md
```

Rules:

- `workspace_id` is derived from the active workspace slug: the basename of the
  workspace path. Outside a workspace, it defaults to `default`. A plain chat
  turn whose active note is not inside a workspace folder resolves to `default`;
  the plugin must not bind an arbitrary workspace (e.g. the first `curate.yml`
  found in the vault) to a conversational chat.
- The query-generated Exhibition frontmatter does **not** carry the language
  bridge fields `input_language`, `english_query`, or `final_output_language`.
  Those are response/trace-only and are returned in the `wiki plugin query` JSON,
  never persisted into the saved EXH. Persisting a `final_output_language` caused
  later questions in a different language to be answered in the stale language.
- Query-generated Exhibitions may be cached by `(workspace_id, normalized question,
  final_output_language)` so that the same normalized question asked in different
  input languages does not collide and return a stale-language cached answer.
- Promoted Exhibitions are protected from automatic destructive rewrite.
- Backprop may invalidate caches that cite changed Concepts, but must preserve
  human-verified promoted artifacts unless explicitly requested.
- **L4 Constraints**: Query-generated Exhibitions are ONLY created if the query hits at least one L3 Concept. If no L3 Concepts are relevant, the system responds without generating an L4.
- **Ephemeral GC**: Exhibitions with `ephemeral: true` are subject to garbage collection. `wiki lint` automatically deletes these files if they are older than 24 hours to prevent vault pollution.

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
