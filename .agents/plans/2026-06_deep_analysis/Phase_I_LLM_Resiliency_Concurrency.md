# Phase I: Multi-Agent LLM Resiliency — Senior Committee Deep Analysis

**Target Files**: `llm.py` (1629 lines), `mcp_server.py`, `db.py` (ingest_jobs schema)

**Panel**: Charlie (Security), Frank (Backend), Alice (Architect), Hannah (QA)

---

## Debate Transcript

### 1. The System Already Detects Capacity Errors — But Does Nothing

**Frank (Backend Specialist)**:
"I found something fascinating in `llm.py:166-176`. The `_is_capacity_error()` function already detects rate limit errors:

```python
def _is_capacity_error(text: str) -> bool:
    return (
        'No capacity available' in text
        or 'MODEL_CAPACITY_EXHAUSTED' in text
        or 'QUOTA_EXHAUSTED' in text
        or 'RESOURCE_EXHAUSTED' in text
        or '429' in text
    )
```

And in `AntigravityCliClient` (line 721), there's even a `_capacity_blocked_until` timestamp that records when a capacity error occurred. But there is **no circuit breaker logic** that actually uses this timestamp to prevent subsequent calls. The next call will hit the same capacity error, waste time, and fail again.

I researched the **Semantic Circuit Breaker** pattern recommended for multi-agent LLM systems. The standard implementation has three states:
- **Closed** (normal): Calls proceed normally
- **Open** (tripped): All calls are immediately rejected for a cool-down period
- **Half-Open** (testing): A single probe call is allowed to test if the service has recovered

Our `_capacity_blocked_until` is a proto-implementation of the Open state — but it's never checked before making a new call."

### 2. Budget Guardrails Already Have Infrastructure

**Charlie (Security Lead)**:
"Here's what's remarkable: `db.py` already tracks token usage and cost at the job level. The `ingest_jobs` table has columns `input_tokens`, `output_tokens`, and `estimated_cost_usd` (lines 488-505). The `get_stats()` function (lines 579-612) even aggregates total costs.

But there is **no hard cap**. No threshold that says 'if this single pipeline run exceeds $X, stop'. An agent running in a loop could drain the entire API budget without any guardrail."

**Alice (Chief Architect)**:
"The fix is straightforward. Before every LLM call, the middleware checks:
1. Is the circuit breaker in Open state? If yes, reject immediately.
2. Has this session exceeded its token budget? If yes, halt and notify.
3. Has this tool failed N times consecutively? If yes, trip the circuit.

This is a 50-line middleware that wraps the existing `chat()` / `chat_stream()` methods."

**Hannah (QA Engineer)**:
"We need **Chaos Engineering** tests. I want to simulate `HTTP 429` rate limit responses in CI and assert that the circuit breaker trips correctly. Currently, when our mock LLM server drops a request, the test suite hangs indefinitely because there's no timeout or circuit breaker."

### 📝 Consensus & Action Items

1. **[Backend]** Implement a `CircuitBreaker` wrapper around all LLM client classes (`OllamaClient`, `AntigravityCliClient`, `ClaudeCodeClient`) that enforces the Closed/Open/Half-Open state machine.
2. **[Architecture]** Add `max_tokens_per_session` and `max_cost_per_session` configuration fields that serve as hard budget caps.
3. **[Backend]** Wire the existing `_capacity_blocked_until` timestamp into actual call rejection logic.
4. **[QA]** Implement Chaos Engineering tests that simulate `429` and `503` responses to verify circuit breaker behavior.
