# Incurator MCP Operational Scenarios (v0.1.0)

This document defines the official operational scenarios and tool interaction patterns for the Incurator MCP (Model Context Protocol) server. It bridges the high-level 4-layer pipeline theory with the practical execution flow triggered by Agent or Human commands.

## 1. Environment & Initialization Scenarios

### 1.1 Session Entry & Synchronization (`curator_check_workspace`)
*   **Trigger**: Automatically called by the Agent at the start of every session.
*   **Logic Flow**:
    1.  **Path Resolution**: Discovers the `vault_root` by walking upward from `workspace_path`.
    2.  **State Validation**: Checks for `curate.yml` existence and the presence of a staged Exhibition in the search index.
    3.  **Result**: Returns initialization status (`needs_initialization`) and exhibition status (`exhibition_exists`).

### 1.2 Workspace Scaffolding (`curator_workspace_init`)
*   **Trigger**: Initiated when `check_workspace` returns `needs_initialization: true`.
*   **Logic Flow**:
    1.  **Requirement Specification**: Generates `curate.yml` with explicit `vault_root` to prevent path drift.
    2.  **Persona Scoping**: Runs an LLM interview to define the Artist Persona (Domain, Goals, Intent).
    3.  **Proactive Curation**: Immediately triggers `wiki curate --workspace` to ensure the Agent has a searchable knowledge package upon entry.

---

## 2. Query & Knowledge Retrieval Scenarios

### 2.1 Persona-Driven Search (`search_curator`)
*   **Logic Flow**:
    1.  Automatically applies `domains`, `topics`, and `min_confidence` filters from the local `curate.yml`.
    2.  If the targeted Exhibition is missing, it **auto-triggers a curation pass** before performing the search.
    3.  Returns results scoped to the project's knowledge requirements, preventing "knowledge noise" from unrelated parts of the vault.

### 2.2 Evidence Traversal (`curator_traverse_evidence`)
*   **Situation**: Search result confidence score is below the high threshold (0.90) but above the low floor (0.60).
*   **Logic Flow**:
    1.  The Agent walks down the evidence chain: `EXH → CON → ATM`.
    2.  Verifies the specific claims and source provenance before citing the information in a task output.

---

## 3. Knowledge Evolution & Integrity Scenarios

### 3.1 Backward Propagation (Knowledge Correction)
*   **Situation**: A Human (Director) or Agent (Artist) identifies an error in a pre-compiled Exhibition or Concept.
*   **Logic Flow**:
    1.  The Agent updates the L4 Exhibition via `curator_update_node`.
    2.  The Engine triggers a **Backward Pass**, tracing the edit back to its constituent Concepts and Atoms.
    3.  The Engine proposes or applies repairs to the underlying DAG nodes to match the corrected truth.
    4.  `wiki sync` ensures the fix is propagated throughout the network.

### 3.2 Synthesis Promotion (The Infinite Loop - Path B)
*   **Situation**: A high-value insight is derived during a conversational session.
*   **Logic Flow**:
    1.  The Human issues a promotion command via `curator_add_knowledge`.
    2.  The Engine selects the insight and atomizes it into a new L2 Atom.
    3.  The Atom is promoted to `02_Wiki/` (the Official Exhibition Hall).
    4.  On the next ingest cycle, this insight is re-absorbed into the L1 pipeline, expanding the system's foundational truth.

---

## 4. Integrity Constraints

*   **No Silent Fallbacks**: During initialization or workspace scoping, the system MUST NOT fallback to `last_root` or CWD if the target path is not within a valid vault. It must fail explicitly to prevent data corruption.
*   **Immutability Hierarchy**: Original sources (`03_Notes`) are never modified by the MCP server. All corrections happen within the DAG (`.curator/`) or via promotion to `02_Wiki/`.
