# v0.39.0 Authored-Note Topology Evidence Ledger

Date: 2026-07-30
Status: PLANNING BASELINE — implementation not started
Master Plan: `.agents/plans/02_authored_note_topology.md`
Rollback anchor: `f7f0b08`
Branch: `release/v0.39.0`

## 1. Repository and Version Reality

| Item | Planning baseline |
|---|---|
| Worktree | clean before plan edits |
| Merged predecessor | v0.38.0, PR #100 |
| Build version | 0.38.0 |
| DB schema | v13 |
| Canonical case | `docs/specs/failure_atlas/cases/F09.yml` |
| Focused F9 result | 1 passed, 1 strict xfail |
| Active testbed | ResNet Dynamics, 3 sources, 0 graph entities/relations |

No application code, schema, production vault, or active testbed content was
changed during planning.

## 2. Current Contract Evidence

### Storage already supports separation

`graph_relations` has `edge_class`, `lifecycle_status`, `topology_weight`,
`generation_id`, and `source_span_ids`. `graph_relation_supports` records
extracted KNU-backed support. The planned behavior fits schema v13.

### Compiler does not create authored topology

The compile path extracts LLM graph objects and persists them through the staged
generation transaction. There is no pipeline parser that emits authored
wikilinks, embeds, tags, or frontmatter references.

### Canonical oracle is not production-shaped

The current F9 strict xfail calls the L1 span test helper and checks that
`graph_relations + dag_edges > 0`. It never invokes the real compiler/publish
boundary. P2 must first make the oracle capable of observing the intended fix.

### Lifecycle assumes one proof model

The lifecycle compiler treats zero support as unsupported, one lineage as
copied-source-only, and two independent lineages as active. The graph audit
applies the same factual corroboration expectation to every active relation.
Authored structural edges require a separate proof rule without weakening the
extracted rule.

### Consumers blur topology and factual evidence

- connected components consume active relations;
- community reports assume active relations have exact extracted supports;
- relation neighborhood exposes every lifecycle status;
- memory paths traverse that neighborhood;
- explore graph status counts all relations.

The implementation must make authoritative traversal active-only and split
community membership topology from factual report evidence.

### Sync identity must be deterministic

Graph table sync uses row id as transport identity. Existing random ids would
let independent devices persist duplicate logical authored edges. Stable ids for
only F9-derived entities/relations provide convergence without a schema change.

## 3. Read-Only User-Vault Syntax Measurement

Scope: `/Users/shin/shinywings/second_brain/03_Notes`

| Pattern | Count |
|---|---:|
| Markdown files | 17 |
| Files containing wikilinks | 7 |
| Wikilinks | 54 |
| `![[...]]` embeds | 27 |
| Heading targets | 18 |
| Block targets | 7 |
| Pipe display aliases | 15 |
| Body tags | 10 |
| Internal Markdown links | 56 |
| Markdown image embeds | 0 |
| Files with YAML tags | 13 |
| Files with YAML aliases | 13 |
| Frontmatter wikilinks | 0 |
| Pandoc citation groups | 0 |

This scan establishes real syntax coverage priorities but does not narrow the
documented Obsidian core contract.

## 4. Rollback and Integrity Requirements

- All writes remain on `release/v0.39.0` until PR merge.
- No migration is planned. If one becomes necessary, implementation stops for
  revised approval.
- Compiler publication remains one transaction. Test failures must prove the
  prior generation survives a staged failure.
- Production vault data remains read-only.
- Testbed smoke uses a temporary copied vault and records cleanup/restoration.
- Every implementation commit remains independently revertible; rollback uses
  additive Git revert, never history rewriting.

## 5. Pre/Post Validation Ledger

| Gate | Pre | Post |
|---|---|---|
| Real F9 production-boundary oracle | strict xfail / needs re-pin | pending |
| Authored-vs-extracted lifecycle tests | missing | pending |
| Edit/delete/rename/failure tests | missing | pending |
| Two-replica authored convergence | missing | pending |
| Active-only explore traversal | missing | pending |
| Community topology/evidence split | missing | pending |
| Full backend pytest | v0.38 predecessor: 1,325 passed | pending |
| Ruff / Mypy | v0.38 predecessor: green | pending |
| Plugin Vitest / build | v0.38 predecessor: 737 passed / green | pending |
| `npm audit` | v0.38 predecessor: 0 vulnerabilities | pending |
| Temporary testbed smoke | not run for F9 | pending |
| Production vault/testbed unchanged | planning read-only | pending |

## 6. Identifier Hygiene

The canonical Failure Atlas F9 is authored-note topology. Later Plan C
hierarchy/fallback comments reused “F9” informally. Those references must be
renamed to their Plan C section labels during P1 so search results and future
audits identify one F9 contract.
