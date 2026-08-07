"""`wiki lint` reports unreadable regions (SYSTEM_BEHAVIOR §26.2b).

158 equation images were discarded from one paper and no surface said so.
The check must also stay quiet on a source that lost nothing — a warning that
fires on clean input trains the user to ignore it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db
from curator.lint import CheckId, Severity, check_extraction_loss


@pytest.fixture()
def paths(tmp_path: Path) -> cfg.WikiPaths:
    p = cfg.WikiPaths(tmp_path)
    p.state_db.parent.mkdir(parents=True, exist_ok=True)
    db.init_db(p.state_db)
    return p


def _add_source(paths: cfg.WikiPaths, relpath: str) -> int:
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES (?, ?, 'pdf', 0, '2026-08-08T00:00:00Z')",
            (relpath, relpath),
        )
        return int(
            conn.execute(
                "SELECT id FROM sources WHERE relpath = ?", (relpath,)
            ).fetchone()["id"]
        )


def _add_span(
    paths: cfg.WikiPaths, source_id: int, key: str, *, lossy: bool, page: int = 11
) -> None:
    meta = (
        {
            "loss": {
                "verdict": "image_only",
                "region": {"width": 221, "height": 18},
                "classified_at": "2026-08-08T00:00:00+00:00",
            }
        }
        if lossy
        else None
    )
    db.upsert_source_span(
        paths.state_db,
        source_id=source_id,
        relpath="x.md",
        span_type="paragraph",
        content_hash=key,
        page_number=page,
        text_preview="…",
        metadata=meta,
    )


def test_reports_a_source_with_unreadable_regions(paths: cfg.WikiPaths) -> None:
    sid = _add_source(paths, "04_Resources/paper.md")
    for i in range(3):
        _add_span(paths, sid, f"lossy{i}", lossy=True)
    _add_span(paths, sid, "clean", lossy=False)

    issues = check_extraction_loss(paths)
    assert len(issues) == 1
    issue = issues[0]
    assert issue.check == CheckId.EXTRACTION_LOSS
    assert issue.severity == Severity.WARNING
    assert "3" in issue.message, "the count of lost regions must be stated"
    assert "paper.md" in issue.message or "paper.md" in issue.page
    assert "vision_model" in issue.suggestion, "the remedy must be named"


def test_stays_silent_when_nothing_was_lost(paths: cfg.WikiPaths) -> None:
    sid = _add_source(paths, "04_Resources/clean.md")
    for i in range(4):
        _add_span(paths, sid, f"clean{i}", lossy=False)
    assert check_extraction_loss(paths) == []


def test_never_claims_the_content_is_absent_from_the_document(
    paths: cfg.WikiPaths,
) -> None:
    """§26.2b: say it could not be READ, never that it does not exist."""
    sid = _add_source(paths, "04_Resources/paper.md")
    _add_span(paths, sid, "lossy", lossy=True)

    text = " ".join(i.message + " " + i.suggestion for i in check_extraction_loss(paths))
    lowered = text.lower()
    assert "absent from" not in lowered
    assert "does not exist" not in lowered
    assert "not in the document" not in lowered


def test_groups_by_source_rather_than_one_issue_per_span(
    paths: cfg.WikiPaths,
) -> None:
    """95 lossy spans on one paper must not produce 95 lint lines."""
    a = _add_source(paths, "04_Resources/a.md")
    b = _add_source(paths, "04_Resources/b.md")
    for i in range(50):
        _add_span(paths, a, f"a{i}", lossy=True)
    for i in range(7):
        _add_span(paths, b, f"b{i}", lossy=True)

    issues = check_extraction_loss(paths)
    assert len(issues) == 2, "expected one issue per affected source"
    counts = sorted(int(i.context["lost_regions"]) for i in issues)
    assert counts == [7, 50]


def test_reports_the_pages_involved(paths: cfg.WikiPaths) -> None:
    sid = _add_source(paths, "04_Resources/paper.md")
    _add_span(paths, sid, "p4", lossy=True, page=4)
    _add_span(paths, sid, "p11", lossy=True, page=11)

    issue = check_extraction_loss(paths)[0]
    assert issue.context["pages"] == [4, 11]


def test_tolerates_malformed_metadata(paths: cfg.WikiPaths) -> None:
    sid = _add_source(paths, "04_Resources/paper.md")
    _add_span(paths, sid, "ok", lossy=True)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO source_spans (id, source_id, relpath, span_type, "
            "content_hash, text_preview, metadata, created_at) "
            "VALUES ('SPAN-bad', ?, 'x.md', 'paragraph', 'bad', '', ?, ?)",
            (sid, "{not json", "2026-08-08T00:00:00Z"),
        )
    issues = check_extraction_loss(paths)
    assert len(issues) == 1 and issues[0].context["lost_regions"] == 1


def test_no_database_is_not_an_error(tmp_path: Path) -> None:
    assert check_extraction_loss(cfg.WikiPaths(tmp_path / "nope")) == []


def test_detects_a_pre_v0490_span_from_its_preview(paths: cfg.WikiPaths) -> None:
    """An existing vault must be reported today, with no migration.

    `upsert_source_span` returns the existing row for an unchanged
    (source_id, content_hash), so a re-parse never refreshes metadata on an
    already-ingested span — and `wiki add --force` would set l2_status back to
    pending, silently triggering a full L2/L3 rebuild across every source.
    """
    sid = _add_source(paths, "04_Resources/legacy.md")
    db.upsert_source_span(
        paths.state_db,
        source_id=sid,
        relpath="legacy.md",
        span_type="paragraph",
        content_hash="legacy1",
        page_number=11,
        text_preview="**==> picture [221 x 18] intentionally omitted <==**",
        metadata=None,  # pre-v0.49.0: no loss record was ever written
    )
    issues = check_extraction_loss(paths)
    assert len(issues) == 1
    assert issues[0].context["lost_regions"] == 1


def test_a_span_counted_once_when_it_has_both_signals(paths: cfg.WikiPaths) -> None:
    sid = _add_source(paths, "04_Resources/both.md")
    db.upsert_source_span(
        paths.state_db,
        source_id=sid,
        relpath="both.md",
        span_type="paragraph",
        content_hash="both1",
        page_number=3,
        text_preview="**==> picture [10 x 10] intentionally omitted <==**",
        metadata={"loss": {"verdict": "image_only", "classified_at": "2026-08-08T00:00:00+00:00"}},
    )
    assert check_extraction_loss(paths)[0].context["lost_regions"] == 1
