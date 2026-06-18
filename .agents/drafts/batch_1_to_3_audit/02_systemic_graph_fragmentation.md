# Systemic Architectural Review (Batch 2): Graph Fragmentation vs. Giant Components

## Target Scope
**Batch 2 (Program 2)**: Evidence Compiler Integrity (Plan B, Plan C)

## Architectural Vulnerability Description
Batch 2 rebuilds the Knowledge DAG from raw notes, establishing stable semantic identities and extracting relations. It faces an unsolvable tension between **Entity Fragmentation** and **Graph Collapse (Giant Component)**.

### Deep Analysis
1. **The Strict Anti-Merge Policy**: To prevent hallucinations and homonym confusion (e.g., merging "Apple" the fruit with "Apple" the company), the architecture strictly forbids automated LLM entity merging without explicit user aliases.
2. **Fragmentation (Recall Drop)**: Because auto-merging is banned, a concept written as "LLM", "Large Language Model", and "LLMs" across three different notes will spawn three disconnected subgraphs. When Batch 3 attempts Graph-guided expansion (PPR or DRIFT), the traversal will prematurely halt, resulting in catastrophic recall loss for associative queries.
3. **The Denoising Dilemma (Giant Component)**: Conversely, if the relation extraction prompt is too loose (to combat fragmentation), it creates weak, generic edges (e.g., linking everything to "Machine Learning"). This creates a "Giant Component" where every node is 2 hops away from every other node. When ContextService expands this graph, it will instantly exhaust its token budget on irrelevant garbage.

### Recommended Mitigation
1. **Soft-Link Proposal System**: Do not auto-merge entities, but introduce a "Soft-Link" or "Candidate Alias" edge type. These edges have a strict confidence weight and are NOT traversed during factual routing, but CAN be traversed during "Explore" routing with a heavy budget penalty.
2. **Graph Density Alerts**: The compiler must calculate the network density and modularity of the generated graph. If a single community report encompasses more than N% of the vault (Giant Component), the compiler must explicitly quarantine those central hub nodes (e.g., "AI", "Physics") from automated traversal.
