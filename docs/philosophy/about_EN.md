# 💡 Core Philosophy: "Increment Your Knowledge"

The ultimate goal of this system is to **"build upon (Increment) existing knowledge to create something new."** It is designed to automate and optimize the process of organically connecting and synthesizing fragmented information into higher-dimensional insights.

---

## 1. Accumulation and Connection: From Zettelkasten to LLM Wiki

The **Zettelkasten** method is a representative learning methodology that embodies our core philosophy. It builds knowledge through four stages:

1.  **Fleeting Notes**: Capturing ideas immediately as they occur.
2.  **Literature Notes**: Summarizing learned content in one's own words.
3.  **Permanent Notes**: Establishing a single idea as an independent "Atom."
4.  **Linking & Synthesis**: Connecting Permanent Notes to generate new ideas.

Note-taking apps like **Obsidian** were built on this philosophy. Features like `[[wikilink]]` and Graph View allow **humans** to visually confirm the network of knowledge and explore previously built ideas when creating something new.

**LLM Wiki** is an evolution of this concept from a data and AI perspective. It automates the exploration and connection process using Large Language Models.

- **The Process**: `Raw Data` ➡️ `Ingest (Summary -> Atoms -> Concepts -> Synthesis)` ➡️ `Wiki (Synthesis as new Raw)`

The shared belief between Zettelkasten and LLM Wiki is that **"prior knowledge is developed through an extraction/synthesis process of 'Summarization ➡️ Atomization ➡️ Concept Creation ➡️ Synthesis of Concepts'."**

---

## 2. Problems with Existing Systems

Most current LLM Wiki implementations allow the LLM to handle everything (Ingest, Wiki generation) after the initial raw data is provided, without human intervention. This leads to two critical problems:

### A. Limitations in Quality Synthesis (Lack of Reasoning)
LLMs excel at decomposing and reassembling data according to rules. However, because many systems rely on scaling model size for "brute force" reasoning, they struggle to find truly valuable "Insights" between raw files to build new knowledge. **Human-in-the-loop (HITL) intervention is essential for high-quality Synthesis.**

### B. Massive Token Consumption and Cost
Collaborating with commercial agents (GPT-4, Claude 3 Opus) for the entire pipeline—from extraction to conceptualization—is prohibitively expensive. Thinking models are optimized for **high-level reasoning**, and using them for simple data decomposition/assembly is an extreme waste of resources. We must avoid "The Bank Account Exhaustion Tragedy" while pursuing the creation of great knowledge 💸.

---

## 3. The Solution: Role Separation and Local Models

The process of decomposing and reassembling data (`Summary -> Atoms -> Concept`) requires very little high-level reasoning. It is an area where LLMs excel and human intervention can be minimized.

**Therefore, we offload this stage to a light Local Model (e.g., Ollama/SLM) running on your own hardware.** This aligns with modern LLM Wiki approaches that use light embedding/search models (like QMD) to reduce search costs. We take it a step further by entrusting the "Structuring" of knowledge itself to the Local Model.

In the final **Synthesis** stage, **Humans** must intervene to discuss the results with the agent, iteratively refining the output to create truly new and valuable knowledge.

---

## 4. Architecture: The Curator and The Artist

To implement this collaboration, we borrowed the metaphor of **Art Curation**.

### 🏛️ The Curator (Local Model-based Data Preprocessing)
The Curator focuses on refining and displaying data rather than deep reasoning:
1.  **Collection & Selection**: Gathering Raw Data.
2.  **Analysis & Contextualization**: Summarizing data and decomposing it into Atoms.
3.  **Spatial Planning & Structuring**: Weaving Atoms into Concepts to form a machine-readable context.
4.  **Exhibition & Engagement**: Instead of a flat list, the Curator stages an **Exhibition** based on a "Knowledge Requirement Specification" (curate.yml). The agent focuses on creation without searching through massive original texts.

### 🎨 The Artist (Human + Agent in Workspace)
The Artist draws a new painting inspired by the Exhibition:
1.  **Workspace**: The painter's studio where projects or research happen.
2.  **The Agent**: A high-reasoning agent resides in the workspace as a human assistant.
3.  **Prior Knowledge Utilization**: The agent retrieves "Exhibits" pre-compiled by the Curator instead of searching heavy raw data.
4.  **Synthesis**: Human and Agent collaborate to create a new "Painting" (Synthesis = New Raw Data).

---

## 5. The Core of the System: Knowledge Compiler

The Curator isn't just an organizer; it's a **Compiler** that produces data in a form the agent can understand most efficiently.

1.  **Token Optimization**: Drastically reduces the tokens consumed by agents for searching and context loading.
2.  **Improved Knowledge Grounding**: Agent response quality improves because data is compiled in a machine-friendly way.
3.  **Two-Track Directory Structure**:
    *   **Curator-made (`.curator/`)**: High-density, machine-readable backend for agents.
    *   **Synthesis-made (`02_Wiki/`)**: Domain-organized, beautiful Zettelkasten for humans.

4.  **Ecosystem Diversity**: As workspaces grow, different agents (Artists) bring their own "style" to the knowledge base, creating a truly organic and rich Wiki ecosystem.

5.  **Learning Metaphor-based Knowledge Cycle (Forward & Backward Pass)**: The system operates similarly to the training process of a deep learning model. The process where `wiki add` builds the foundation (L1-L3) and `wiki curate` synthesizes the final output (L4) acts as the **Forward Pass**. Modifications by humans and agents serve as **Loss Signals**, representing errors in the system's current state. Finally, `wiki sync` performs the **Backward Pass**, tracing these signals back through the graph to repair structural flaws and maintain overall knowledge integrity.

6.  **Self-Evolution & Concreting**: Knowledge is not static historical data. Every time an agent or human discovers and corrects an error during interaction, fragmented information evolves into a more robust and reliable "Concrete" of knowledge, solidifying its place within the system.
