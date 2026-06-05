"""Language-bridge behavior for the plugin `curator_query` entry point.

Covers the v0.2.2 rules that the three language-bridge fields are returned in the
response/trace. As of v0.3.1 the query is sessionless: it returns an answer +
trace and never writes an Exhibition file (curation is a dynamic lens, not a
frozen artifact).
"""

import contextlib
from pathlib import Path

from unittest.mock import patch

from curator import config as cfg
from curator import constants as consts
from curator import plugin_api, query, search


class DummyClient:
    model = "fake"

    def chat(self, messages, *, json_mode=False, temperature=0.3):  # noqa: ARG002
        return (
            '{"answer": "Synthesized answer grounded in concepts.", '
            '"source_span_ids": [], "used_report_ids": [], "confidence": 0.8}'
        )

    def chat_stream(self, messages, temperature=0.0):  # noqa: ARG002
        yield "Synthesized answer grounded in concepts."

    def unload(self) -> None:
        return None


@contextlib.contextmanager
def _dummy_build_client(_config):
    yield DummyClient()


def _seed_concept(paths: cfg.WikiPaths) -> search.SearchResults:
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
    hit = search.SearchHit(
        full_path=f"{consts.LAYER_L3}/CON-lang1234.md",
        title="Language Concept",
        score=0.9,
        full_content=concept_path.read_text(encoding="utf-8"),
    )
    return search.SearchResults(hits=[hit])


def _run(paths: cfg.WikiPaths, *, input_language: str, final_output_language: str):
    results = _seed_concept(paths)
    with (
        patch.object(plugin_api.llm, "build_client", _dummy_build_client),
        patch.object(query, "translate_to_english", return_value="What does this concept mean?"),
        patch.object(query.search, "query", return_value=results),
    ):
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
