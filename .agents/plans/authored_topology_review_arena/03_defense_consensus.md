# Defense and Consensus: Fail Closed at Every Boundary

Date: 2026-07-30 | Agent Persona: System Synthesizer

## 1. Resolved Design

- Scanner work is restricted to existing inline wikilinks, inline Markdown
  links/images, code/comment masking, and tags. No new grammar class is added.
- Masked regions are replaced by spaces while retaining newlines and string
  length, preventing token synthesis across boundaries.
- Resolution uses explicit tri-state stages. A higher-priority ambiguous match
  terminates resolution. Safe lexical `..` normalization is allowed only when
  the combined source-relative path remains inside the vault.
- `.md` and `.markdown` share one `_is_markdown_path` predicate.
- Generation `audit_json.authored_relation_ids` is authoritative membership for
  new v0.39 generations. Missing membership never resurrects a row.
- Sync reassigns only ids listed by the winning audit and runs the existing
  lifecycle compiler; loser-exclusive ids retire.
- DB-only republish carries authored membership only for byte-identical source
  fingerprints. A changed fingerprint without source parsing retires old
  authored rows.
- Pure topology additions retire only reports containing either endpoint.
  Removed topology continues through relation dependency retirement.
- Search includes authored entity types only while attached to active topology,
  and explicit source removal rematerializes derived search rows.
- Full extracted source-delete closure and broad inventory-performance redesign
  remain separate stability work.

## 2. Verification Consensus

- Every confirmed reproduction becomes a regression test before logic changes.
- Add an adversarial two-replica test with intentionally divergent generation
  and row timestamps.
- Add DB-only republish and Markdown→non-Markdown lifecycle tests.
- Add report-addition invalidation and stale authored-search cleanup tests.
- Run focused compiler/sync/report/search tests, full backend checks, plugin
  tests/build/audit, and isolated testbed compile/sync/lint.
