# Critique On Unified Agent Context Service Proposals
Date: 2026-06-11 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

### A single service can become a monolith

Centralizing manifest, retrieval, packing, verification, feedback, and synthesis
may create a god object. Failure in one policy path could affect every client.

### "One QTR" is ambiguous

An iterative or expanded request may need multiple retrieval actions. Forcing
everything into one row can erase child-step detail; creating multiple QTRs can
repeat the current disconnected-trace defect.

### Snapshot identity may be underspecified

`db_epoch`, `search_epoch`, policy hash, and model hash may not capture source
file drift, external Reference Mode changes, embedding model changes, or derived
dependency changes. Strict snapshot conflicts could make expansion unusable in a
frequently changing vault.

### Token accounting can be falsely precise

Provider tokenizers may be unavailable or differ from actual tool/system prompt
accounting. Pack tokens alone do not equal remaining provider context.

### Cross-client parity can erase useful local context

The Obsidian agent has selected text, open tabs, PDF viewer state, images, and
chat history unavailable to external agents. Requiring identical final prompts
would be incorrect.

### Progressive disclosure can hide evidence

An index pack can omit the one decisive contradiction or supporting formula.
Expansion handles are useless if the agent does not know what was omitted.

### Feedback can bias or poison retrieval

Relevance feedback and corrections are subjective, snapshot-specific, and
potentially malicious. Feeding them directly into ranking or truth state can
degrade future answers.

### Compatibility can preserve divergence

Keeping current public names risks retaining their old semantics behind thin
wrappers. A "compatibility surface" must not become a second implementation.

### Persistence can leak sensitive content

Durable packs and feedback may duplicate private source excerpts and chat-like
user statements, increasing storage and sync exposure.

## 2. Suggested Alternatives

- Define internal ports: snapshot resolver, policy evaluator, Plan-A retrieval
  execution port,
  pack assembler, provenance validator, trace recorder, and feedback recorder.
- Use one root QTR with ordered child steps/actions, not one flat event.
- Define snapshot closure explicitly and provide typed conflict/rebase behavior.
- Treat service token accounting as evidence-pack accounting; let each client
  reserve its own system/history/local-context budget.
- Require semantic normalized-pack parity, not identical final prompts.
- Include omission categories, coverage signals, contradiction indicators, and
  high-priority expansion reasons.
- Quarantine feedback from ranking/truth changes until reviewed/evaluated.
- Define compatibility deprecation tests that prove all old surfaces delegate.
- Minimize persisted excerpts; persist ids/hashes and only content required for
  reproducibility under an explicit retention policy.
