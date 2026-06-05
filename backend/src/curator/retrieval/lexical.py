"""P4: deterministic lexical query parsing + BM25 retrieval over FTS5 (v0.3.2).

Turns a raw user question into a *safe* FTS5 MATCH string (exact phrases,
negation, hyphen/dotted identifiers, prefix matching) and runs BM25 over the two
FTS tables maintained by the materializer (P3):

- ``search_documents_fts``      — ``unicode61`` (``tokenchars '_-.'``) primary.
- ``search_documents_fts_tri``  — ``trigram`` fallback for Korean/CJK and
  substring/identifier recall.

The lexical layer hands RRF (P6) a *rank-ordered* doc list; it never normalizes
BM25 scores (fusion uses ranks). It needs no model and is fully deterministic.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from .. import db
from .evidence import _STOP

__all__ = ["LexicalQuery", "LexicalHit", "parse_query", "build_fts_match", "lexical_search"]

_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
_PHRASE_RE = re.compile(r'"([^"]+)"')
# FTS5 query operators / quoting we must neutralize inside bare terms.
_FTS_SPECIAL = re.compile(r'[":()*^]')
# Internal identifier punctuation kept whole by the unicode61 tokenchars config.
_IDENT_RE = re.compile(r"[.\-_/]")
# Leading/trailing punctuation to trim from a token without splitting identifiers.
_STRIP_CHARS = ".,;:!?'\"()[]{}"


@dataclass(frozen=True)
class LexicalQuery:
    """The deterministic parse of a raw question into FTS5-ready parts."""

    raw: str
    terms: tuple[str, ...]
    phrases: tuple[str, ...]
    excludes: tuple[str, ...]
    is_cjk: bool


@dataclass(frozen=True)
class LexicalHit:
    """One lexical candidate. ``score`` is raw BM25 (lower = more relevant)."""

    doc_id: str
    record_type: str
    record_id: str
    title: str
    score: float
    rank: int  # 1-based; lower = better


def parse_query(raw: str) -> LexicalQuery:
    """Split a raw question into phrases, negations, and ranked terms."""
    phrases = [m.strip() for m in _PHRASE_RE.findall(raw) if m.strip()]
    rest = _PHRASE_RE.sub(" ", raw)

    excludes: list[str] = []
    terms: list[str] = []
    for tok in rest.split():
        neg = tok.startswith("-") and len(tok) > 1
        word = (tok[1:] if neg else tok).strip(_STRIP_CHARS)
        if not word:
            continue
        if neg:
            if word not in excludes:
                excludes.append(word)
            continue
        is_ident = bool(_IDENT_RE.search(word))
        low = word.lower()
        # Stopword / too-short filtering applies to plain ASCII words only;
        # identifiers, acronyms, and CJK tokens are always kept.
        if not is_ident and word.isascii():
            if low in _STOP or (len(word) <= 2 and not word.isupper()):
                continue
        if word not in terms:
            terms.append(word)

    return LexicalQuery(
        raw=raw,
        terms=tuple(terms),
        phrases=tuple(phrases),
        excludes=tuple(excludes),
        is_cjk=bool(_CJK_RE.search(raw)),
    )


def build_fts_match(parsed: LexicalQuery, *, prefix: bool = True, trigram: bool = False) -> str:
    """Render a parsed query into a safe FTS5 MATCH string.

    ``trigram=True`` quotes every term as a substring phrase (no prefix operator)
    and drops sub-3-char tokens the trigram tokenizer cannot index.
    """
    parts: list[str] = []

    for ph in parsed.phrases:
        cleaned = _FTS_SPECIAL.sub(" ", ph).strip()
        if trigram and len(cleaned) < 3:
            continue
        if cleaned:
            parts.append(f'"{cleaned}"')

    or_group: list[str] = []
    for term in parsed.terms:
        cleaned = _FTS_SPECIAL.sub(" ", term).strip()
        if not cleaned:
            continue
        if trigram:
            if len(cleaned) < 3:  # trigram needs >=3 chars
                continue
            or_group.append(f'"{cleaned}"')
        elif _IDENT_RE.search(cleaned):
            # quote so '.' '-' '/' aren't read as operators; keep prefix recall
            or_group.append(f'"{cleaned}"' + ("*" if prefix else ""))
        else:
            or_group.append(cleaned + ("*" if prefix else ""))
    if or_group:
        parts.append("(" + " OR ".join(or_group) + ")")

    match = " ".join(parts)
    for ex in parsed.excludes:
        cleaned = _FTS_SPECIAL.sub(" ", ex).strip()
        if cleaned and not (trigram and len(cleaned) < 3):
            match += f' NOT "{cleaned}"'
    return match.strip()


def _like_scan(db_path, parsed: LexicalQuery, limit: int) -> list[dict]:
    """Bounded substring fallback for very short CJK queries (< trigram floor)."""
    needles = [n for n in (parsed.raw.strip(), *parsed.terms) if n]
    if not needles:
        return []
    clause = " OR ".join(["title LIKE ? OR body LIKE ?"] * len(needles))
    args: list[object] = []
    for needle in needles:
        like = f"%{needle}%"
        args.extend([like, like])
    with db.connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT doc_id, record_type, record_id, title FROM search_documents "
            f"WHERE {clause} LIMIT ?",
            (*args, limit),
        ).fetchall()
    return [{**dict(r), "score": 0.0} for r in rows]


def lexical_search(
    db_path,
    raw: str,
    *,
    families: set[str] | None = None,
    limit: int = 50,
    prefix: bool = True,
) -> list[LexicalHit]:
    """BM25 lexical retrieval over both FTS tables, merged by best rank.

    A document keeps its strongest (lowest) BM25 score across the two indexes.
    For CJK queries the trigram index is added; if both indexes return nothing
    (e.g. a sub-3-char CJK query) a bounded LIKE scan recovers candidates.
    """
    parsed = parse_query(raw)
    best: dict[str, dict] = {}

    def _run(use_trigram: bool) -> None:
        match = build_fts_match(parsed, prefix=prefix and not use_trigram, trigram=use_trigram)
        if not match:
            return
        try:
            rows = db.fts_search(db_path, match, trigram=use_trigram, limit=limit * 2)
        except sqlite3.OperationalError:
            return  # malformed MATCH for this tokenizer → skip this index
        for row in rows:
            doc_id = row["doc_id"]
            score = float(row["score"])
            current = best.get(doc_id)
            if current is None or score < current["score"]:
                best[doc_id] = {**dict(row), "score": score}

    _run(use_trigram=False)
    if parsed.is_cjk:
        _run(use_trigram=True)
    if parsed.is_cjk and not best:
        for row in _like_scan(db_path, parsed, limit):
            best.setdefault(row["doc_id"], row)

    items = list(best.values())
    if families:
        items = [r for r in items if r["record_type"] in families]
    items.sort(key=lambda r: r["score"])
    items = items[:limit]
    return [
        LexicalHit(
            doc_id=r["doc_id"],
            record_type=r["record_type"],
            record_id=r["record_id"],
            title=r.get("title", ""),
            score=r["score"],
            rank=i,
        )
        for i, r in enumerate(items, start=1)
    ]
