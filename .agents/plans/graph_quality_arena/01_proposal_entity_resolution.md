# Entity Resolution Proposal: Reversible Alias Graph With Strict Merge Gate

Date: 2026-06-11 | Agent Persona: graph_resolution_architect

## 1. Core Logic & Implementation

Separate candidate generation, aliasing, and identity merge:

```text
extracted entity mention
  -> deterministic comparison normalization
  -> candidate entities
  -> compatibility evidence
  -> alias/proposal/accepted-merge decision
  -> canonical redirect with provenance union
```

### Candidate signals

- normalized display name and known aliases;
- compatible entity type;
- claim/source context overlap;
- relation-neighborhood compatibility;
- authored alias/frontmatter signals;
- embedding similarity as a candidate signal only;
- contradiction and `curate.yml avoid_merges` guards.

### Decision policy

- Auto-link as alias only for exact/high-certainty compatible forms with no
  contradiction/homonym guard.
- Default ambiguous cases to `proposed`.
- Destructive identity merge requires an accepted decision record and remains
  reversible through redirect/merge lineage.
- Similarity alone never auto-merges.

### Stable identity

Accepted canonical entities retain stable `ENT-` ids. Aliases resolve to the
canonical id while preserving alias display, source support, and resolution
reason. Merge/reversal must preserve the union of source spans, knowledge units,
and relation-support records.

### Pseudocode

```python
candidate_set = find_resolution_candidates(mention)
decision = resolve_with_guards(mention, candidate_set, avoid_merges)
if decision.kind == "alias":
    record_alias(decision)
elif decision.kind == "merge_proposal":
    record_proposal(decision)
else:
    create_distinct_entity(mention)
```

## 2. Pros & Cons

### Pros

- Improves synonym recall without sacrificing homonym safety.
- Makes every identity-changing decision inspectable and reversible.
- Prevents duplicate entities from distorting degree and communities.

### Cons

- Proposal lifecycle requires explicit status and cleanup rules.
- Reversible merges complicate endpoint resolution and DB sync.
- Conservative defaults leave some duplicates unresolved.
