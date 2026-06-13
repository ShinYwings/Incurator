"""SQLite state database for ingest history, dedupe, and metadata.

This is the *internal* state DB. It's separate from the QMD search index (which
QMD manages itself in Stage 4). This DB tracks:

- which files have been ingested (by content hash, for dedupe)
- when they were ingested
- which wiki pages were created/updated as a result
- ingest run history
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import constants as consts

SCHEMA_VERSION = 8

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

-- Tracks every source file we've seen in raw_dirs
CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    relpath         TEXT NOT NULL UNIQUE,    -- path relative to project root
    content_hash    TEXT NOT NULL,           -- sha256 of normalized content
    file_type       TEXT NOT NULL,           -- pdf, md, html, docx, txt, image
    bytes           INTEGER NOT NULL,
    added_at        TEXT NOT NULL,           -- ISO timestamp
    last_ingested   TEXT,                    -- NULL if not yet processed by LLM
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending|force_pending|curated|error|skipped
    context_id      TEXT,                    -- CTX-UUID of L1 Context page
    l1_status       TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|error|skipped
    l2_status       TEXT NOT NULL DEFAULT 'pending',
    l3_status       TEXT NOT NULL DEFAULT 'pending',
    l4_status       TEXT NOT NULL DEFAULT 'pending',
    layer_error     TEXT,                    -- latest layer-scoped error message/reason
    domain          TEXT,                    -- cached from L1 summary frontmatter
    tags            TEXT,                    -- JSON array, cached from L1 summary frontmatter
    import_origin   TEXT,                    -- original absolute path/URI when imported via helper
    import_policy   TEXT,                    -- import policy used, e.g. mirror_03_to_04
    external_path   TEXT,                    -- absolute external path hint for Reference Mode
    is_reference    INTEGER NOT NULL DEFAULT 0, -- 1=external reference, 0=vault-local copy
    logical_source_id TEXT,                  -- stable source identity across path/hash drift
    error_reason    TEXT                     -- empty_file|parse_error|llm_error — set when status='error'
);

CREATE INDEX IF NOT EXISTS idx_sources_hash   ON sources(content_hash);
CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);
CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain);
CREATE INDEX IF NOT EXISTS idx_sources_logical_source_id ON sources(logical_source_id);
CREATE INDEX IF NOT EXISTS idx_sources_external_path ON sources(external_path);

-- Page-level provenance for parsed PDFs. Text is intentionally not stored here;
-- callers re-parse the local source file when they need page text.
CREATE TABLE IF NOT EXISTS source_pdf_pages (
    source_id       INTEGER NOT NULL,
    relpath         TEXT NOT NULL,
    page_number     INTEGER NOT NULL,
    content_hash    TEXT NOT NULL,
    char_count      INTEGER NOT NULL DEFAULT 0,
    word_count      INTEGER NOT NULL DEFAULT 0,
    metadata        TEXT,
    extracted_at    TEXT NOT NULL,
    PRIMARY KEY (source_id, page_number),
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_source_pdf_pages_relpath ON source_pdf_pages(relpath);

-- Tracks each ingest run (one row per `wiki ingest` invocation)
CREATE TABLE IF NOT EXISTS ingest_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    source_id       INTEGER,                 -- FK to sources, nullable for batch runs
    mode            TEXT NOT NULL,           -- interactive|batch
    pages_created   INTEGER DEFAULT 0,
    pages_updated   INTEGER DEFAULT 0,
    error           TEXT,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

-- Maps which wiki pages came from which source (for provenance/lint)
CREATE TABLE IF NOT EXISTS source_pages (
    source_id       INTEGER NOT NULL,
    wiki_path       TEXT NOT NULL,           -- e.g. '02_Atoms/ATM-9f8e7d6c.md'
    operation       TEXT NOT NULL,           -- created|updated
    at              TEXT NOT NULL,
    PRIMARY KEY (source_id, wiki_path, at),
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

-- Persistent ingest jobs — survive tab close, restart, etc.
CREATE TABLE IF NOT EXISTS ingest_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       INTEGER NOT NULL DEFAULT 0,
    job_type        TEXT NOT NULL DEFAULT 'l2_atoms',
    trigger         TEXT NOT NULL DEFAULT 'wiki_add',
    node_id         TEXT,
    state           TEXT NOT NULL DEFAULT 'queued',  -- queued|running|done|failed|interrupted
    phase           TEXT,                    -- latest phase label
    progress        REAL DEFAULT 0.0,        -- 0.0..1.0
    progress_current INTEGER DEFAULT 0,
    progress_total   INTEGER DEFAULT 0,
    source_name      TEXT DEFAULT '',
    pages_created   INTEGER DEFAULT 0,
    pages_updated   INTEGER DEFAULT 0,
    error           TEXT,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT
    -- Note: no FK on source_id — source_id=0 is the sentinel for global L3 jobs.
);

CREATE INDEX IF NOT EXISTS idx_jobs_state   ON ingest_jobs(state);
CREATE INDEX IF NOT EXISTS idx_jobs_source  ON ingest_jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON ingest_jobs(created_at);

-- Per-job event log — live progress + rejoin-on-reload
CREATE TABLE IF NOT EXISTS job_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL,
    seq             INTEGER NOT NULL,        -- monotonic per job
    kind            TEXT NOT NULL,           -- status|extracted|page|chunk|error|done
    data            TEXT NOT NULL,           -- JSON payload
    at              TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES ingest_jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_events_job_seq ON job_events(job_id, seq);

-- L2 Atoms
CREATE TABLE IF NOT EXISTS atoms (
    id                      TEXT PRIMARY KEY,        -- ATM-[UUID8]
    name                    TEXT NOT NULL DEFAULT '', -- canonical concept name
    parent_source           TEXT NOT NULL,           -- 01_Contexts/CTX-UUID8 (plain string)
    source_path             TEXT NOT NULL DEFAULT '', -- relative/path/to/source.md
    claim_type              TEXT NOT NULL,           -- fact|claim|entity|procedure|relationship
    one_liner               TEXT NOT NULL DEFAULT '', -- single-sentence description
    contradicts             TEXT,                    -- JSON array of ATM-UUIDs
    is_verified_by_human    INTEGER DEFAULT 0,       -- boolean 0|1
    is_flagged_for_agent    INTEGER DEFAULT 0,       -- boolean 0|1
    last_updated            TEXT NOT NULL            -- ISO timestamp
);

CREATE INDEX IF NOT EXISTS idx_atoms_flagged    ON atoms(is_flagged_for_agent);
CREATE INDEX IF NOT EXISTS idx_atoms_claim_type ON atoms(claim_type);

-- L3 Concepts
CREATE TABLE IF NOT EXISTS concepts (
    id                      TEXT PRIMARY KEY,        -- CON-[UUID8]
    name                    TEXT NOT NULL DEFAULT '', -- concept name
    dependencies            TEXT NOT NULL,           -- JSON array of ATM-UUIDs
    domain                  TEXT NOT NULL,
    last_updated            TEXT NOT NULL            -- ISO timestamp
);

CREATE INDEX IF NOT EXISTS idx_concepts_domain ON concepts(domain);

-- L4 Exhibitions
CREATE TABLE IF NOT EXISTS synthesis (
    id                      TEXT PRIMARY KEY,        -- SYN-[UUID8]
    topic                   TEXT NOT NULL DEFAULT '', -- synthesis topic name
    core_concepts           TEXT NOT NULL DEFAULT '', -- JSON array of CON-UUIDs
    confidence_score        REAL NOT NULL,           -- 0.00–1.00
    last_updated            TEXT NOT NULL            -- ISO timestamp
);

CREATE INDEX IF NOT EXISTS idx_synthesis_confidence ON synthesis(confidence_score);

-- Tracks the last known hash of generated wiki pages for fast sync
CREATE TABLE IF NOT EXISTS page_hashes (
    wiki_path       TEXT PRIMARY KEY,        -- path relative to project root
    content_hash    TEXT NOT NULL,           -- sha256 of page content
    last_synced     TEXT NOT NULL            -- ISO timestamp
);

-- DAG edge index for SQL-based traversal (spec 04/08/09)
-- Enables incremental sync downstream expansion and Canvas generation
-- without filesystem scanning.
CREATE TABLE IF NOT EXISTS dag_edges (
    id          TEXT PRIMARY KEY,   -- '{from_id}:{to_id}'
    from_id     TEXT NOT NULL,      -- CTX-xxx | ATM-xxx | CON-xxx
    to_id       TEXT NOT NULL,      -- ATM-xxx | CON-xxx | SYN-xxx
    edge_type   TEXT NOT NULL,
    -- 'extracted_from'  : CTX → ATM  (L1 → L2)
    -- 'clustered_to'    : ATM → CON  (L2 → L3)
    -- 'synthesized_to'  : CON → EXH  (L3 → L4)
    source_id   INTEGER REFERENCES sources(id),
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dag_edges_from ON dag_edges(from_id);
CREATE INDEX IF NOT EXISTS idx_dag_edges_to   ON dag_edges(to_id);

-- =====================================================================
-- v0.3.1 curation-native records (SCHEMA.md §11)
-- =====================================================================

-- Precise, hashed regions of a source. The atomic citation unit.
CREATE TABLE IF NOT EXISTS source_spans (
    id              TEXT PRIMARY KEY,        -- SPAN-[UUID8]
    source_id       INTEGER NOT NULL,
    relpath         TEXT NOT NULL,
    span_type       TEXT NOT NULL,           -- heading_section|paragraph|page|equation|code|table|figure_caption
    page_number     INTEGER,
    section_title   TEXT,
    toc_id          TEXT,                    -- matches CTX toc[].id (sN) when available
    start_char      INTEGER,
    end_char        INTEGER,
    content_hash    TEXT NOT NULL,           -- hash of the exact span text
    text_preview    TEXT NOT NULL DEFAULT '',
    metadata        TEXT,                    -- JSON
    created_at      TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_source_spans_source ON source_spans(source_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_spans_source_hash
    ON source_spans(source_id, content_hash);

-- Typed L2 knowledge units, each citing >=1 source span.
CREATE TABLE IF NOT EXISTS knowledge_units (
    id              TEXT PRIMARY KEY,        -- KNU-[UUID8]
    unit_type       TEXT NOT NULL,           -- claim|definition|equation|procedure|method|result|observation|constraint|entity|relationship
    canonical_name  TEXT NOT NULL,
    statement       TEXT NOT NULL,
    source_span_ids TEXT NOT NULL,           -- JSON array of SPAN- ids (non-empty for source_supported)
    source_id       INTEGER,
    confidence      REAL NOT NULL DEFAULT 0.0,
    truth_status    TEXT NOT NULL DEFAULT 'source_supported',
                                             -- source_supported|derived_insight|contradiction|promoted_human_truth
    atom_node_id    TEXT,                    -- linked ATM- page when written
    prompt_run_id   TEXT,                    -- PTR- of extraction run
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    -- Plan B (v0.8.0, SCHEMA §20.1) additive claim-level support / formula columns.
    semantic_hash   TEXT,                    -- normalized-claim fingerprint (reconciliation candidates only)
    support_status  TEXT NOT NULL DEFAULT 'unchecked',  -- unchecked|verified|failed|stale
    support_reason  TEXT NOT NULL DEFAULT '',
    formula_status  TEXT NOT NULL DEFAULT 'not_applicable',
                                             -- not_applicable|preserved_in_text|linked_evidence|omitted_incidental|missing|uncertain
    retired_at      TEXT,                    -- ISO 8601 UTC; non-NULL = retired by reconciliation
    generation_id   TEXT                     -- GEN- compiler generation that last produced/revalidated this row
);
CREATE INDEX IF NOT EXISTS idx_knowledge_units_source ON knowledge_units(source_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_units_type   ON knowledge_units(unit_type);
-- The support/generation indexes are created in _apply_migrations (after the
-- columns are added), so a pre-existing v7 knowledge_units table — which this
-- IF NOT EXISTS CREATE TABLE does not alter — is not indexed on a missing column.

-- Plan B (v0.8.0, SCHEMA §20.2) claim-level minimal support records.
CREATE TABLE IF NOT EXISTS claim_supports (
    knowledge_unit_id TEXT NOT NULL,
    source_span_id    TEXT NOT NULL,
    support_role      TEXT NOT NULL,         -- primary|contextual|formula
    support_status    TEXT NOT NULL,         -- unchecked|verified|failed|stale
    support_reason    TEXT NOT NULL DEFAULT '',
    evidence_hash     TEXT NOT NULL,         -- content_hash of the span text at validation time
    validator_trace_id TEXT,                 -- PTR- of model validation; NULL for deterministic-only verdicts
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    PRIMARY KEY (knowledge_unit_id, source_span_id, support_role)
);
CREATE INDEX IF NOT EXISTS idx_claim_supports_span ON claim_supports(source_span_id);
CREATE INDEX IF NOT EXISTS idx_claim_supports_status ON claim_supports(support_status);

-- Plan B (v0.8.0, SCHEMA §20.3) staged compiler generations (atomic publish).
CREATE TABLE IF NOT EXISTS compiler_generations (
    id               TEXT PRIMARY KEY,       -- GEN-[UUID8]
    source_id        INTEGER,                -- per-source scope; NULL = corpus-wide stage set
    status           TEXT NOT NULL DEFAULT 'staged',  -- staged|authoritative|discarded
    prompt_contract_version TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    published_at     TEXT,
    discarded_at     TEXT,
    audit_json       TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_compiler_generations_source ON compiler_generations(source_id, status);

-- Named graph nodes (entry points for local/explore retrieval).
CREATE TABLE IF NOT EXISTS graph_entities (
    id                 TEXT PRIMARY KEY,     -- ENT-[UUID8]
    canonical_name     TEXT NOT NULL,
    entity_type        TEXT NOT NULL,        -- concept|method|dataset|metric|system|person|organization|other
    description        TEXT NOT NULL DEFAULT '',
    source_span_ids    TEXT NOT NULL DEFAULT '[]',
    knowledge_unit_ids TEXT NOT NULL DEFAULT '[]',
    prompt_run_id      TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_entities_name
    ON graph_entities(canonical_name, entity_type);

-- Typed, directed, confidence-scored edges between entities.
CREATE TABLE IF NOT EXISTS graph_relations (
    id                TEXT PRIMARY KEY,      -- REL-[UUID8]
    source_entity_id  TEXT NOT NULL,         -- ENT-
    target_entity_id  TEXT NOT NULL,         -- ENT-
    relation_type     TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    assertion_source  TEXT NOT NULL DEFAULT 'source_states',
                                             -- source_states|system_infers|workspace_derives
    source_span_ids   TEXT NOT NULL DEFAULT '[]',
    confidence        REAL NOT NULL DEFAULT 0.0,
    prompt_run_id     TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_graph_relations_src ON graph_relations(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_graph_relations_tgt ON graph_relations(target_entity_id);

-- GraphRAG-style summaries of graph communities, for global reasoning.
CREATE TABLE IF NOT EXISTS community_reports (
    id              TEXT PRIMARY KEY,        -- REP-[UUID8]
    community_key   TEXT NOT NULL,
    level           INTEGER NOT NULL DEFAULT 0,
    title           TEXT NOT NULL,
    summary         TEXT NOT NULL,
    full_content    TEXT NOT NULL,
    finding_json    TEXT NOT NULL DEFAULT '[]',
    entity_ids      TEXT NOT NULL DEFAULT '[]',
    relation_ids    TEXT NOT NULL DEFAULT '[]',
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    rank            REAL NOT NULL DEFAULT 0.0,
    prompt_run_id   TEXT,
    dependency_hash TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_community_reports_key ON community_reports(community_key);

-- HippoRAG-style associative walks over the graph, for explore retrieval.
CREATE TABLE IF NOT EXISTS memory_paths (
    id              TEXT PRIMARY KEY,        -- MPATH-[UUID8]
    query_hash      TEXT NOT NULL,
    route           TEXT NOT NULL,
    start_node_id   TEXT NOT NULL DEFAULT '',
    path_json       TEXT NOT NULL,           -- ordered JSON list of {entity_id, relation_id} hops
    score           REAL NOT NULL DEFAULT 0.0,
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_paths_query ON memory_paths(query_hash);

-- One LLM prompt invocation: provenance, hashes, validator status.
CREATE TABLE IF NOT EXISTS prompt_runs (
    trace_id         TEXT PRIMARY KEY,       -- PTR-[UUID8]
    prompt_id        TEXT NOT NULL,
    prompt_version   TEXT NOT NULL,
    family           TEXT NOT NULL,
    role             TEXT NOT NULL DEFAULT '',
    model_provider   TEXT NOT NULL DEFAULT '',
    model_name       TEXT NOT NULL DEFAULT '',
    input_hash       TEXT NOT NULL,
    output_hash      TEXT NOT NULL DEFAULT '',
    validator_status TEXT NOT NULL DEFAULT 'pending',  -- pending|ok|repaired|failed
    validator_errors TEXT NOT NULL DEFAULT '[]',
    retry_count      INTEGER NOT NULL DEFAULT 0,
    source_ids       TEXT NOT NULL DEFAULT '[]',
    source_span_ids  TEXT NOT NULL DEFAULT '[]',
    curate_spec_hash TEXT NOT NULL DEFAULT '',
    query_trace_id   TEXT,
    latency_ms       INTEGER,
    created_at       TEXT NOT NULL,
    finished_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_prompt_runs_prompt ON prompt_runs(prompt_id, prompt_version);
CREATE INDEX IF NOT EXISTS idx_prompt_runs_query  ON prompt_runs(query_trace_id);

-- Compiled per-workspace curation plan (curate.yml -> runtime policy).
CREATE TABLE IF NOT EXISTS curation_plans (
    id                   TEXT PRIMARY KEY,   -- PLAN-[UUID8]
    workspace_id         TEXT NOT NULL,
    workspace_path       TEXT NOT NULL DEFAULT '',
    project              TEXT NOT NULL DEFAULT '',
    curate_spec_hash     TEXT NOT NULL,
    route                TEXT NOT NULL,
    source_policy_json   TEXT NOT NULL,
    retrieval_policy_json TEXT NOT NULL,
    prompt_profile       TEXT NOT NULL DEFAULT '',
    evidence_plan_json   TEXT NOT NULL DEFAULT '{}',
    prompt_run_id        TEXT,
    created_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_curation_plans_ws ON curation_plans(workspace_id);

-- Provisional derived insights / corrections / promotions awaiting review.
CREATE TABLE IF NOT EXISTS insight_candidates (
    id               TEXT PRIMARY KEY,       -- INS-[UUID8]
    workspace_id     TEXT NOT NULL DEFAULT '',
    source_event_id  TEXT NOT NULL DEFAULT '',
    classification   TEXT NOT NULL,          -- correction|contradiction|derived_insight|style_only|promotion_request|ambiguous
    statement        TEXT NOT NULL,
    evidence_json    TEXT NOT NULL DEFAULT '[]',
    affected_node_ids TEXT NOT NULL DEFAULT '[]',
    confidence       REAL NOT NULL DEFAULT 0.0,
    status           TEXT NOT NULL DEFAULT 'pending',  -- pending|accepted|rejected|promoted|needs_review
    prompt_run_id    TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_insight_candidates_ws     ON insight_candidates(workspace_id);
CREATE INDEX IF NOT EXISTS idx_insight_candidates_status ON insight_candidates(status);

-- Staleness/invalidation index at source-span/knowledge-unit granularity.
CREATE TABLE IF NOT EXISTS artifact_dependencies (
    artifact_id     TEXT NOT NULL,
    artifact_type   TEXT NOT NULL,           -- knowledge_unit|entity|relation|community_report|synthesis_node|curation_plan
    depends_on_id   TEXT NOT NULL,
    depends_on_type TEXT NOT NULL,           -- source_span|knowledge_unit|entity|relation|community_report
    dependency_hash TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (artifact_id, depends_on_id, depends_on_type)
);
CREATE INDEX IF NOT EXISTS idx_artifact_deps_dependson ON artifact_dependencies(depends_on_id);

-- L4 Synthesis: shared, durable corpus-wide synthesized insights (SCHEMA
-- redesign). Workspace-INDEPENDENT distillation above concepts/community reports;
-- the dynamic per-workspace "Curation" lens draws on these but does not store
-- itself here. Source-grounded like every other generated layer.
CREATE TABLE IF NOT EXISTS synthesis_nodes (
    id                   TEXT PRIMARY KEY,   -- SYN-[UUID8]
    title                TEXT NOT NULL,
    statement            TEXT NOT NULL,      -- the synthesized insight
    full_content         TEXT NOT NULL DEFAULT '',
    community_report_ids TEXT NOT NULL DEFAULT '[]',
    concept_ids          TEXT NOT NULL DEFAULT '[]',
    source_span_ids      TEXT NOT NULL DEFAULT '[]',
    confidence           REAL NOT NULL DEFAULT 0.0,
    prompt_run_id        TEXT,
    dependency_hash      TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_synthesis_nodes_conf ON synthesis_nodes(confidence);

-- v0.3.2 DB-native search (retires the external qmd binary). See SCHEMA §11.12–§11.16.
CREATE TABLE IF NOT EXISTS search_documents (
    doc_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,       -- source_span | knowledge_unit | graph_entity | graph_relation | community_report | synthesis_node
    record_id TEXT NOT NULL,
    source_id INTEGER,
    projection_path TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    dependency_hash TEXT NOT NULL,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_search_documents_record ON search_documents(record_type, record_id);
CREATE INDEX IF NOT EXISTS idx_search_documents_source ON search_documents(source_id);

CREATE TABLE IF NOT EXISTS search_chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    text TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(doc_id) REFERENCES search_documents(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_search_chunks_doc ON search_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_search_chunks_record ON search_chunks(record_type, record_id);

CREATE VIRTUAL TABLE IF NOT EXISTS search_documents_fts USING fts5(
    title,
    body,
    record_type UNINDEXED,
    record_id UNINDEXED,
    doc_id UNINDEXED,
    tokenize = "unicode61 remove_diacritics 2 tokenchars '_-.'"
);

CREATE VIRTUAL TABLE IF NOT EXISTS search_documents_fts_tri USING fts5(
    title,
    body,
    record_type UNINDEXED,
    record_id UNINDEXED,
    doc_id UNINDEXED,
    tokenize = "trigram"
);

CREATE TABLE IF NOT EXISTS search_embeddings (
    chunk_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL,
    input_hash TEXT NOT NULL,
    dependency_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    error TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY(chunk_id, provider, model),
    FOREIGN KEY(chunk_id) REFERENCES search_chunks(chunk_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_search_embeddings_model ON search_embeddings(provider, model);

CREATE TABLE IF NOT EXISTS search_index_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS query_traces (
    trace_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    question_hash TEXT NOT NULL,
    route TEXT NOT NULL,
    route_reason TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    community_report_ids TEXT NOT NULL DEFAULT '[]',
    synthesis_node_ids TEXT NOT NULL DEFAULT '[]',
    memory_path_ids TEXT NOT NULL DEFAULT '[]',
    prompt_trace_ids TEXT NOT NULL DEFAULT '[]',
    insight_candidate_ids TEXT NOT NULL DEFAULT '[]',
    retrieval_trace_json TEXT NOT NULL DEFAULT '{}',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    latency_ms INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_query_traces_workspace_created ON query_traces(workspace_id, created_at);

-- Cross-device sync tombstones: records deleted on this device so other devices can apply the deletion on import.
CREATE TABLE IF NOT EXISTS deleted_records (
    table_name  TEXT NOT NULL,
    record_id   TEXT NOT NULL,
    deleted_at  TEXT NOT NULL,
    PRIMARY KEY (table_name, record_id),
    CHECK (table_name IN (
        'sources','atoms','concepts','synthesis_nodes',
        'source_spans','knowledge_units','graph_entities','graph_relations',
        'community_reports','memory_paths','prompt_runs','dag_edges',
        'curation_plans','insight_candidates','artifact_dependencies',
        'synthesis','query_traces','source_pages','source_pdf_pages',
        'claim_supports','compiler_generations'
    ))
);
CREATE INDEX IF NOT EXISTS idx_deleted_records_at ON deleted_records(deleted_at);
"""


