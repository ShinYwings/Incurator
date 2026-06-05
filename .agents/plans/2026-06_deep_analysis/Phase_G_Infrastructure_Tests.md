# Phase G: Infrastructure & Tests — Senior Committee Deep Analysis

**Target Files**: `scripts/`, `backend/tests/`, `testbed/`

**Panel**: Hannah (QA), Alice (Architect), Frank (Backend), Charlie (Security)

---

## Debate Transcript

### 1. Obsolete Test Suites: Dead Weight in CI

**Hannah (QA Engineer)**:
"I identified four test files in `backend/tests/` that validate deprecated backpropagation logic:
- `test_v021_backprop_evidence.py` — tests the old L4-to-L3 reverse-parsing
- `test_v031_backprop_lifecycle.py` — tests EXH-dependent backprop lifecycle
- `test_v031_backprop_sync.py` — tests backward sync propagation
- `test_lint_ephemeral_gc.py` — tests ephemeral Exhibition cleanup (L4 files are now permanent)

These tests will break immediately when the legacy code is deleted. They should be deleted alongside the code, not left as dead weight in CI."

**Frank (Backend Specialist)**:
"But the *domain scenarios* inside these tests are valuable. The 'ResNet block as a Neural ODE Euler step' scenario in `test_v021_backprop_evidence.py` is a beautiful test case for knowledge correction propagation. We need to migrate this scenario — not the test infrastructure — into a new test suite that validates the `curator_propose_correction` → HITL approval → knowledge propagation pipeline."

### 2. Testbed Manager: Not Adapted to Dynamic Lens Architecture

**Alice (Chief Architect)**:
"The project's own `AGENTS.md` requires: 'All feature additions must be validated in the testbed/ vault.' The `wiki testbed init` command creates a testbed from templates in `scripts/dev/`. But these templates were designed for the static Exhibition architecture, not the Dynamic Lens model.

For the Dynamic Lens architecture, testbed initialization must:
1. Seed the SQLite DB with `insight_candidates` in various states (`pending`, `needs_review`, `promoted`, `rejected`)
2. Seed `graph_entities` and `graph_relations` for graph-based retrieval testing
3. Include a `curate.yml` that exercises the full `CurationPolicy` routing logic
4. Include mock sources with known errors to test the `curator_propose_correction` workflow"

### 3. Chaos Engineering for LLM Resilience

**Hannah (QA Engineer)**:
"Building on Phase I's circuit breaker recommendations, we need dedicated Chaos Engineering tests in CI. I researched the 2024/2025 best practices for LLM agent resilience testing:

| Test Scenario | What It Validates |
|---|---|
| Mock LLM returns `HTTP 429` rate limit | Circuit breaker trips after N failures |
| Mock LLM returns `HTTP 503` server error | Retry with jitter + backoff, then circuit trip |
| Mock LLM returns garbage JSON | `prompting.py` validator catches and retries cleanly |
| Simulated API budget exhaustion | Session terminates gracefully before budget cap |
| Two concurrent `wiki curate` invocations | SQLite WAL handles concurrent writes without corruption |

These are not exotic requirements. Any production LLM system needs these tests. The industry term is **'Agent SRE'** — applying Site Reliability Engineering principles to agent-based systems."

**Charlie (Security Lead)**:
"One more critical test: we need a guard test that attempts to write `status='approved'` to `insight_candidates` from an agent context and asserts that the middleware blocks it. This is the runtime enforcement of the HITL contract from Phase F."

### 📝 Consensus & Action Items

1. **[QA]** Delete the 4 obsolete backprop test files. Migrate the ResNet/Neural ODE scenario to a new `curator_propose_correction`-based TDD test suite.
2. **[Infrastructure]** Adapt `wiki testbed init` to seed GraphRAG-era data: `graph_entities`, `insight_candidates` in multiple states, and a full `curate.yml`.
3. **[QA]** Implement a Chaos Engineering test suite for LLM resilience: mock `429`/`503`, garbage JSON, budget exhaustion, and concurrent writes.
4. **[Security/QA]** Add a guard test for the HITL contract: assert that agent-context writes to `status='approved'` are blocked.
