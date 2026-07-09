"""REDESIGN R1 (v0.3.1): shared L4 Synthesis layer.

The synthesis layer distills community reports into corpus-wide, source-grounded
synthesized insights stored in ``synthesis_nodes`` and projected to
``.curator/Collections/04_Synthesis/SYN-*.md``. It is workspace-INDEPENDENT and
regenerated wholesale, but skipped when the report corpus is unchanged.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db
from curator.llm import ChatMessage
from curator.pipeline import synthesis


class SynthFakeClient:
    """Emits one cross-cutting synthesis citing the first span it sees."""

    model = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        self.calls += 1
        text = "\n".join(m.content for m in messages)
        spans = re.findall(r"SPAN-[0-9a-f]{8}", text)
        first = spans[0] if spans else "SPAN-00000000"
        return json.dumps(
            {
                "syntheses": [
                    {
                        "title": "Residual learning as discretized dynamics",
                        "statement": "Residual blocks across communities behave like Euler steps.",
                        "full_content": "Cross-community synthesis.",
                        "source_span_ids": [first],
                        "confidence": 0.6,
                    }
                ]
            }
        )


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        paths = cfg.WikiPaths(root)
        db.init_db(paths.state_db)
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES ('04_Resources/r.md', 'h', 'md', 1, datetime('now'))"
            )
        span = db.upsert_source_span(
            paths.state_db, source_id=1, relpath="04_Resources/r.md",
            span_type="paragraph", content_hash="c1",
            text_preview="Residual connections ease optimization.",
        )
        a = db.upsert_graph_entity(paths.state_db, canonical_name="residual learning",
                                   entity_type="concept", source_span_ids=[span])
        db.upsert_community_report(
            paths.state_db, community_key="comm-1", title="Residual community",
            summary="ResNet eases optimization.", full_content="...",
            dependency_hash="d1", entity_ids=[a], source_span_ids=[span], rank=0.7,
        )
        yield paths, span


def test_generate_synthesis_writes_nodes_and_projection(vault) -> None:
    paths, span = vault
    client = SynthFakeClient()
    ids = synthesis.generate_synthesis(paths, client)
    assert ids and ids[0].startswith("SYN-")

    nodes = db.list_synthesis_nodes(paths.state_db)
    assert len(nodes) == 1
    node = nodes[0]
    assert span in node["source_span_ids"]
    assert node["community_report_ids"]  # grounded in the report corpus
    assert node["prompt_run_id"]  # prompt trace recorded

    # Projection emitted to the disposable search projection.
    page = (paths.synthesis / f"{node['id']}.md").read_text(encoding="utf-8")
    assert "type: synthesis" in page
    assert "Residual learning as discretized dynamics" in page


def test_generate_synthesis_records_concept_ids(vault) -> None:
    paths, _ = vault
    client = SynthFakeClient()
    report_id = db.list_community_reports(paths.state_db)[0]["id"]
    ids = synthesis.generate_synthesis(
        paths,
        client,
        concept_ids_by_report={report_id: "CON-test0001"},
    )
    assert ids
    node = db.list_synthesis_nodes(paths.state_db)[0]
    assert node["concept_ids"] == ["CON-test0001"]
    page = (paths.synthesis / f"{node['id']}.md").read_text(encoding="utf-8")
    assert "concept_ids:\n- 03_Concepts/CON-test0001" in page


def test_generate_synthesis_is_skipped_when_corpus_unchanged(vault) -> None:
    paths, _ = vault
    client = SynthFakeClient()
    synthesis.generate_synthesis(paths, client)
    assert client.calls == 1
    # Second run with no report changes must not call the LLM again.
    synthesis.generate_synthesis(paths, client)
    assert client.calls == 1


def test_generate_synthesis_regenerates_on_report_change(vault) -> None:
    paths, span = vault
    client = SynthFakeClient()
    synthesis.generate_synthesis(paths, client)
    assert client.calls == 1
    # Mutate the report corpus -> dependency hash changes -> regenerate.
    db.upsert_community_report(
        paths.state_db, community_key="comm-2", title="Optimization community",
        summary="Skip connections improve gradient flow.", full_content="more",
        dependency_hash="d2", entity_ids=[], source_span_ids=[span], rank=0.5,
    )
    synthesis.generate_synthesis(paths, client)
    assert client.calls == 2


def test_no_reports_yields_no_synthesis(vault) -> None:
    paths, _ = vault
    db.clear_synthesis_nodes(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute("DELETE FROM community_reports")

    class Boom:
        model = "fake"
        def chat(self, *a, **k):  # pragma: no cover - must not be called
            raise AssertionError("must not synthesize without reports")

    assert synthesis.generate_synthesis(paths, Boom()) == []