def _now_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    ddl: str,
) -> None:
    if column not in _column_names(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply small idempotent migrations for existing vaults."""
    tables = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "sources" not in tables:
        return
    _add_column_if_missing(conn, "sources", "import_origin", "import_origin TEXT")
    _add_column_if_missing(conn, "sources", "import_policy", "import_policy TEXT")
    _add_column_if_missing(conn, "sources", "external_path", "external_path TEXT")
    _add_column_if_missing(
        conn,
        "sources",
        "is_reference",
        "is_reference INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(conn, "sources", "logical_source_id", "logical_source_id TEXT")
    if "ingest_jobs" in tables:
        _add_column_if_missing(
            conn,
            "ingest_jobs",
            "job_type",
            "job_type TEXT NOT NULL DEFAULT 'l2_atoms'",
        )
        _add_column_if_missing(
            conn,
            "ingest_jobs",
            "trigger",
            "trigger TEXT NOT NULL DEFAULT 'wiki_add'",
        )
        _add_column_if_missing(conn, "ingest_jobs", "node_id", "node_id TEXT")
        _add_column_if_missing(
            conn,
            "ingest_jobs",
            "progress_current",
            "progress_current INTEGER DEFAULT 0",
        )
        _add_column_if_missing(
            conn,
            "ingest_jobs",
            "progress_total",
            "progress_total INTEGER DEFAULT 0",
        )
        _add_column_if_missing(
            conn,
            "ingest_jobs",
            "source_name",
            "source_name TEXT DEFAULT ''",
        )
        _add_column_if_missing(
            conn,
            "ingest_jobs",
            "retry_count",
            "retry_count INTEGER NOT NULL DEFAULT 0",
        )
        _add_column_if_missing(
            conn,
            "ingest_jobs",
            "input_tokens",
            "input_tokens INTEGER DEFAULT 0",
        )
        _add_column_if_missing(
            conn,
            "ingest_jobs",
            "output_tokens",
            "output_tokens INTEGER DEFAULT 0",
        )
        _add_column_if_missing(
            conn,
            "ingest_jobs",
            "estimated_cost_usd",
            "estimated_cost_usd REAL DEFAULT 0.0",
        )
        # Migration: drop the FK constraint on ingest_jobs.source_id.
        # source_id=0 is the sentinel for global L3 jobs which have no sources row.
        # The FK caused IntegrityError when inserting those jobs.
        # SQLite requires table-rebuild to drop a constraint; idempotent via FK check.
        has_fk = any(
            "REFERENCES sources" in str(row[0])
            for row in conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='ingest_jobs'"
            ).fetchall()
        )
        if has_fk:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ingest_jobs_new (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id        INTEGER NOT NULL DEFAULT 0,
                    job_type         TEXT NOT NULL DEFAULT 'l2_atoms',
                    trigger          TEXT NOT NULL DEFAULT 'wiki_add',
                    node_id          TEXT,
                    state            TEXT NOT NULL DEFAULT 'queued',
                    phase            TEXT,
                    progress         REAL DEFAULT 0.0,
                    progress_current INTEGER DEFAULT 0,
                    progress_total   INTEGER DEFAULT 0,
                    source_name      TEXT DEFAULT '',
                    pages_created    INTEGER DEFAULT 0,
                    pages_updated    INTEGER DEFAULT 0,
                    error            TEXT,
                    retry_count      INTEGER NOT NULL DEFAULT 0,
                    input_tokens     INTEGER DEFAULT 0,
                    output_tokens    INTEGER DEFAULT 0,
                    estimated_cost_usd REAL DEFAULT 0.0,
                    created_at       TEXT NOT NULL,
                    started_at       TEXT,
                    finished_at      TEXT
                );
                INSERT INTO ingest_jobs_new SELECT
                    id,
                    COALESCE(source_id, 0),
                    job_type,
                    COALESCE(trigger, 'wiki_add'),
                    node_id, state, phase,
                    COALESCE(progress, 0.0),
                    COALESCE(progress_current, 0),
                    COALESCE(progress_total, 0),
                    COALESCE(source_name, ''),
                    COALESCE(pages_created, 0),
                    COALESCE(pages_updated, 0),
                    error,
                    COALESCE(retry_count, 0),
                    COALESCE(input_tokens, 0),
                    COALESCE(output_tokens, 0),
                    COALESCE(estimated_cost_usd, 0.0),
                    created_at, started_at, finished_at
                FROM ingest_jobs;
                DROP TABLE ingest_jobs;
                ALTER TABLE ingest_jobs_new RENAME TO ingest_jobs;
                CREATE INDEX IF NOT EXISTS idx_jobs_state   ON ingest_jobs(state);
                CREATE INDEX IF NOT EXISTS idx_jobs_source  ON ingest_jobs(source_id);
                CREATE INDEX IF NOT EXISTS idx_jobs_created ON ingest_jobs(created_at);
                """
            )
            conn.execute("PRAGMA foreign_keys = ON")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sources_logical_source_id "
        "ON sources(logical_source_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sources_external_path "
        "ON sources(external_path)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_pdf_pages (
            source_id       INTEGER NOT NULL,
            relpath         TEXT NOT NULL,
            page_number     INTEGER NOT NULL,
            content_hash    TEXT NOT NULL,
            char_count      INTEGER NOT NULL DEFAULT 0,
            word_count      INTEGER NOT NULL DEFAULT 0,
            metadata        TEXT,
            extracted_at    TEXT NOT NULL,
            PRIMARY KEY (source_id, page_number),
            FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_pdf_pages_relpath "
        "ON source_pdf_pages(relpath)"
    )

    _migrate_v8_compiler_integrity(conn, tables)



