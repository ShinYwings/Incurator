"""P6: Reciprocal Rank Fusion (RRF) for v0.3.2 DB-native hybrid search.

RRF fuses the per-variant ranked lists (lexical raw/expansion, vector raw/
expansion/HyDE) using **ranks only**, which is exactly why it tolerates the
BM25-negated vs cosine score-scale mismatch with zero normalization. Defaults
mirror qmd parity: ``k=60``, original-query weighting (raw lists outweigh
expansions), a candidate cap per list, and a small top-rank bonus. Every
candidate carries a full per-list contribution trace for the dashboard.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

__all__ = ["FusedHit", "rrf_fuse", "DEFAULT_WEIGHTS"]

# Original-query weighting: raw lex/vec dominate; expansions add recall only.
DEFAULT_WEIGHTS: dict[str, float] = {
    "lex_raw": 1.0,
    "vec_raw": 0.9,
    "lex_exp": 0.6,
    "vec_exp": 0.6,
    "vec_hyde": 0.7,
}


@dataclass(frozen=True)
class FusedHit:
    doc_id: str
    score: float
    rank: int  # 1-based; lower = better
    contributions: list[dict] = field(default_factory=list)


def rrf_fuse(
    ranked_lists: dict[str, tuple[float, list[str]]],
    *,
    k: int = 60,
    candidate_cap: int = 100,
    fuse_cap: int = 40,
    top_rank_bonus: float = 0.5,
) -> list[FusedHit]:
    """Fuse ``{list_name: (weight, [doc_id in rank order])}`` into one ranking.

    Each list is truncated to ``candidate_cap`` before fusion; the fused output is
    truncated to ``fuse_cap``. A document at rank 1 of any list gets a small
    additive ``top_rank_bonus / (k+1)`` bonus.
    """
    scores: dict[str, float] = defaultdict(float)
    trace: dict[str, list[dict]] = defaultdict(list)

    for name, (weight, docs) in ranked_lists.items():
        for rank, doc_id in enumerate(docs[:candidate_cap], start=1):
            contribution = weight * (1.0 / (k + rank))
            if rank == 1:
                contribution += top_rank_bonus / (k + 1)
            scores[doc_id] += contribution
            trace[doc_id].append(
                {"list": name, "rank": rank, "weight": weight, "contribution": contribution}
            )

    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:fuse_cap]
    return [
        FusedHit(doc_id=doc_id, score=score, rank=i, contributions=trace[doc_id])
        for i, (doc_id, score) in enumerate(fused, start=1)
    ]
