# 💡 Core Philosophy: "Increment Your Knowledge"

The ultimate goal of this system is to **"build upon (Increment) existing knowledge to create something new."** It is designed to automate and optimize the process of organically connecting and synthesizing fragmented information into higher-dimensional insights.

---

## 1. Accumulation and Connection: From Zettelkasten to Incurator

The **Zettelkasten** method is a representative learning methodology that embodies our core philosophy. It builds knowledge through four stages:

1.  **Fleeting Notes**: Capturing ideas immediately as they occur.
2.  **Literature Notes**: Summarizing learned content in one's own words.
3.  **Permanent Notes**: Establishing a single idea as an independent "Atom."
4.  **Linking & Synthesis**: Connecting Permanent Notes to generate new ideas.

Note-taking apps like **Obsidian** were built on this philosophy. Features like `[[wikilink]]` and Graph View allow **humans** to visually confirm the network of knowledge and explore previously built ideas when creating something new.

**Incurator** is an evolution of this concept from a data and AI perspective. It automates the exploration and connection process using Large Language Models.

- **The Process**: `Raw Data` ➡️ `Ingest (Summary -> Atoms -> Concepts -> Synthesis)` ➡️ `Wiki (Synthesis as new Raw)`

The shared belief between Zettelkasten and Incurator is that **"prior knowledge is developed through a summarization/refinement process of 'Summarization ➡️ Atomization ➡️ Concept Creation ➡️ Synthesis of Concepts'."**

---

## 2. Problems with Existing LLM Wiki Systems

Most current LLM Wiki implementations allow the LLM to handle everything (Ingest, Wiki generation) after the initial raw data is provided, without human intervention. This leads to two critical problems:

### A. Limitations in Quality Synthesis (Lack of Reasoning)
LLMs excel at decomposing and reassembling data according to rules. However, because many systems rely on scaling model size for "brute force" reasoning, they struggle to find truly valuable "Insights" between raw files to build new knowledge. **Human-in-the-loop (HITL) intervention is essential for high-quality Synthesis.**

### B. Massive Token Consumption and Cost
Collaborating with commercial agents (GPT-4, Claude 3 Opus) for the entire pipeline—from extraction to conceptualization—is prohibitively expensive. Thinking models are optimized for **high-level reasoning**, and using them for simple data decomposition/assembly is an extreme waste of resources. We must avoid "The Bank Account Exhaustion Tragedy" while pursuing the creation of great knowledge 💸.

---

## 3. The Solution: Role Separation and Local Models

The process of decomposing and reassembling data (`Summary -> Atoms -> Concept`) requires very little high-level reasoning. It is an area where LLMs excel and human intervention can be minimized.

**Therefore, we offload this stage to a light Local Model (e.g., Ollama/SLM) or a non-reasoning model.** Local embedding, expansion, and reranking models reduce retrieval cost, while the configured generation model handles knowledge structuring.

In the final **Insight Derivation (Synthesis)** stage, **Humans** must intervene to discuss the results with the agent, iteratively refining the output to create truly new and valuable knowledge.

- **AI-Only Space (`.curator/`)**: The **Archive/Storage**. `state.sqlite` is authoritative; generated CTX/ATM/CON/SYN Markdown is a disposable inspection projection.
- **Human-Only Space (`02_Wiki/`)**: The **Permanent Collection**. Only explicitly promoted, human-reviewed knowledge is durable here.

---

## 4. Architecture: The Curator and The Artist

To implement this collaboration, we borrowed the metaphor of **Art Curation**.

### 🏛️ The Curator (Manager of the Vault)
The Curator resides in the **Vault**, the home of your knowledge. It focuses on refining and displaying data rather than deep reasoning:
1.  **Collection & Selection**: Gathering Raw Data.
2.  **Analysis & Contextualization**: Summarizing data and decomposing it into Atoms.
3.  **Spatial Planning & Structuring**: Weaving Atoms into Concepts to form a machine-readable context.
4. **Curation & Engagement**: Instead of staging a frozen subset, the Curator applies the workspace Knowledge Requirement Specification (`curate.yml`) as a dynamic retrieval lens over the live DAG.

### 🎨 The Artist (Resident of the Workspace: Human + Agent)
The Artist resides in the **Workspace**, the painter's studio where projects or research happen. Drawing a new painting (Synthesis) requires immense creativity and reasoning:
1.  **Workspace**: The painter's studio where projects or research happen.
2.  **The Agent**: A high-reasoning agent resides in the workspace as a human assistant.
3.  **Prior Knowledge Utilization**: The agent retrieves a bounded, traceable evidence pack selected from the refined live DAG.
4.  **Insight Derivation (Synthesis)**: Human and Agent collaborate to create a new "Painting" (Synthesis = New Raw Data).

---

## 5. The Core of the System: Knowledge Compiler

The Curator isn't just an organizer; it's a **Refinement Engine** that produces data in a form the agent can understand most efficiently.

1.  **Reviewed Knowledge Compiler:**
    *   `wiki add` and `wiki build` perform the **Forward Pass** that compiles source-grounded L1-L4 knowledge.
    *   Human or agent feedback enters as a classified proposal. Source truth is protected, and no generated record is silently overwritten.
    *   Approved follow-up actions and integrity checks improve the compiled knowledge while preserving an auditable boundary between source, generated knowledge, and promoted human knowledge.

2.  **High-Fidelity Knowledge Grounding (Quality):**
    *   Agent response quality and contextual understanding improve because a project-specific Curation lens selects bounded evidence from the compiled DAG.
    *   The agent doesn't get lost in massive datasets, providing hallucination-free answers by leveraging only the refined essence of curated knowledge.

3.  **Token Optimization (AI FinOps):**
    *   By offloading repetitive data preprocessing (summarization, atomization) to a **Local SLM (Curator)**, we drastically reduce the tokens consumed by high-performance commercial models (Artist).
    *   Heavy models are shielded from "grunt work," allowing you to concentrate your budget only on tasks that require high-level reasoning.

4.  **Two-Track Directory Structure (UX):**
    *   We perfectly separate machine-readable, high-density data (managed via the repo-cache `state.sqlite` replica) from human-readable, domain-organized wikis (`02_Wiki/`).
    *   Generated L1-L4 Markdown stays hidden under `.curator/Collections/` as a disposable inspection projection; durable human knowledge remains isolated in `02_Wiki/`.

5.  **Ecosystem Diversity & Growth:**
    *   Agents residing in the workspace become unique 'Artists' reflecting the user's style and project goals.
    *   As different agents generate diverse insights from various perspectives, your knowledge base evolves from a flat list of information into a rich, organically growing ecosystem.

6.  **Persona: Expressing Your Knowledge Model**
    *   The Zettelkasten method doesn't impose structure — the way a user views knowledge *becomes* the structure. Incurator's **Persona System** implements this at the system level.
    *   The **Global Persona** (set via an interview during `wiki init`) embeds your knowledge domain, intent, and verification style into the core of the Curator — it defines the *identity* of the Curator residing in each vault.
    *   While knowledge is most powerful when concentrated, you may wish to separate fundamentally different expert domains (e.g., "Scientist" vs "Chef"). This is the one justified reason to run separate vaults — each Curator interprets and exhibits knowledge through a different expert lens.
    *   The **Artist Persona** (set in `curate.yml`) overlays workspace-specific context on top, allowing the same curation engine to frame the same underlying facts in fundamentally different ways depending on the project's goal.