def _migrate_v8_compiler_integrity(
    conn: sqlite3.Connection, tables: set[str]
) -> None:
    """SCHEMA_VERSION 7 -> 8 (Plan B): additive claim-support / formula /
    compiler-generation schema. Forward-only and idempotent (SCHEMA §20.6).

    The ADD COLUMN ... NOT NULL DEFAULT statements backfill every existing
    knowledge_units row as ``support_status='unchecked'`` and
    ``formula_status='not_applicable'`` automatically; no support rows are
    created and nothing is silently verified.
    """
    if "knowledge_units" in tables:
        _add_column_if_missing(conn, "knowledge_units", "semantic_hash", "semantic_hash TEXT")
        _add_column_if_missing(
            conn, "knowledge_units", "support_status",
            "support_status TEXT NOT NULL DEFAULT 'unchecked'",
        )
        _add_column_if_missing(
            conn, "knowledge_units", "support_reason",
            "support_reason TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn, "knowledge_units", "formula_status",
            "formula_status TEXT NOT NULL DEFAULT 'not_applicable'",
        )
        _add_column_if_missing(conn, "knowledge_units", "retired_at", "retired_at TEXT")
        _add_column_if_missing(conn, "knowledge_units", "generation_id", "generation_id TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_units_support "
            "ON knowledge_units(support_status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_units_generation "
            "ON knowledge_units(generation_id)"
        )

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS claim_supports (
            knowledge_unit_id TEXT NOT NULL,
            source_span_id    TEXT NOT NULL,
            support_role      TEXT NOT NULL,
            support_status    TEXT NOT NULL,
            support_reason    TEXT NOT NULL DEFAULT '',
            evidence_hash     TEXT NOT NULL,
            validator_trace_id TEXT,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            PRIMARY KEY (knowledge_unit_id, source_span_id, support_role)
        );
        CREATE INDEX IF NOT EXISTS idx_claim_supports_span ON claim_supports(source_span_id);
        CREATE INDEX IF NOT EXISTS idx_claim_supports_status ON claim_supports(support_status);

        CREATE TABLE IF NOT EXISTS compiler_generations (
            id               TEXT PRIMARY KEY,
            source_id        INTEGER,
            status           TEXT NOT NULL DEFAULT 'staged',
            prompt_contract_version TEXT NOT NULL,
            created_at       TEXT NOT NULL,
            published_at     TEXT,
            discarded_at     TEXT,
            audit_json       TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_compiler_generations_source
            ON compiler_generations(source_id, status);
        """
    )

    # Extend the deleted_records CHECK list so the two new canonical tables can
    # be tombstoned on a migrated (old) DB. SQLite cannot ALTER a CHECK in
    # place, so rebuild the table only when its CHECK predates Plan B.
    if "deleted_records" in tables:
        ddl_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='deleted_records'"
        ).fetchone()
        if ddl_row and "claim_supports" not in str(ddl_row[0]):
            conn.executescript(
                """
                CREATE TABLE deleted_records_new (
                    table_name  TEXT NOT NULL,
                    record_id   TEXT NOT NULL,
                    deleted_at  TEXT NOT NULL,
                    PRIMARY KEY (table_name, record_id),
                    CHECK (table_name IN (
                        'sources','atoms','concepts','synthesis_nodes',
                        'source_spans','knowledge_units','graph_entities','graph_relations',
                        'community_reports','memory_paths','prompt_runs','dag_edges',
                        'curation_plans','insight_candidates','artifact_dependencies',
                        'synthesis','query_traces','source_pages','source_pdf_pages',
                        'claim_supports','compiler_generations'
                    ))
                );
                INSERT INTO deleted_records_new SELECT table_name, record_id, deleted_at
                    FROM deleted_records;
                DROP TABLE deleted_records;
                ALTER TABLE deleted_records_new RENAME TO deleted_records;
                CREATE INDEX IF NOT EXISTS idx_deleted_records_at
                    ON deleted_records(deleted_at);
                """
            )



def init_db(db_path: Path) -> None:
    """Create the state database and apply the schema. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # sqlite3's context manager only commits/rolls back the transaction; it
    # does not close the connection. Close explicitly so the WAL sidecars do
    # not outlive this call on a GC-timing-dependent schedule.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_SQL)
        _apply_migrations(conn)
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )
        else:
            # Handle version mismatch if necessary
            current_version = row[0]
            if current_version != SCHEMA_VERSION:
                # In v0.1.0 fresh start, we just stamp it.
                # In production, this would trigger migration logic.
                conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))

        conn.commit()
    finally:
        conn.close()



