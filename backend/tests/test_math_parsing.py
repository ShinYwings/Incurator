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
