# 💡 Why Incurator Exists

## The Core Problem

You have PDFs, research papers, and notes. When working with them, you don't just want search results or one-off summaries—you want AI to help you **build upon and synthesize your existing knowledge (Increment)**.

Most LLM-based Wiki and knowledge management systems attempt to automate the entire lifecycle (Ingest → Structure → Synthesis) without human guidance. This creates two fundamental failure modes:

### 1. The Quality Trap: Shallow Synthesis
LLMs excel at parsing, decomposing, and restructuring documents according to rules. However, fully automated pipelines struggle to derive genuine, high-value insights across disparate sources without human context and domain intuition. Truly valuable synthesis requires **Human-in-the-Loop (HITL)** collaboration. Without it, automated wikis accumulate shallow summaries and trivial connections.

### 2. The Cost Trap: Token Waste on Grunt Work
Frontier reasoning models (such as Claude 3.5 Sonnet or GPT-4) are optimized for complex problem-solving. Running raw document parsing, structural extraction, and atomization through expensive commercial models quickly exhausts token budgets on repetitive preprocessing. Simple data compilation does not require heavy reasoning.

---

## The Solution: Separating Compilation from Reasoning

Incurator resolves this tension by splitting the knowledge lifecycle into two distinct operations:

1. **Knowledge Compilation (Grunt Work)**:
   - Structural parsing, atomic fact extraction, and concept clustering (`Summary → Atoms → Concepts`).
   - Handled autonomously by lightweight local models (e.g., Ollama/SLMs) or fast non-reasoning APIs.
   - Inexpensive, automated, and fully reproducible.

2. **Knowledge Reasoning (Creative Synthesis)**:
   - Querying, multi-source analysis, hypothesis evaluation, and insight synthesis (`Query → Insight → New Knowledge`).
   - Handled interactively by frontier reasoning models collaborating directly with the user.
   - High-value, human-directed, and strictly grounded in compiled evidence.

---

## Two Spaces, One Continuous Loop

To enforce this separation cleanly, Incurator structures your vault into two distinct tiers:

- **AI Space (`.curator/`)**: The machine-readable knowledge graph. Powered by `state.sqlite` with disposable inspection projections (`01_Contexts/`, `02_Atoms/`, `03_Concepts/`, `04_Synthesis/`). This entire directory can be safely recompiled from source documents at any time.
- **Human Space (`02_Wiki/`)**: The permanent, curated knowledge base. Only insights explicitly reviewed and promoted by the human user become durable wiki artifacts.

### The Lifecycle Loop
1. **Raw Sources** (PDFs, papers, notes) are registered in the vault.
2. **The Curator** (backend daemon) compiles them into structured evidence layers in `.curator/`.
3. **The User & Agent** explore, query, and synthesize insights inside the workspace (Obsidian sidebar or MCP).
4. **Promoted Insights** become permanent notes in `02_Wiki/`, which in turn serve as verified raw sources for future compilation cycles.

Knowledge is not merely searched—it organically accumulates and grows over time.
