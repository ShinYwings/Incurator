# v0.3.1 Curation-Native Architecture

## 1. Purpose

This document defines the target architecture for v0.3.1. It keeps Incurator's
curation identity and upgrades the internal compiler, graph, retrieval, prompt,
and trace layers.

The architecture is not a separate greenfield `.curator/notebase/` product.
Instead, it is a rebuild of the Curator pipeline around a stronger
`curate.yml` specification and a richer graph/report/memory substrate.

## 2. Core Entities

### 2.1 Human Director

The human owns source truth and decides whether derived insights become durable
knowledge. The system may propose, but promotion requires explicit action.

### 2.2 Curator

The Curator is the backend compiler in the vault. It:

- registers source truth;
- builds source maps;
- extracts knowledge units;
- builds entity/relation/claim graph structures;
- stages workspace Exhibitions from `curate.yml`;
- records prompt and evidence traces;
- repairs generated knowledge through backprop.

### 2.3 Artist

The Artist is the workspace human/agent collaboration context. It:

- expresses knowledge requirements in `curate.yml`;
- consumes Exhibitions and curation traces;
- asks local/global/explore queries;
- produces new notes, decisions, and insights;
- sends corrections or promotion requests back to the Curator.

## 3. Upgraded Layer Model

v0.3.1 should preserve the staged L1-L4 mental model while expanding what each
stage means.

### 3.1 L1 Source Context

L1 is no longer just a summary page. It is a source map.

It should contain or index:

- source identity and hash;
- logical source id;
- Reference Mode identity;
- source spans;
- section/page markers;
- Markdown headings;
- PDF page and figure provenance;
- math block preservation;
- wikilink references;
- parser and prompt trace.

### 3.2 L2 Knowledge Units

L2 expands beyond generic Atoms into typed knowledge units:

- claim;
- equation;
- definition;
- entity mention;
- method;
- procedure;
- observation;
- result;
- constraint;
- contradiction candidate.

Every unit must have:

- source span;
- confidence;
- extraction prompt id/version;
- relation to source context;
- optional relation to entities.

### 3.3 L3 Concept, Entity, And Community Layer

L3 becomes the semantic organization layer:

- Concepts remain human-inspectable clusters of L2 units.
- Entities provide graph entry points.
- Relations connect entities, claims, concepts, sources, and Exhibitions.
- Community reports provide GraphRAG-style global summaries.
- Memory paths support HippoRAG-style associative retrieval.

This layer is where GraphRAG and memory-RAG features enter Incurator, but they
enter as Curator artifacts.

### 3.4 L4 Exhibition

L4 remains central. It is the workspace-specific curated context package staged
from `curate.yml`.

An Exhibition should include:

- the workspace goal;
- selected evidence;
- relevant concepts and communities;
- source-span citations;
- unresolved gaps;
- contradictions;
- insight candidates;
- action directives shaped by Artist persona;
- prompt trace ids;
- backprop eligibility metadata.

An Exhibition is not merely an answer transcript.

## 4. Curation Plan

Before writing an Exhibition, the backend should generate a `CurationPlan`.

Inputs:

- `curate.yml`;
- Curator persona;
- source registry;
- graph/community status;
- previous Exhibition if present;
- recent query/backprop traces.

Outputs:

- selected source scope;
- excluded scope and reasons;
- target concepts/entities;
- required community report levels;
- retrieval mode mix;
- expected output shape;
- verification policy;
- prompt profile;
- known gaps.

The `CurationPlan` should be inspectable through CLI/MCP/plugin trace.

## 5. Retrieval Modes Inside Curation

### 5.1 Local

Use for exact source/entity/concept questions.

Pipeline:

1. Extract query entities and constraints.
2. Resolve entities through lexical, vector, and graph matches.
3. Expand to related claims, concepts, and source spans.
4. Build a bounded context pack.
5. Synthesize with local-answer prompt contract.

### 5.2 Global

Use for broad workspace/vault questions.

Pipeline:

1. Select community reports based on `curate.yml` and query.
2. Run map/reduce synthesis with rated intermediate points.
3. Backfill final points with source spans and concept links.
4. Return global answer plus report trace.

### 5.3 Explore

Use for insight discovery.

Pipeline:

1. Build a global primer from community reports.
2. Generate follow-up questions.
3. Run local searches for each promising follow-up.
4. Build exploration tree.
5. Rank insight candidates.
6. Return candidates as provisional, not truth.

### 5.4 Exhibition

Use when a workspace has an active Exhibition and the question should be
answered from staged context first.

Pipeline:

1. Load active Exhibition from `curate.yml`.
2. Check freshness against source/report/graph hashes.
3. Use active Exhibition as pinned context.
4. Optionally supplement with local/global/explore retrieval.
5. Record whether the Exhibition should be refreshed.

## 6. Graph And Report Objects

The future schema should include backend-owned records for:

- `source_spans`
- `knowledge_units`
- `entities`
- `entity_mentions`
- `relations`
- `concept_memberships`
- `community_reports`
- `memory_paths`
- `curation_plans`
- `query_traces`
- `prompt_runs`
- `insight_candidates`
- `backprop_events`

These records may live in `state.sqlite` or a dedicated internal database if
that is later justified. The planning requirement is that they remain backend
state and stay compatible with sync safety rules.

## 7. Trace Model

Every curation/query/explore/backprop run should produce a trace:

- operation id;
- workspace path;
- `curate.yml` hash;
- route decision;
- sources considered;
- sources excluded;
- graph objects used;
- prompt runs;
- model provider/model;
- validation results;
- latency/cost;
- generated artifact ids.

Trace is not optional. It is the trust surface for both humans and agents.

## 8. Relationship To Legacy L1-L4 Files

v0.3.1 should not blindly delete existing `.curator/Collections/`.

Recommended migration stance:

- Keep existing CTX/ATM/CON/EXH filenames and prefixes for compatibility where
  practical.
- Add richer metadata and backend tables to represent upgraded semantics.
- Allow old pages to be read as compatibility artifacts.
- Prefer rebuilding generated artifacts from source truth when schema changes
  are too large to migrate safely.
- Never migrate by rewriting `03_Notes/` or external source truth.

## 9. Acceptance Criteria

The architecture is accepted when it can explain:

- how `curate.yml` controls curation;
- how GraphRAG-style reports fit without replacing Exhibitions;
- how source spans survive every generated layer;
- how prompt trace is stored;
- how local/global/explore modes differ;
- how backprop operates without source contamination;
- how plugin and external agents consume the same backend truth.

