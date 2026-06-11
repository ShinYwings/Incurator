# Integration Proposal: Cross-Client Parity And Feedback Lineage
Date: 2026-06-11 | Agent Persona: agent_integration_architect

## 1. Core Logic & Implementation

### Cross-client parity

MCP and plugin/CLI adapters translate transport details only. They must expose
the same normalized pack for equivalent requests.

Obsidian selected/open-note/PDF context remains highest-priority immediate
context. The plugin calculates remaining provider budget, requests a bounded
pack, and sends the pack as grounding. Backend answer synthesis is used only
when explicitly requested.

Sources & Trace renders:

- exact evidence items used;
- route and route reason;
- budget and omissions;
- snapshot/freshness/degradation;
- working structured locators and expansion/verification actions.

### Feedback contract

Feedback types:

- relevant;
- irrelevant;
- incorrect;
- stale;
- insufficient;
- duplicate;
- new insight;
- correction;
- promotion request.

Every event retains:

- originating `trace_id`, `pack_id`, and `snapshot_id`;
- client and request purpose;
- target record/item/claim;
- reviewed evidence ids and source spans;
- user statement and classification;
- review/promotion status and resulting artifact lineage.

Feedback cannot directly mutate `03_Notes/`, reference spaces, or derived truth.
Corrections and promotions follow existing review-gated insight lifecycle rules.

## 2. Pros & Cons

### Pros

- Agents reason over evidence instead of another model's synthesized answer.
- Feedback becomes auditable and can be evaluated for future retrieval impact.
- Sources & Trace reflects actual grounding.

### Cons

- Plugin migration touches complex context-priority and provider-budget logic.
- Semantic parity is harder than JSON-shape parity.
- Feedback retention requires privacy/storage policy and lifecycle decisions.
