# Incurator Lineage Analysis For v0.3.1

## 1. Purpose

v0.3.1 must not be designed by looking only at external RAG systems. The project
already has a strong identity expressed across earlier plans and docs. This
document recovers that identity so the rebuild strengthens it instead of
accidentally replacing it.

The central conclusion is that `curate.yml`, Exhibition staging, source truth
protection, and backprop are the core system. They are not legacy features.

## 1.1 Evidence Map

This section makes the lineage audit explicit. Each cited source is treated as
prior architectural evidence, not merely background reading.

| Source artifact | Relevant conclusion carried forward into v0.3.1 |
| --- | --- |
| `.agents/plans/2024-05_v0.2.0_system_build/INCURATOR_SYSTEM_BUILD.md` | The Python backend is the authoritative curation engine; the Obsidian plugin is a client surface. Generated state belongs under backend control, not plugin-owned mutation. |
| `.agents/plans/2024-05_v0.2.0_system_build/INCURATOR_SYSTEM_BUILD_EVIDENCE.md` | Operational evidence matters: plans must be grounded in actual code paths, state files, and workflow behavior rather than aspirational architecture. v0.3.1 therefore needs prompt traces, evidence traces, and inspectable curation plans. |
| `.agents/plans/2024-05_v0.2.1_update/v0.2.1_specs/00_Master_Plan.md` | Incurator is a knowledge compiler with feedback and backpropagation, not just a retrieval wrapper. The two-track direction of instant reading plus durable DAG compilation remains the right foundation. |
| `.agents/plans/2024-05_v0.2.1_update/v0.2.1_specs/01_Architecture_Analysis.md` | Agent behavior must be routed by backend source state. A viewer-only context, an L1-ready source, and a graph-ready source require different prompts and different claims about reliability. |
| `.agents/plans/2024-05_v0.2.1_update/v0.2.1_specs/03_Autoencoder_DAG_Compiler.md` | L1-L4 is a human-editable latent-space compiler. GraphRAG entities, relations, and reports should enrich this latent space rather than replace it with opaque vector retrieval. |
| `.agents/plans/2024-05_v0.2.1_update/v0.2.1_specs/05_Sync_Backprop.md` | Human edits and contradictions are loss signals. Backprop must diagnose before patching, preserve human-verified artifacts, and repair only the affected generated subgraph. |
| `.agents/plans/2024-05_v0.2.1_update/v0.2.1_specs/09_Visualization_and_Observability.md` | Trust requires traceability. v0.3.1 should extend existing graph/query observability with prompt id, prompt version, prompt input hash, model, validation result, and `curate.yml` hash. |
| `.agents/plans/2024-05_v0.2.1_update/reference_mode_rag_plan.md` | Reference Mode protects external-source workflows. Source identity and source spans must work for Zotero/external roots without assuming every source is copied into the vault. |
| `.agents/plans/2026-06-01_Math_RAG_Backprop_Plan.md` | The ResNet/Neural ODE case proves that later useful interpretation must not be inserted into original source context as if the source said it. Derived insight needs its own lifecycle. |
| `.agents/plans/2026-06-01_Generative_Backprop_Plan.md` | Backprop is not only error correction; it is the mechanism by which generated curation artifacts learn from human/agent synthesis while keeping source truth and promoted knowledge distinct. |
| `.agents/plans/2026-06-02_plugin_backend_ipc_plan.md` | MCP remains external-agent-facing, while the local Obsidian plugin should use backend-owned JSON commands and snapshots. v0.3.1 interfaces must keep those two surfaces separate. |
| `.agents/plans/2026-06-02_zotero_backend_plugin_redesign_plan.md` | Zotero discovery, source registration, and PDF resolution belong to the backend. The plugin presents confirmation and status, but source binding decisions must remain backend-governed. |
| `.agents/plans/2026-06_notebase_rag_plan.md` | The notebase RAG direction is valid only when it is absorbed into Curator identity. A standalone `.curator/notebase/` product would weaken `curate.yml`, Exhibition, and backprop. |
| `docs/philosophy/ABOUT.md` | The product promise is not search but the growth of prior knowledge into new insight. v0.3.1 should make insight discovery and note-writing assistance explicit while preserving curation discipline. |
| `docs/guides/USER_GUIDE.md` and `docs/guides/WORKFLOW_GUIDE.md` | User-facing workflows already distinguish source registration, workspace curation, query, sync, and lint. v0.3.1 should extend those workflows instead of inventing an unrelated UX. |
| `docs/guides/MCP_USER_GUIDE.md` | External agents must receive backend-curated context through MCP rather than guessing from raw vault files. v0.3.1 should expose query, explore, trace, and insight operations through agent-safe tools. |
| `docs/guides/PLUGIN_GUIDE.md` | The plugin is a local Obsidian surface over backend behavior. v0.3.1 plugin work should expose curation state, prompt traces, and insight actions without taking ownership of backend state. |
| `docs/specs/curator_schema/SCHEMA_v0.2.2.md` | Current schema contracts preserve L1-L4, source provenance, workspace state, and generated artifacts. v0.3.1 schema changes must be synchronized and must not pollute human source truth. |
| `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.2.2.md` | Backend authority, adaptive routing, instant L1, async graph build, and query-time Exhibition behavior are current behavior contracts. v0.3.1 must upgrade these contracts rather than contradict them. |
| `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.2.2.md` | Plugin authority and backend authority are separate. v0.3.1 plugin interfaces must preserve version compatibility and avoid direct `.curator/` mutation. |

