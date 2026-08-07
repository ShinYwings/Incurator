"""Routing and entity seeding must not depend on the question's language.

Measured before this change: all four of a Korean user's questions routed
`local` and returned 0 of the vault's 233 community reports and 0 of its 4
synthesis nodes. The identical questions in English routed `global`. The cause
was ASCII-only keyword regexes — the distilled L3/L4 layers were not badly
ranked for a Korean speaker, they were unreachable.

USER_GUIDE documents Korean, English, Chinese, Japanese and Russian as
supported, so those are the languages under test here.
"""

from __future__ import annotations

import pytest

from curator.retrieval.evidence import seed_terms
from curator.retrieval.router import _EXPLORE_SIGNALS, _GLOBAL_SIGNALS


def _signal(question: str) -> str:
    if _EXPLORE_SIGNALS.search(question):
        return "explore"
    if _GLOBAL_SIGNALS.search(question):
        return "global"
    return "local"


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # The user's real question — a specific fact, correctly local.
        ("ellipsoid 형태의 quadric 은 어떻게 매트릭스로 표현되나?", "local"),
        # The one that exposed the bug: explicitly asks to synthesize across
        # papers, and routed `local` purely because it is not English.
        (
            "2D Gaussian Splatting이 3D보다 표면 재구성에 유리한 이유를 "
            "여러 논문을 종합해서 설명해줘",
            "global",
        ),
        ("내 볼트의 전반적인 주제는 무엇인가?", "global"),
        ("이것과 관련된 아이디어를 더 찾아줘", "explore"),
        # English must keep working exactly as before.
        ("Summarize across all papers how kernel fusion helps", "global"),
        ("What are the overall themes in my vault?", "global"),
        ("What else connects to this?", "explore"),
        ("How is the rendering equation defined?", "local"),
        # The other documented languages.
        ("全体的なテーマは何ですか", "global"),
        ("总结一下所有论文的主要观点", "global"),
        ("Обобщи основные темы", "global"),
    ],
)
def test_route_signals_are_language_independent(question: str, expected: str) -> None:
    assert _signal(question) == expected


def test_the_same_question_routes_the_same_way_in_either_language() -> None:
    """The precise defect: translation changed the route."""
    korean = "여러 논문을 종합해서 설명해줘"
    english = "Summarize across all the papers"
    assert _signal(korean) == _signal(english) == "global"


def test_seed_terms_finds_terms_in_a_non_latin_question() -> None:
    """A pure-Korean question used to yield zero seeds, so entity resolution
    returned nothing regardless of route or graph coverage."""
    terms = seed_terms("ellipsoid 형태의 quadric 은 어떻게 매트릭스로 표현되나?")
    assert "quadric" in terms, "Latin terms must still be found"
    assert any(not t.isascii() for t in terms), "Korean terms must be found too"


def test_seed_terms_drops_single_character_particles() -> None:
    """A lone Hangul character is a grammatical particle, not a search term.

    Seeding on it matches every entity that merely contains the character.
    """
    terms = seed_terms("quadric 은 무엇인가?")
    assert "은" not in terms
    assert "quadric" in terms


def test_seed_terms_keeps_short_cjk_words() -> None:
    """The <=3-char floor is an English-filler rule and must not apply to CJK,
    where a two-character token is a full and often highly specific word."""
    terms = seed_terms("행렬 표현")
    assert "행렬" in terms


def test_seed_terms_still_drops_english_filler() -> None:
    terms = seed_terms("what is the aim of the method")
    assert "the" not in terms and "is" not in terms
    assert "method" in terms
