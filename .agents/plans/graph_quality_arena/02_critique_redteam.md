# Critique On Graph Resolution And Hierarchy Proposals

Date: 2026-06-11 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

### R1 — Alias auto-linking can still collapse homonyms indirectly

Even without a destructive merge, resolving an ambiguous alias to one canonical
entity can route retrieval and edges incorrectly. Ambiguous aliases need a
distinct unresolved state, not a forced target.

### R2 — Merge reversibility can be nominal rather than real

If downstream relation endpoints and reports are rewritten without merge lineage,
reversing the merge cannot reconstruct the original graph. All rewritten
dependencies must preserve origin identity.

### R3 — Relation support counts can reward duplicated sources

Three notes quoting one PDF are not three independent supports. Independence must
use source lineage/corpus identity, not row count.

### R4 — Quarantine can become an opaque discard pile

Edges need reason codes, inspection surfaces, re-evaluation triggers, and
retention policy. Otherwise quarantine hides potentially valuable evidence.

### R5 — Authored links can dominate or underweight semantics

A wikilink is high-confidence authored topology but not necessarily a factual
relation. It must remain a separate edge class; assigning a universal high
weight can distort communities.

### R6 — Leiden can pass modularity while failing knowledge quality

No algorithm may be selected on modularity alone. Homonym, provenance,
stability, giant-component, and report-support metrics are mandatory.

### R7 — Stable community ids can preserve obsolete partitions

Over-prioritizing identity stability can prevent correct restructuring after
source changes. Stability is a measured quality property, not a reason to retain
stale membership.

### R8 — Graph reconciliation can race with Plan B claim retirement

If graph extraction reads mixed claim generations, it can create edges against
retired units. C must consume only a published B compiler generation.

### R9 — Quota can creep back through growth metrics

Measuring duplicate amplification/artifact growth is valid compiler quality.
Implementing UI, limits, or storage admission in C is scope violation.

## 2. Suggested Alternatives

- Represent ambiguous aliases as unresolved candidates.
- Preserve origin ids and decision lineage through every accepted merge.
- Compute independent support from source lineage and claim support, not counts.
- Give quarantine explicit reason/status/recheck contracts.
- Keep authored and extracted edge classes distinct through hierarchy input.
- Select hierarchy through a multi-metric benchmark and retain filtered connected
  components as explicit fallback.
- Pin graph compilation to one published claim-generation id.
