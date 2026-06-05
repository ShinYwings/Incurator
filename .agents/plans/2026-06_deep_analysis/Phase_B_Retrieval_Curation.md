# Phase B: Retrieval & Curation — Senior Committee Deep Analysis

**Target Files**: `orchestrator.py` (196 lines), `evidence.py` (214 lines), `prompts.py` (1351 lines)

**Panel**: Alice (Architect), Bob (Data), Frank (Backend), Grace (UX), Hannah (QA)

---

## Debate Transcript

### 1. The Smoking Gun: `_run_explore()` Mutates the Database During a Read Query

**Frank (Backend Specialist)**:
"I found the exact violation. In `orchestrator.py:153-195`, the `_run_explore()` method:

1. Builds an evidence pack (read operation — fine)
2. Runs a prompt via `prompting.run_prompt()` (LLM call — fine)
3. **Lines 179-190**: Iterates over `candidates` from the LLM response and calls `db.create_insight_candidate()` for each one, writing directly to the `insight_candidates` table.

This means a user's exploratory query — which should be a pure **read** operation — is silently inserting rows into the database. This violates the **Command-Query Separation (CQS)** principle that every serious backend engineer learns in year one.

For comparison, I researched **LlamaIndex's** architecture. They enforce a strict two-plane separation:
- `QueryPipeline`: Stateless, read-only. No side effects.
- `Workflow` (with explicit `Context`): Stateful, mutation-capable.

Our `_run_explore()` merges both planes into one function."

**Alice (Chief Architect)**:
"The irony is that this system already has the correct separation in its *schema* — `insight_candidates` is explicitly described as 'provisional' (db.py:357). But the *runtime* violates the schema's intent by auto-inserting candidates without human review."

**Hannah (QA Engineer)**:
"This is a testing nightmare. I cannot write a pure unit test for `_run_explore()` that asserts 'zero database mutations during a read operation', because the function is designed to mutate. Every test has to mock the DB layer, which then tests nothing meaningful. The mutation must be extracted into a separate, independently testable function."

### 2. The Evidence Pipeline: Already GraphRAG-Grade, But Underutilized

**Alice (Chief Architect)**:
"I read `evidence.py` carefully and was impressed. The `build_evidence()` function (lines 140-213) implements a multi-route retrieval strategy:

| Route | Evidence Sources | Lines |
|-------|-----------------|-------|
| `source-section` | Source spans only | 148-163 |
| `global` | Synthesis nodes → Community reports → qmd fallback | 165-179 |
| `explore` | Entity evidence → Memory paths (HippoRAG) → Synthesis + Community | 181-205 |
| `local` | Entity evidence → Source spans → qmd hits | 207-213 |

This is a genuine **hybrid retrieval architecture** combining:
1. **Graph-based retrieval** (entities + relations via `_entity_evidence`)
2. **Associative memory** (HippoRAG-style `memory_paths` via `mp.build_memory_paths`)
3. **Hierarchical summarization** (GraphRAG-style `community_reports` and `synthesis_nodes`)
4. **Full-text search** (qmd fallback via `_qmd_hits`)

This is on par with the **2024/2025 SOTA hybrid retrieval architectures** described in the Microsoft GraphRAG paper and subsequent work on LightRAG and HyperGraphRAG."

**Bob (Data Engineer)**:
"But there is a critical gap. Look at `_entity_evidence()` (lines 59-77). It uses a simple `seed_terms()` function to extract keywords from the query, then does a brute-force `db.find_graph_entities()` lookup. There is **no embedding-based semantic search** over entities. The entity matching is purely lexical. If the user asks about 'neural networks' but the entity is stored as 'artificial neural network', it won't match.

Microsoft GraphRAG and HippoRAG both use **embedding-based entity retrieval** with cosine similarity as the first stage. We are missing this entirely."

### 3. Session Context Loss: The Goldfish Problem

**Grace (UI/UX Designer)**:
"From a user journey perspective, the system has a fatal UX flaw. Looking at `models.py:31`, the `QueryRequest` dataclass actually **does** declare a `session_id: str | None = None` field. But here's the problem — this field is **dead code**. Neither `evidence.py` nor `orchestrator.py` ever reads or propagates `session_id`. There is no conversation history, no previous turn context, and no session state.

The structural skeleton for session tracking exists, but the runtime never uses it. Every query is functionally treated as a brand-new, independent request.

Industry-standard conversational RAG systems (e.g., LangChain's `ConversationRetrievalChain`, LlamaIndex's `ChatEngine`) maintain a `chat_history` buffer. Our system forces the user to re-explain their entire context with every follow-up question."

### 4. The Prompts Are Excellent

**Frank (Backend Specialist)**:
"I want to call out something positive. `prompts.py` is genuinely well-engineered. The `SUMMARY_INSTRUCTIONS` (lines 52-98) enforce 'MAXIMUM INFORMATION EXTRACTION' with explicit rules against compression. The `ATOM_COORDINATOR_INSTRUCTIONS` (lines 287-312) implement semantic deduplication. The `CONCEPT_CLUSTERING_INSTRUCTIONS` (lines 385-408) enforce boundary preservation.

These prompts are production-grade. The problem is not the prompt engineering — it's the plumbing around them."

### 📝 Consensus & Action Items

1. **[Backend]** Extract the `db.create_insight_candidate()` call out of `_run_explore()`. Insight candidates discovered during exploration should be returned in the response payload for the frontend to display as suggestions, not silently inserted into the DB.
2. **[Architecture]** Add embedding-based semantic search over `graph_entities` to complement the current lexical `seed_terms()` matching. This would bring the entity retrieval stage up to GraphRAG/HippoRAG SOTA.
3. **[UX/Backend]** Add a `session_id` or `conversation_history` field to `QueryRequest` to enable multi-turn context continuity.
4. **[QA]** Write pure-function tests for `_run_explore()` that assert zero DB mutations.
