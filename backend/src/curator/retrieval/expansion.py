"""P6: typed query expansion (lex / vec / hyde) for v0.3.2 DB-native search.

Two tiers, per the qmd-parity requirement that a naive single-vector probe is
below parity:

- **Tier 1 (deterministic, always runs):** parse the question (phrases, negation,
  identifiers, CJK), derive an ``intent``, seed the lexical MATCH + the raw vector
  probe, and fold in static acronym synonyms and KRS/persona ``boosts``.
- **Tier 2 (optional LLM expander):** a configured callable adds lexical
  paraphrases, extra vector probes, and a HyDE hypothetical-answer probe. HyDE is
  recovery-only (engaged when lexical recall is thin / vector confidence low) so
  it is not a fixed per-query tax.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import lexical

__all__ = ["ExpandedQuery", "expand", "Expander"]

# A Tier-2 expander returns a dict with optional keys:
#   {"lex_terms": [...], "vec_texts": [...], "hyde_text": "..."}
Expander = Callable[[str], dict]

# Static bidirectional acronym/synonym map (recall without an LLM).
_SYNONYMS: dict[str, list[str]] = {
    "rrf": ["reciprocal rank fusion"],
    "knu": ["knowledge unit"],
    "ctx": ["context"],
    "atm": ["atom"],
    "con": ["concept"],
    "exh": ["exhibition"],
    "fts": ["full text search"],
    "bm25": ["okapi bm25"],
    "knn": ["nearest neighbor"],
}

_INTENT_CUES: list[tuple[str, tuple[str, ...]]] = [
    ("definition", ("what is", "define", "definition of", "무엇", "이란", "란 ")),
    ("comparison", (" vs ", "versus", "compare", "difference between", "차이")),
    ("procedure", ("how to", "how do", "steps to", "방법", "어떻게")),
]


@dataclass
class ExpandedQuery:
    raw: str
    intent: str = "default"
    is_cjk: bool = False
    parsed: lexical.LexicalQuery | None = None
    lex_match: str = ""
    lex_terms_expanded: list[str] = field(default_factory=list)  # extra OR terms
    vec_texts: list[str] = field(default_factory=list)  # texts to embed for KNN
    hyde_text: str = ""
    boosts: list[str] = field(default_factory=list)


def _detect_intent(raw: str) -> str:
    low = raw.lower()
    for intent, cues in _INTENT_CUES:
        if any(cue in low for cue in cues):
            return intent
    return "default"


def _synonym_terms(parsed: lexical.LexicalQuery) -> list[str]:
    extra: list[str] = []
    for term in parsed.terms:
        for syn in _SYNONYMS.get(term.lower(), ()):
            if syn not in extra:
                extra.append(syn)
    return extra


def expand(
    raw: str,
    *,
    boosts: list[str] | None = None,
    expander: Expander | None = None,
    want_hyde: bool = False,
) -> ExpandedQuery:
    """Build a typed ``ExpandedQuery`` from a raw question (Tier 1 + optional Tier 2)."""
    parsed = lexical.parse_query(raw)
    exp = ExpandedQuery(
        raw=raw,
        intent=_detect_intent(raw),
        is_cjk=parsed.is_cjk,
        parsed=parsed,
        lex_match=lexical.build_fts_match(parsed),
        lex_terms_expanded=_synonym_terms(parsed),
        vec_texts=[raw],
        boosts=list(boosts or []),
    )

    if expander is not None:
        try:
            extra = expander(raw) or {}
        except Exception:
            extra = {}
        for term in extra.get("lex_terms", []) or []:
            if term and term not in exp.lex_terms_expanded:
                exp.lex_terms_expanded.append(term)
        for text in extra.get("vec_texts", []) or []:
            if text and text not in exp.vec_texts:
                exp.vec_texts.append(text)
        if want_hyde:
            exp.hyde_text = str(extra.get("hyde_text") or "")

    return exp
