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
from typing import Any, Iterator

SCHEMA_VERSION = 3

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
    source_id       INTEGER NOT NULL,
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
    id                      TEXT PRIMARY KEY,        -- EXH-[UUID8]
    topic                   TEXT NOT NULL DEFAULT '', -- exhibition topic name
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
    to_id       TEXT NOT NULL,      -- ATM-xxx | CON-xxx | EXH-xxx
    edge_type   TEXT NOT NULL,
    -- 'extracted_from'  : CTX → ATM  (L1 → L2)
    -- 'clustered_to'    : ATM → CON  (L2 → L3)
    -- 'synthesized_to'  : CON → EXH  (L3 → L4)
    source_id   INTEGER REFERENCES sources(id),
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dag_edges_from ON dag_edges(from_id);
CREATE INDEX IF NOT EXISTS idx_dag_edges_to   ON dag_edges(to_id);
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


def init_db(db_path: Path) -> None:
    """Create the state database and apply the schema. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
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



@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Context-managed connection with row factory and foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    _apply_migrations(conn)
    try:
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
            "SELECT COUNT(*) FROM sources WHERE l1_status = 'done'"
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
    """Create or reuse a queued/running ingest job for a source and job type."""
    with connect(db_path) as conn:
        existing = conn.execute(
            """
            SELECT id FROM ingest_jobs
            WHERE source_id = ? AND job_type = ? AND state IN ('queued', 'running')
            ORDER BY id DESC LIMIT 1
            """,
            (source_id, job_type),
        ).fetchone()
        if existing:
            return int(existing["id"])
        cur = conn.execute(
            """
            INSERT INTO ingest_jobs
                (source_id, job_type, trigger, node_id, state, phase, progress,
                 progress_current, progress_total, source_name, created_at)
            VALUES (?, ?, ?, ?, 'queued', ?, 0.0, 0, 0, ?, ?)
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
            """
            SELECT * FROM ingest_jobs
            WHERE source_id = ? AND state IN ('queued', 'running')
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
    order = "ASC" if states and any(s in {"queued", "running"} for s in states) else "DESC"
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
            """
            SELECT * FROM ingest_jobs
            WHERE state = 'queued'
            ORDER BY id ASC LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            """
            UPDATE ingest_jobs
            SET state = 'running', phase = 'running', started_at = ?, error = NULL
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
            """
            UPDATE ingest_jobs
            SET state = 'queued', phase = 'recovered', error = NULL
            WHERE state = 'running'
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
            """
            UPDATE ingest_jobs
            SET state = 'done', phase = 'done', progress = 1.0,
                finished_at = ?, pages_created = ?, pages_updated = ?, error = NULL
            WHERE id = ?
            """,
            (_now_iso(), pages_created, pages_updated, job_id),
        )


def mark_job_failed(db_path: Path, job_id: int, error: str) -> None:
    """Mark a job as failed."""
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE ingest_jobs
            SET state = 'failed', phase = 'failed', finished_at = ?, error = ?
            WHERE id = ?
            """,
            (_now_iso(), error[:2000], job_id),
        )


def requeue_job_for_retry(db_path: Path, job_id: int, retry_count: int, error: str) -> None:
    """Reset a failed job back to queued for retry, recording the attempt count."""
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE ingest_jobs
            SET state = 'queued', phase = 'retry', progress = 0.0,
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
            "SELECT COUNT(*) FROM ingest_jobs WHERE job_type = 'l2_atoms' AND state IN ('queued', 'running')"
        ).fetchone()
        return int(row[0]) if row else 0


def get_jobs_done_today(db_path: Path) -> list[dict]:
    """Return jobs completed today (UTC date), newest first."""
    if not db_path.exists():
        return []
    today_prefix = _now_iso()[:10]  # "YYYY-MM-DD"
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM ingest_jobs WHERE state = 'done' AND finished_at LIKE ? ORDER BY id DESC",
            (f"{today_prefix}%",),
        ).fetchall()
        return [dict(r) for r in rows]


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
    relpath = relpath or source_path_to_relpath(root, source_path)
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
                   OR import_origin = ?
                   OR logical_source_id = ?
                """,
                (relpath, relpath, relpath, relpath),
            ).fetchone()
        else:
            row = None
    return dict(row) if row else None
