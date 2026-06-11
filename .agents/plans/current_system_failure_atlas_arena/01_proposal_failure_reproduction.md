# Failure Reproduction Proposal: Minimal Fixtures And Boundary Oracles

Date: 2026-06-11 | Agent Persona: source_pair_analyst
Status: DRAFT PROPOSAL

## 1. Core Logic & Implementation

### Fixture rule

Every reproduced defect must have the smallest fixture that still demonstrates
the loss. Large live-vault observations may motivate a case, but they cannot be
the only oracle.

### Core diagnostic fixtures

| Fixture | Distinctive evidence | Target failures |
|---|---|---|
| `provenance_search_hit` | one unique claim and one distractor | F1, F2, F6 |
| `policy_scope` | included and excluded sources with same keywords | F3 |
| `bounded_routes` | many reports/spans with only two relevant items | F4, F5 |
| `mutation_reconciliation` | edit/delete/rename/split source set | F7 |
| `graph_noise` | synonym, homonym, bridge edge, contradiction | F8 |
| `authored_topology` | wikilink, embed, heading, block id, alias, tag | F9 |
| `long_source_recall` | claim outside preview window | F10 |
| `iterative_gap` | answer requires a follow-up retrieval | F11 |
| `cross_client_parity` | same request through MCP/plugin/backend | F12 |
| `current_architecture_testbed` | no qmd/EXH assumptions | F13 |

### Boundary oracle

For every evidence-bearing transformation:

```text
input identity
  -> output identity
  -> minimal support relation
  -> exact locator
  -> freshness/dependency identity
```

The oracle must distinguish:

- **identity validity**: referenced record/span exists;
- **support correctness**: cited span supports the associated claim;
- **support completeness**: all material answer claims have support;
- **locator resolution**: source can be opened at the intended location;
- **freshness**: evidence belongs to the declared corpus snapshot.

### F1 minimal reproduction

1. Materialize one authoritative record carrying a known `source_span_id`.
2. Run DB-native hybrid search and assert the `EngineHit` contains the span id.
3. Build local evidence and inspect the matching `search_hit`.
4. Reproduce that the `EvidenceItem.source_span_ids` is empty and that
   `pack.source_span_ids` derives only from entity evidence.
5. Capture both traces to prove whether the engine creates a separate `QTR-`.

### Mutation oracle

Before and after each source mutation, compare:

- authoritative row identities/content/dependency hashes;
- stale and duplicate records;
- search documents/chunks/embeddings;
- graph/report/synthesis dependencies;
- query results and citations;
- projection files only as derived inspection output.

An unchanged rebuild must not create new authoritative identities. A failed
batch must not leave partially authoritative truth.

### Existing scenario handling

The `complex_math_backprop` scenario is evidence of historical intent, not a
valid current oracle. Program 1 must inventory and classify its EXH/qmd-era
assertions, preserve any still-useful source fixtures, and author a current
DB-native scenario rather than patching old expected behavior into passing.

## 2. Pros & Cons

### Pros

- Pinpoints loss boundaries instead of producing vague end-to-end failures.
- Makes regressions cheap to rerun.
- Preserves useful historical fixtures without accepting retired contracts.

### Cons

- Minimal fixtures can underrepresent live-vault scale and ambiguity.
- Mutation cases are expensive if every derived layer is rebuilt.
- Support correctness requires carefully labeled claim/span pairs.