## 2. v0.2.0 System Build: Backend As Source-Of-Truth Engine

The v0.2.0 system build plan made the backend/client boundary explicit.

Important conclusions:

- The Python backend owns `.curator/state.sqlite`, qmd state, source
  registration, provenance, generated Curator pages, MCP tools, and integrity
  repair.
- The Obsidian plugin owns chat UI, PDF interaction, context chips, import
  confirmations, and user-facing status.
- The plugin must not directly write `.curator/` state.
- `03_Notes/` is human truth.
- `04_Resources/` is source/reference material.
- `02_Wiki/` is promoted human-facing knowledge.
- `.curator/` is machine-readable Curator state.

Design implication for v0.3.1:

The rebuild must not move durable knowledge authority into the plugin or into a
generic local UI feature. Any new graph, prompt trace, insight candidate, or
community report must be backend-owned. The plugin may display and request
actions; it does not become the curation engine.

## 3. v0.2.1 Master Plan: Refined Knowledge Compiler

The v0.2.1 master plan framed the system as a refined knowledge compiler with
feedback and backpropagation. It did not simply aim for faster search.

Important conclusions:

- The system was moving away from a blocking eager extractor.
- The intended architecture included a two-track system:
  - immediate reading for active documents;
  - complete DAG compilation for long-term knowledge.
- The system needed backpropagation from human/agent feedback.
- Observability was required because black-box curation is not trustworthy.
- Exhibition lifecycle and query-time curation were already recognized as
  first-class concerns.

Design implication for v0.3.1:

Modern RAG features should be integrated as compiler stages, not as a separate
assistant search panel. Retrieval must serve curation and backprop.

## 4. Architecture Analysis: Fog Of War And Adaptive Routing

The v0.2.1 architecture analysis identified "Fog of War" in document viewing:
agents can only see what the viewer exposes unless the backend has a durable
source map. It also introduced adaptive routing based on source status.

Important conclusions:

- Immediate document context and durable graph knowledge are separate states.
- Backend-generated CTX/source maps should be trusted more than ephemeral plugin
  PDF.js text for durable curation.
- Agents should be told what mode they are in:
  - unregistered viewer context;
  - L1-ready but L2/L3 pending;
  - graph-ready curator query.
- State detection should route behavior, not rely on user guessing.

Design implication for v0.3.1:

The new query router should generalize this idea. The system should route among
local, global, explore, source-section, and Exhibition modes based on curation
state and `curate.yml`.

## 5. Autoencoder DAG Compiler: Human-Editable Latent Space

The autoencoder DAG compiler plan described Incurator as a staged compression
pipeline:

```text
L1 Context -> L2 Atoms -> L3 Concepts -> L4 Exhibitions
```

Its most important idea was not the exact layer names. The important idea was
that Incurator creates a human-inspectable latent space. Generated knowledge is
not hidden inside opaque vectors.

Important conclusions:

- L2/L3 are a human-editable latent space.
- Math, equations, and source provenance must survive compression.
- L4 should not blindly read raw L1; it should synthesize from refined Concepts
  and Atoms so the agent receives curated knowledge, not raw source dump.
- Incremental rebuild should touch only affected graph regions.

Design implication for v0.3.1:

GraphRAG-style entities, relations, community reports, and memory paths should
augment the latent space. They should not replace it with an opaque vector-only
index.

