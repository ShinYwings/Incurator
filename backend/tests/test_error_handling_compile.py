"""XC-1 slice 1: error-handling for pipeline/compile.py best-effort hydration.

``hydrate_spans`` must omit (not crash on) spans whose source is missing or
unparseable, and now log the omission instead of swallowing it silently.
"""

import logging

from curator import config as cfg
from curator import db
from curator.pipeline import compile as compile_mod


def test_hydrate_spans_omits_unavailable_source_and_logs(tmp_path, caplog):
    paths = cfg.WikiPaths(tmp_path)
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, l1_status) "
            "VALUES (?, ?, ?, ?, datetime('now'), 'done')",
            ("04_Resources/missing.md", "h", "md", 1),
        )
    span_id = db.upsert_source_span(
        paths.state_db,
        source_id=1,
        relpath="04_Resources/missing.md",  # file intentionally does not exist
        span_type="section",
        content_hash="deadbeef",
        page_number=None,
        section_title="X",
        toc_id=None,
        text_preview="preview",
    )

    with caplog.at_level(logging.DEBUG, logger="curator.pipeline.compile"):
        out = compile_mod.hydrate_spans(paths.state_db, [span_id])

    assert out == {}  # unavailable source omitted, not crashed
    assert any("hydration skipped" in r.message for r in caplog.records)
