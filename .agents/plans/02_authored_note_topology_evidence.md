# v0.39.0 Authored-Note Topology Evidence Ledger

Date: 2026-07-30
Status: IMPLEMENTED — focused regression green, full release validation pending
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
| P1 docs/spec/atlas contract | not implemented | 121 passed; Ruff green |
| Real F9 production-boundary oracle | strict xfail / needs re-pin | passing; strict xfail removed; F9 retired |
| Authored-vs-extracted lifecycle tests | missing | passing, including exact generation/source ownership |
| Edit/delete/rename/failure tests | missing | passing, including dependent-report retirement |
| Two-replica authored convergence | missing | passing with non-empty IDs, one authoritative generation, compiler/graph audits clean |
| Active-only explore traversal | missing | passing; deterministic relation order |
| Community topology/evidence split | missing | passing; authored dependency retained, factual relation ids excluded |
| Focused compiler/graph/sync/search regression | not run | 283 passed, 4 expected xfails |
| Full backend pytest | v0.38 predecessor: 1,325 passed | pending |
| Ruff / Mypy | v0.38 predecessor: green | focused Ruff green; Mypy 126 files green |
| Plugin Vitest / build | v0.38 predecessor: 737 passed / green | pending |
| `npm audit` | v0.38 predecessor: 0 vulnerabilities | pending |
| Temporary testbed smoke | not run for F9 | pending |
| Production vault/testbed unchanged | planning read-only | pending |

## 6. Identifier Hygiene

The canonical Failure Atlas F9 is authored-note topology. Later Plan C
hierarchy/fallback comments reused “F9” informally. Those references must be
renamed to their Plan C section labels during P1 so search results and future
audits identify one F9 contract.

## 7. Implementation and Review Evidence

- Added one closed deterministic authored-topology parser/resolver and kept all
  graph mutation inside the existing compiler publish transaction.
- Stable endpoint keys use Unicode NFC; entity/relation IDs converge across
  independent replicas.
- Authored lifecycle now has one decision path: persist as provisional, publish
  the generation, then invoke the shared lifecycle compiler.
- Relation retirement and dependent-report retirement use one DB operation from
  compiler edit, source deletion, and replica reconciliation paths.
- DB import restores the one-authoritative-generation invariant per portable
  source, preferring the LWW source-content fingerprint and newest publication,
  and retires authored rows owned only by losing generations.
- Existing relation re-assertion preserves lifecycle/topology metadata unless a
  caller explicitly replaces those fields; this prevents active extracted
  relations from being reset to provisional by the new API.
- Active authored audit/lifecycle requires the generation's registered Markdown
  source path to match the relation's source `vault_note` endpoint.