@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Context-managed connection with row factory and foreign keys enabled."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # Everything after instantiation runs inside try so a failure in schema
    # setup or migration cannot leak the connection (and its WAL sidecars).
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        # Self-heal for existing empty/corrupted state DB files missing base tables.
        conn.executescript(SCHEMA_SQL)
        _apply_migrations(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_stats(db_path: Path) -> dict:
    """Quick stats for `wiki status`."""
    if not db_path.exists():
        return {
            "sources_total": 0,
            "sources_l1_done": 0,
            "sources_curated": 0,
            "ingest_runs": 0,
        }
    with connect(db_path) as conn:
        sources_total = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        sources_l1_done = conn.execute(
            f"SELECT COUNT(*) FROM sources WHERE l1_status = '{consts.STATUS_DONE}'"
        ).fetchone()[0]
        sources_curated = conn.execute(
            "SELECT COUNT(*) FROM sources WHERE status = 'curated'"
        ).fetchone()[0]
        ingest_runs = conn.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0]
        token_row = conn.execute(
            "SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0), "
            "COALESCE(SUM(estimated_cost_usd), 0.0) FROM ingest_jobs WHERE state = 'done'"
        ).fetchone()
        total_input_tokens = int(token_row[0])
        total_output_tokens = int(token_row[1])
        total_cost_usd = float(token_row[2])
    return {
        "sources_total": sources_total,
        "sources_l1_done": sources_l1_done,
        "sources_curated": sources_curated,
        "ingest_runs": ingest_runs,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost_usd": total_cost_usd,
    }


def enqueue_job(
    db_path: Path,
    source_id: int,
    job_type: str,
    *,
    trigger: str = "wiki_add",
    node_id: str | None = None,
    source_name: str = "",
) -> int:
    """Create or reuse a queued/running ingest job for a source and job type.

    source_id=0 is the sentinel for global jobs (e.g. L3 clustering) that are
    not tied to a specific source row.  The ingest_jobs table has no FK on
    source_id (removed in migration) so 0 inserts cleanly.
    """
    with connect(db_path) as conn:
        existing = conn.execute(
            f"""
            SELECT id FROM ingest_jobs
            WHERE source_id = ? AND job_type = ? AND state IN ('{consts.STATUS_QUEUED}', '{consts.STATUS_RUNNING}')
            ORDER BY id DESC LIMIT 1
            """,
            (source_id, job_type),
        ).fetchone()
        if existing:
            return int(existing["id"])
        cur = conn.execute(
            f"""
            INSERT INTO ingest_jobs
                (source_id, job_type, trigger, node_id, state, phase, progress,
                 progress_current, progress_total, source_name, created_at)
            VALUES (?, ?, ?, ?, '{consts.STATUS_QUEUED}', ?, 0.0, 0, 0, ?, ?)
            """,
            (
                source_id,
                job_type,
                trigger,
                node_id,
                "queued",
                source_name,
                _now_iso(),
            ),
        )
        return int(cur.lastrowid)



def get_pending_jobs_for_source(db_path: Path, source_id: int) -> list[dict]:
    """Return queued/running jobs for one source."""
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM ingest_jobs
            WHERE source_id = ? AND state IN ('{consts.STATUS_QUEUED}', '{consts.STATUS_RUNNING}')
            ORDER BY id ASC
            """,
            (source_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_ingest_jobs(
    db_path: Path,
    *,
    states: tuple[str, ...] | None = None,
    limit: int = 50,
) -> list[dict]:
    """List ingest jobs, newest first unless filtered to queued/running."""
    params: list[object] = []
    query = "SELECT * FROM ingest_jobs"
    if states:
        query += f" WHERE state IN ({','.join('?' for _ in states)})"
        params.extend(states)
    order = "ASC" if states and any(s in {consts.STATUS_QUEUED, consts.STATUS_RUNNING} for s in states) else "DESC"
    query += f" ORDER BY id {order} LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with connect(db_path) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]


def claim_next_job(db_path: Path) -> dict | None:
    """Atomically claim the oldest queued job."""
    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"""
            SELECT * FROM ingest_jobs
            WHERE state = '{consts.STATUS_QUEUED}'
            ORDER BY id ASC LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_RUNNING}', phase = '{consts.STATUS_RUNNING}', started_at = ?, error = NULL
            WHERE id = ?
            """,
            (_now_iso(), row["id"]),
        )
        updated = conn.execute(
            "SELECT * FROM ingest_jobs WHERE id = ?",
            (row["id"],),
        ).fetchone()
        return dict(updated) if updated else None


def recover_stale_jobs(db_path: Path) -> int:
    """Return interrupted running jobs to the queue after a process restart."""
    with connect(db_path) as conn:
        cur = conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_QUEUED}', phase = 'recovered', error = NULL
            WHERE state = '{consts.STATUS_RUNNING}'
            """
        )
        return int(cur.rowcount or 0)


def update_job_progress(
    db_path: Path,
    job_id: int,
    *,
    phase: str,
    progress: float | None = None,
    progress_current: int | None = None,
    progress_total: int | None = None,
) -> None:
    """Update progress fields for a running job."""
    fields = ["phase = ?"]
    values: list[object] = [phase]
    if progress is not None:
        fields.append("progress = ?")
        values.append(max(0.0, min(1.0, float(progress))))
    if progress_current is not None:
        fields.append("progress_current = ?")
        values.append(int(progress_current))
    if progress_total is not None:
        fields.append("progress_total = ?")
        values.append(int(progress_total))
    values.append(job_id)
    with connect(db_path) as conn:
        conn.execute(
            f"UPDATE ingest_jobs SET {', '.join(fields)} WHERE id = ?",
            tuple(values),
        )


def mark_job_done(
    db_path: Path,
    job_id: int,
    *,
    pages_created: int = 0,
    pages_updated: int = 0,
) -> None:
    """Mark a job as completed."""
    with connect(db_path) as conn:
        conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_DONE}', phase = '{consts.STATUS_DONE}', progress = 1.0,
                finished_at = ?, pages_created = ?, pages_updated = ?, error = NULL
            WHERE id = ?
            """,
            (_now_iso(), pages_created, pages_updated, job_id),
        )


def mark_job_failed(db_path: Path, job_id: int, error: str) -> None:
    """Mark a job as failed."""
    with connect(db_path) as conn:
        conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_FAILED}', phase = '{consts.STATUS_FAILED}', finished_at = ?, error = ?
            WHERE id = ?
            """,
            (_now_iso(), error[:2000], job_id),
        )


def cancel_job(db_path: Path, job_id: int) -> bool:
    """Cancel a queued job. Running jobs are left untouched by design."""
    with connect(db_path) as conn:
        cur = conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_CANCELLED}', phase = '{consts.STATUS_CANCELLED}',
                finished_at = ?, error = 'Cancelled by user'
            WHERE id = ? AND state = '{consts.STATUS_QUEUED}'
            """,
            (_now_iso(), job_id),
        )
        return bool(cur.rowcount)


def rerun_job(db_path: Path, job_id: int) -> bool:
    """Return a completed, failed, or cancelled job to the queued state."""
    with connect(db_path) as conn:
        cur = conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_QUEUED}', phase = 'rerun', progress = 0.0,
                progress_current = 0, progress_total = 0, retry_count = 0,
                error = NULL, started_at = NULL, finished_at = NULL
            WHERE id = ? AND state IN (?, ?, ?)
            """,
            (job_id, consts.STATUS_DONE, consts.STATUS_FAILED, consts.STATUS_CANCELLED),
        )
        return bool(cur.rowcount)


def requeue_job_for_retry(db_path: Path, job_id: int, retry_count: int, error: str) -> None:
    """Reset a failed job back to queued for retry, recording the attempt count."""
    with connect(db_path) as conn:
        conn.execute(
            f"""
            UPDATE ingest_jobs
            SET state = '{consts.STATUS_QUEUED}', phase = 'retry', progress = 0.0,
                retry_count = ?, error = ?, started_at = NULL, finished_at = NULL
            WHERE id = ?
            """,
            (retry_count, error[:2000], job_id),
        )


