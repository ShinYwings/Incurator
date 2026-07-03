"""SQLite state database for ingest history, dedupe, and metadata.

This is the *internal* state DB. It also owns DB-native search state. This DB tracks:

- which files have been ingested (by content hash, for dedupe)
- when they were ingested
- which wiki pages were created/updated as a result
- ingest run history
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .. import constants as consts

SCHEMA_VERSION = 11

# --- Plan C (v0.9.0, SCHEMA §21.1/§21.2) frozen resolution enums -------------
# Entity-resolution lifecycle (entity_aliases.resolution_status, §21.1).
RESOLUTION_STATUS_CODES = frozenset(
    {
        "alias",
        "ambiguous_candidate",
        "merge_proposed",
        "accepted",
        "rejected",
        "reversed",
    }
)
# Merge-decision lifecycle (entity_merge_proposals.decision, §21.2).
MERGE_DECISION_CODES = frozenset({"proposed", "accepted", "rejected", "reversed"})
# Frozen relation quarantine reason codes (graph_relations.quarantine_reason,
# §21.6). There is DELIBERATELY no `duplicate_proposition`: a relation's identity
# IS its canonical proposition, so re-assertion AGGREGATES support (§21.5) rather
# than creating a duplicate row to quarantine. The support-side outcome is a total
# partition by independent-source-lineage count (0 -> unsupported, exactly 1 ->
# copied_source_only, >=2 -> active), plus the structural reasons self_loop,
# contradiction, bridge_risk, and endpoint_unresolved.
QUARANTINE_REASON_CODES = frozenset(
    {
        "unsupported",
        "self_loop",
        "contradiction",
        "copied_source_only",
        "bridge_risk",
        "endpoint_unresolved",
    }
)
# Re-evaluation triggers paired with each quarantine reason (§21.6: every
# quarantined relation carries a reason code AND a reeval_trigger describing what
# would re-admit it; quarantine is inspectable and re-evaluable, never an opaque
# discard pile, Arena decision 8).
_QUARANTINE_REEVAL_TRIGGERS = {
    "unsupported": "support_added",
    "self_loop": "endpoints_distinct",
    "contradiction": "contradiction_cleared",
    "copied_source_only": "independent_support_added",
    "bridge_risk": "topology_corroborated",
    "endpoint_unresolved": "endpoint_resolved",
}
# Corroboration threshold (§21.5/§27.2): a relation is `active` only with >=2
# DISTINCT verified source lineages. Exactly 1 is a single uncorroborated source
# (copied_source_only); 0 is unsupported.
_RELATION_CORROBORATION_THRESHOLD = 2

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
    import_origin_ref TEXT,                  -- portable @root_key/relative origin
    import_policy   TEXT,                    -- import policy used, e.g. mirror_03_to_04
    external_ref    TEXT,                    -- portable @root_key/relative locator
    is_reference    INTEGER NOT NULL DEFAULT 0, -- 1=external reference, 0=vault-local copy
    logical_source_id TEXT,                  -- stable source identity across path/hash drift
    error_reason    TEXT,                    -- empty_file|parse_error|llm_error — set when status='error'
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_sources_hash   ON sources(content_hash);
CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);
CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain);
CREATE INDEX IF NOT EXISTS idx_sources_logical_source_id ON sources(logical_source_id);

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

-- v0.22.0: device-local cache of VLM page transcriptions (SYSTEM_BEHAVIOR §26.2a).
-- Keyed by (rendered-image hash, resolved model) so switching vision_model in the
-- Dashboard invalidates stale extractions (R12). Never exported (device-local).
CREATE TABLE IF NOT EXISTS vision_page_cache (
    image_hash      TEXT NOT NULL,           -- sha256[:16] of the rendered page PNG
    model           TEXT NOT NULL,           -- resolved provider::model
    latex           TEXT NOT NULL,           -- normalized transcription
    created_at      TEXT NOT NULL,
    PRIMARY KEY (image_hash, model)
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
    updated_at         TEXT NOT NULL,
    -- Plan C (v0.9.0, SCHEMA §21.4) merge-redirect columns.
    resolution_state      TEXT NOT NULL DEFAULT 'canonical',  -- canonical | redirected
    redirect_to_entity_id TEXT,                               -- ENT- canonical survivor when redirected
    decision_id           TEXT                                -- DEC- merge decision that redirected this row
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
    updated_at        TEXT NOT NULL,
    -- Plan C (v0.9.0, SCHEMA §21.6) lifecycle / edge-class / topology columns.
    lifecycle_status  TEXT NOT NULL DEFAULT 'provisional',  -- active | provisional | quarantined | retired
    quarantine_reason TEXT NOT NULL DEFAULT '',
    edge_class        TEXT NOT NULL DEFAULT 'extracted',    -- authored | extracted
    topology_weight   REAL NOT NULL DEFAULT 0.0,
    reeval_trigger    TEXT NOT NULL DEFAULT '',
    generation_id     TEXT                                  -- GEN- that produced/revalidated
);
CREATE INDEX IF NOT EXISTS idx_graph_relations_src ON graph_relations(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_graph_relations_tgt ON graph_relations(target_entity_id);
-- idx_graph_relations_lifecycle is created in _migrate_v9_graph_quality (after the
-- lifecycle_status column is added), so a pre-existing v8 graph_relations table is
-- not indexed on a column this IF NOT EXISTS CREATE TABLE does not add.

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
    updated_at      TEXT NOT NULL,
    -- Plan C (v0.9.0, SCHEMA §21.7) community-identity / hierarchy columns.
    parent_community_key TEXT,                       -- hierarchy parent; NULL at top level
    config_hash          TEXT NOT NULL DEFAULT '',   -- algorithm+seed+threshold config identity
    member_hash          TEXT NOT NULL DEFAULT '',   -- hash of sorted active member entity ids
    support_hash         TEXT NOT NULL DEFAULT '',   -- hash of the eligible active-support set
    retired_at           TEXT                        -- ISO 8601 UTC; non-NULL = retired stale community
);
CREATE INDEX IF NOT EXISTS idx_community_reports_key ON community_reports(community_key);
-- idx_community_reports_parent is created in _migrate_v9_graph_quality (after the
-- parent_community_key column is added), for the same reason as the lifecycle index.

-- Plan C (v0.9.0, SCHEMA §21.1) entity surface-form aliases. Surrogate `id` PK so
-- one normalized surface form may resolve to MANY distinct entities (homonyms).
CREATE TABLE IF NOT EXISTS entity_aliases (
    id                 TEXT PRIMARY KEY,     -- ALI-<UUID8> surrogate key
    alias_normalized   TEXT NOT NULL,        -- deterministic normalization (candidate key, NOT unique alone)
    entity_id          TEXT,                 -- ENT- this alias resolves to; NULL while only a candidate
    alias_display      TEXT NOT NULL,        -- original surface form as written
    source_span_ids    TEXT NOT NULL DEFAULT '[]',
    knowledge_unit_ids TEXT NOT NULL DEFAULT '[]',
    confidence         REAL NOT NULL DEFAULT 0.0,
    resolution_status  TEXT NOT NULL,        -- §21.1 enum (RESOLUTION_STATUS_CODES)
    resolution_reason  TEXT NOT NULL DEFAULT '',
    decision_id        TEXT,                 -- entity_merge_proposals.id that decided this alias
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity ON entity_aliases(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_normalized ON entity_aliases(alias_normalized);
-- A RESOLVED alias is unique per (surface form, entity, status): admits one normalized
-- surface resolving to several entities (homonyms) while blocking an exact duplicate
-- resolved row. Unresolved candidates (entity_id IS NULL) are keyed only by `id`.
CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_aliases_resolved
    ON entity_aliases(alias_normalized, entity_id, resolution_status)
    WHERE entity_id IS NOT NULL;

-- Plan C (v0.9.0, SCHEMA §21.2) entity merge proposals/decisions.
CREATE TABLE IF NOT EXISTS entity_merge_proposals (
    id               TEXT PRIMARY KEY,       -- DEC-<UUID8>
    source_entity_id TEXT NOT NULL,          -- ENT- being merged away (origin)
    target_entity_id TEXT NOT NULL,          -- ENT- surviving canonical
    decision         TEXT NOT NULL,          -- §21.2 enum (MERGE_DECISION_CODES)
    rationale        TEXT NOT NULL,
    evidence_json    TEXT NOT NULL,          -- JSON: candidate signals, guard checks, span/claim evidence
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entity_merge_proposals_src ON entity_merge_proposals(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_merge_proposals_tgt ON entity_merge_proposals(target_entity_id);

-- Plan C (v0.9.0, SCHEMA §21.3) reversible merge rewrite lineage.
CREATE TABLE IF NOT EXISTS entity_resolution_lineage (
    decision_id         TEXT NOT NULL,       -- entity_merge_proposals.id
    origin_entity_id    TEXT NOT NULL,       -- ENT- as it existed before the merge
    canonical_entity_id TEXT NOT NULL,       -- ENT- it was redirected into
    rewrite_json        TEXT NOT NULL,       -- JSON: pre-merge entity row + every rewrite applied
    PRIMARY KEY (decision_id, origin_entity_id)
);

-- Plan C (v0.9.0, SCHEMA §21.5) independent claim-level relation supports.
CREATE TABLE IF NOT EXISTS graph_relation_supports (
    relation_id         TEXT NOT NULL,       -- REL-
    knowledge_unit_id   TEXT NOT NULL,       -- KNU- asserting this relation
    source_span_ids     TEXT NOT NULL,       -- JSON array of SPAN- ids carrying the assertion
    assertion_source    TEXT NOT NULL,       -- source_states | system_infers | workspace_derives
    confidence          REAL NOT NULL,
    support_status      TEXT NOT NULL,       -- unchecked | verified | failed | stale
    support_hash        TEXT NOT NULL,       -- content hash of (proposition + cited spans); dedup within a relation
    source_lineage_hash TEXT NOT NULL,       -- hash of logical source lineage; the INDEPENDENCE key
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY (relation_id, knowledge_unit_id, support_hash)
);
CREATE INDEX IF NOT EXISTS idx_graph_relation_supports_rel ON graph_relation_supports(relation_id);
CREATE INDEX IF NOT EXISTS idx_graph_relation_supports_lineage ON graph_relation_supports(source_lineage_hash);

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

-- v0.3.2 DB-native search. See SCHEMA §11.12–§11.16.
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
        'claim_supports','compiler_generations',
        'entity_aliases','entity_merge_proposals','entity_resolution_lineage',
        'graph_relation_supports'
    ))
);
CREATE INDEX IF NOT EXISTS idx_deleted_records_at ON deleted_records(deleted_at);

-- Checkpoint records for L2 extraction resume. Each row records one
-- successfully persisted batch (by its deterministic content hash) so that
-- on retry only unfinished batches are re-sent to the LLM.
CREATE TABLE IF NOT EXISTS l2_checkpoints (
    source_id  INTEGER NOT NULL,
    batch_hash TEXT    NOT NULL,
    PRIMARY KEY (source_id, batch_hash)
);
"""


