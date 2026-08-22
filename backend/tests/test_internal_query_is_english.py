"""The system's internal language is English, with no exceptions.

USER_GUIDE: the agent "answers in that same language, using English only as the
internal search/reasoning language". `QueryRequest.english_query` is the slot
for that internal form and `working_query` returns it.

It was never populated on the ContextService path, so `working_query` silently
fell back to the raw question and every internal component — route signals,
entity seeding, BM25 matching — read Korean. All four of a real user's questions
returned 0 of 233 community reports and 0 of 4 synthesis nodes as a result.
"""

from __future__ import annotations

from pathlib import Path

from curator.prompting.families.query import SearchQueryOutput
from curator.query import derive_search_query
from curator.retrieval.evidence import seed_terms
from curator.retrieval.router import _EXPLORE_SIGNALS, _GLOBAL_SIGNALS


class _Client:
    """Returns a canned derivation, so the test pins OUR contract not a model."""

    model = "fake"

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls = 0

    def chat(self, messages, **kwargs) -> str:  # noqa: ANN001
        self.calls += 1
        return self.payload


class _DeadClient:
    model = "fake"

    def chat(self, messages, **kwargs) -> str:  # noqa: ANN001
        raise RuntimeError("provider unavailable")


def test_internal_signals_stay_english_only() -> None:
    """The internals must NOT be taught other languages.

    A multilingual regex table here would mean the internal representation had
    gone multilingual, obliging every future internal component to carry the
    same table. The boundary translates instead.
    """
    assert not _GLOBAL_SIGNALS.search("여러 논문을 종합해서 설명해줘")
    assert not _EXPLORE_SIGNALS.search("이것과 관련된 아이디어 더 찾아줘")
    # ...and English, which is what actually reaches them, still works.
    assert _GLOBAL_SIGNALS.search("Summarize across all the papers")
    assert _EXPLORE_SIGNALS.search("What else connects to this?")


def test_seed_terms_stay_latin_only() -> None:
    assert seed_terms("여러 논문을 종합해서 설명해줘") == []
    assert "quadric" in seed_terms("how is a quadric parametrized")


def test_a_knowledge_question_yields_an_english_search_query(tmp_path: Path) -> None:
    from curator import config as cfg, db

    paths = cfg.WikiPaths(tmp_path)
    db.init_db(paths.state_db)
    client = _Client(SearchQueryOutput(
        search_query="dual quadric matrix parametrization",
        is_knowledge_question=True,
        reason="asks how a quadric is represented",
    ).model_dump_json())

    query, is_knowledge, _ = derive_search_query(
        paths.state_db, client, "ellipsoid 형태의 quadric 은 어떻게 매트릭스로 표현되나?"
    )

    assert is_knowledge is True
    assert query == "dual quadric matrix parametrization"
    assert query.isascii(), "the internal query must be English"


def test_a_do_this_to_my_text_request_is_not_a_knowledge_question(
    tmp_path: Path,
) -> None:
    """The case that breaks naive translation.

    Translating "translate this to Korean: <body>" into English produces an
    English sentence asking for a Korean translation, which would then be routed
    and BM25-matched as if it asked something about the vault. Extraction
    decides there is nothing to look up — by reading intent, not by matching a
    list of words like "번역".
    """
    from curator import config as cfg, db

    paths = cfg.WikiPaths(tmp_path)
    db.init_db(paths.state_db)
    client = _Client(SearchQueryOutput(
        search_query="",
        is_knowledge_question=False,
        reason="asks for supplied text to be rewritten, needs no stored knowledge",
    ).model_dump_json())

    query, is_knowledge, reason = derive_search_query(
        paths.state_db, client, "다음 문장을 한글로 번역해줘: The quadric is parametrized..."
    )

    assert is_knowledge is False
    assert query == ""
    assert reason


def test_derivation_failure_degrades_to_ascii_terms_not_silence(
    tmp_path: Path,
) -> None:
    """Mixed-script questions dominate this domain, so the ASCII fallback is a
    real query rather than a token gesture — and a provider outage must not
    take retrieval down with it."""
    from curator import config as cfg, db

    paths = cfg.WikiPaths(tmp_path)
    db.init_db(paths.state_db)

    query, is_knowledge, reason = derive_search_query(
        paths.state_db, _DeadClient(), "ellipsoid 형태의 quadric 은 어떻게 표현되나?"
    )

    assert is_knowledge is True
    assert "quadric" in query and "ellipsoid" in query
    assert "unavailable" in reason, "the degradation must be stated, not hidden"


def test_fallback_keeps_diacritics_it_used_to_shred(tmp_path: Path) -> None:
    """`Plücker` must survive the fallback. It did not.

    The character class was `[^A-Za-z0-9_./+-]+`, which strips every non-ASCII
    character — so the single most discriminating term in a query like this
    became two meaningless fragments, `Pl` and `cker`.

    Measured against the live index before the fix: `"Plücker"` and `"plucker"`
    each match **172 documents across 22 sources** (FTS normalises the
    diacritic), while `"Pl" AND "cker"` matches **0**. The fallback then
    compensated by matching junk single letters (`L`, `T`, `Q`), returning more
    hits with worse precision.
    """
    from curator import config as cfg, db

    paths = cfg.WikiPaths(tmp_path)
    db.init_db(paths.state_db)

    query, is_knowledge, _ = derive_search_query(
        paths.state_db,
        _DeadClient(),
        "Plücker Line 과 Dual Quadric 의 관통/접합 손실은 무슨 뜻이야?",
    )

    assert is_knowledge is True
    assert "Plücker" in query, f"the diacritic term was shredded: {query!r}"
    assert "Pl cker" not in query
    assert "Quadric" in query


def test_fallback_drops_single_character_noise(tmp_path: Path) -> None:
    """Matrix notation is not a search term.

    A selected passage carries fragments like `L`, `T`, `Q`, `m` from
    `L^T M(Q)L = 0`. Each matches almost every document, so they flood the
    result set: measured, the old fallback returned 1,310 hits against the LLM
    query's 1,500 while missing the one term that discriminates.
    """
    from curator import config as cfg, db

    paths = cfg.WikiPaths(tmp_path)
    db.init_db(paths.state_db)

    query, _, _ = derive_search_query(
        paths.state_db, _DeadClient(), "Plücker Line L = [l^T, m^T]^T 은 무엇인가?"
    )

    assert "Plücker" in query
    for noise in (" L ", " T ", " m "):
        assert noise not in f" {query} ", f"single-character noise survived: {query!r}"


def test_fallback_still_answers_the_mixed_script_case_it_was_built_for(
    tmp_path: Path,
) -> None:
    """The existing contract must not regress: the pre-existing test asserts
    `quadric` and `ellipsoid` survive, and Korean terms are now kept too."""
    from curator import config as cfg, db

    paths = cfg.WikiPaths(tmp_path)
    db.init_db(paths.state_db)

    query, is_knowledge, _ = derive_search_query(
        paths.state_db, _DeadClient(), "ellipsoid 형태의 quadric 은 어떻게 표현되나?"
    )
    assert is_knowledge is True
    assert "quadric" in query and "ellipsoid" in query
    assert "형태의" in query, "Korean terms are searchable content, not punctuation"
