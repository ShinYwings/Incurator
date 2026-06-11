# Critique On Retrieval, Provenance, And Answer-Link Proposals

Date: 2026-06-11 | Agent Persona: red_teamer
Status: DRAFT CRITIQUE

## 1. Vulnerabilities & Flaws

### R1 - A unified ContextService can become a rewrite

Replacing every query surface at once risks a long-lived branch, hidden
regressions, and incompatible clients. The plan needs delegation/parity phases
and explicit removal gates.

### R2 - Serving can hide compiler defects with polished locators

A perfectly structured link to a broadly related span is still false
provenance. Plan A must reject unsupported compiler output rather than render it
convincingly.

### R3 - Snapshot consistency can create unusable expansion

Rejecting expansion after any state change may frustrate users in active vaults.
The contract must distinguish meaningful evidence-epoch conflicts from unrelated
changes and permit a clear refresh path.

### R4 - Token budgets can be falsely precise

Provider tokenizers differ, remote models may be unknown, and plugin prompt
assembly adds client-owned context after backend selection. Budget reports need
declared estimators and safety margins.

### R5 - Graph/agentic retrieval can hurt factual quality

PPR, communities, DRIFT, and iterative retrieval can add plausible but irrelevant
evidence. They need route-specific gates and hard stops, not one blended score.

### R6 - Link validation can pass in testbed and fail on user devices

External Reference Mode paths, aliases, renamed notes, printed PDF page numbers,
and duplicate block ids are device/vault dependent. Fallback and warning
behavior must be first-class.

### R7 - Cross-client parity can overstuff Obsidian prompts

Forcing full backend pack parity after immediate selected/viewer context can
exceed provider budgets and reduce answer quality. Parity must apply before
client-specific final packing, with explicit omissions.

### R8 - Storing packs can become an unbounded answer cache

Durable pack state risks reproducing the retired frozen-Exhibition problem:
staleness, duplication, and growth. Prefer bounded transaction records and
deterministic expansion handles over durable content duplication.

### R9 - Compatibility aliases can preserve broken semantics forever

Keeping existing names is reasonable, but old response shapes and behavior
cannot remain indefinite if they contradict the normalized contract. Removal
criteria and no-backward-compatibility decisions must be explicit.

### R10 - Ranking tuning can overfit the frozen suite

The frozen suite is necessary but insufficient. Holdouts, adversarial cases,
live-vault samples, per-family reports, and latency/token costs remain required.

## 2. Suggested Alternatives

- Migrate one service operation/surface at a time behind delegation parity tests.
- Treat compiler trust as a hard entry gate and unsupported evidence as
  explicitly unavailable.
- Define evidence epochs narrowly and supply refresh/re-fetch behavior.
- Record tokenizer/estimator identity and reserve safety margin.
- Make graph/iterative retrieval opt-in by measured route policy and bounded stop
  conditions.
- Treat locator fallback/warnings as successful safe behavior, not test failure.
- Persist compact transaction/selection metadata, not duplicated evidence bodies.
- Publish explicit compatibility removal gates.