def accumulate_job_tokens(
    db_path: Path,
    job_id: int,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float = 0.0,
) -> None:
    """Add token counts to a job row (cumulative, safe to call multiple times)."""
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE ingest_jobs
            SET input_tokens  = COALESCE(input_tokens, 0)  + ?,
                output_tokens = COALESCE(output_tokens, 0) + ?,
                estimated_cost_usd = COALESCE(estimated_cost_usd, 0.0) + ?
            WHERE id = ?
            """,
            (int(input_tokens), int(output_tokens), float(cost_usd), job_id),
        )


def count_active_l2_jobs(db_path: Path) -> int:
    """Return the number of queued or running l2_atoms jobs."""
    if not db_path.exists():
        return 0
    with connect(db_path) as conn:
        row = conn.execute(
            f"SELECT COUNT(*) FROM ingest_jobs WHERE job_type = 'l2_atoms' AND state IN ('{consts.STATUS_QUEUED}', '{consts.STATUS_RUNNING}')"
        ).fetchone()
        return int(row[0]) if row else 0


def get_jobs_done_today(db_path: Path) -> list[dict]:
    """Return jobs completed today (UTC date), newest first."""
    if not db_path.exists():
        return []
    today_prefix = _now_iso()[:10]  # "YYYY-MM-DD"
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM ingest_jobs WHERE state = '{consts.STATUS_DONE}' AND finished_at LIKE ? ORDER BY id DESC",
            (f"{today_prefix}%",),
        ).fetchall()
        return [dict(r) for r in rows]


def get_pending_count(db_path: Path) -> int:
    """Count sources with status 'pending' or 'force_pending'."""
    if not db_path.exists():
        return 0
    with connect(db_path) as conn:
        return conn.execute(
            f"SELECT COUNT(*) FROM sources WHERE status IN ('{consts.STATUS_PENDING}', 'force_pending')"
        ).fetchone()[0]


def set_source_layer_status(
    db_path: Path,
    source_id: int,
    layer: str,
    status: str,
    *,
    error: str | None = None,
) -> None:
    """Update a source's per-layer pipeline status.

    layer must be one of: l1, l2, l3, l4.
    status should be: pending, running, done, error, or skipped.
    """
    if layer not in {"l1", "l2", "l3", "l4"}:
        raise ValueError(f"Invalid layer status key: {layer}")
    column = f"{layer}_status"
    with connect(db_path) as conn:
        conn.execute(
            f"UPDATE sources SET {column} = ?, layer_error = ? WHERE id = ?",
            (status, error, source_id),
        )


def set_sources_layer_status(
    db_path: Path,
    source_ids: list[int],
    layer: str,
    status: str,
    *,
    error: str | None = None,
) -> None:
    """Bulk update per-layer status for source rows."""
    if not source_ids:
        return
    if layer not in {"l1", "l2", "l3", "l4"}:
        raise ValueError(f"Invalid layer status key: {layer}")
    column = f"{layer}_status"
    with connect(db_path) as conn:
        conn.execute(
            f"UPDATE sources SET {column} = ?, layer_error = ? "
            f"WHERE id IN ({','.join('?' * len(source_ids))})",
            (status, error, *source_ids),
        )
def insert_dag_edge(
    db_path: str | Path,
    from_id: str,
    to_id: str,
    edge_type: str,
    source_id: int | str | None,
) -> None:
    """Record a directed edge in the DAG. Idempotent (INSERT OR IGNORE)."""
    with connect(Path(db_path)) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO dag_edges "
            "(id, from_id, to_id, edge_type, source_id, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (f"{from_id}:{to_id}", from_id, to_id, edge_type, source_id, _now_iso()),
        )


def get_dag_edges_for_source(db_path: str | Path, source_id: str) -> list[dict]:
    """Return all dag_edges recorded for a given source_id."""
    with connect(Path(db_path)) as conn:
        rows = conn.execute(
            "SELECT from_id, to_id, edge_type FROM dag_edges WHERE source_id=?",
            (source_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_dag_edges_for_atoms(db_path: str | Path, atom_ids: list[str]) -> list[dict]:
    """Return dag_edges where from_id is one of the given ATM IDs (ATM→CON, source_id=NULL)."""
    if not atom_ids:
        return []
    placeholders = ",".join("?" for _ in atom_ids)
    with connect(Path(db_path)) as conn:
        rows = conn.execute(
            f"SELECT from_id, to_id, edge_type FROM dag_edges WHERE from_id IN ({placeholders})",
            tuple(atom_ids),
        ).fetchall()
        return [dict(r) for r in rows]


def get_page_hashes(db_path: Path) -> dict[str, str]:
    """Load all known page hashes: {wiki_path: content_hash}."""
    if not db_path.exists():
        return {}
    with connect(db_path) as conn:
        rows = conn.execute("SELECT wiki_path, content_hash FROM page_hashes").fetchall()
        return {row["wiki_path"]: row["content_hash"] for row in rows}


def update_page_hash(db_path: Path, wiki_path: str, content_hash: str) -> None:
    """Upsert the hash for a specific wiki page."""
    import datetime
    now = datetime.datetime.now().isoformat()
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO page_hashes (wiki_path, content_hash, last_synced) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(wiki_path) DO UPDATE SET "
            "content_hash = excluded.content_hash, "
            "last_synced = excluded.last_synced",
            (wiki_path, content_hash, now),
        )


def delete_page_hash(db_path: Path, wiki_path: str) -> None:
    """Remove a page hash entry (e.g. if file deleted)."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM page_hashes WHERE wiki_path = ?", (wiki_path,))


def replace_source_pdf_pages(
    db_path: Path,
    source_id: int,
    relpath: str,
    pages: list[dict],
) -> None:
    """Replace page-level PDF provenance rows for one source."""
    now = _now_iso()
    with connect(db_path) as conn:
        conn.execute("DELETE FROM source_pdf_pages WHERE source_id = ?", (source_id,))
        for page in pages:
            page_number = int(page.get("page") or page.get("page_number") or 0)
            if page_number <= 0:
                continue
            metadata = {
                k: v
                for k, v in page.items()
                if k
                not in {"page", "page_number", "content_hash", "char_count", "word_count", "text"}
            }
            conn.execute(
                """
                INSERT INTO source_pdf_pages
                    (source_id, relpath, page_number, content_hash, char_count,
                     word_count, metadata, extracted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    relpath,
                    page_number,
                    str(page.get("content_hash") or ""),
                    int(page.get("char_count") or 0),
                    int(page.get("word_count") or 0),
                    json_dumps(metadata),
                    now,
                ),
            )


def list_source_pdf_pages(db_path: Path, source_id: int) -> list[dict]:
    """Return PDF page metadata rows for one source."""
    if not db_path.exists():
        return []
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT source_id, relpath, page_number, content_hash, char_count,
                   word_count, metadata, extracted_at
            FROM source_pdf_pages
            WHERE source_id = ?
            ORDER BY page_number ASC
            """,
            (source_id,),
        ).fetchall()
        out: list[dict] = []
        for row in rows:
            item = dict(row)
            metadata_raw = item.get("metadata")
            if metadata_raw:
                try:
                    import json

                    item["metadata"] = json.loads(metadata_raw)
                except Exception:
                    item["metadata"] = {}
            else:
                item["metadata"] = {}
            out.append(item)
        return out


def record_source_page(
    db_path: Path,
    source_id: int,
    wiki_path: str,
    operation: str,
) -> None:
    """Record that a wiki page was created or updated from a source."""
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO source_pages (source_id, wiki_path, operation, at)
            VALUES (?, ?, ?, ?)
            """,
            (source_id, wiki_path, operation, _now_iso()),
        )


def list_source_pages(db_path: Path, source_id: int) -> list[dict]:
    """Return wiki pages recorded as generated from one source."""
    if not db_path.exists():
        return []
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT source_id, wiki_path, operation, at
            FROM source_pages
            WHERE source_id = ?
            ORDER BY at DESC
            """,
            (source_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def json_dumps(value) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def source_path_to_relpath(root: Path, source_path: str) -> str:
    """Convert a source path (absolute or relative) to a vault-relative relpath.

    Handles expanduser and resolve for absolute paths. Falls back to the raw
    string when the path is not inside the vault root.
    """
    if not source_path:
        return ""
    path = Path(source_path).expanduser()
    if path.is_absolute():
        try:
            return str(path.resolve().relative_to(root.resolve()))
        except ValueError:
            return str(source_path)
    return str(source_path)


def get_source_row(
    db_path: Path,
    root: Path,
    *,
    source_id: int | None = None,
    relpath: str = "",
    source_path: str = "",
) -> dict[str, Any] | None:
    """Unified source lookup by id, relpath, external_path, import_origin,
    or logical_source_id.

    When ``source_path`` is given and ``relpath`` is empty, the path is
    resolved against ``root`` to produce a relpath first.
    """
    lookup = relpath or source_path
    relpath = relpath or source_path_to_relpath(root, source_path)
    resolved_lookup = ""
    if lookup:
        path = Path(lookup).expanduser()
        if path.is_absolute():
            resolved_lookup = str(path.resolve(strict=False))
    with connect(db_path) as conn:
        if source_id is not None:
            row = conn.execute(
                "SELECT * FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
        elif relpath:
            row = conn.execute(
                """
                SELECT * FROM sources
                WHERE relpath = ?
                   OR external_path = ?
                   OR external_path = ?
                   OR import_origin = ?
                   OR import_origin = ?
                   OR logical_source_id = ?
                """,
                (relpath, relpath, resolved_lookup, relpath, resolved_lookup, relpath),
            ).fetchone()
        else:
            row = None
    return dict(row) if row else None


# =====================================================================
# v0.3.1 curation-native accessors (SCHEMA.md §11)
# =====================================================================


def _new_id(prefix: str) -> str:
    """Generate a typed `<PREFIX>-<UUID8>` id."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _loads_list(raw: Any) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _loads_obj(raw: Any) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _decode_span_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["metadata"] = _loads_obj(data.get("metadata"))
    return data


# --- source_spans ----------------------------------------------------


def upsert_source_span(
    db_path: Path,
    *,
    source_id: int,
    relpath: str,
    span_type: str,
    content_hash: str,
    page_number: int | None = None,
    section_title: str | None = None,
    toc_id: str | None = None,
    start_char: int | None = None,
    end_char: int | None = None,
    text_preview: str = "",
    metadata: dict | None = None,
) -> str:
    """Insert a source span, or return the existing id for the same
    (source_id, content_hash). Span ids are stable across re-parses when the
    exact span text is unchanged."""
    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM source_spans WHERE source_id = ? AND content_hash = ?",
            (source_id, content_hash),
        ).fetchone()
        if existing:
            return str(existing["id"])
        span_id = _new_id("SPAN")
        conn.execute(
            """
            INSERT INTO source_spans
                (id, source_id, relpath, span_type, page_number, section_title,
                 toc_id, start_char, end_char, content_hash, text_preview,
                 metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                span_id,
                source_id,
                relpath,
                span_type,
                page_number,
                section_title,
                toc_id,
                start_char,
                end_char,
                content_hash,
                text_preview,
                json.dumps(metadata) if metadata else None,
                _now_iso(),
            ),
        )
        return span_id


def list_source_spans(db_path: Path, source_id: int) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM source_spans WHERE source_id = ? ORDER BY "
            "page_number IS NULL, page_number, start_char IS NULL, start_char",
            (source_id,),
        ).fetchall()
        return [_decode_span_row(row) for row in rows]


def get_source_spans_by_ids(db_path: Path, span_ids: list[str]) -> list[dict]:
    if not span_ids:
        return []
    with connect(db_path) as conn:
        placeholders = ",".join("?" for _ in span_ids)
        rows = conn.execute(
            f"SELECT * FROM source_spans WHERE id IN ({placeholders})",
            tuple(span_ids),
        ).fetchall()
        return [_decode_span_row(row) for row in rows]


# --- knowledge_units -------------------------------------------------


def upsert_knowledge_unit(
    db_path: Path,
    *,
    unit_type: str,
    canonical_name: str,
    statement: str,
    source_span_ids: list[str],
    source_id: int | None = None,
    confidence: float = 0.0,
    truth_status: str = "source_supported",
    atom_node_id: str | None = None,
    prompt_run_id: str | None = None,
    unit_id: str | None = None,
) -> str:
    """Insert a typed knowledge unit, or update it in place when `unit_id` is
    given and already exists."""
    now = _now_iso()
    spans_json = json.dumps(source_span_ids)
    with connect(db_path) as conn:
        if unit_id:
            existing = conn.execute(
                "SELECT id FROM knowledge_units WHERE id = ?", (unit_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE knowledge_units
                       SET unit_type = ?, canonical_name = ?, statement = ?,
                           source_span_ids = ?, source_id = ?, confidence = ?,
                           truth_status = ?, atom_node_id = ?, prompt_run_id = ?,
                           updated_at = ?
                     WHERE id = ?
                    """,
                    (
                        unit_type, canonical_name, statement, spans_json,
                        source_id, confidence, truth_status, atom_node_id,
                        prompt_run_id, now, unit_id,
                    ),
                )
                return unit_id
        new_unit_id = unit_id or _new_id("KNU")
        conn.execute(
            """
            INSERT INTO knowledge_units
                (id, unit_type, canonical_name, statement, source_span_ids,
                 source_id, confidence, truth_status, atom_node_id,
                 prompt_run_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_unit_id, unit_type, canonical_name, statement, spans_json,
                source_id, confidence, truth_status, atom_node_id,
                prompt_run_id, now, now,
            ),
        )
        return new_unit_id


def _decode_unit_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    return data


def list_knowledge_units_for_source(db_path: Path, source_id: int) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM knowledge_units WHERE source_id = ? ORDER BY created_at",
            (source_id,),
        ).fetchall()
        return [_decode_unit_row(row) for row in rows]


