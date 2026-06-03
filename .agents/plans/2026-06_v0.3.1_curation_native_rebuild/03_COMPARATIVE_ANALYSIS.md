# Comparative Analysis: External RAG Systems And Incurator

## 1. Purpose

This document compares external RAG systems against current Incurator using the
dimensions that matter for a curation-native Obsidian knowledge compiler.

The point is not to select one winner. The point is to decide what v0.3.1 should
inherit from each system while preserving Incurator's identity.

## 2. Comparison Matrix

| Dimension | GraphRAG | LightRAG | HippoRAG | RAPTOR | LlamaIndex PG | Cursor | Current Incurator | v0.3.1 Direction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Provenance fidelity | Medium: has text units but summaries can dominate | Medium | Medium unless extended | Medium-low because summaries drift | Depends on implementation | High for code chunks, low for knowledge truth | High intent via CTX/ATM/CON/EXH and source paths | Source spans required for every claim/report/path |
| Global reasoning | Strong via community reports | Medium-high | Medium | Medium via summary tree | Depends on retrievers | Weak | Weak-medium via Exhibitions | Add community reports inside curation |
| Local/entity retrieval | Strong | Strong | Strong | Medium | Strong | Strong for code | Medium via qmd/concepts | Entity/relation local search |
| Associative memory | Medium | Medium | Strong | Medium | Medium | Weak-medium | Emerging through DAG | Add memory paths / graph walks |
| Insight discovery | DRIFT is strong | Medium | Strong for associations | Medium | Depends | Weak | Philosophically strong but underimplemented | DRIFT-like curation exploration |
| Prompt controllability | Prompt-tunable but external | Moderate | Moderate | Moderate | Framework-driven | Proprietary | Weak: scattered strings | Prompt registry/contracts/traces |
| Incremental rebuild | Nontrivial | Stronger focus | Depends | Potentially expensive | Depends | Strong | Partial via hashes/jobs | Hash chunk cache + subgraph rebuild |
| Obsidian UX fit | Not native | Not native | Not native | Not native | Not native | IDE-native, not notes | Strong plugin/vault fit | Preserve and deepen |
| External-agent fit | API-style | API-style | Research system | Research system | Framework-style | IDE-agent | Strong MCP | Keep MCP curation-first |
| Human approval safety | Not central | Not central | Not central | Not central | Not central | Not central | Strong | Preserve promotion/backprop gates |

## 3. What Current Incurator Already Does Better

### 3.1 Source Truth Separation

Most RAG systems treat the corpus as data to retrieve from. Incurator has a
clearer lifecycle:

- `03_Notes/` is human truth.
- `04_Resources/` is immutable reference/source material.
- external source roots are supported through Reference Mode.
- generated Curator artifacts are not automatically human truth.
- `02_Wiki/` is promoted knowledge.

This is a major product advantage. v0.3.1 must preserve it.

### 3.2 Curation Specification

GraphRAG has query modes, but it does not have an Obsidian workspace-level
Knowledge Requirement Specification like `curate.yml`.

`curate.yml` can become more powerful than a query parameter because it can
declare:

- the workspace's goal;
- source boundaries;
- disambiguation rules;
- expected answer format;
- verification thresholds;
- prompt profile;
- contradiction policy;
- desired exploration behavior.

### 3.3 Exhibition As Agent Context Package

Most RAG systems return answers. Incurator stages Exhibitions as reusable,
workspace-specific context assets. This is closer to how agents actually work:
they need stable context packages, not only one-shot answers.

### 3.4 Backpropagation

Most systems do not close the loop when a human or agent identifies a mistake or
new insight. Incurator's backprop model can turn feedback into graph repair or
derived insight lifecycle events.

## 4. What External Systems Do Better

### 4.1 Global Theme Discovery

GraphRAG's community reports solve broad dataset questions better than current
Incurator's qmd/concept search. Incurator should adopt community reports as a
curation-stage artifact.

### 4.2 Query Mode Separation

GraphRAG's local/global/DRIFT split is clearer than current Incurator's single
`curator_query` path. Incurator should add a router while keeping Exhibition
semantics.

### 4.3 Associative Memory

HippoRAG-style graph walks are better suited to "what does this remind me of?"
or "which prior notes connect to this idea?" than flat search.

### 4.4 Incremental Index Discipline

Cursor's hash/tree/chunk cache thinking is more mature than Incurator's current
index invalidation. Incurator should adopt chunk-level invalidation and prompt
trace caching where possible.

### 4.5 Prompt Architecture

External systems increasingly define query modes, context builders, map/reduce
prompts, and state objects. Incurator's prompt strings should become versioned
contracts with validation and trace.

## 5. Product-Specific Requirements That External Systems Do Not Cover

Incurator needs all of the following:

- Obsidian Markdown compatibility.
- Vault-local and external-reference source handling.
- Human note protection.
- Curator/Artist role separation.
- Workspace-specific curation specs.
- Agent-facing MCP and plugin-local JSON paths.
- Promotion into `02_Wiki/`.
- Backprop without source contamination.
- Prompt output that can be inspected and evaluated.

No external system supplies this combination directly.

## 6. v0.3.1 Synthesis

The right architecture is not:

```text
Incurator + separate GraphRAG/notebase module
```

The right architecture is:

```text
Incurator Curator compiler
  + stronger curate.yml KRS
  + graph/community/report structures
  + local/global/explore router
  + prompt registry/contracts/traces
  + source-span provenance
  + insight/backprop lifecycle
```

## 7. Decision Table

| External feature | Adopt? | Incurator adaptation |
| --- | --- | --- |
| GraphRAG entity/relation extraction | Yes | Add to L2/L3 extraction with source spans |
| GraphRAG community reports | Yes | Treat as generated curation artifacts, not human truth |
| GraphRAG DRIFT | Yes | Add workspace exploration mode controlled by `curate.yml` |
| LightRAG graph/vector hybrid | Yes | Use as retrieval composition principle |
| LightRAG incremental update | Yes | Add chunk/report invalidation plan |
| HippoRAG PPR memory | Yes | Add memory paths for associative prior-knowledge search |
| RAPTOR recursive summaries | Partial | Use for long source/community abstraction, not primary graph |
| LlamaIndex framework | No direct dependency by default | Borrow modular extractor/retriever design |
| Cursor Merkle/chunk cache | Yes | Use source/chunk hashes, async updates, fast context availability |

