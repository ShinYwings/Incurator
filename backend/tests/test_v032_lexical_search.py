"""v0.3.2 Phase 4: deterministic lexical query parser + BM25 over FTS5.

No models needed — parser shape and BM25 ordering are fully deterministic.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from curator import db
from curator.retrieval import lexical


@pytest.fixture()
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.sqlite"
        db.init_db(path)
        yield path


def _doc(db_path: Path, record_id: str, title: str, body: str, record_type: str = "knowledge_unit"):
    return db.upsert_search_document(
        db_path, record_type=record_type, record_id=record_id,
        title=title, body=body, content_hash=record_id, dependency_hash=record_id,
    )


# --- parser -----------------------------------------------------------------


def test_parse_phrases_negation_identifiers_stopwords():
    parsed = lexical.parse_query('What is "reciprocal rank fusion" with nn.Conv2d -deprecated?')
    assert parsed.phrases == ("reciprocal rank fusion",)
    assert parsed.excludes == ("deprecated",)
    # stopwords (what/is/with) dropped; identifier kept whole; trailing '?' trimmed
    assert "nn.Conv2d" in parsed.terms
    assert "what" not in [t.lower() for t in parsed.terms]
    assert "fusion" not in parsed.terms  # consumed by the phrase
    assert parsed.is_cjk is False


def test_parse_keeps_acronyms_and_detects_cjk():
    parsed = lexical.parse_query("RRF 합성이란 무엇인가")
    assert "RRF" in parsed.terms  # short but uppercase acronym kept
    assert parsed.is_cjk is True
    assert "합성이란" in parsed.terms


# --- match builder ----------------------------------------------------------


def test_build_match_quotes_phrase_and_identifier_with_prefix():
    parsed = lexical.parse_query('"rank fusion" nn.Conv2d residual -stale')
    match = lexical.build_fts_match(parsed, prefix=True)
    assert '"rank fusion"' in match
    assert '"nn.Conv2d"*' in match
    assert "residual*" in match
    assert 'NOT "stale"' in match
    assert " OR " in match  # plain terms OR-grouped for recall


def test_build_match_trigram_drops_short_tokens_and_no_prefix():
    parsed = lexical.parse_query("ab residual")  # 'ab' < 3 chars
    match = lexical.build_fts_match(parsed, trigram=True)
    assert '"residual"' in match
    assert "*" not in match  # trigram never uses prefix operator
    assert "ab" not in match


# --- end-to-end BM25 over the materialized FTS ------------------------------


def test_lexical_search_ranks_and_filters_families(db_path: Path):
    hit_id = _doc(db_path, "ATM-1", "Residual learning",
                  "Residual connections ease optimization in deep networks.")
    _doc(db_path, "ATM-2", "Attention", "Attention weights tokens by relevance.")
    span_id = _doc(db_path, "SPAN-1", "", "Residual residual residual blocks.",
                   record_type="source_span")

    hits = lexical.lexical_search(db_path, "residual optimization")
    assert hits and hits[0].rank == 1
    ids = {h.doc_id for h in hits}
    assert hit_id in ids and span_id in ids

    # family filter keeps only knowledge_unit docs
    filtered = lexical.lexical_search(db_path, "residual", families={"knowledge_unit"})
    assert {h.record_type for h in filtered} == {"knowledge_unit"}


def test_lexical_search_negation_excludes(db_path: Path):
    keep = _doc(db_path, "ATM-1", "Stable training", "Residual blocks help training.")
    _doc(db_path, "ATM-2", "Deprecated", "Residual blocks are deprecated here.")
    hits = lexical.lexical_search(db_path, "residual -deprecated")
    ids = {h.doc_id for h in hits}
    assert keep in ids
    assert all("deprecated" not in h.title.lower() or h.doc_id == keep for h in hits)


def test_lexical_search_cjk_trigram(db_path: Path):
    doc = _doc(db_path, "SPAN-1", "", "잔차 학습은 최적화를 돕는다", record_type="source_span")
    hits = lexical.lexical_search(db_path, "최적화 방법")
    assert any(h.doc_id == doc for h in hits)


def test_lexical_search_cjk_like_fallback_for_short_query(db_path: Path):
    doc = _doc(db_path, "SPAN-1", "", "합성 데이터 생성", record_type="source_span")
    # '합성' is 2 chars — below the trigram floor; LIKE fallback recovers it.
    hits = lexical.lexical_search(db_path, "합성")
    assert any(h.doc_id == doc for h in hits)
