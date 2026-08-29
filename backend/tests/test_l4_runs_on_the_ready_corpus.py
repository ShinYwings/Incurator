"""ROADMAP C2: L4 had never produced a single row, in the whole vault's history.

| | |
|---|---|
| `synthesis_nodes` rows | **0** |
| `SYN-*` files | **0** |
| sources at `l4_status='done'` | **0** |

Meanwhile three code paths — `retrieval/materializer.py`, `retrieval/evidence.py`
and `context_service.py` — read `synthesis_nodes`, a table that had never had a
row to read.

**The cause was a single gate**: `compile.py` ran synthesis only `if not
l3_errors`, and `l3_errors` collects one entry per failed report prose. Across
417 reports with a provider that refuses on capacity, that list has never once
been empty. One failed report out of 417 blocked the entire top layer.

The gate was inherited rather than decided: `git log -S` puts its current form in
f663a0a ("make terminal layer statuses truthful"), which split a shared `errors`
list into `l3_errors`/`l4_errors` while fixing status reporting. It carried the
condition forward; it never argued for it.

And it contradicts the function it guards. `generate_synthesis` computes
`corpus_dependency_hash` and skips when the corpus is unchanged — it is built to
be re-run as the corpus evolves. The gate prevented exactly the re-running the
design assumes.
"""

from __future__ import annotations

import json
from pathlib import Path

from curator import config as cfg
from curator import db
from curator.pipeline import synthesis


class _Client:
    model = "fake"

    def __init__(self) -> None:
        self.calls = 0
        self.last_prompt = ""

    def chat(self, messages, *, json_mode: bool = False, temperature: float = 0.3) -> str:
        self.calls += 1
        self.last_prompt = "\n".join(m.content for m in messages)
        spans = sorted({t.strip(".,") for t in self.last_prompt.split() if t.startswith("SPAN-")})
        return json.dumps({
            "syntheses": [{
                "title": "Optimization stability",
                "statement": "Residual connections ease optimization.",
                "full_content": "Across the corpus, residual connections recur.",
                "source_span_ids": spans[:1] or ["SPAN-00000000"],
                "confidence": 0.6,
            }]
        })


def _vault(tmp_path: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES ('04_Resources/a.md', 'h', 'md', 1, datetime('now'))"
        )
    return paths


def _report(paths: cfg.WikiPaths, key: str, *, prose: str) -> str:
    span = db.upsert_source_span(
        paths.state_db, source_id=1, relpath="04_Resources/a.md", span_type="paragraph",
        content_hash=f"c-{key}", section_title=key,
        text_preview="Residual connections ease optimization.",
    )
    ent = db.upsert_graph_entity(
        paths.state_db, canonical_name=f"concept-{key}", entity_type="concept",
        source_span_ids=[span],
    )
    return db.upsert_community_report(
        paths.state_db, community_key=key, title=f"Title {key}",
        summary=f"Summary {key}", full_content=prose, dependency_hash=f"d-{key}",
        entity_ids=[ent], source_span_ids=[span], rank=0.5,
    )


def test_synthesis_runs_when_some_reports_are_still_unwritten(tmp_path: Path) -> None:
    """THE fix. 238 of 417 reports had prose and L4 still produced nothing."""
    paths = _vault(tmp_path)
    _report(paths, "done-1", prose="Full prose one.")
    _report(paths, "done-2", prose="Full prose two.")
    _report(paths, "pending", prose="")

    ids = synthesis.generate_synthesis(paths, _Client())

    assert ids, "L4 produced nothing despite a corpus with completed reports"
    assert db.list_synthesis_nodes(paths.state_db)


def test_unwritten_reports_are_not_fed_to_the_model(tmp_path: Path) -> None:
    """A report without prose has not finished its own layer (SYSTEM_BEHAVIOR
    §27.5 — prose is what that pass adds). Feeding the skeleton would make L4's
    output depend on how far L3 happened to get."""
    paths = _vault(tmp_path)
    _report(paths, "done-1", prose="Full prose one.")
    _report(paths, "pending", prose="")
    client = _Client()

    synthesis.generate_synthesis(paths, client)

    assert "Summary done-1" in client.last_prompt
    assert "Summary pending" not in client.last_prompt


def test_a_corpus_with_no_completed_report_does_not_call_the_model(tmp_path: Path) -> None:
    """Nothing to synthesise is not a failure, but it must not cost a call."""
    paths = _vault(tmp_path)
    _report(paths, "pending", prose="")
    client = _Client()

    assert synthesis.generate_synthesis(paths, client) == []
    assert client.calls == 0


def test_completing_a_report_re_triggers_synthesis(tmp_path: Path) -> None:
    """The lifecycle the gate prevented: L4 runs on what is ready, and runs again
    when more becomes ready. Without this, synthesising early would freeze a
    partial view."""
    paths = _vault(tmp_path)
    _report(paths, "done-1", prose="Full prose one.")
    pending_id = _report(paths, "pending", prose="")
    client = _Client()

    synthesis.generate_synthesis(paths, client)
    assert client.calls == 1

    # Re-running an unchanged corpus must stay free.
    synthesis.generate_synthesis(paths, client)
    assert client.calls == 1

    db.upsert_community_report(
        paths.state_db, community_key="pending", title="Title pending",
        summary="Summary pending", full_content="Now written.",
        dependency_hash="d-pending",
    )
    synthesis.generate_synthesis(paths, client)
    assert client.calls == 2, "a newly completed report did not re-trigger synthesis"
    assert pending_id



def test_l4_status_follows_what_synthesis_cited_not_merely_what_exists(
    tmp_path: Path,
) -> None:
    """Retrospective review finding on v0.69.6, caught after it shipped.

    v0.69.6 made synthesis skip prose-less reports, but left the per-source L4
    status deriving from EVERY live report. Combined with `generate_synthesis`
    returning the existing node ids on its unchanged-corpus path — so the old
    `if synthesis_ids` gate is true on almost every round — a source whose report
    was still a bare skeleton got `l4_status='done'` in the same round it got
    `l3_status='error'`. Self-contradictory, and `l4_complete` then told callers
    that content had reached the top layer when synthesis had filtered it out.

    Status must follow what the synthesis nodes actually CITE.
    """
    paths = _vault(tmp_path)
    written = _report(paths, "written", prose="Real prose.")
    skeleton = _report(paths, "skeleton", prose="")
    synthesis.generate_synthesis(paths, _Client())

    cited = {
        rid
        for node in db.list_synthesis_nodes(paths.state_db)
        for rid in (node.get("community_report_ids") or [])
    }

    assert written in cited, "a report with prose was not synthesised"
    assert skeleton not in cited, (
        "a prose-less report was cited by synthesis; L4 status derived from the "
        "full report list would mark its source done"
    )
