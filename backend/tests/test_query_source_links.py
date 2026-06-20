"""Chat synthesis cites the original source documents outside `.curator/`."""

from __future__ import annotations

from pathlib import Path

from curator import config as cfg
from curator import db, plugin_api, search
from curator.query import (
    _build_synthesis_user_prompt,
    _source_wikilink,
    resolve_source_links,
    save_wiki_page,
)


def _vault_with_source(tmp_path: Path, relpath: str = "04_Resources/a.md") -> tuple[cfg.WikiPaths, str]:
    paths = cfg.WikiPaths(tmp_path)
    paths.state_db.parent.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        sid = conn.execute(
            """
            INSERT INTO sources
                (relpath, content_hash, file_type, bytes, added_at, context_id,
                 l1_status, l2_status, l3_status)
            VALUES (?, ?, 'md', 128, '2026-06-04T00:00:00Z', ?, 'done', 'done', 'done')
            """,
            (relpath, f"h-{relpath}", f"CTX-{relpath}"),
        ).lastrowid
    span = db.upsert_source_span(
        paths.state_db,
        source_id=sid or 0,
        relpath=relpath,
        span_type="paragraph",
        section_title="s",
        start_char=0,
        end_char=10,
        content_hash="h-span",
        text_preview="evidence",
    )
    return paths, span


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


def test_resolve_source_links_from_spans(tmp_path: Path) -> None:
    paths, span = _vault_with_source(tmp_path, "04_Resources/a.md")
    assert resolve_source_links(paths, [span]) == ["[[04_Resources/a]]"]
    assert resolve_source_links(paths, []) == []


def test_save_wiki_page_appends_deduped_sources_footer(tmp_path: Path) -> None:
    paths = cfg.WikiPaths(tmp_path)
    rel = save_wiki_page(
        paths,
        "What is X?",
        "X is Y.",
        "Cat",
        "slug",
        source_links=["[[04_Resources/a]]", "[[04_Resources/b]]", "[[04_Resources/a]]"],
    )
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert "## Sources" in text
    assert "- [[04_Resources/a]]" in text
    assert "- [[04_Resources/b]]" in text
    # Deduped: the repeated link appears once.
    assert text.count("- [[04_Resources/a]]") == 1


def test_save_wiki_page_omits_footer_when_no_links(tmp_path: Path) -> None:
    paths = cfg.WikiPaths(tmp_path)
    rel = save_wiki_page(paths, "q?", "answer", "Cat", "slug")
    assert "## Sources" not in (tmp_path / rel).read_text(encoding="utf-8")


def test_promote_answer_writes_source_graph_links(tmp_path: Path) -> None:
    """A 02_Wiki promotion with the answer's spans must list the source documents
    so they appear in Obsidian's Graph view / Backlinks (c3 hybrid)."""
    paths, span = _vault_with_source(tmp_path, "04_Resources/a.md")
    out = plugin_api.promote_answer(
        paths,
        question="What is residual learning?",
        answer="Residual learning uses skip connections.",
        source_span_ids=[span],
    )
    assert out["ok"], out
    text = (tmp_path / out["promoted_to"]).read_text(encoding="utf-8")
    assert "## Sources" in text
    assert "[[04_Resources/a]]" in text
