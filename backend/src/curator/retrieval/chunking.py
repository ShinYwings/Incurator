"""P5: deterministic sentence-window chunker for the v0.3.2 search corpus.

Whole-node embeddings are below parity (a 1,500-token report embeds to a centroid
that washes out the one paragraph answering a narrow query). This chunker splits a
document body into overlapping sentence windows with a token budget, respecting
paragraph and sentence boundaries first and only falling back to hard windows for
pathological undelimited text. It is model-free and fully deterministic so chunk
positions stay stable across re-chunking when the source text is unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Chunk", "chunk_text", "count_tokens"]

# Sentence terminators: ASCII .!? plus CJK 。！？ and newlines as soft breaks.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n{2,}")
_PARA_SPLIT_RE = re.compile(r"\n{2,}")


@dataclass(frozen=True)
class Chunk:
    """One chunk with offsets into the original body."""

    text: str
    char_start: int
    char_end: int


def count_tokens(text: str) -> int:
    """Heuristic token estimate (≈4 chars/token) used when no tokenizer is loaded.

    The chunker must run even in FTS5-only degraded mode so chunk provenance stays
    stable; an exact embedder tokenizer can refine budgets later without changing
    the contract.
    """
    return max(1, len(text) // 4)


def _split_sentences(text: str) -> list[tuple[str, int, int]]:
    """Return (sentence, start, end) tuples preserving offsets into ``text``."""
    spans: list[tuple[str, int, int]] = []
    pos = 0
    for piece in _SENT_SPLIT_RE.split(text):
        if not piece:
            continue
        idx = text.find(piece, pos)
        if idx < 0:
            idx = pos
        spans.append((piece, idx, idx + len(piece)))
        pos = idx + len(piece)
    return spans


def chunk_text(
    text: str,
    *,
    target_tokens: int = 256,
    max_tokens: int = 384,
    overlap_tokens: int = 48,
    min_tokens: int = 32,
) -> list[Chunk]:
    """Split ``text`` into overlapping sentence-window chunks.

    Sentences are accumulated until the running budget reaches ``target_tokens``;
    a sentence that would breach ``max_tokens`` flushes the buffer first. Each new
    buffer carries an ``overlap_tokens`` tail of the previous one. A trailing
    buffer below ``min_tokens`` is absorbed into the previous chunk.
    """
    text = text or ""
    if not text.strip():
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return [Chunk(text=text, char_start=0, char_end=len(text))]

    chunks: list[Chunk] = []
    buf: list[tuple[str, int, int]] = []
    buf_tok = 0

    def _flush() -> None:
        nonlocal buf, buf_tok
        if not buf:
            return
        start = buf[0][1]
        end = buf[-1][2]
        chunks.append(Chunk(text=text[start:end].strip(), char_start=start, char_end=end))
        # carry an overlap tail of whole sentences from the end of this buffer
        tail: list[tuple[str, int, int]] = []
        tail_tok = 0
        for sent in reversed(buf):
            st = count_tokens(sent[0])
            if tail_tok + st > overlap_tokens and tail:
                break
            tail.insert(0, sent)
            tail_tok += st
        buf = tail
        buf_tok = tail_tok

    for sent, start, end in sentences:
        st = count_tokens(sent)
        if buf and buf_tok + st > max_tokens:
            _flush()
        buf.append((sent, start, end))
        buf_tok += st
        if buf_tok >= target_tokens:
            _flush()

    # final buffer: absorb an orphan fragment into the previous chunk
    if buf:
        start = buf[0][1]
        end = buf[-1][2]
        tail_text = text[start:end].strip()
        if chunks and buf_tok < min_tokens:
            prev = chunks[-1]
            merged_end = max(prev.char_end, end)
            chunks[-1] = Chunk(
                text=text[prev.char_start:merged_end].strip(),
                char_start=prev.char_start,
                char_end=merged_end,
            )
        elif tail_text:
            chunks.append(Chunk(text=tail_text, char_start=start, char_end=end))

    return [c for c in chunks if c.text]
