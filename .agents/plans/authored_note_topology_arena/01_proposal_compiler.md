# Compiler Proposal: Deterministic Authored Topology in the Existing Graph

Date: 2026-07-30 | Agent Persona: Lead Architect

## 1. Core Logic & Implementation

Add one focused deterministic module,
`backend/src/curator/pipeline/authored_topology.py`, and reuse the existing
graph tables. It returns an in-memory set of normalized entities and relations;
it performs no DB writes while the LLM/compiler stage is still fallible.

### Extraction

Mask YAML boundaries, fenced code, inline code, and comments before scanning the
body. Parse YAML separately. Emit only:

- `links_to` from internal note links;
- `embeds` from note or asset embeds;
- `tagged_with` from body/YAML tags;
- `property_ref` from frontmatter wikilinks.

Normalize page fragments and display aliases away from endpoint identity.
`aliases` are a target lookup aid only.

### Exact resolution

Resolve an internal target in this order:

1. exact vault-root path;
2. exact source-relative path;
3. unique visible filename/stem;
4. unique visible Markdown frontmatter alias.

Reject hidden/control paths, root escapes, external URLs, ambiguity, and
unresolved targets. Only registered Markdown sources may emit authored
relations. Targets may be visible Markdown notes or visible vault assets.

### Deterministic identity

Use canonical vault-relative keys to derive stable ids:

```text
ENT = hash("vault-note\0" + canonical_path)
ENT = hash("vault-asset\0" + canonical_path)
ENT = hash("tag\0" + normalized_tag)
REL = hash(source_entity_id + "\0" + target_entity_id + "\0" + relation_type)
```

This makes unchanged rebuilds idempotent and lets existing id-based database
sync converge across devices.

### Atomic publication

During the existing successful compiler publish transaction:

1. upsert deterministic source/target/tag entities;
2. retire previous authored outgoing relations owned by the same source;
3. upsert the new set with `edge_class='authored'`,
   `assertion_source='source_states'`, exact structural confidence/topology
   weight, and the current `generation_id`;
4. publish the compiler generation.

No authored graph mutation occurs if extraction, LLM generation, or publication
fails. Source deletion retires the source-owned authored relations. Rename is
an old-source retirement plus new canonical identity publication.

### Downstream split

- active authored and active extracted relations may shape connected components
  and graph paths;
- only active extracted relations with verified
  `graph_relation_supports` may appear as factual relations/citations in
  community reports;
- authored-only components do not manufacture a factual community report;
- report dependency identity still includes authored topology that shaped
  membership, so link edits invalidate the affected generation;
- ordinary explore traversal uses active relations only; inspection APIs may
  opt into non-active rows.

## 2. Pros & Cons

### Pros

- No schema migration or parallel edge store.
- Human structure stays distinguishable from inferred facts.
- Deterministic ids provide rebuild and cross-device convergence.
- Atomic integration preserves the current staged compiler safety model.
- The parser/resolver is isolated and testable without an LLM.

### Cons

- Existing graph helper signatures need small extensions for explicit ids and
  authored fields.
- Community building must separate topology membership from factual report
  evidence.
- Rename changes path-derived entity identity and therefore requires explicit
  stale-edge retirement.
- Alias resolution needs a vault inventory pass and ambiguity detection.
