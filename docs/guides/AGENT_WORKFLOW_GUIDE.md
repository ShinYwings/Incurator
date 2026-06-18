# Incurator Agent Workflow Guide

This document defines the official operational scenarios and tool interaction patterns for the Incurator MCP (Model Context Protocol) server. It bridges the high-level 4-layer pipeline theory with the practical execution flow triggered by Agent or Human commands.

## 1. Environment & Initialization Scenarios

### 1.1 Session Entry & Synchronization (`curator_check_workspace`)
*   **Trigger**: Automatically called by the Agent at the start of every session.
*   **Logic Flow**:
    1.  **Path Resolution**: Discovers the `vault_root` by walking upward from `workspace_path`.
    2.  **State Validation**: Checks for `curate.yml` existence and agent-rule readiness.
    3.  **Result**: Returns initialization status (`needs_initialization`), project metadata, and actionable setup issues.

### 1.2 Workspace Scaffolding (`curator_workspace_init`)
*   **Trigger**: Initiated when `check_workspace` returns `needs_initialization: true`.
*   **Logic Flow**:
    1.  **Requirement Specification**: Generates `curate.yml` with explicit `vault_root` to prevent path drift.
    2.  **Persona Scoping**: Runs an LLM interview to define the Artist Persona (Domain, Goals, Intent).
    3.  **Initial Build**: Immediately triggers `wiki build` to refine the shared DAG (L2 Atoms → L3 Concepts → L4 Synthesis) so the Agent has evidence to ground on. Curation itself is a dynamic query-time lens — no per-workspace Exhibition is generated.

---

## 2. Query & Knowledge Retrieval Scenarios

### 2.1 Persona-Driven Query & Search (`curator_query` & `search_curator`)
*   **Logic Flow (`curator_query`)**:
    1.  Applies the workspace `curate.yml` persona/KRS when a workspace is specified; Vault mode uses the global fallback persona.
    2.  Returns a sessionless answer with a `QTR-` trace over selected L3 Concepts, L4 Synthesis nodes, source sections, reports, and insight candidates.
*   **Logic Flow (`search_curator`)**:
    1.  Automatically applies `domains`, `topics`, and `min_confidence` filters from the local `curate.yml`.
    2.  Searches DB-native search rows over authoritative records; it does not trigger a staging pass.
    3.  Returns results scoped to the project's knowledge requirements, preventing "knowledge noise" from unrelated parts of the vault.

### 2.2 Evidence Traversal (`curator_traverse_evidence`)
*   **Situation**: Search result confidence score is below the high threshold (0.90) but above the low floor (0.60).
*   **Logic Flow**:
    1.  The Agent walks down the evidence chain: `SYN -> CON/REP -> ATM/source spans`.
    2.  Verifies the specific claims and source provenance before citing the information in a task output.

### 2.2.1 Context Pack Grounding (`curator_fetch_context`)
*   **Situation**: The agent will perform its own reasoning and needs bounded,
    traceable prior knowledge instead of a backend-written answer.
*   **Logic Flow**:
    1.  The agent calls `curator_fetch_context` with a workspace path, query,
        scope, and budget.
    2.  The backend returns one normalized pack with a `QTR-*` root,
        attached `RTR-*`, snapshot id, policy filters, budget accounting,
        evidence items, omissions, and expansion/verification handles.
    3.  The agent cites only evidence from that pack or from later expansions
        that match the same snapshot. A snapshot conflict requires refetch/rebase
        before using new evidence.

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
    1.  The Obsidian plugin captures immediate viewer context first: current page text, current page image when enabled, nearby page text window, document outline if available, and PDF-local lexical RAG hits. This local PDF.js path must not block on backend status.
    2.  If local context is sufficient, answer from it. Passive chat never imports or registers the PDF.
    3.  If local context is unavailable, the plugin checks read-only source status and requests backend PDF context. An unregistered PDF receives an ephemeral parse; a registered L1-complete PDF receives durable CTX sections.
    4.  Only an L3-complete registered PDF may add a PDF-focused `curator_query` result. Backend evidence supplements rather than replaces immediate viewer context.

### 2.5 MCP Mutation Rules
*   **No silent note edits**: MCP tools must not edit `03_Notes/`.
*   **No direct plugin state writes**: The plugin must not modify `.curator/state.sqlite`.
*   **Explicit vault root**: `VAULT_ROOT` or an explicit `workspace_path`/`vault_root` argument must resolve to a valid vault. If resolution fails, MCP must return an error instead of falling back to CWD.
*   **No overwrite import**: Source import must never overwrite an existing file in `04_Resources/`. Same-hash duplicates reuse the existing record; different-hash filename collisions require a suffix or a human-selected destination.
*   **Dry-run first for destructive ambiguity**: Any operation that changes persistent source identity, such as rebind or import collision repair, must support a dry-run/proposal result before mutation.

---

## 3. Knowledge Evolution & Integrity Scenarios

### 3.1 Backward Propagation (Knowledge Correction)
*   **Situation**: A Human (Director) or Agent (Artist) identifies an error in generated knowledge.
*   **Logic Flow**:
    1.  The Agent calls `curator_propose_correction` with the claim, correction, and evidence context.
    2.  The Engine classifies the feedback before any patch.
    3.  The Engine returns a recommended action and affected generated node ids without patching automatically; source truth is never edited autonomously.
    4.  A separate reviewed workflow applies any approved change, after which `wiki sync` can verify graph consistency.

