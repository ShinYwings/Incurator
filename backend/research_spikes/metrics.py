"""Hand-computable Plan E evaluation metrics."""

from __future__ import annotations


def recall_at(ranked: list[str], expected: set[str], k: int) -> float:
    if not expected:
        raise ValueError("expected set must not be empty")
    return len(expected & set(ranked[:k])) / len(expected)


def mrr_at(ranked: list[str], expected: set[str], k: int) -> float:
    if not expected:
        raise ValueError("expected set must not be empty")
    rank = next((index + 1 for index, record_id in enumerate(ranked[:k]) if record_id in expected), None)
    return 0.0 if rank is None else 1.0 / rank


def hard_negative_outranks(ranked: list[str], expected: set[str], hard_negatives: set[str]) -> int:
    expected_rank = next((index for index, record_id in enumerate(ranked) if record_id in expected), None)
    if expected_rank is None:
        return sum(1 for record_id in ranked if record_id in hard_negatives)
    return sum(
        1
        for index, record_id in enumerate(ranked)
        if record_id in hard_negatives and index < expected_rank
    )


def set_coverage(observed: set[str], expected: set[str]) -> float:
    if not expected:
        raise ValueError("expected set must not be empty")
    return len(observed & expected) / len(expected)


def set_correctness(observed: set[str], valid: set[str]) -> float:
    if not observed:
        return 0.0
    return len(observed & valid) / len(observed)