# --- claim_supports / compiler_generations (Plan B, v0.8.0, SCHEMA §20) ------

SUPPORT_ROLES = frozenset({"primary", "contextual", "formula"})
SUPPORT_STATUSES = frozenset({"unchecked", "verified", "failed", "stale"})
FORMULA_STATUSES = frozenset({
    "not_applicable", "preserved_in_text", "linked_evidence",
    "omitted_incidental", "missing", "uncertain",
})
GENERATION_STATUSES = frozenset({"staged", "authoritative", "discarded"})


def upsert_claim_support(
    db_path: Path,
    *,
    knowledge_unit_id: str,
    source_span_id: str,
    support_role: str,
    support_status: str,
    evidence_hash: str,
    support_reason: str = "",
    validator_trace_id: str | None = None,
) -> None:
    """Insert or update one minimal-support record (SCHEMA §20.2). Storage only:
    callers (P4 validation) decide roles/statuses; a valid span id is never
    proof of support on its own."""
    if support_role not in SUPPORT_ROLES:
        raise ValueError(f"invalid support_role: {support_role!r}")
    if support_status not in SUPPORT_STATUSES:
        raise ValueError(f"invalid support_status: {support_status!r}")
    now = _now_iso()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO claim_supports
                (knowledge_unit_id, source_span_id, support_role, support_status,
                 support_reason, evidence_hash, validator_trace_id,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (knowledge_unit_id, source_span_id, support_role)
            DO UPDATE SET support_status = excluded.support_status,
                          support_reason = excluded.support_reason,
                          evidence_hash  = excluded.evidence_hash,
                          validator_trace_id = excluded.validator_trace_id,
                          updated_at = excluded.updated_at
            """,
            (knowledge_unit_id, source_span_id, support_role, support_status,
             support_reason, evidence_hash, validator_trace_id, now, now),
        )


def list_claim_supports(db_path: Path, knowledge_unit_id: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM claim_supports WHERE knowledge_unit_id = ? "
            "ORDER BY support_role, source_span_id",
            (knowledge_unit_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def set_unit_support_status(
    db_path: Path, unit_id: str, status: str, reason: str = ""
) -> None:
    """Update a knowledge unit's claim-level support verdict (SCHEMA §20.1)."""
    if status not in SUPPORT_STATUSES:
        raise ValueError(f"invalid support_status: {status!r}")
    if status in {"failed", "stale"} and not reason:
        raise ValueError(f"support_status={status!r} requires a non-empty reason")
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE knowledge_units SET support_status = ?, support_reason = ?, "
            "updated_at = ? WHERE id = ?",
            (status, reason, _now_iso(), unit_id),
        )


def set_unit_formula_status(
    db_path: Path, unit_id: str, status: str, reason: str = ""
) -> None:
    """Update a knowledge unit's formula lifecycle status (SCHEMA §20.1)."""
    if status not in FORMULA_STATUSES:
        raise ValueError(f"invalid formula_status: {status!r}")
    with connect(db_path) as conn:
        if reason:
            conn.execute(
                "UPDATE knowledge_units SET formula_status = ?, support_reason = ?, "
                "updated_at = ? WHERE id = ?",
                (status, reason, _now_iso(), unit_id),
            )
        else:
            conn.execute(
                "UPDATE knowledge_units SET formula_status = ?, updated_at = ? "
                "WHERE id = ?",
                (status, _now_iso(), unit_id),
            )


def retire_knowledge_unit(db_path: Path, unit_id: str) -> None:
    """Tombstone a unit retired by source edit/delete/split reconciliation
    (SCHEMA §20.1). Retired rows are never deleted by the compiler and never
    feed downstream stages."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE knowledge_units SET retired_at = ?, updated_at = ? "
            "WHERE id = ? AND retired_at IS NULL",
            (_now_iso(), _now_iso(), unit_id),
        )


def list_eligible_knowledge_units(
    db_path: Path, source_id: int | None = None
) -> list[dict]:
    """Active downstream-eligible units: retired_at IS NULL AND
    support_status='verified' (SCHEMA §20.1 eligibility rule). `unchecked`
    legacy rows are intentionally excluded from compiler inputs."""
    sql = (
        "SELECT * FROM knowledge_units "
        "WHERE retired_at IS NULL AND support_status = 'verified'"
    )
    params: tuple = ()
    if source_id is not None:
        sql += " AND source_id = ?"
        params = (source_id,)
    sql += " ORDER BY created_at"
    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_decode_unit_row(row) for row in rows]


def refresh_support_freshness(db_path: Path) -> set[str]:
    """Re-check every verified claim_supports.evidence_hash against the cited
    span's current content_hash; mark mismatched support rows and their owning
    units `stale` (SYSTEM_BEHAVIOR §26.1 freshness re-check). Returns the set of
    unit ids newly marked stale."""
    now = _now_iso()
    stale_units: set[str] = set()
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT cs.knowledge_unit_id AS uid, cs.source_span_id AS span,
                   cs.support_role AS role, cs.evidence_hash AS hash,
                   ss.content_hash AS current_hash
            FROM claim_supports cs
            LEFT JOIN source_spans ss ON ss.id = cs.source_span_id
            WHERE cs.support_status = 'verified'
            """
        ).fetchall()
        for r in rows:
            if r["current_hash"] is None or r["current_hash"] != r["hash"]:
                conn.execute(
                    "UPDATE claim_supports SET support_status = 'stale', "
                    "support_reason = ?, updated_at = ? "
                    "WHERE knowledge_unit_id = ? AND source_span_id = ? "
                    "AND support_role = ?",
                    ("cited span content changed or was removed", now,
                     r["uid"], r["span"], r["role"]),
                )
                stale_units.add(r["uid"])
        for uid in stale_units:
            conn.execute(
                "UPDATE knowledge_units SET support_status = 'stale', "
                "support_reason = ?, updated_at = ? "
                "WHERE id = ? AND support_status = 'verified'",
                ("stale support: cited span content changed or was removed", now, uid),
            )
    return stale_units


def create_compiler_generation(
    db_path: Path,
    *,
    prompt_contract_version: str,
    source_id: int | None = None,
) -> str:
    """Open a new staged compiler generation (SCHEMA §20.3). Rows attributed to
    it stay invisible to query/search until it publishes."""
    gen_id = _new_id("GEN")
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO compiler_generations "
            "(id, source_id, status, prompt_contract_version, created_at, audit_json) "
            "VALUES (?, ?, 'staged', ?, ?, '{}')",
            (gen_id, source_id, prompt_contract_version, _now_iso()),
        )
    return gen_id


def get_authoritative_generation(
    db_path: Path, source_id: int | None
) -> dict | None:
    """The single authoritative generation for a source scope, or None."""
    with connect(db_path) as conn:
        if source_id is None:
            row = conn.execute(
                "SELECT * FROM compiler_generations "
                "WHERE source_id IS NULL AND status = 'authoritative' LIMIT 1"
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM compiler_generations "
                "WHERE source_id = ? AND status = 'authoritative' LIMIT 1",
                (source_id,),
            ).fetchone()
    return dict(row) if row else None


