# Arena Reframing: Vault-As-Codebase Knowledge System

Date: 2026-06-11 | Agent Persona: system_synthesizer

## User Intent Restatement

The system's heart is not a search feature, a math parser, or a graph database in
isolation. It is the capability to compile a human notes vault into reusable prior
knowledge and let agents use that knowledge with codebase-like discipline:
discover, retrieve, follow dependencies, inspect exact evidence, reason, verify,
and feed reviewed improvements back.

## Why The Previous Split Was Wrong

The earlier retrieval/math/graph split was organized by implementation component.
It created invalid sequencing:

- math/compiler changes alter the corpus and invalidate retrieval baselines;
- graph resolution changes global retrieval after retrieval was called stable;
- quota UI does not establish knowledge correctness;
- a valid span id was treated too easily as proof that a generated claim was
  supported.

## New End-To-End Correctness Boundaries

### 1. Truth and observability boundary

Can the system state exactly what source/claim/corpus/config/model produced an
answer, and can a test prove whether that answer was supported?

### 2. Compiler boundary

Can the system transform note/PDF source truth into stable, minimal,
source-grounded reusable knowledge without duplication, stale records, or
semantic corruption?

### 3. Serving boundary

Can any agent obtain the right bounded prior knowledge, expand it progressively,
verify it, and submit lineage-preserving feedback under explicit latency/token
budgets?

## Consensus

The three programs must follow those correctness boundaries. External techniques
are isolated candidates to benchmark inside them. No framework name, graph
algorithm, model, or retrieval style is itself a completion criterion.
