# Defense And Consensus: PDF Adaptive Routing
Date: 2026-06-12 | Agent Persona: System Synthesizer

## Consensus

The requested “automatic upgrade” is a routing-priority change, not a rule that
registered PDFs must always bypass local viewer context.

Locked priority:

1. Explicit selected text/crop/current visible PDF.js context remains primary.
2. Registered + L1-complete sources may use durable L1 projection sections for
   missing local context, broader page windows, and `toc_id` expansion.
3. Unregistered or degraded registered sources may use read-only original-PDF
   parsing as fallback.
4. No passive path may call import/register.
5. L3-only knowledge-graph query is clearly separated from L1 section serving.

For v0.5.6, CTX projection is the durable exact-text read model because SQLite
does not store full span text. Responses must say `durable_l1_projection`, not
claim full DB-native text serving. A future RAG stabilization milestone may
introduce an authoritative full-text span store.