def publish_compiler_generation(
    db_path: Path, gen_id: str, *, audit_json: str = "{}"
) -> None:
    """Flip a staged generation to authoritative (SCHEMA §20.3). Discards the
    prior authoritative generation for the same source scope so the
    at-most-one-authoritative invariant holds. The publish GATE (audit
    validation) is enforced by the compiler in P6, not here."""
    now = _now_iso()
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT source_id, status FROM compiler_generations WHERE id = ?",
            (gen_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown compiler generation: {gen_id}")
        if row["status"] != "staged":
            raise ValueError(f"generation {gen_id} is not staged (is {row['status']})")
        source_id = row["source_id"]
        if source_id is None:
            conn.execute(
                "UPDATE compiler_generations SET status = 'discarded', "
                "discarded_at = ? WHERE source_id IS NULL AND status = 'authoritative'",
                (now,),
            )
        else:
            conn.execute(
                "UPDATE compiler_generations SET status = 'discarded', "
                "discarded_at = ? WHERE source_id = ? AND status = 'authoritative'",
                (now, source_id),
            )
        conn.execute(
            "UPDATE compiler_generations SET status = 'authoritative', "
            "published_at = ?, audit_json = ? WHERE id = ?",
            (now, audit_json, gen_id),
        )


def discard_compiler_generation(db_path: Path, gen_id: str) -> None:
    """Mark a staged generation discarded after a failed compile (SCHEMA §20.3).
    No partial authoritative publish is representable."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE compiler_generations SET status = 'discarded', discarded_at = ? "
            "WHERE id = ? AND status = 'staged'",
            (_now_iso(), gen_id),
        )


# --- graph_entities / graph_relations --------------------------------


def upsert_graph_entity(
    db_path: Path,
    *,
    canonical_name: str,
    entity_type: str,
    description: str = "",
    source_span_ids: list[str] | None = None,
    knowledge_unit_ids: list[str] | None = None,
    prompt_run_id: str | None = None,
) -> str:
    """Insert or merge an entity, deduplicated by (canonical_name, entity_type).
    On merge, span/knowledge-unit references are unioned and a non-empty
    description replaces an empty one."""
    now = _now_iso()
    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT * FROM graph_entities WHERE canonical_name = ? AND entity_type = ?",
            (canonical_name, entity_type),
        ).fetchone()
        if existing:
            merged_spans = sorted(
                set(_loads_list(existing["source_span_ids"]))
                | set(source_span_ids or [])
            )
            merged_units = sorted(
                set(_loads_list(existing["knowledge_unit_ids"]))
                | set(knowledge_unit_ids or [])
            )
            new_desc = description or str(existing["description"])
            conn.execute(
                """
                UPDATE graph_entities
                   SET description = ?, source_span_ids = ?,
                       knowledge_unit_ids = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    new_desc, json.dumps(merged_spans), json.dumps(merged_units),
                    now, existing["id"],
                ),
            )
            return str(existing["id"])
        entity_id = _new_id("ENT")
        conn.execute(
            """
            INSERT INTO graph_entities
                (id, canonical_name, entity_type, description, source_span_ids,
                 knowledge_unit_ids, prompt_run_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id, canonical_name, entity_type, description,
                json.dumps(source_span_ids or []),
                json.dumps(knowledge_unit_ids or []),
                prompt_run_id, now, now,
            ),
        )
        return entity_id


def upsert_graph_relation(
    db_path: Path,
    *,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str,
    description: str = "",
    assertion_source: str = "source_states",
    source_span_ids: list[str] | None = None,
    confidence: float = 0.0,
    prompt_run_id: str | None = None,
) -> str:
    """Insert a relation. Both endpoints must be declared entities."""
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"relation confidence out of range: {confidence}")
    with connect(db_path) as conn:
        for endpoint in (source_entity_id, target_entity_id):
            found = conn.execute(
                "SELECT 1 FROM graph_entities WHERE id = ?", (endpoint,)
            ).fetchone()
            if not found:
                raise ValueError(f"relation endpoint is not a declared entity: {endpoint}")
        existing = conn.execute(
            """
            SELECT id FROM graph_relations
            WHERE source_entity_id = ? AND target_entity_id = ? AND relation_type = ?
            """,
            (source_entity_id, target_entity_id, relation_type),
        ).fetchone()
        now = _now_iso()
        if existing:
            conn.execute(
                """
                UPDATE graph_relations
                   SET description = ?, assertion_source = ?, source_span_ids = ?,
                       confidence = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    description, assertion_source,
                    json.dumps(source_span_ids or []), confidence, now,
                    existing["id"],
                ),
            )
            return str(existing["id"])
        relation_id = _new_id("REL")
        conn.execute(
            """
            INSERT INTO graph_relations
                (id, source_entity_id, target_entity_id, relation_type, description,
                 assertion_source, source_span_ids, confidence, prompt_run_id,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relation_id, source_entity_id, target_entity_id, relation_type,
                description, assertion_source, json.dumps(source_span_ids or []),
                confidence, prompt_run_id, now, now,
            ),
        )
        return relation_id


def _decode_entity_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    data["knowledge_unit_ids"] = _loads_list(data.get("knowledge_unit_ids"))
    return data


def _decode_relation_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    return data


def get_graph_entity(db_path: Path, entity_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM graph_entities WHERE id = ?", (entity_id,)
        ).fetchone()
        return _decode_entity_row(row) if row else None


def find_graph_entities(db_path: Path, name_like: str, limit: int = 12) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM graph_entities WHERE canonical_name LIKE ? "
            "ORDER BY canonical_name LIMIT ?",
            (f"%{name_like}%", limit),
        ).fetchall()
        return [_decode_entity_row(row) for row in rows]


def relation_neighborhood(db_path: Path, entity_ids: list[str]) -> list[dict]:
    """Return relations touching any of the given entities (one hop)."""
    if not entity_ids:
        return []
    with connect(db_path) as conn:
        placeholders = ",".join("?" for _ in entity_ids)
        rows = conn.execute(
            f"""
            SELECT * FROM graph_relations
            WHERE source_entity_id IN ({placeholders})
               OR target_entity_id IN ({placeholders})
            """,
            tuple(entity_ids) + tuple(entity_ids),
        ).fetchall()
        return [_decode_relation_row(row) for row in rows]


# --- community_reports -----------------------------------------------


def upsert_community_report(
    db_path: Path,
    *,
    community_key: str,
    title: str,
    summary: str,
    full_content: str,
    dependency_hash: str,
    level: int = 0,
    findings: list | None = None,
    entity_ids: list[str] | None = None,
    relation_ids: list[str] | None = None,
    source_span_ids: list[str] | None = None,
    rank: float = 0.0,
    prompt_run_id: str | None = None,
) -> str:
    """Insert or replace the report for a community key."""
    now = _now_iso()
    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id, created_at FROM community_reports WHERE community_key = ?",
            (community_key,),
        ).fetchone()
        report_id = str(existing["id"]) if existing else _new_id("REP")
        created_at = str(existing["created_at"]) if existing else now
        conn.execute(
            """
            INSERT OR REPLACE INTO community_reports
                (id, community_key, level, title, summary, full_content,
                 finding_json, entity_ids, relation_ids, source_span_ids, rank,
                 prompt_run_id, dependency_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id, community_key, level, title, summary, full_content,
                json.dumps(findings or []), json.dumps(entity_ids or []),
                json.dumps(relation_ids or []), json.dumps(source_span_ids or []),
                rank, prompt_run_id, dependency_hash, created_at, now,
            ),
        )
        return report_id


def _decode_report_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["findings"] = _loads_list(data.pop("finding_json", "[]"))
    data["entity_ids"] = _loads_list(data.get("entity_ids"))
    data["relation_ids"] = _loads_list(data.get("relation_ids"))
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    return data


def list_community_reports(db_path: Path, *, level: int | None = None) -> list[dict]:
    with connect(db_path) as conn:
        if level is None:
            rows = conn.execute(
                "SELECT * FROM community_reports ORDER BY rank DESC, level"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM community_reports WHERE level = ? ORDER BY rank DESC",
                (level,),
            ).fetchall()
        return [_decode_report_row(row) for row in rows]


def get_community_report(db_path: Path, report_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM community_reports WHERE id = ?", (report_id,)
        ).fetchone()
        return _decode_report_row(row) if row else None


# --- memory_paths ----------------------------------------------------


def record_memory_path(
    db_path: Path,
    *,
    query_hash: str,
    route: str,
    path: list[dict],
    start_node_id: str = "",
    score: float = 0.0,
    source_span_ids: list[str] | None = None,
) -> str:
    with connect(db_path) as conn:
        path_id = _new_id("MPATH")
        conn.execute(
            """
            INSERT INTO memory_paths
                (id, query_hash, route, start_node_id, path_json, score,
                 source_span_ids, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                path_id, query_hash, route, start_node_id, json.dumps(path),
                score, json.dumps(source_span_ids or []), _now_iso(),
            ),
        )
        return path_id


def list_memory_paths(db_path: Path, query_hash: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM memory_paths WHERE query_hash = ? ORDER BY score DESC",
            (query_hash,),
        ).fetchall()
        out = []
        for row in rows:
            data = dict(row)
            data["path"] = _loads_list(data.pop("path_json", "[]"))
            data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
            out.append(data)
        return out


# --- prompt_runs -----------------------------------------------------


def record_prompt_run(
    db_path: Path,
    *,
    prompt_id: str,
    prompt_version: str,
    family: str,
    role: str = "",
    model_provider: str = "",
    model_name: str = "",
    input_hash: str,
    source_ids: list[int] | None = None,
    source_span_ids: list[str] | None = None,
    curate_spec_hash: str = "",
    query_trace_id: str | None = None,
) -> str:
    """Start a prompt run. Returns the PTR- trace id; status begins 'pending'."""
    with connect(db_path) as conn:
        trace_id = _new_id("PTR")
        conn.execute(
            """
            INSERT INTO prompt_runs
                (trace_id, prompt_id, prompt_version, family, role,
                 model_provider, model_name, input_hash, source_ids,
                 source_span_ids, curate_spec_hash, query_trace_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace_id, prompt_id, prompt_version, family, role,
                model_provider, model_name, input_hash,
                json.dumps(source_ids or []), json.dumps(source_span_ids or []),
                curate_spec_hash, query_trace_id, _now_iso(),
            ),
        )
        return trace_id


def finish_prompt_run(
    db_path: Path,
    trace_id: str,
    *,
    output_hash: str = "",
    validator_status: str = "ok",
    validator_errors: list[str] | None = None,
    retry_count: int = 0,
    latency_ms: int | None = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE prompt_runs
               SET output_hash = ?, validator_status = ?, validator_errors = ?,
                   retry_count = ?, latency_ms = ?, finished_at = ?
             WHERE trace_id = ?
            """,
            (
                output_hash, validator_status,
                json.dumps(validator_errors or []), retry_count, latency_ms,
                _now_iso(), trace_id,
            ),
        )


def _decode_prompt_run_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["validator_errors"] = _loads_list(data.get("validator_errors"))
    data["source_ids"] = _loads_list(data.get("source_ids"))
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    return data


def get_prompt_run(db_path: Path, trace_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM prompt_runs WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        return _decode_prompt_run_row(row) if row else None


def list_prompt_runs_for_query(db_path: Path, query_trace_id: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM prompt_runs WHERE query_trace_id = ? ORDER BY created_at",
            (query_trace_id,),
        ).fetchall()
        return [_decode_prompt_run_row(row) for row in rows]


# --- curation_plans --------------------------------------------------


def record_curation_plan(
    db_path: Path,
    *,
    workspace_id: str,
    curate_spec_hash: str,
    route: str,
    source_policy: dict,
    retrieval_policy: dict,
    workspace_path: str = "",
    project: str = "",
    prompt_profile: str = "",
    evidence_plan: dict | None = None,
    prompt_run_id: str | None = None,
) -> str:
    with connect(db_path) as conn:
        plan_id = _new_id("PLAN")
        conn.execute(
            """
            INSERT INTO curation_plans
                (id, workspace_id, workspace_path, project, curate_spec_hash,
                 route, source_policy_json, retrieval_policy_json, prompt_profile,
                 evidence_plan_json, prompt_run_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id, workspace_id, workspace_path, project, curate_spec_hash,
                route, json.dumps(source_policy), json.dumps(retrieval_policy),
                prompt_profile, json.dumps(evidence_plan or {}), prompt_run_id,
                _now_iso(),
            ),
        )
        return plan_id


def _decode_plan_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["source_policy"] = _loads_obj(data.pop("source_policy_json", "{}"))
    data["retrieval_policy"] = _loads_obj(data.pop("retrieval_policy_json", "{}"))
    data["evidence_plan"] = _loads_obj(data.pop("evidence_plan_json", "{}"))
    return data


def get_curation_plan(db_path: Path, workspace_id: str) -> dict | None:
    """Return the most recent curation plan for a workspace."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM curation_plans WHERE workspace_id = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (workspace_id,),
        ).fetchone()
        return _decode_plan_row(row) if row else None


# --- insight_candidates ----------------------------------------------


def create_insight_candidate(
    db_path: Path,
    *,
    classification: str,
    statement: str,
    workspace_id: str = "",
    source_event_id: str = "",
    evidence: list | None = None,
    affected_node_ids: list[str] | None = None,
    confidence: float = 0.0,
    status: str = "pending",
    prompt_run_id: str | None = None,
) -> str:
    now = _now_iso()
    with connect(db_path) as conn:
        ins_id = _new_id("INS")
        conn.execute(
            """
            INSERT INTO insight_candidates
                (id, workspace_id, source_event_id, classification, statement,
                 evidence_json, affected_node_ids, confidence, status,
                 prompt_run_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ins_id, workspace_id, source_event_id, classification, statement,
                json.dumps(evidence or []), json.dumps(affected_node_ids or []),
                confidence, status, prompt_run_id, now, now,
            ),
        )
        return ins_id


def _decode_insight_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["evidence"] = _loads_list(data.pop("evidence_json", "[]"))
    data["affected_node_ids"] = _loads_list(data.get("affected_node_ids"))
    return data


def list_insight_candidates(
    db_path: Path,
    *,
    workspace_id: str | None = None,
    status: str = "pending",
) -> list[dict]:
    clauses = []
    params: list[object] = []
    if workspace_id is not None:
        clauses.append("workspace_id = ?")
        params.append(workspace_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM insight_candidates{where} ORDER BY created_at DESC",
            tuple(params),
        ).fetchall()
        return [_decode_insight_row(row) for row in rows]


