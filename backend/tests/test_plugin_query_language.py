"""Language-bridge behavior for the plugin `curator_query` entry point.

Covers the v0.2.2 rules that the three language-bridge fields are returned in the
response/trace. As of v0.3.1 the query is sessionless: it returns an answer +
trace and never writes an Exhibition file (curation is a dynamic lens, not a
frozen artifact).
"""

import contextlib
import json
import re
from pathlib import Path

import pytest
from unittest.mock import patch

from curator import config as cfg
from curator import constants as consts
from curator import db, plugin_api


class DummyClient:
    model = "fake"

    def chat(self, messages, *, json_mode=False, temperature=0.3):  # noqa: ARG002
        text = "\n".join(message.content for message in messages)
        spans = re.findall(r"SPAN-[0-9a-f]{8}", text)
        return json.dumps({
            "answer": "Synthesized answer grounded in concepts.",
            "source_span_ids": spans[:1],
            "used_report_ids": [],
            "confidence": 0.8,
        })

    def chat_stream(self, messages, temperature=0.0):  # noqa: ARG002
        yield "Synthesized answer grounded in concepts."

    def unload(self) -> None:
        return None


@contextlib.contextmanager
def _dummy_build_client(_config):
    yield DummyClient()


def _seed_context_service_graph(paths: cfg.WikiPaths) -> str:
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath,content_hash,file_type,bytes,added_at) "
            "VALUES ('x.md','c1','md',1,datetime('now'))"
        )
    span = db.upsert_source_span(
        paths.state_db,
        source_id=1,
        relpath="x.md",
        span_type="paragraph",
        content_hash="c1",
        section_title="Context",
        text_preview="language concept",
    )
    db.upsert_graph_entity(
        paths.state_db,
        canonical_name="Language Concept",
        entity_type="concept",
        source_span_ids=[span],
    )
    paths.concepts.mkdir(parents=True, exist_ok=True)
    concept_path = paths.concepts / "CON-lang1234.md"
    concept_path.write_text(
        """---
id: CON-lang1234
type: concept
name: Language Concept
domain: Test
confidence_score: 0.8
---

# Language Concept
""",
        encoding="utf-8",
    )
    return span


def _run(paths: cfg.WikiPaths, *, input_language: str, final_output_language: str):
    _seed_context_service_graph(paths)
    with patch.object(plugin_api.llm, "build_client", _dummy_build_client):
        return plugin_api.curator_query(
            paths,
            question="이 개념은 무엇을 의미하나요?",
            input_language=input_language,
            english_query="What does this concept mean?",
            final_output_language=final_output_language,
        )


def test_curator_query_returns_language_fields_in_response(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    cfg.save_config(cfg.WikiPaths(vault), {})
    paths = cfg.paths_from_config(vault)

    result = _run(paths, input_language="Korean", final_output_language="Korean")

    assert result["ok"] is True
    # Response/trace exposes the language bridge fields.
    assert result["input_language"] == "Korean"
    assert result["english_query"] == "What does this concept mean?"
    assert result["final_output_language"] == "Korean"
    assert result["trace"]["pack_id"].startswith("PACK-")
    assert result["trace"]["snapshot"]["snapshot_id"].startswith("SNAP-")
    assert result["trace"]["source_span_ids"]
    assert result["trace"]["prompt_trace_ids"]


def test_curator_query_l3_complete_uses_single_context_service_root(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    cfg.save_config(cfg.WikiPaths(vault), {})
    paths = cfg.paths_from_config(vault)

    with patch.object(
        plugin_api.search,
        "query",
        side_effect=AssertionError("L3-complete plugin query must not use legacy search"),
    ):
        result = _run(paths, input_language="Korean", final_output_language="Korean")

    assert result["ok"] is True
    assert result["trace_id"].startswith("QTR-")
    assert result["pack_id"].startswith("PACK-")
    assert result["pack_id"] == result["trace"]["pack_id"]
    assert result["snapshot"] == result["trace"]["snapshot"]
    assert result["budget"] == result["trace"]["budget"]
    assert result["prompt_trace_ids"] == result["trace"]["prompt_trace_ids"]

    traces = db.list_query_traces(paths.state_db)
    assert len(traces) == 1
    trace = db.get_query_trace(paths.state_db, result["trace_id"])
    assert trace is not None
    context_trace = trace["retrieval_trace"]["context_service"]
    assert context_trace["pack_id"] == result["pack_id"]
    assert context_trace["snapshot"]["snapshot_id"] == result["snapshot"]["snapshot_id"]
    assert any(
        action["action_type"] == "synthesis"
        and action["child_id"] in result["prompt_trace_ids"]
        for action in context_trace["actions"]
    )


def test_curator_query_is_sessionless_writes_no_exhibition(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    cfg.save_config(cfg.WikiPaths(vault), {})
    paths = cfg.paths_from_config(vault)

    result = _run(paths, input_language="Korean", final_output_language="Korean")
    assert result["ok"] is True
    removed_cache_key = "cache" + "_hit"
    removed_artifact_key = "exhibition" + "_id"
    assert removed_cache_key not in result
    assert removed_artifact_key not in result
    # No generated query artifact is written (sessionless Q&A returns answer + trace only).
    assert not paths.synthesis.exists() or not list(
        paths.synthesis.glob(f"{consts.PREFIX_L4}-*.md")
    )


def test_curator_query_does_not_relabel_unexpected_runtime_error(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    cfg.save_config(cfg.WikiPaths(vault), {})
    paths = cfg.paths_from_config(vault)
    _seed_context_service_graph(paths)

    with (
        patch.object(plugin_api.llm, "build_client", _dummy_build_client),
        patch(
            "curator.retrieval.QueryOrchestrator.run",
            side_effect=RuntimeError("programming defect"),
        ),
        pytest.raises(RuntimeError, match="programming defect"),
    ):
        plugin_api.curator_query(paths, question="What does this concept mean?")
