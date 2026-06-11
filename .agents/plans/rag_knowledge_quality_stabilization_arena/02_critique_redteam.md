# Critique On The Stabilization Proposals

Date: 2026-06-11 | Agent Persona: red_teamer

> **Reframing note:** This critique was written against the first-pass
> component-oriented proposal. Its risks remain valid, but the active program
> structure is now Truth Contract & Quality Observatory → Evidence Compiler
> Integrity → Agentic Query Serving & Sensemaking. See
> `04_reframing_vault_as_codebase.md` and
> `../03_rag_knowledge_quality_stabilization.md`.

## 1. Vulnerabilities & Flaws

### R1 — Retrieval tuning can overfit the new fixture

A small golden corpus can make weights look better while degrading real vault
queries. Require query-family splits and holdout cases. Report per-family metrics,
not only one aggregate score.

### R2 — Provenance presence is not provenance correctness

A non-empty `source_span_ids` list can still point to an unrelated span. Fixtures
must assert expected ids and verify that the hydrated source contains the claim.

### R3 — Block ids are user-controlled and can be duplicated or stale

Do not assume block ids are globally unique. Resolve them within a file, detect
duplicates, and fall back safely when an anchor is stale.

### R4 — VLM formula recovery can hallucinate cleaner math

Recovered LaTeX must retain page/bounding-box provenance, model identity,
confidence, and raw crop identity. Low-confidence recovery must not silently
replace parser text.

### R5 — Formula-retention prompts can produce bloated Atoms

Require centrality: preserve formulas that carry the claim, not every equation in
the source span. Evaluate concise grounded units as well as retention.

### R6 — Entity auto-merge can irreversibly combine homonyms

Similarity alone is unsafe. Entity type compatibility, source context, relation
neighborhood, contradiction checks, and an audit record are mandatory. Default to
alias proposal, not merge.

### R7 — Leiden can hide quality regressions behind "better clustering"

Community quality needs deterministic seeded runs and explicit metrics. A
community algorithm change must not invalidate provenance or create giant
communities from noisy edges.

### R8 — Quota enforcement can block normal operation or miscount externals

Separate managed vault bytes, derived bytes, caches, and external references.
Warnings should precede hard blocking. Never delete automatically.

### R9 — Three programs can still become one giant branch

Each program needs a separate branch/PR/version bump, its own docs/tests, and a
hard stop before the next program. Programs 2 and 3 cannot begin from an
unmerged predecessor branch.

### R10 — The current branch is already occupied

The worktree contains Claude's in-flight `feature/editor-latex-copy` work. Planning
files may be authored, but no RAG branch creation, code, tests, specs, or version
bump may start until that work is concluded and the user approves this plan.

## 2. Suggested Alternatives

- Freeze a baseline and a holdout set before any retrieval tuning.
- Use provenance correctness tests, not count-only checks.
- Store formula recovery as an evidence candidate until validated.
- Make entity alias proposals the normal path; reserve auto-merge for exact/high
  certainty cases.
- Treat quota as visibility and admission control, never garbage collection.
- Enforce separate release branches and approval gates.