## 6. Sync Backprop: Loss Signals And Safe Repair

The sync/backprop plan defined user edits, contradictions, and logical gaps as
loss signals.

Important conclusions:

- Forward pass builds source knowledge into generated curation artifacts.
- Backward pass diagnoses changes and repairs affected generated nodes.
- Human-verified nodes must not be overwritten destructively.
- Backprop must distinguish upstream source truth from downstream derived
  interpretation.
- Incremental repair should be subgraph-scoped.

Design implication for v0.3.1:

The new insight lifecycle must classify feedback before acting:

- correction to generated knowledge;
- new derived insight;
- contradiction between sources;
- style-only edit;
- request for promotion.

The system must not rewrite source truth simply because a later insight is
useful.

## 7. Observability: Trace As Trust

The observability plan identified three required trace boundaries:

- background ingest worker progress;
- knowledge refinement graph structure;
- agent query path.

Important conclusions:

- `dag_edges` exists because filesystem scanning is insufficient for real
  observability.
- Users need to see what the system did, not only a final answer.
- Query trace should show concepts, sources, evidence paths, and generated
  Exhibition IDs.

Design implication for v0.3.1:

Prompt trace must be added to evidence trace. The system should show not only
which nodes were used, but which prompt contract, prompt version, model,
`curate.yml` hash, and validation result produced the output.

## 8. Reference Mode And Zotero: Source Truth Without Forced Copying

The Reference Mode and Zotero plans established that source identity is not the
same thing as vault-local file copying.

Important conclusions:

- External PDFs can remain in Zotero or other external roots.
- Vault-local markdown stubs can anchor those sources without duplicating large
  files.
- Device-local absolute paths must not become synced global truth.
- Rebind requires human approval.
- Backend owns Zotero discovery and PDF resolution; plugin presents UI.

Design implication for v0.3.1:

Any upgraded source map, entity graph, or community report must support
Reference Mode. It must cite logical source identity and source spans, not
assume every source is a stable vault-local path.

## 9. Plugin/Backend Boundary: MCP For External Agents, JSON For Local Plugin

The plugin/backend sharing plan moved local Obsidian behavior away from MCP
dependency.

Important conclusions:

- MCP remains important for external agents.
- The local plugin should use backend-owned JSON commands and runtime snapshots.
- Static backend metadata can be bundled at build time when appropriate.
- Dynamic backend state can be read from backend-owned snapshots.
- Mutating actions must call backend code.

Design implication for v0.3.1:

New curation features need two interfaces:

- external-agent MCP tools;
- local plugin JSON commands.

Both must call the same backend services and return the same payload contracts.

## 10. Math RAG And Backprop Testbed: Source Truth Vs Later Insight

The ResNet/dynamics testbed plan made a subtle but critical distinction:

- Original source L1 should remain faithful to the paper.
- Later Neural ODE or PDE interpretation should not be inserted into the
  original paper's source context as if the paper said it.
- Later insight may enter as an EXH correction, promoted wiki artifact, or
  separate source.

Design implication for v0.3.1:

The insight lifecycle must explicitly encode derived knowledge. "Useful" is not
the same as "source-supported by this source." Prompt contracts must enforce
that distinction.

## 11. Current Docs: Philosophy And v0.2.2 Specs

The philosophy docs define the core product promise: increment knowledge by
connecting and synthesizing prior knowledge into new insight. They also define
role separation:

- Curator: background refinement engine in the vault.
- Artist: workspace human/agent doing high-reasoning synthesis.
- Exhibition: curated context package staged from `curate.yml`.

The v0.2.2 specs define:

- backend authority;
- plugin authority;
- workspace agent authority;
- source registration and adaptive routing;
- instant L1;
- async build;
- query-time Exhibition behavior;
- prompt language handling;
- plugin local runtime snapshots.

Design implication for v0.3.1:

Specs should be upgraded, not contradicted. The core authority boundaries and
source protection rules remain.

## 12. Preserved Identity

v0.3.1 must preserve these identity statements:

- Incurator is a Curator, not just a retriever.
- `curate.yml` is the Artist's specification to the Curator.
- Exhibition is the staged bridge from prior knowledge to current work.
- Backprop is the mechanism for learning from human/agent correction.
- Source truth is protected.
- Promoted knowledge is explicit.
- Trace is required for trust.
- Prompt quality is part of the system contract, not a hidden implementation
  detail.
