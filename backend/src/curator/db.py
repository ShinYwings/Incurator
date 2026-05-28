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
