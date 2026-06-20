"""Chat synthesis cites the original source documents outside `.curator/`."""

from __future__ import annotations

from curator import search
from curator.query import _build_synthesis_user_prompt, _source_wikilink


def test_source_wikilink_strips_only_md() -> None:
    assert _source_wikilink("04_Resources/paper.md") == "[[04_Resources/paper]]"
    # Non-.md sources keep their extension so the link resolves to the real file.
    assert _source_wikilink("04_Resources/scan.pdf") == "[[04_Resources/scan.pdf]]"


def _results() -> search.SearchResults:
    return search.SearchResults(
        hits=[
            search.SearchHit(
                full_path="04_Synthesis/SYN-abc12345.md",
                title="Residual learning",
                score=0.9,
                snippet="Skip connections ease optimization.",
                source_span_ids=["SPAN-a", "SPAN-b"],
            )
        ]
    )


def test_prompt_renders_source_documents_and_cite_instruction() -> None:
    prompt = _build_synthesis_user_prompt(
        "How does ResNet help?",
        _results(),
        source_links=[["[[04_Resources/a]]", "[[04_Resources/b]]"]],
    )
    assert "Wikilink path: [[04_Synthesis/SYN-abc12345]]" in prompt
    assert "Source document(s): [[04_Resources/a]], [[04_Resources/b]]" in prompt
    # The closing instruction must direct the model to cite the source link too.
    assert "source-document [[wikilink]]" in prompt


def test_prompt_omits_source_line_when_no_links() -> None:
    prompt = _build_synthesis_user_prompt("q", _results(), source_links=[[]])
    assert "Source document(s):" not in prompt
    assert "source-document [[wikilink]]" not in prompt
    # Falls back to the original curator-only citation instruction.
    assert "Cite each claim with [[wikilinks]]" in prompt