### 3.2 Synthesis Promotion (The Infinite Loop - Path B)
*   **Situation**: A high-value insight is derived during a conversational session.
*   **Logic Flow**:
    1.  The Human issues a promotion command via `curator_add_knowledge`.
    2.  The Engine writes the reviewed answer or insight only to `02_Wiki/`.
    3.  The promotion becomes source material only if a later explicit ingest operation registers it; promotion itself does not mutate the generated DAG.

---

## 4. Integrity Constraints

*   **No Silent Fallbacks**: During initialization or workspace scoping, the system MUST NOT fallback to `last_root` or CWD if the target path is not within a valid vault. It must fail explicitly to prevent data corruption.
*   **Immutability Hierarchy**: Original sources (`03_Notes`) are never modified by the MCP server. All corrections happen within the DAG (`.curator/`) or via promotion to `02_Wiki/`.

---

## 5. Failure Atlas Diagnostics (Program 1)

The Failure Atlas (`docs/specs/failure_atlas/FAILURE_ATLAS.md`) is the
versioned record of every known end-to-end quality failure (F1–F13) in the
RAG/DAG system, with deterministic reproductions and frozen oracles. Agents
working on retrieval, the compiler pipeline, or client surfaces MUST consult it
before changing behavior in those areas.

### 5.1 Running the diagnostic suite

```bash
uv venv "$(git rev-parse --show-toplevel)/.venv-dev"
uv pip install --python "$(git rev-parse --show-toplevel)/.venv-dev/bin/python" \
  -e "$(git rev-parse --show-toplevel)/backend[dev,mcp]"
# Atlas record integrity (schema, lifecycle, snapshot identities)
scripts/backend-check pytest backend/tests/test_failure_atlas_contract.py -q
# Deterministic reproductions (baseline + strict-xfail oracles)
scripts/backend-check pytest backend/tests/test_failure_atlas_repro.py -q
# Mutation/degradation/atomicity experiments
scripts/backend-check pytest backend/tests/test_failure_atlas_experiments.py -q
# Frozen retrieval baseline (CI never reruns the consumed D2 holdout)
scripts/backend-check pytest backend/tests/test_failure_atlas_eval.py -q
```

### 5.2 Rules when your change touches an atlas case

*   **Baseline tests pin current behavior**: `test_f*_baseline_*` passing means
    the documented defect still exists. If your change makes a baseline test
    fail, you have changed measured behavior — update the corresponding
    `docs/specs/failure_atlas/cases/F*.yml` record in the same commit.
*   **Oracle tests are the handoff**: `test_f*_oracle_*` are
    `xfail(strict=True)`. Fixing a failure makes its oracle XPASS, which fails
    CI on purpose. Remove the marker, flip the case record's status with a new
    `status_history` entry, and update the baseline test — all in the fixing
    commit. Never weaken an oracle to make it pass; oracle renegotiation
    requires a new atlas version per `FAILURE_ATLAS.md` §3.
*   **Capture before repair**: no production behavior may be repaired before
    its current failure baseline is captured in the atlas.
*   **No holdout tuning**: queries in the `holdout` partition of
    `docs/specs/failure_atlas/qrels.yml` are frozen and must never be used to
    develop or tune retrieval changes. D2 recorded one valid `Q06` result
    after two audit-invalidated methodology runs under the identical frozen
    ranking configuration; CI validates `D2_HOLDOUT_RESULT.yml` and does not
    rerun it.
*   **Use fine-grained gates**: report Recall@k, MRR, citation correctness and
    completeness, provenance resolution, hard-negative outranks, cost, and
    latency separately per query family. Aggregate-only quality claims are not
    release evidence.

## 6. Claim Support & Compiler Integrity Rules (v0.8.0)

Plan B (Evidence Compiler Integrity) adds claim-level grounding on top of the
span citation rules of §4. Agents consuming or producing knowledge MUST:

*   **Respect support labels**: a knowledge unit's `support_status`
    (`verified`/`unchecked`/`failed`/`stale`) and `retired_at` are part of its
    truth contract. Only `verified`, non-retired claims may be presented as
    grounded knowledge; `unchecked` legacy claims are display-only context and
    `failed`/`stale`/retired claims must never be served as facts.
*   **Never equate a span id with support**: minimal support lives in
    `claim_supports` rows (roles `primary`/`contextual`/`formula`) whose
    `evidence_hash` must match the current span content. Citing a real but
    irrelevant span is the F6 anti-pattern and a release-blocking defect.
*   **Preserve formulas through distillation**: any distillation/summary step
    must keep extraction formulas visible or record an explicit
    `omitted_incidental` exception. Silent formula drops are defects. Visual
    recovery candidates are additive, lifecycle-gated, and never overwrite raw
    parser/source evidence. A candidate is not served unless it reaches the
    `0.80` confidence threshold, carries a validator trace, exactly matches an
    owning-claim formula, and passes claim-support revalidation.
*   **Respect generation boundaries**: staged (`GEN-` `status='staged'`)
    compiler output is invisible to query/evidence surfaces by contract. Do
    not read or cite staged rows; a failed compile leaves only the prior
    authoritative generation.
*   **Gate on the audit**: `wiki lint` (or MCP `curator_lint`) reports the
    Compiler Integrity audit. Treat release-blocking findings (unsupported
    active claims, evidence-hash mismatches, broad-fallback grounding,
    formula-status inconsistencies) as CI failures, not warnings.
