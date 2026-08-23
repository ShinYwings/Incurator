"""ROADMAP C1: the L3 prose pass re-ran work it had already completed.

Measured on the reference vault when this was written:

| | |
|---|---|
| sources with `l3_status='error'` | **36** |
| live community reports | **417** |
| of those, prose already generated | **238 (57%)** |

`generate_report_prose` called the provider for **every** report on **every**
run, with no check for work already done. So a retry after a capacity refusal
spent its first 238 calls regenerating prose that was already on disk, and was
refused again long before reaching the 179 reports that still needed writing.
That is why all 36 sources stayed stuck rather than converging over successive
runs.

This is the same defect v0.62.0 fixed for L2 extraction and v0.63.0 fixed for
graph extraction, one layer up. Unlike those, it needs **no new table**: the
report already stores `prompt_run_id`, and `prompt_runs.input_hash` is the same
digest-of-the-rendered-prompt those two use as their resume key. All 238
prose-bearing reports in the live vault join cleanly to their run.
"""

from __future__ import annotations

import json
from pathlib import Path

from curator import db
from curator.pipeline import community_reports


class _CountingClient:
    """Answers the community-report contract and counts provider round trips."""

    model = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, *, json_mode: bool = False, temperature: float = 0.3) -> str:
        self.calls += 1
        text = "\n".join(m.content for m in messages)
        span = "SPAN-00000000"
        for token in text.split():
            if token.startswith("SPAN-"):
                span = token.strip()
                break
        return json.dumps({
            "title": "Residual connections",
            "summary": "They ease optimization.",
            "full_content": "Residual connections ease optimization.",
            "findings": [],
            "rank": 0.5,
            "source_span_ids": [span],
        })


def _seed(tmp_path: Path) -> tuple[Path, dict]:
    db_path = tmp_path / "state.sqlite"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES ('04_Resources/a.md', 'h', 'md', 1, datetime('now'))"
        )
    span = db.upsert_source_span(
        db_path, source_id=1, relpath="04_Resources/a.md", span_type="paragraph",
        content_hash="c1", section_title="Intro",
        text_preview="Residual connections ease optimization.",
    )
    ent = db.upsert_graph_entity(
        db_path, canonical_name="residual connection", entity_type="concept",
        source_span_ids=[span],
    )
    rep_id = db.upsert_community_report(
        db_path, community_key="comm-1", title="t", summary="s", full_content="",
        dependency_hash="d1", entity_ids=[ent], source_span_ids=[span], rank=0.1,
    )
    report = db.get_community_report(db_path, rep_id)
    assert report is not None
    return db_path, report


def test_prose_is_generated_the_first_time(tmp_path: Path) -> None:
    db_path, report = _seed(tmp_path)
    client = _CountingClient()

    rep_id = community_reports.generate_report_prose(db_path, client, report)

    assert client.calls == 1
    stored = db.get_community_report(db_path, rep_id)
    assert stored is not None and stored["full_content"]
    assert stored["prompt_run_id"]


def test_unchanged_prose_is_not_regenerated(tmp_path: Path) -> None:
    """THE fix. 238 of 417 reports were re-sent to the provider on every retry."""
    db_path, report = _seed(tmp_path)
    client = _CountingClient()

    first = community_reports.generate_report_prose(db_path, client, report)
    refreshed = db.get_community_report(db_path, first)
    assert refreshed is not None

    second = community_reports.generate_report_prose(db_path, client, refreshed)

    assert client.calls == 1, "the provider was called again for identical inputs"
    assert second == first


def test_changed_inputs_still_regenerate(tmp_path: Path) -> None:
    """The guard must key on the RENDERED PROMPT, not merely on prose existing.

    A report whose grounding changed has a different prompt and must be
    rewritten; skipping on `full_content` alone would freeze stale prose over
    a graph that has moved.
    """
    db_path, report = _seed(tmp_path)
    client = _CountingClient()
    first = community_reports.generate_report_prose(db_path, client, report)
    refreshed = db.get_community_report(db_path, first)
    assert refreshed is not None

    other_span = db.upsert_source_span(
        db_path, source_id=1, relpath="04_Resources/a.md", span_type="paragraph",
        content_hash="c2", section_title="Method",
        text_preview="Euler discretization view.",
    )
    changed = dict(refreshed)
    changed["source_span_ids"] = [*(refreshed["source_span_ids"] or []), other_span]

    community_reports.generate_report_prose(db_path, client, changed)

    assert client.calls == 2, "changed grounding must produce new prose"


def test_a_report_with_no_prose_is_generated_even_with_a_run_link(tmp_path: Path) -> None:
    """Prose and `prompt_run_id` are written together on success, so this pairing
    should not occur — but a half-written row must retry rather than be skipped
    into permanent emptiness."""
    db_path, report = _seed(tmp_path)
    client = _CountingClient()
    first = community_reports.generate_report_prose(db_path, client, report)
    with db.connect(db_path) as conn:
        conn.execute("UPDATE community_reports SET full_content='' WHERE id=?", (first,))
    refreshed = db.get_community_report(db_path, first)
    assert refreshed is not None

    community_reports.generate_report_prose(db_path, client, refreshed)

    assert client.calls == 2
