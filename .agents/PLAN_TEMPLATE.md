# Incurator Planning Blueprint (The Arena Model)

This template is not just a simple notepad. It is a design specification where multiple sub-agents reach conclusions through **Fierce Asynchronous Debate**.
It prohibits flat, single-waterfall style planning. Instead, it follows a structure where multiple agents pour out proposals and critique documents in subfolders, and only the final consensus is left as a Master Plan in the root folder.

---

[!CRITICAL]
## 1. Architecture Planning Philosophy & Process (The Arena Workflow)
1. **The Briefing**: The main agent creates a new debate folder (`.agents/plans/[feature_name]_arena/`) and writes a problem definition document (`00_problem.md`) to be solved.
2. **Fierce Debate**: Sub-agent personas in charge of each domain (Security, DB, Frontend, Performance, etc.) write proposals (`01_proposal_*.md`) from their respective perspectives.
3. **Cross-Critique**: Agents read each other's proposals and write scathing critique documents (`02_critique_*.md`) and corresponding defense/revision logic (`03_defense_*.md`) to find a technical Consensus.
4. **Master Plan Synthesis**: Once the debate is complete, the main agent leaves the debate folder and writes a single perfect Master Plan (`[XX]_[feature_name].md`) in the `.agents/plans/` root directory. The debate folder is then preserved or archived.

---

## 2. Multi-Agent Debate Protocol (The Planning Committee)
(Mandatory verification simulation roles that agents must go through when writing Major/Minor plans)

- **`lead_architect` (The Proposer)**: Responsible for drafting the initial `01_proposal.md`. Defines the core architecture, data flow, and APIs. Focuses on feasibility and meeting the user's intent.
- **`red_teamer` (The Adversary)**: Actively attacks the architect's proposal (`02_critique_redteam.md`). Looks for hallucination risks, infinite loops, race conditions, edge cases, and security vulnerabilities. Their sole goal is to break the plan.
- **`domain_specialists` (The Validators)**:
  - **`schema_guardian`**: Defends DB integrity, schema compatibility, and migration safety.
  - **`source_pair_analyst`**: Analyzes the impact on the RAG pipeline (L1~L4 DAG) and backprop mechanisms.
- **`system_synthesizer` (The Closer)**: Reads the proposal and all critiques. Resolves conflicts, enforces compromises, and authors the final `Master Implementation Plan`.

---

[!CRITICAL]
## 3. Arena Document Skeleton
This is the skeleton used by sub-agents to create documents in the subfolder (`_arena/`).

### 2.1 Proposal Skeleton
```markdown
# [Domain] Proposal: [Idea Title]
Date: YYYY-MM-DD | Agent Persona: [e.g. DB Architect / Frontend Expert]

## 1. Core Logic & Implementation
(Core designs, SQL statements, Python pseudocode, architecture diagrams, etc., to be used for implementation)

## 2. Pros & Cons
(Specify the pros and cons of your proposed structure and limitations in the current codebase)
```

### 2.2 Critique/Defense Skeleton
```markdown
# Critique on [Target Proposal]
Date: YYYY-MM-DD | Agent Persona: [e.g. Security Auditor]

## 1. Vulnerabilities & Flaws
(Fiercely critique side effects of the existing proposal, schema violations, missing edge cases, etc.)

## 2. Suggested Alternatives
(Go beyond simple criticism and provide specific alternatives on how to fix it)
```

---

## 4. Master Plan Skeleton
Once the debate is over, copy the skeleton below and write `.agents/plans/[XX]_[feature_name].md`.

```markdown
# [Version] Master Implementation Plan

Date: YYYY-MM-DD
Status: APPROVED — Arena debate concluded. Specs are authored, tests are spec-first.

## Strict quality condition
- (e.g. RAG search performance must be equal to or better than the existing engine)

## Locked design decisions (Arena Consensus)
- (Summary of architectures, algorithms, schemas, and backward compatibility rules confirmed in the Arena)

## Evidence Ledger
Items collected and verified during the planning phase to ensure documentation, DB migrations, and plugin code do not diverge from the actual repository and vault state.
- **Current Repository & Schema Reality**: Pre-fact-check whether the current schema (`sources`, `synthesis_nodes`, etc.) accurately reflects the system spec documentation.
- **Current Dirty Worktree**: Identify uncommitted changes currently being worked on by the user or other agents (to prevent forced overwrites).
- **Rollback Requirements**: Specify safe backup and rollback points before destructive operations (e.g., DB changes).

## Execution Phases (Follow TDD and CI at each phase)
- **P1 — [DB Schema]**: Schema update. (Verify: Migrations and DB integrity work normally)
- **P2 — [Core Logic]**: Backend logic implementation. (Verify: Pass `pytest tests/test_*.py` and `ruff`)
- **P3 — [Integration]**: Plugin/UI integration, etc.
- **P4 — [Testbed Smoke]**: E2E Parity verification such as `wiki add/sync/query`.
```

---

> **LIFECYCLE & VERSIONING RULE REMINDER**:
> 1. **Update Version & Changelog**: Once all implementations and local CI pass, bump the version specification (`pyproject.toml`, etc.) and update `CHANGELOG.md`.
> 2. **Update Report**: Delete or move resolved items in `USER_REPORT.md`.
> 3. **Push and PR**: The entire process ends by raising a GitHub PR according to the `Universal Strict Workflow` specified in `AGENTS.md`.
