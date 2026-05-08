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

## 2. Problems with Existing Systems

Most current Incurator implementations allow the LLM to handle everything (Ingest, Wiki generation) after the initial raw data is provided, without human intervention. This leads to two critical problems:

### A. Limitations in Quality Synthesis (Lack of Reasoning)
LLMs excel at decomposing and reassembling data according to rules. However, because many systems rely on scaling model size for "brute force" reasoning, they struggle to find truly valuable "Insights" between raw files to build new knowledge. **Human-in-the-loop (HITL) intervention is essential for high-quality Synthesis.**

### B. Massive Token Consumption and Cost
Collaborating with commercial agents (GPT-4, Claude 3 Opus) for the entire pipeline—from extraction to conceptualization—is prohibitively expensive. Thinking models are optimized for **high-level reasoning**, and using them for simple data decomposition/assembly is an extreme waste of resources. We must avoid "The Bank Account Exhaustion Tragedy" while pursuing the creation of great knowledge 💸.

---

## 3. The Solution: Role Separation and Local Models

The process of decomposing and reassembling data (`Summary -> Atoms -> Concept`) requires very little high-level reasoning. It is an area where LLMs excel and human intervention can be minimized.

**Therefore, we offload this stage to a light Local Model (e.g., Ollama/SLM) or a non-reasoning model.** This aligns with modern Incurator approaches that use light embedding/search models (like QMD) to reduce search costs. We take it a step further by entrusting the "Structuring" of knowledge itself to the Local Model or a non-reasoning model.

In the final **Insight Derivation (Synthesis)** stage, **Humans** must intervene to discuss the results with the agent, iteratively refining the output to create truly new and valuable knowledge.

**This role separation naturally leads to a dual-track physical directory structure tailored to the needs of each participant:**
- **AI Space (`.curator/`)**: A machine-friendly backend designed for agents to instantly search and leverage knowledge. (Database for search and reasoning)
- **Human Space (`02_Wiki/`)**: A beautiful knowledge library designed for users to read, manage, and own long-term. (Obsidian Wiki)

---

## 4. Architecture: The Curator and The Artist

To implement this collaboration, we borrowed the metaphor of **Art Curation**.

### 🏛️ The Curator (Local/Non-reasoning Model-based Data Refinement)
The Curator focuses on refining and displaying data rather than deep reasoning:
1.  **Collection & Selection**: Gathering Raw Data.
2.  **Analysis & Contextualization**: Summarizing data and decomposing it into Atoms.
3.  **Spatial Planning & Structuring**: Weaving Atoms into Concepts to form a machine-readable context.
4.  **Exhibition & Engagement**: Instead of a flat list, the Curator stages an **Exhibition** based on a "Knowledge Requirement Specification" (curate.yml). The agent focuses on creation without searching through massive original texts.

### 🎨 The Artist (Human + Agent in Workspace)
The Artist draws a new painting inspired by the Exhibition:
1.  **Workspace**: The painter's studio where projects or research happen.
2.  **The Agent**: A high-reasoning agent resides in the workspace as a human assistant.
3.  **Prior Knowledge Utilization**: The agent retrieves "Exhibits" pre-refined by the Curator instead of searching heavy raw data.
4.  **Insight Derivation (Synthesis)**: Human and Agent collaborate to create a new "Painting" (Synthesis = New Raw Data).

---

## 5. The Core of the System: Knowledge Compiler

The Curator isn't just an organizer; it's a **Refinement Engine** that produces data in a form the agent can understand most efficiently.

1.  **Self-Healing Knowledge Compiler:**
    *   The system operates similarly to a deep learning model. `wiki add/curate` performs the **Forward Pass** to build the knowledge foundation and synthesize outputs.
    *   Modifications by humans or agents act as **Loss Signals**, representing errors in the current state. `wiki sync` then performs the **Backward Pass**, tracing these signals through the graph to restore logical integrity.
    *   Through this iterative cycle, fragmented information evolves into a robust "Concrete" of knowledge, fostering a **Self-Healing** ecosystem that grows more accurate and sophisticated through interaction.

2.  **High-Fidelity Knowledge Grounding (Quality):**
    *   Agent response quality and contextual understanding improve significantly because data is compiled (Exhibition) in a way that is tailored to the current project and task context.
    *   The agent doesn't get lost in massive datasets, providing hallucination-free answers by leveraging only the refined essence of curated knowledge.

3.  **Token Optimization (AI FinOps):**
    *   By offloading repetitive data preprocessing (summarization, atomization) to a **Local SLM (Curator)**, we drastically reduce the tokens consumed by high-performance commercial models (Artist).
    *   Heavy models are shielded from "grunt work," allowing you to concentrate your budget only on tasks that require high-level reasoning.

4.  **Two-Track Directory Structure (UX):**
    *   We have perfectly separated machine-readable, high-density data (`.curator/`) from human-readable, domain-organized wikis (`02_Wiki/`).
    *   Users can comfortably browse and manage refined knowledge without being distracted by complex machine-generated intermediate artifacts.

5.  **Ecosystem Diversity & Growth:**
    *   Agents residing in the workspace become unique 'Artists' reflecting the user's style and project goals.
    *   As different agents generate diverse insights from various perspectives, your knowledge base evolves from a flat list of information into a rich, organically growing ecosystem.
