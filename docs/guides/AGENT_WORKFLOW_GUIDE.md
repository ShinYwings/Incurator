# Incurator Agent Workflow Guide

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

### 2.1 Persona-Driven Query & Search (`curator_query` & `search_curator`)
*   **Logic Flow (`curator_query`)**:
    1.  Implements **Dual Architecture**: If a Workspace is specified, uses the Pinned L4 Exhibition and persona from `curate.yml` (no ephemeral files). If Vault mode (no workspace), dynamically generates an Ephemeral L4 Exhibition per chat session.
    2.  Enforces **L3 Constraints**: L4 Exhibitions are only generated if L3 Concepts are present. Otherwise, skips L4 generation and returns a direct answer or falls back to raw search.
*   **Logic Flow (`search_curator`)**:
    1.  Automatically applies `domains`, `topics`, and `min_confidence` filters from the local `curate.yml`.
    2.  If the targeted Exhibition is missing, it **auto-triggers a curation pass** before performing the search.
    3.  Returns results scoped to the project's knowledge requirements, preventing "knowledge noise" from unrelated parts of the vault.

### 2.2 Evidence Traversal (`curator_traverse_evidence`)
*   **Situation**: Search result confidence score is below the high threshold (0.90) but above the low floor (0.60).
*   **Logic Flow**:
    1.  The Agent walks down the evidence chain: `EXH → CON → ATM`.
    2.  Verifies the specific claims and source provenance before citing the information in a task output.

### 2.3 External Resource Integration & Hash Healing
*   **Situation**: Connecting external references like Zotero PDFs without duplicating files into the vault, or repairing broken links when those files are modified outside the vault.
*   **Logic Flow**:
    1.  **Configuration**: The Agent calls `curator_list_external_resources` to retrieve the configured external libraries (e.g., Zotero path) from the platform-aware config.
    2.  **Import Proposal**: The Agent or Obsidian plugin calls `curator_import_source(..., dry_run=true)` before mutation. The backend returns the computed hash, detected duplicate status, proposed destination or proxy anchor, and whether the operation would be copy mode or Reference Mode.
    3.  **Human Approval**: The client presents the destination/policy to the Human. External PDFs must not be copied into `04_Resources/` or registered as references without visible approval.
    4.  **Import**: The Agent calls `curator_import_source(policy="reference")` or `curator_import_source(destination_policy="mirror_03_to_04")` with mutation enabled. The Engine calculates the file's Content Hash, creates the source record, and records `is_reference`, `external_path`, `logical_source_id`, `import_origin`, and `import_policy` in the database.
    5.  **Status Check**: When fetching the status of an external resource via `curator_source_status`, the Engine uses the `external_path` cache.
    6.  **Detection**: If the file is modified (e.g., Apple Pencil annotations) causing "Hash Drift", or if it is moved, the `external_path` cache fails during the next scan. The Engine executes high-speed `rglob` re-discovery and flags the source as `STATUS: MOVED`.
    7.  **Healing (HITL)**: The Human is prompted via UI ("Location moved. Accept re-binding?"). Upon Human approval, the Agent calls `curator_rebind_source(logical_source_id, new_path)` to securely re-establish the connection, updating the DB and healing the proxy note.

### 2.4 Source-Aware PDF Search
*   **Situation**: The user is reading a PDF in Obsidian and asks a question that depends on the current page, nearby pages, and previously ingested source knowledge.
*   **Logic Flow**:
    1.  The Obsidian plugin captures immediate viewer context: current page text, current page image when enabled, nearby page text window, document outline if available, and PDF-local lexical RAG hits.
    2.  The plugin calls `curator_source_status` to determine whether the PDF is untracked, queued, running, indexed, stale, moved, or errored.
    3.  If the source is indexed, the plugin may call `curator_search_sources(query, source_id/source_path, limit=N)` to retrieve backend RAG hits with page provenance.
    4.  The final provider prompt includes the plugin's immediate viewer context and backend hits as distinct sections. The backend hits must not overwrite viewer context; the viewer context gives immediacy, while the backend gives durable provenance.

### 2.5 MCP Mutation Rules
*   **No silent note edits**: MCP tools must not edit `03_Notes/`.
*   **No direct plugin state writes**: The plugin must not modify `.curator/state.sqlite`.
*   **Explicit vault root**: `VAULT_ROOT` or an explicit `workspace_path`/`vault_root` argument must resolve to a valid vault. If resolution fails, MCP must return an error instead of falling back to CWD.
*   **No overwrite import**: Source import must never overwrite an existing file in `04_Resources/`. Same-hash duplicates reuse the existing record; different-hash filename collisions require a suffix or a human-selected destination.
*   **Dry-run first for destructive ambiguity**: Any operation that changes persistent source identity, such as rebind or import collision repair, must support a dry-run/proposal result before mutation.

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
