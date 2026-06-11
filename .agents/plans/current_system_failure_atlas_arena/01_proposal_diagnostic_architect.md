# Diagnostic Architecture Proposal: Experiment-First Failure Atlas

Date: 2026-06-11 | Agent Persona: lead_architect
Status: DRAFT PROPOSAL

## 1. Core Logic & Implementation

### Design principle

Treat diagnosis as a reproducible build artifact, not a narrative investigation.
Each experiment receives a stable case id and produces an evidence bundle that
can be reviewed without rerunning the entire vault.

### Failure-atlas record

Each concern is represented by a structured record:

```yaml
case_id: F1-search-hit-provenance-drop
program_owner: program-1
status: suspected  # suspected | reproduced | disproven | accepted | assigned
boundary:
  input: HybridEngine EngineHit
  output: EvidencePack search_hit
fixture: diagnostic_provenance_search_hit
snapshot:
  git_sha: ...
  schema_version: ...
  db_fingerprint: ...
  config_hashes: ...
  provider_fingerprints: ...
commands: []
oracle:
  deterministic_assertions: []
  labeled_expectations: []
observed: {}
artifacts: []
downstream_owner: program-1-observatory
```

The persisted format may be JSON/YAML/SQLite after Program 1 specification
approval. The plan locks the information contract, not a premature storage
choice.

### Experiment classes

1. **Boundary experiments**
   - Trace one distinctive claim through source -> span -> unit -> graph -> report ->
     synthesis -> search -> evidence -> answer.
   - Compare input/output identities and support text at every boundary.

2. **Mutation experiments**
   - unchanged rebuild;
   - edit one claim;
   - delete a source;
   - rename a note;
   - split one section;
   - fail a compile mid-batch;
   - change `curate.yml`;
   - remove embedder/reranker/LLM availability.

3. **Query-family experiments**
   - exact lexical/identifier;
   - Korean/CJK;
   - paraphrase/vector;
   - formula/symbol;
   - direct factual;
   - source-scoped;
   - associative/multi-hop;
   - global synthesis;
   - contradiction/hard negative;
   - heading/block/PDF locator.

4. **Cross-client experiments**
   - raw search;
   - `curator_fetch_context`;
   - `curator_query`;
   - CLI/plugin JSON;
   - Obsidian provider-context assembly.

### Evidence bundle

Every run captures:

- command/request and normalized request identity;
- git SHA and dirty-worktree declaration;
- DB schema fingerprint and authoritative table counts;
- corpus/source hashes;
- `curate.yml` and search-config hashes;
- provider/model fingerprints and degraded-mode status;
- selected evidence ids in order;
- hydrated source-span ids and support excerpts;
- query/prompt/retrieval traces;
- latency, tokens where available, and warnings;
- pass/fail result with oracle version.

### Phased diagnosis

```text
inventory current reality
  -> freeze fixtures and labels
  -> execute deterministic failures
  -> execute LLM/provider-sensitive failures
  -> classify and assign
  -> specify minimum observatory substrate
```

## 2. Pros & Cons

### Pros

- Separates evidence from interpretation.
- Makes future algorithm comparisons use the same baseline.
- Prevents a plausible trace id or non-empty span list from being mistaken for
  correctness.
- Supports post-release regression diagnosis without relying on one agent's
  memory.

### Cons

- Produces substantial diagnostic artifacts before visible product changes.
- Some semantic support labels require human review.
- LLM-sensitive cases cannot be made perfectly deterministic.
- Storage and retention policy must prevent evidence bundles from bloating the
  repository or vault.
