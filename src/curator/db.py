"""SQLite state database for ingest history, dedupe, and metadata.

This is the *internal* state DB. It's separate from the QMD search index (which
QMD manages itself in Stage 4). This DB tracks:

- which files have been ingested (by content hash, for dedupe)
- when they were ingested
- which wiki pages were created/updated as a result
- ingest run history
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 1

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
    error_reason    TEXT                     -- empty_file|parse_error|llm_error — set when status='error'
);

CREATE INDEX IF NOT EXISTS idx_sources_hash   ON sources(content_hash);
CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);
CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain);

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
    source_id       INTEGER NOT NULL,
    state           TEXT NOT NULL DEFAULT 'queued',  -- queued|running|done|failed|interrupted
    phase           TEXT,                    -- latest phase label
    progress        REAL DEFAULT 0.0,        -- 0.0..1.0
    pages_created   INTEGER DEFAULT 0,
    pages_updated   INTEGER DEFAULT 0,
    error           TEXT,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT,
    FOREIGN KEY (source_id) REFERENCES sources(id)
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
    claim_type              TEXT NOT NULL,           -- fact|equation|theoretical_constraint
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
    id                      TEXT PRIMARY KEY,        -- EXH-[UUID8]
    topic                   TEXT NOT NULL DEFAULT '', -- exhibition topic name
    core_concepts           TEXT NOT NULL DEFAULT '', -- JSON array of CON-UUIDs
    confidence_score        REAL NOT NULL,           -- 0.00–1.00
    requires_math_rigor     INTEGER DEFAULT 0,       -- boolean 0|1
    last_updated            TEXT NOT NULL            -- ISO timestamp
);

CREATE INDEX IF NOT EXISTS idx_synthesis_confidence ON synthesis(confidence_score);
"""


def init_db(db_path: Path) -> None:
    """Create the state database and apply the schema. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
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



@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Context-managed connection with row factory and foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_stats(db_path: Path) -> dict:
    """Quick stats for `wiki status`."""
    if not db_path.exists():
        return {"sources_total": 0, "sources_curated": 0, "ingest_runs": 0}
    with connect(db_path) as conn:
        sources_total = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        sources_curated = conn.execute(
            "SELECT COUNT(*) FROM sources WHERE status = 'curated'"
        ).fetchone()[0]
        ingest_runs = conn.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0]
    return {
        "sources_total": sources_total,
        "sources_curated": sources_curated,
        "ingest_runs": ingest_runs,
    }


def get_pending_count(db_path: Path) -> int:
    """Count sources with status 'pending' or 'force_pending'."""
    if not db_path.exists():
        return 0
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM sources WHERE status IN ('pending', 'force_pending')"
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
