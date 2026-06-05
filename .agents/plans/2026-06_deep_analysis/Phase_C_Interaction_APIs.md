# Phase C: Interaction APIs & CLI — Senior Committee Deep Analysis

**Target Files**: `mcp_server.py` (~6000 lines), `cli.py` (~5800 lines), `plugin_api.py`

**Panel**: Charlie (Security), Alice (Architect), Frank (Backend), Evan (Plugin), Hannah (QA)

---

## Debate Transcript

### 1. Agent Bypass Vulnerability: The Missing RBAC Layer

**Charlie (Security Lead)**:
"I researched **LangGraph's** agent security model. In production LangGraph deployments, agents are issued scoped tokens that restrict them to 'propose' operations. Write operations require a human-gated approval step built into the graph's control flow.

Our `mcp_server.py` exposes `curator_propose_correction` as the 'safe' agent tool. But here's the problem: the MCP server also exposes general-purpose tools that let agents execute arbitrary CLI commands. An agent could bypass `curator_propose_correction` entirely and run `wiki sync` or `wiki curate` directly, force-committing changes without human review.

The fix is not just documentation — it's a **runtime enforcement layer**. Every MCP tool invocation must pass through a middleware that checks `is_agent_context=True` and blocks any write operation."

**Frank (Backend Specialist)**:
"Looking at `cli.py`, the Typer commands embed business logic directly inside command handlers. For example, the `curate` command handler directly calls `pipeline.run_l3_concepts()` and `pipeline.run_l4_exhibitions()`. This tight coupling makes it impossible to intercept and block agent-initiated writes without wrapping every command handler.

The correct architecture: extract all business logic into a `curator.core` service layer. The CLI becomes a thin presentation wrapper. The MCP server calls the same service layer but with an `agent_context` flag that enforces read-only or propose-only semantics."

### 2. CLI Fragmentation: 15+ Commands Causing Agent Hallucinations

**Alice (Chief Architect)**:
"The current CLI has organically grown to 15+ top-level commands. When an agent like Claude reads `wiki --help`, it sees a wall of commands and often hallucinates incorrect flag combinations. The '6 Pillars' consolidation (`source`, `build`, `maintain`, `config`, `agent`, `query`) reduces cognitive load for both humans and agents."

**Evan (Plugin Specialist)**:
"From the plugin perspective, the current CLI output is raw text. The plugin has to parse this text with brittle regex patterns to extract structured data. When we consolidate the CLI, every command must support a `--json` flag that emits structured output. This way the plugin can consume clean JSON payloads instead of scraping terminal output."

**Hannah (QA Engineer)**:
"We need a `--dry-run` mode for every write command. Without it, I cannot safely test agent workflows in CI without risking actual data mutations on the testbed."

### 📝 Consensus & Action Items

1. **[Backend]** Extract business logic from `cli.py` command handlers into `curator.core` service layer.
2. **[Security]** Implement `agent_context` middleware in `mcp_server.py` that enforces write-blocking for all agent-initiated calls.
3. **[Plugin API]** Add `--json` output mode to all CLI commands for structured plugin consumption.
4. **[QA]** Add `--dry-run` mode to all write commands to enable safe E2E testing in CI.
