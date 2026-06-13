# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

## 📝 User Inbox

### 2026-06-13 — P6 review Flaw 3: generation-scoped read visibility (§26.3 gap)

Source: reviewer of the Plan B P6 staged-generation work. **Real bug, but
non-trivial — routed here for a plan-first fix (not hot-patched).**

**Reviewer's report (verbatim):**

> **Flaw 3: Eligibility Leakage (Staged Rows Visible Outside Compiler)** —
> `backend/src/curator/db.py` (`list_eligible_knowledge_units`). Defect:
> `list_eligible_knowledge_units` filters only by
> `retired_at IS NULL AND support_status = 'verified'`. It completely ignores
> `generation_id` and `compiler_generations.status`. This violates
> SYSTEM_BEHAVIOR §26.3: "Query, evidence, and search surfaces read only
> authoritative-generation rows. Staged rows are invisible everywhere outside
> the compiler." If a staged unit is verified but its generation fails the
> publish gate, that unit immediately leaks into search materialization.
> Reviewer's proposed resolution: join `compiler_generations` and bound
> visibility to `(cg.status = 'authoritative' OR ku.generation_id IS NULL)`.

**Why this needs a plan (not the reviewer's one-liner):**

- The proposed `(authoritative OR generation_id IS NULL)` filter is INCOMPLETE
  and conflicts with the committed Flaw 2 fix. Flaw 2 defers `generation_id`
  assignment until AFTER the publish gate, so during compile units carry
  `generation_id IS NULL` and rely on the NULL escape hatch — meaning
  mid-compile and failed-audit units (still NULL) keep being served. To truly
  hide staged units they must be attributed to a staged generation BEFORE the
  gate, which is exactly what Flaw 2 forbids (it overwrites the prior
  authoritative generation's per-unit attribution).
- `list_eligible_knowledge_units` serves TWO masters: compiler-internal callers
  (`compile_source_l2` ATM/graph emit; `recompile_source` verified_ids) that
  MUST see the units being compiled, and serving callers (search
  materialization, query/evidence) that must see ONLY authoritative rows. A
  single blanket filter cannot satisfy both.
- Root cause: the compiler mutates one row set in place (re-attributing
  `generation_id`), so there is no separation between a staged row version and
  the authoritative one. §26.3's "publish together or not at all" implies
  staged rows are a separate set until publish.

**Proposed fix options (need a decision in the plan):**
1. Dual-context eligibility — split into `compiler_visible` (includes the
   staged generation under compile) vs `serving_eligible` (authoritative only),
   and attribute units to a staged generation at compile START so a failed
   generation's rows are filtered out of serving.
2. Staged/authoritative row separation (copy-on-stage) — the heavier but
   spec-literal model where a generation owns its own row versions.

**Mitigating context:** in the current single-process compiler (one
`wiki build`/`wiki update` at a time, SQLite, no concurrent compiler), the leak
window is within a single function call and not observable by concurrent
queries, so practical exposure today is low — but §26.3 is a frozen P1 contract
and is not currently enforced. Recorded as a known P6 limitation in
`.agents/plans/B_roadmap_evidence.md`.
