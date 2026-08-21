import pytest

from curator.ingest_raw import _chunk_text

def test_chunk_text_preserves_latex():
    # Construct a document with a massive LaTeX block
    math_block = "$$\n" + "A \\times B = C\n" * 200 + "$$"
    # Total length of math block is 200 * 16 + 5 = 3205 characters.
    # If we set chunk_size to 2000, the naive chunker will split the math block.
    
    text = "Introduction\n\n" + math_block + "\n\nConclusion"
    
    # We want chunk_size = 2000. 
    # An AST-aware chunker should NOT split the math block, but rather push it to the next chunk or keep it whole.
    chunks = _chunk_text(text, chunk_size=2000, overlap=100)
    
    # Check that no chunk contains a broken math block (an odd number of $$)
    for i, chunk in enumerate(chunks):
        count = chunk.count("$$")
        assert count % 2 == 0, f"Chunk {i} has broken LaTeX boundary: {count} '$$' markers"


@pytest.mark.parametrize("bad_size", [-300, 0])
def test_chunk_text_rejects_a_non_positive_chunk_size(bad_size: int) -> None:
    """A non-positive chunk size is a programming error, not a small chunk (v0.61.2).

    The forward-progress guard (`if next_start <= start: next_start = start + 1`)
    was written to prevent a hang and succeeded — by converting an illegal size
    into one chunk per character POSITION, each holding nearly the whole
    remaining text. Measured before the fix: `chunk_size=-300` over 3,000
    characters emitted 3,000 chunks totalling 810,000 characters, a 270x
    amplification that never hangs, never raises, and never logs. It only
    spends. Fail at the boundary instead.
    """
    with pytest.raises(ValueError):
        _chunk_text("x" * 3000, chunk_size=bad_size, overlap=500)
