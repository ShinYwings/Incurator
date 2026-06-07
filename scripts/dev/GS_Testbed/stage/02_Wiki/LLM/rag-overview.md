---
title: Retrieval-Augmented Generation Overview
type: Synthesized
tags:
  - rag
  - llm
  - retrieval
  - nlp
created: 2026-04-29
updated: 2026-04-29
---

# Retrieval-Augmented Generation (RAG)

Retrieval-Augmented Generation (RAG) is a technique that combines large language models with external knowledge retrieval to produce more accurate and grounded responses. Unlike pure generative models that rely solely on parametric memory, RAG systems first retrieve relevant documents from a knowledge base, then use these documents as context for generation.

## Key Components

1. **Retriever**: Searches a document corpus using sparse (BM25) or dense (vector embedding) methods to find the most relevant passages for a given query.
2. **Generator**: A language model (typically a transformer) that takes the retrieved passages as additional context and produces a final response.
3. **Knowledge Base**: A curated collection of documents, often indexed for efficient retrieval.

## Why RAG Matters

- **Reduces hallucination**: By grounding generation in retrieved facts, RAG significantly reduces the tendency of LLMs to fabricate information.
- **Updatable knowledge**: The knowledge base can be updated without retraining the model, making it cheaper to keep information current.
- **Transparency**: Retrieved sources can be cited, improving traceability and trust.

## Notable Implementations

- **Lewis et al. (2020)** introduced the original RAG framework combining DPR with BART.
- **Karpathy's incurator pattern** uses a local-first RAG approach with Obsidian as the knowledge base.
- **QMD (Query Markup Documents)** provides a lightweight search backend for markdown-based knowledge bases.

## Limitations

RAG systems are only as good as their retrieval component. If the relevant information is not in the knowledge base, or if the retriever fails to surface it, the generator may still hallucinate or provide incomplete answers.