def _now_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Keep `IN (?, ?, …)` parameter counts well under SQLite's
# SQLITE_MAX_VARIABLE_NUMBER (999 on older builds) so large sources (many spans)
# do not crash bulk span queries.
_SQL_VAR_CHUNK = 900


def _chunked(seq: list, size: int = _SQL_VAR_CHUNK):
    """Yield successive ``size``-length slices of ``seq``."""
    for start in range(0, len(seq), size):
        yield seq[start:start + size]


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
    source_columns = _column_names(conn, "sources")
    if "external_ref" not in source_columns:
        _add_column_if_missing(conn, "sources", "import_origin", "import_origin TEXT")
        _add_column_if_missing(conn, "sources", "external_path", "external_path TEXT")
    _add_column_if_missing(conn, "sources", "last_ingested", "last_ingested TEXT")
    _add_column_if_missing(conn, "sources", "context_id", "context_id TEXT")
    for layer in ("l1", "l2", "l3", "l4"):
        _add_column_if_missing(
            conn,
            "sources",
            f"{layer}_status",
            f"{layer}_status TEXT NOT NULL DEFAULT 'pending'",
        )
    _add_column_if_missing(conn, "sources", "layer_error", "layer_error TEXT")
    _add_column_if_missing(conn, "sources", "domain", "domain TEXT")
    _add_column_if_missing(conn, "sources", "tags", "tags TEXT")
    _add_column_if_missing(conn, "sources", "import_policy", "import_policy TEXT")
    _add_column_if_missing(
        conn,
        "sources",
        "is_reference",
        "is_reference INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(conn, "sources", "logical_source_id", "logical_source_id TEXT")
    _add_column_if_missing(conn, "sources", "error_reason", "error_reason TEXT")
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

    _migrate_v10_portable_sources(conn)
    _add_column_if_missing(conn, "sources", "updated_at", "updated_at TEXT")
    needs_source_revision_backfill = conn.execute(
        "SELECT 1 FROM sources WHERE updated_at IS NULL OR updated_at = '' LIMIT 1"
    ).fetchone()
    if needs_source_revision_backfill is not None:
        conn.execute(
            """
            UPDATE sources
            SET updated_at = CASE
                WHEN length(COALESCE(last_ingested, added_at, '')) = 20
                THEN substr(COALESCE(last_ingested, added_at), 1, 19) || '.000Z'
                ELSE COALESCE(last_ingested, added_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            END
            WHERE updated_at IS NULL OR updated_at = ''
            """
        )
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS sources_touch_updated_at
        AFTER UPDATE ON sources
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
            UPDATE sources
            SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = NEW.id;
        END;
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sources_logical_source_id "
        "ON sources(logical_source_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sources_external_ref "
        "ON sources(external_ref)"
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
    _migrate_v9_graph_quality(conn, tables)
    if "schema_version" in tables:
        version_row = conn.execute(
            "SELECT version FROM schema_version LIMIT 1"
        ).fetchone()
        if version_row is not None and int(version_row[0]) != SCHEMA_VERSION:
            conn.execute(
                "UPDATE schema_version SET version = ?",
                (SCHEMA_VERSION,),
            )


def _migrate_v10_portable_sources(conn: sqlite3.Connection) -> None:
    """Replace legacy absolute-path source columns with portable refs.

    Rows containing absolute legacy locators require the explicit config-aware
    migration service. Empty/non-absolute legacy columns can be rebuilt safely
    during normal schema initialization.
    """
    columns = _column_names(conn, "sources")
    if {"external_ref", "import_origin_ref"} <= columns:
        return
    if "external_path" not in columns or "import_origin" not in columns:
        return
    absolute = conn.execute(
        """
        SELECT id FROM sources
        WHERE relpath LIKE '/%'
           OR external_path LIKE '/%'
           OR import_origin LIKE '/%'
           OR external_path GLOB '[A-Za-z]:[\\/]*'
           OR import_origin GLOB '[A-Za-z]:[\\/]*'
        LIMIT 1
        """
    ).fetchone()
    if absolute is not None:
        raise RuntimeError(
            "portable path migration required; run `wiki paths migrate --apply`"
        )

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(
        """
        DROP INDEX IF EXISTS idx_sources_external_path;
        CREATE TABLE sources_v10 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            relpath TEXT NOT NULL UNIQUE,
            content_hash TEXT NOT NULL,
            file_type TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            added_at TEXT NOT NULL,
            last_ingested TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            context_id TEXT,
            l1_status TEXT NOT NULL DEFAULT 'pending',
            l2_status TEXT NOT NULL DEFAULT 'pending',
            l3_status TEXT NOT NULL DEFAULT 'pending',
            l4_status TEXT NOT NULL DEFAULT 'pending',
            layer_error TEXT,
            domain TEXT,
            tags TEXT,
            import_origin_ref TEXT,
            import_policy TEXT,
            external_ref TEXT,
            is_reference INTEGER NOT NULL DEFAULT 0,
            logical_source_id TEXT,
            error_reason TEXT,
            updated_at TEXT
        );
        INSERT INTO sources_v10 (
            id, relpath, content_hash, file_type, bytes, added_at,
            last_ingested, status, context_id,
            l1_status, l2_status, l3_status, l4_status,
            layer_error, domain, tags, import_origin_ref, import_policy,
            external_ref, is_reference, logical_source_id, error_reason, updated_at
        )
        SELECT
            id, relpath, content_hash, file_type, bytes, added_at,
            last_ingested, status, context_id,
            l1_status, l2_status, l3_status, l4_status,
            layer_error, domain, tags, NULLIF(import_origin, ''), import_policy,
            NULLIF(external_path, ''), is_reference, logical_source_id, error_reason,
            CASE
                WHEN length(COALESCE(last_ingested, added_at, '')) = 20
                THEN substr(COALESCE(last_ingested, added_at), 1, 19) || '.000Z'
                ELSE COALESCE(last_ingested, added_at)
            END
        FROM sources;
        DROP TABLE sources;
        ALTER TABLE sources_v10 RENAME TO sources;
        CREATE INDEX idx_sources_hash ON sources(content_hash);
        CREATE INDEX idx_sources_status ON sources(status);
        CREATE INDEX idx_sources_domain ON sources(domain);
        CREATE INDEX idx_sources_logical_source_id ON sources(logical_source_id);
        CREATE INDEX idx_sources_external_ref ON sources(external_ref);
        """
    )
    conn.execute("PRAGMA foreign_keys = ON")



def _migrate_generation_backfill(
    conn: sqlite3.Connection, tables: set[str]
) -> None:
    """Plan B2 (data-only): attribute legacy verified units that have no
    `generation_id` to a deterministic synthetic authoritative generation per
    source, so generation-scoped visibility (§26.3) has no permanent NULL escape
    hatch. Runs on the explicit ``init_db`` path (not every ``connect``) so it is
    a one-time cleanup of pre-B2 vaults, never a mid-session side effect; new
    units are attributed to a generation by the compiler. Idempotent (a no-op
    once every verified unit is attributed); deterministic ids converge across
    devices.
    """
    if "knowledge_units" not in tables or "compiler_generations" not in tables:
        return
    rows = conn.execute(
        "SELECT source_id, id FROM knowledge_units "
        "WHERE generation_id IS NULL AND retired_at IS NULL AND support_status = 'verified'"
    ).fetchall()
    by_source: dict[Any, list[str]] = {}
    for r in rows:
        by_source.setdefault(r[0], []).append(str(r[1]))
    now = _now_iso()
    for source_id, unit_ids in by_source.items():
        # Attribute to an existing authoritative generation for this source if one
        # exists; otherwise mint the deterministic synthetic migration generation.
        if source_id is None:
            existing = conn.execute(
                "SELECT id FROM compiler_generations "
                "WHERE source_id IS NULL AND status = 'authoritative' LIMIT 1"
            ).fetchone()
            chash = ""
        else:
            existing = conn.execute(
                "SELECT id FROM compiler_generations "
                "WHERE source_id = ? AND status = 'authoritative' LIMIT 1",
                (source_id,),
            ).fetchone()
            src = conn.execute(
                "SELECT content_hash FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
            chash = src[0] if src else ""
        if existing is not None:
            gen_id = str(existing[0])
        else:
            gen_id = f"GEN-mig-{source_id if source_id is not None else 'global'}"
            audit = json.dumps(
                {"content_hash": chash, "unit_ids": sorted(unit_ids),
                 "unit_count": len(unit_ids), "migrated": True},
                sort_keys=True,
            )
            conn.execute(
                "INSERT INTO compiler_generations (id, source_id, status, "
                "prompt_contract_version, created_at, published_at, audit_json) "
                "VALUES (?, ?, 'authoritative', 'migrated', ?, ?, ?)",
                (gen_id, source_id, now, now, audit),
            )
        for start in range(0, len(unit_ids), 900):
            chunk = unit_ids[start:start + 900]
            placeholders = ",".join("?" for _ in chunk)
            conn.execute(
                f"UPDATE knowledge_units SET generation_id = ? WHERE id IN ({placeholders})",
                (gen_id, *chunk),
            )


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



def _migrate_v9_graph_quality(
    conn: sqlite3.Connection, tables: set[str]
) -> None:
    """SCHEMA_VERSION 8 -> 9 (Plan C): additive entity/relation resolution,
    independent claim-level support, and community-identity schema (SCHEMA §21.8 /
    SYSTEM_BEHAVIOR §27.7). Forward-only and idempotent.

    The four new tables (`entity_aliases`, `entity_merge_proposals`,
    `entity_resolution_lineage`, `graph_relation_supports`) are created by the
    base ``SCHEMA_SQL`` executescript that always runs before this function. This
    migration adds the §21.4/§21.6/§21.7 ALTER columns to the pre-existing
    `graph_entities`/`graph_relations`/`community_reports` tables (which the
    ``CREATE TABLE IF NOT EXISTS`` in SCHEMA_SQL does NOT alter) and the indexes
    that depend on those new columns.

    Backfill INFERS NOTHING (§27.7 item 2): the ADD COLUMN ... DEFAULT statements
    set every legacy `graph_entities` row to `resolution_state='canonical'`
    (`redirect_to_entity_id` NULL) and every legacy `graph_relations` row to
    `lifecycle_status='provisional'`, `edge_class='extracted'`, `generation_id`
    NULL. No alias/proposal/lineage/support rows are created and no relation is
    auto-promoted to `active` — relations become `active` only after rebuild from
    the authoritative B claim generation.
    """
    if "graph_entities" in tables:
        _add_column_if_missing(
            conn, "graph_entities", "resolution_state",
            "resolution_state TEXT NOT NULL DEFAULT 'canonical'",
        )
        _add_column_if_missing(
            conn, "graph_entities", "redirect_to_entity_id",
            "redirect_to_entity_id TEXT",
        )
        _add_column_if_missing(
            conn, "graph_entities", "decision_id", "decision_id TEXT"
        )
    if "graph_relations" in tables:
        _add_column_if_missing(
            conn, "graph_relations", "lifecycle_status",
            "lifecycle_status TEXT NOT NULL DEFAULT 'provisional'",
        )
        _add_column_if_missing(
            conn, "graph_relations", "quarantine_reason",
            "quarantine_reason TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn, "graph_relations", "edge_class",
            "edge_class TEXT NOT NULL DEFAULT 'extracted'",
        )
        _add_column_if_missing(
            conn, "graph_relations", "topology_weight",
            "topology_weight REAL NOT NULL DEFAULT 0.0",
        )
        _add_column_if_missing(
            conn, "graph_relations", "reeval_trigger",
            "reeval_trigger TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn, "graph_relations", "generation_id", "generation_id TEXT"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_graph_relations_lifecycle "
            "ON graph_relations(lifecycle_status)"
        )
    if "community_reports" in tables:
        _add_column_if_missing(
            conn, "community_reports", "parent_community_key",
            "parent_community_key TEXT",
        )
        _add_column_if_missing(
            conn, "community_reports", "config_hash",
            "config_hash TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn, "community_reports", "member_hash",
            "member_hash TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn, "community_reports", "support_hash",
            "support_hash TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn, "community_reports", "retired_at", "retired_at TEXT"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_community_reports_parent "
            "ON community_reports(parent_community_key)"
        )

    # Extend the deleted_records CHECK list so the four new canonical tables can be
    # tombstoned on a migrated (old) DB. SQLite cannot ALTER a CHECK in place, so
    # rebuild the table only when its CHECK predates Plan C.
    if "deleted_records" in tables:
        ddl_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='deleted_records'"
        ).fetchone()
        if ddl_row and "entity_aliases" not in str(ddl_row[0]):
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
                        'claim_supports','compiler_generations',
                        'entity_aliases','entity_merge_proposals',
                        'entity_resolution_lineage','graph_relation_supports'
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
        # One-time data cleanup of pre-B2 vaults (NOT in connect()'s hot path):
        # attribute legacy verified NULL-generation units to a synthetic
        # authoritative generation (SYSTEM_BEHAVIOR §26.3).
        _tables = {
            str(r[0]) for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        _migrate_generation_backfill(conn, _tables)
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


@contextmanager
def _maybe_conn(
    db_path: Path, conn: sqlite3.Connection | None
) -> Iterator[sqlite3.Connection]:
    """Yield ``conn`` when provided (the caller owns the transaction — no commit
    here), else open a fresh :func:`connect` block. Lets compiler helpers run
    inside ONE caller-controlled transaction so a multi-step publish is atomic
    (SYSTEM_BEHAVIOR §26.3): any exception rolls the whole transaction back."""
    if conn is not None:
        yield conn
    else:
        with connect(db_path) as owned:
            yield owned


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
