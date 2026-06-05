# Phase F: Documentation & Architecture Contracts — Senior Committee Deep Analysis

**Target Files**: `docs/specs/`, `docs/guides/`, `AGENTS.md`, `CLAUDE.md`

**Panel**: Diana (Docs), Alice (Architect), Charlie (Security), Hannah (QA)

---

## Debate Transcript

### 1. The Documentation is Lying: Spec Drift as a Hallucination Vector

**Diana (Documentation Specialist)**:
"This project follows strict Docs-First Development: specs are supposed to be updated *before* code changes. However, Frank and I cross-validated the documentation against the actual codebase (`cli.py` and `mcp_server.py`) and found catastrophic drift.

**CLI Command Drift (`wiki --help` vs Docs)**:
- `WORKFLOW_GUIDE.md` references the `wiki curate` command extensively (e.g., `wiki curate --workspace 01_Workspaces/MyProject`).
- **Reality**: `wiki curate` was completely removed from the root CLI in v0.3.1. It only exists as a plugin subcommand (`wiki plugin curate`). The actual top-level commands are `add`, `build`, `sync`, etc. Agents reading the guide will hallucinate the `wiki curate` command.

**MCP Tool Drift (`MCP_USER_GUIDE.md` vs `mcp_server.py`)**:
- **Phantom Tools**: The docs list `curator_source_status`, `curator_get_source_page`, and `curator_curate_workspace`. These tools **do not exist** in `mcp_server.py`.
- **Ghost Tools**: The codebase contains 9 tools that are **completely undocumented**, including Zotero integration tools (`curator_search_zotero_items`, `curator_get_zotero_item_metadata`, `curator_resolve_zotero_pdf`), config tools (`curator_get_provider_config`), and contradiction management tools (`curator_resolve_contradiction`).

When an AI agent (Claude, Codex, Antigravity) reads these guides as authoritative instructions, it will attempt to execute non-existent commands and remain blind to powerful new tools. **The documentation is actively inducing agent hallucinations.**"

**Alice (Chief Architect)**:
"The fix requires a systematic grep across the entire `docs/` tree for legacy terms: `sync --backward`, `backprop_sync`, `update_node`, `Exhibition parsing`, `frozen file`. Every hit must be either deleted or rewritten to describe the current architecture: Dynamic Lens, `curator_propose_correction`, Insight Candidates."

### 2. Missing HITL Contract in Agent Rules

**Charlie (Security Lead)**:
"I read `AGENTS.md` carefully. The file contains excellent operational rules for agent behavior (Docs-First Development, Testbed validation, Spec versioning). But it is missing a critical architectural protection clause:

**There is no explicit rule that prohibits agents from force-injecting data into the `insight_candidates` table with status='APPROVED'.** Without this rule, a future agent might bypass the HITL workflow entirely by directly writing to the DB with the correct status string. This is not a theoretical risk — it's exactly what Phase B's `_run_explore()` already does (silently writing `pending` candidates).

The `AGENTS.md` Core Rules must include:
```
'All Knowledge Corrections MUST remain in CANDIDATE status until 
explicitly approved by a Human via the HITL interface. Agents MUST 
NEVER inject or force-commit records with APPROVED status.'
```"

**Hannah (QA Engineer)**:
"We should also add a test guard — a pytest assertion that scans the entire codebase for any code path that sets `status='approved'` or `status='promoted'` outside of the explicit human approval function in `insight_lifecycle.py`."

### 📝 Consensus & Action Items

1. **[Docs]** Run a systematic `grep_search` across `docs/` for all deprecated terms and rewrite them to reflect the Dynamic Lens architecture.
2. **[Docs]** Update `_KR.md` counterparts in the same commit as their English sources.
3. **[Security/Docs]** Add an explicit HITL contract to `AGENTS.md` and `CLAUDE.md` prohibiting direct status manipulation.
4. **[QA]** Add a codebase-level guard test asserting no unauthorized `status='approved'` writes.