def get_insight_candidate(db_path: Path, insight_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM insight_candidates WHERE id = ?", (insight_id,)
        ).fetchone()
        return _decode_insight_row(row) if row else None


def update_insight_candidate_status(
    db_path: Path, insight_id: str, *, status: str
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE insight_candidates SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now_iso(), insight_id),
        )


# --- artifact_dependencies -------------------------------------------


def record_artifact_dependency(
    db_path: Path,
    *,
    artifact_id: str,
    artifact_type: str,
    depends_on_id: str,
    depends_on_type: str,
    dependency_hash: str,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO artifact_dependencies
                (artifact_id, artifact_type, depends_on_id, depends_on_type,
                 dependency_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id, artifact_type, depends_on_id, depends_on_type,
                dependency_hash, _now_iso(),
            ),
        )


def dependents_of(db_path: Path, depends_on_id: str) -> list[dict]:
    """Return artifacts that depend on the given record (for invalidation)."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM artifact_dependencies WHERE depends_on_id = ?",
            (depends_on_id,),
        ).fetchall()
        return [dict(row) for row in rows]


# --- synthesis_nodes (L4 shared synthesis) ---------------------------


def upsert_synthesis_node(
    db_path: Path,
    *,
    title: str,
    statement: str,
    dependency_hash: str,
    full_content: str = "",
    community_report_ids: list[str] | None = None,
    concept_ids: list[str] | None = None,
    source_span_ids: list[str] | None = None,
    confidence: float = 0.0,
    prompt_run_id: str | None = None,
    node_id: str | None = None,
) -> str:
    """Insert or replace a shared synthesis node (SYN-)."""
    now = _now_iso()
    with connect(db_path) as conn:
        existing = None
        if node_id:
            existing = conn.execute(
                "SELECT created_at FROM synthesis_nodes WHERE id = ?", (node_id,)
            ).fetchone()
        syn_id = node_id or _new_id("SYN")
        created_at = str(existing["created_at"]) if existing else now
        conn.execute(
            """
            INSERT OR REPLACE INTO synthesis_nodes
                (id, title, statement, full_content, community_report_ids,
                 concept_ids, source_span_ids, confidence, prompt_run_id,
                 dependency_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                syn_id, title, statement, full_content,
                json.dumps(community_report_ids or []), json.dumps(concept_ids or []),
                json.dumps(source_span_ids or []), confidence, prompt_run_id,
                dependency_hash, created_at, now,
            ),
        )
        return syn_id


def _decode_synthesis_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["community_report_ids"] = _loads_list(data.get("community_report_ids"))
    data["concept_ids"] = _loads_list(data.get("concept_ids"))
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    return data


def list_synthesis_nodes(db_path: Path) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM synthesis_nodes ORDER BY confidence DESC, created_at"
        ).fetchall()
        return [_decode_synthesis_row(row) for row in rows]


def get_synthesis_node(db_path: Path, node_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM synthesis_nodes WHERE id = ?", (node_id,)
        ).fetchone()
        return _decode_synthesis_row(row) if row else None


def clear_synthesis_nodes(db_path: Path) -> None:
    """Delete every synthesis node (the shared L4 layer is regenerated wholesale)."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM synthesis_nodes")


# ---------------------------------------------------------------------------
# v0.3.2 DB-native search accessors (SCHEMA §11.12–§11.16)
# ---------------------------------------------------------------------------


def upsert_search_document(
    db_path: Path,
    *,
    record_type: str,
    record_id: str,
    body: str,
    content_hash: str,
    dependency_hash: str,
    doc_id: str | None = None,
    source_id: int | None = None,
    projection_path: str = "",
    title: str = "",
    language: str = "",
    provenance: dict | None = None,
) -> str:
    """Insert/replace one row of the authoritative search corpus and re-index FTS."""
    did = doc_id or f"DOC-{record_type}-{record_id}"
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO search_documents
                (doc_id, record_type, record_id, source_id, projection_path, title,
                 body, language, content_hash, dependency_hash, provenance_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                did, record_type, record_id, source_id, projection_path, title,
                body, language, content_hash, dependency_hash,
                json.dumps(provenance or {}), _now_iso(),
            ),
        )
        for tbl in ("search_documents_fts", "search_documents_fts_tri"):
            conn.execute(f"DELETE FROM {tbl} WHERE doc_id = ?", (did,))
            conn.execute(
                f"INSERT INTO {tbl} (title, body, record_type, record_id, doc_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (title, body, record_type, record_id, did),
            )
    return did


def _decode_search_document(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["provenance"] = _loads_obj(data.pop("provenance_json", "{}"))
    return data


def get_search_document(db_path: Path, doc_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM search_documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        return _decode_search_document(row) if row else None


def list_search_documents(db_path: Path) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM search_documents ORDER BY doc_id").fetchall()
        return [_decode_search_document(r) for r in rows]


def delete_search_document(db_path: Path, doc_id: str) -> None:
    """Delete a search document (cascades chunks/embeddings) and its FTS rows."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM search_documents WHERE doc_id = ?", (doc_id,))
        for tbl in ("search_documents_fts", "search_documents_fts_tri"):
            conn.execute(f"DELETE FROM {tbl} WHERE doc_id = ?", (doc_id,))


def clear_search_corpus(db_path: Path) -> None:
    """Drop the entire derived search corpus (rebuilt by `wiki reindex`)."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM search_documents")  # cascades chunks → embeddings
        conn.execute("DELETE FROM search_documents_fts")
        conn.execute("DELETE FROM search_documents_fts_tri")


def fts_search(
    db_path: Path,
    match: str,
    *,
    trigram: bool = False,
    limit: int = 50,
) -> list[dict]:
    """BM25 lexical search over one FTS table. Lower bm25() = more relevant.

    Returns rows: doc_id, record_type, record_id, title, score (rank, ascending).
    """
    table = "search_documents_fts_tri" if trigram else "search_documents_fts"
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT doc_id, record_type, record_id, title, bm25({table}) AS score
            FROM {table}
            WHERE {table} MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (match, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_search_chunk(
    db_path: Path,
    *,
    chunk_id: str,
    doc_id: str,
    record_type: str,
    record_id: str,
    chunk_index: int,
    char_start: int,
    char_end: int,
    text: str,
    input_hash: str,
    source_span_ids: list[str] | None = None,
    provenance: dict | None = None,
) -> str:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO search_chunks
                (chunk_id, doc_id, record_type, record_id, chunk_index, char_start,
                 char_end, text, input_hash, source_span_ids, provenance_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id, doc_id, record_type, record_id, chunk_index, char_start,
                char_end, text, input_hash, json.dumps(source_span_ids or []),
                json.dumps(provenance or {}),
            ),
        )
    return chunk_id


def _decode_search_chunk(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    data["provenance"] = _loads_obj(data.pop("provenance_json", "{}"))
    return data


def list_search_chunks_for_doc(db_path: Path, doc_id: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM search_chunks WHERE doc_id = ? ORDER BY chunk_index", (doc_id,)
        ).fetchall()
        return [_decode_search_chunk(r) for r in rows]


def get_search_chunk(db_path: Path, chunk_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM search_chunks WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        return _decode_search_chunk(row) if row else None


def upsert_search_embedding(
    db_path: Path,
    *,
    chunk_id: str,
    provider: str,
    model: str,
    dim: int,
    vector: bytes,
    input_hash: str,
    dependency_hash: str,
    status: str = "ready",
    error: str = "",
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO search_embeddings
                (chunk_id, provider, model, dim, vector, input_hash, dependency_hash,
                 status, error, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chunk_id, provider, model, dim, vector, input_hash, dependency_hash,
             status, error, _now_iso()),
        )


def get_search_embeddings(db_path: Path, provider: str, model: str) -> list[dict]:
    """Return all ready embeddings for one provider/model (chunk_id, dim, vector)."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT chunk_id, dim, vector, input_hash, dependency_hash FROM search_embeddings "
            "WHERE provider = ? AND model = ? AND status = 'ready'",
            (provider, model),
        ).fetchall()
        return [dict(r) for r in rows]


def has_search_embeddings(db_path: Path, provider: str, model: str) -> bool:
    """Cheap probe: True if any ready embedding exists for this provider/model."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM search_embeddings WHERE provider = ? AND model = ? "
            "AND status = 'ready' LIMIT 1",
            (provider, model),
        ).fetchone()
        return row is not None


def get_index_meta(db_path: Path, key: str, default: str | None = None) -> str | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM search_index_meta WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row else default


def set_index_meta(db_path: Path, key: str, value: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO search_index_meta (key, value) VALUES (?, ?)",
            (key, value),
        )


def insert_query_trace(
    db_path: Path,
    *,
    route: str,
    question_hash: str,
    workspace_id: str = "default",
    route_reason: str = "",
    evidence: list | None = None,
    source_span_ids: list[str] | None = None,
    community_report_ids: list[str] | None = None,
    synthesis_node_ids: list[str] | None = None,
    memory_path_ids: list[str] | None = None,
    prompt_trace_ids: list[str] | None = None,
    insight_candidate_ids: list[str] | None = None,
    retrieval_trace: dict | None = None,
    warnings: list[str] | None = None,
    latency_ms: int | None = None,
    trace_id: str | None = None,
) -> str:
    """Persist a durable QTR- query trace. Returns the trace_id."""
    tid = trace_id or _new_id("QTR")
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO query_traces
                (trace_id, workspace_id, question_hash, route, route_reason,
                 evidence_json, source_span_ids, community_report_ids,
                 synthesis_node_ids, memory_path_ids, prompt_trace_ids,
                 insight_candidate_ids, retrieval_trace_json, warnings_json,
                 latency_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tid, workspace_id, question_hash, route, route_reason,
                json.dumps(evidence or []), json.dumps(source_span_ids or []),
                json.dumps(community_report_ids or []), json.dumps(synthesis_node_ids or []),
                json.dumps(memory_path_ids or []), json.dumps(prompt_trace_ids or []),
                json.dumps(insight_candidate_ids or []), json.dumps(retrieval_trace or {}),
                json.dumps(warnings or []), latency_ms, _now_iso(),
            ),
        )
    return tid


def _decode_query_trace(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["evidence"] = _loads_list(data.pop("evidence_json", "[]"))
    for key in (
        "source_span_ids", "community_report_ids", "synthesis_node_ids",
        "memory_path_ids", "prompt_trace_ids", "insight_candidate_ids",
    ):
        data[key] = _loads_list(data.get(key))
    data["retrieval_trace"] = _loads_obj(data.pop("retrieval_trace_json", "{}"))
    data["warnings"] = _loads_list(data.pop("warnings_json", "[]"))
    return data


def list_query_traces(
    db_path: Path, workspace_id: str | None = None, limit: int = 50
) -> list[dict]:
    with connect(db_path) as conn:
        if workspace_id:
            rows = conn.execute(
                "SELECT * FROM query_traces WHERE workspace_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (workspace_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM query_traces ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_decode_query_trace(r) for r in rows]


def get_query_trace(db_path: Path, trace_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM query_traces WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        return _decode_query_trace(row) if row else None
