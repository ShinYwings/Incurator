# Client Integration Proposal: External And Obsidian Pack Parity

Date: 2026-06-11 | Agent Persona: agent_integration_architect
Status: DRAFT PROPOSAL

> **Consensus scope transfer:** MCP/plugin/Obsidian integration, client budgets,
> Sources & Trace, and feedback lineage are owned by
> `../F_agent_context_service.md`. This proposal remains as a dependency record
> for the Plan-A retrieval-result handoff.

## 1. Core Logic & Implementation

### Parity definition

Equivalent backend requests from MCP and Obsidian receive equivalent normalized
context packs: same transaction/snapshot, route, selected backend evidence,
policy results, budgets, warnings, and locators.

Parity does not erase client-specific context:

- Obsidian selected/open-note/PDF viewer context remains highest-priority
  immediate context.
- External agents may supply their own active files/scope.
- The normalized backend pack is an additional trusted prior-knowledge layer.

### Obsidian grounding rule

1. Assemble user-selected and visible immediate context.
2. Calculate remaining provider budget after system prompt, pinned context, and
   chat history.
3. Fetch a bounded backend context pack with that remaining budget.
4. Supply evidence cards/excerpts, not a truncated backend answer by default.
5. Render the exact backend pack used for reasoning in Sources & Trace.
6. Use backend answer synthesis only when explicitly requested by the surface.

### Compatibility surfaces

- MCP exposes full context operations.
- `curator_fetch_context` maps to `context_fetch`.
- `curator_query` fetches the same pack and optionally synthesizes.
- plugin CLI JSON uses the same response contract.
- raw source/PDF tools remain valid for immediate exact expansion and untracked
  PDF viewer context.

### Sources & Trace requirements

Display:

- selected route and reason;
- policy inclusions/exclusions;
- used/omitted budget;
- freshness/snapshot;
- degradation warnings;
- selected evidence and ranking explanation;
- exact locator action;
- safe fallback reason;
- transaction and prompt/retrieval children.

### Feedback lineage

Relevance, incorrect, stale, insufficient, duplicate, contradiction,
new-insight, correction, and promotion events retain:

- originating transaction/pack/snapshot;
- target records and evidence ids;
- user review state;
- resulting candidate/promotion identity.

Feedback never silently mutates source truth.

## 2. Pros & Cons

### Pros

- Stops external and Obsidian agents from reasoning over materially different
  backend evidence.
- Preserves immediate viewer context and backend durable knowledge roles.
- Makes feedback auditable.

### Cons

- Provider token accounting varies by model/client.
- Plugin migration is broad and must preserve existing immediate PDF behavior.
- Full trace display can overwhelm users without progressive disclosure.
