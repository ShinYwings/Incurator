# Domain Analysis B: Dashboard Counts and L1 Repair

Date: 2026-07-03 | Domain: pipeline / plugin observability

## Design Constraints

- Collection Markdown is a disposable DB projection.
- Guides define L1 as sources with `l1_status=done`, L2 as serving knowledge
  units, L3 as live community reports/concepts, and L4 as synthesis nodes.
- A projection repair failure must not destroy authoritative DB state.
- Reference Mode must resolve portable identity without ingesting the stub text
  as if it were the original PDF.
- `l3_ready` promises concept-grounded answers, so an exception-free pass that
  emits zero live community reports cannot be labeled L3 done.
- L4 is shared/corpus-global; a source may be L4 done only when the current
  synthesis corpus exists, otherwise its terminal state is skipped or error.

## Alternatives and Trade-offs

1. Delete orphan CTX files and keep counting files: fixes one vault once but
   preserves the architectural defect. Rejected.
2. Count all raw DB rows: DB-native, but includes retired/staged artifacts.
   Rejected for L2/L3.
3. Count the same serving sets used by projection re-emission: matches user
   behavior and source-of-truth rules. Accepted.
4. On missing CTX, mark L1 error whenever re-emission fails: visible, but turns a
   derived-file failure into false source corruption. Rejected for previously
   complete L1.
5. Treat “compiler returned without exception” as L3 completion: matches current
   tests but produces false `l3_ready` with zero concepts. Rejected.

## Final Decision

- Compute dashboard layer counts from authoritative serving DB queries:
  L1 done sources, serving L2 units, live L3 community reports, L4 synthesis
  nodes.
- Keep projection-file counts out of health/status contracts.
- Make missing-projection repair preserve an already-valid L1 row on projection
  failure; first-ingest failures still set L1 error.
- Make L1 publication order DB-first and projection-safe; partial projection
  output is replaced atomically.
- Resolve both `zotero_attachment_key` and legacy `zotero_key`; if a reference
  target cannot resolve, report a reference-resolution error instead of parsing
  the stub Markdown as source content.
- Set per-source L3 done only when the current live report set contains
  source-grounded L3 output; use skipped when the pass completed with no eligible
  concept/report for that source. Set L4 done only when current synthesis nodes
  exist; otherwise use skipped, and reserve error for failed generation.
- Add a repair command/path that re-emits disposable projections from DB and
  retries only genuinely invalid L1 rows.

## Implementation Pseudocode

```text
layer_counts():
  contexts = count sources where l1_status = done
  atoms = count serving knowledge_units
  concepts = count non-retired community_reports
  synthesis = count synthesis_nodes

global_stage_status(source):
  l3 = done if source spans support a live report else skipped
  l4 = done if current synthesis nodes exist else skipped
  error only when the corresponding compiler stage failed

resolve_reference_stub(frontmatter):
  key = zotero_attachment_key || zotero_key
  if key: resolve Zotero PDF
  else: resolve portable DB locator
  if unresolved: raise ReferenceUnavailable

heal_missing_projection(source):
  remember authoritative L1 state
  attempt target resolution + re-emission
  if derived-only repair fails and L1 was valid: preserve DB state, surface warning
  if source itself is invalid/new: set L1 error and reset downstream pending
```
