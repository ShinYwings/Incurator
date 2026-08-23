"""ROADMAP C4: the community partition is flat, and nothing said which algorithm built it.

SYSTEM_BEHAVIOR §27.4 permits the degraded filtered-connected-components path,
but on one condition — *"the fallback never silently changes serving mode: when
the degraded filtered-connected-components path runs, it is recorded in
`config_hash` and surfaced by the audit, not hidden."*

It was hidden. `config_hash` is `_sha16(_GRAPH_FALLBACK_CONFIG)` — a 16-character
digest of a dict, irreversible at the point of reading — and `graph_audit`
returns relation-level violations only (support, canonicality, quarantine
reasons). Nothing anywhere named the algorithm.

Measured on the reference vault: **417 live community reports, every one at
`level = 0`, `parent_community_key` never set, the largest holding 567 entities
and 293 of 417 holding just two.** §27.4's "real hierarchy levels" are not built,
which is allowed — going unmentioned is not.

**Deliberately an INFO, and deliberately not a threshold.** §27.4 gates the
giant-component check on "the approved threshold" from a benchmark freeze that
has never run, and no such constant exists in the tree; inventing one here would
be the hand-maintained number that goes stale unnoticed. This reports what the
partition IS and which algorithm produced it.

**It retires itself.** The signal is a hash comparison against the fallback
config, so the day an approved hierarchy algorithm ships, `config_hash` stops
matching and the line disappears without anyone editing it.
"""

from __future__ import annotations

from pathlib import Path

from curator import config as cfg
from curator import db
from curator.lint import CheckId, Severity, check_community_algorithm


def _vault(tmp_path: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    return paths


def _report(paths: cfg.WikiPaths, key: str, entities: list[str], *, config_hash: str) -> str:
    return db.upsert_community_report(
        paths.state_db, community_key=key, title=key, summary="s", full_content="c",
        dependency_hash=f"d-{key}", entity_ids=entities, source_span_ids=[],
        rank=0.1, config_hash=config_hash,
    )


def test_names_the_degraded_algorithm_when_it_is_serving(tmp_path: Path) -> None:
    paths = _vault(tmp_path)
    fallback = db.graph_config_hash()
    _report(paths, "c1", ["E1", "E2", "E3"], config_hash=fallback)
    _report(paths, "c2", ["E4", "E5"], config_hash=fallback)

    issues = check_community_algorithm(paths)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity is Severity.INFO
    assert issue.check is CheckId.GRAPH_QUALITY
    assert "connected_components" in issue.message
    assert "27.4" in issue.message or "27.4" in (issue.suggestion or "")


def test_reports_the_shape_that_makes_it_matter(tmp_path: Path) -> None:
    """"Flat" is abstract; "the largest community holds 3 of 5 entities and 1 of
    2 communities is a bare pair" is what a reader can act on."""
    paths = _vault(tmp_path)
    fallback = db.graph_config_hash()
    _report(paths, "big", ["E1", "E2", "E3"], config_hash=fallback)
    _report(paths, "pair", ["E4", "E5"], config_hash=fallback)

    message = check_community_algorithm(paths)[0].message

    assert "2" in message          # communities
    assert "3" in message          # largest membership
    assert "pair" in message.lower()


def test_silent_when_a_different_algorithm_produced_the_communities(
    tmp_path: Path,
) -> None:
    """The self-retiring property. When an approved hierarchy algorithm ships,
    `config_hash` stops matching the fallback and this line disappears on its
    own — no constant to remember to delete."""
    paths = _vault(tmp_path)
    _report(paths, "c1", ["E1", "E2"], config_hash="not-the-fallback")

    assert check_community_algorithm(paths) == []


def test_silent_on_an_empty_graph(tmp_path: Path) -> None:
    """No communities is not a degraded partition; it is no partition."""
    assert check_community_algorithm(_vault(tmp_path)) == []


def test_retired_communities_do_not_count(tmp_path: Path) -> None:
    """A retired report is superseded structure. Counting it would report a
    partition the system is not serving."""
    paths = _vault(tmp_path)
    fallback = db.graph_config_hash()
    rep = _report(paths, "gone", ["E1", "E2"], config_hash=fallback)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE community_reports SET retired_at = '2026-01-01T00:00:00Z' WHERE id = ?",
            (rep,),
        )

    assert check_community_algorithm(paths) == []
