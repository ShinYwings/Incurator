# v0.39.0 Authored-Note Topology Master Implementation Plan

Date: 2026-07-30
Status: DRAFT — Arena debate concluded; awaiting user approval before code

## 1. Objective

Close canonical Failure Atlas F9 by compiling exact human-authored note
wikilinks, embeds, tags, and frontmatter references into deterministic,
lifecycle-aware graph topology.

Definition of done:

- a real Markdown compile creates distinguishable active authored relations;
- authored topology affects active graph traversal and partitioning;
- it never masquerades as an LLM-extracted, independently corroborated fact;
- unchanged rebuilds and cross-device sync converge;
- edits, renames, deletion, and failed compilation cannot leave or publish stale
  topology;
- the real production compiler boundary replaces and retires the strict F9
  xfail;
- specs, EN/KR guides, tests, testbed evidence, version manifests, and changelog
  agree on v0.39.0.

## 2. Explicit Non-Goals

- No fuzzy or probabilistic link resolution.
- No general semantic entity-alias merge lifecycle.
- No new graph edge table or schema-v14 migration.
- No plugin-specific citation grammar such as Pandoc `[@key]`.
- No PDF/external-attachment content parsing as authored note topology.
- No stored reverse backlink rows; backlinks remain incoming traversal.
- No heading/block entities or separate endpoints for pipe display aliases and
  embed sizes.
- No redesign of L1 source-span extraction.
- No reintroduction of retired Exhibition artifacts or an external graph/search
  dependency.

## 3. Strict Quality Conditions & Release Gates

- The F9 oracle invokes the production compile/publish boundary and asserts
  exact endpoint, relation type, edge class, lifecycle, and generation.
- Extracted relation lifecycle remains unchanged: two independent verified
  source lineages are still required for active factual claims.
- Authored relations never create `graph_relation_supports` and never appear as
  factual report relation ids or citations.
- All ordinary graph traversal is active-only; inspection paths remain
  explicitly labeled and may opt into non-active rows.
- Unchanged rebuild produces no duplicate entities/relations or sync churn.
- Edit, rename, source deletion, failed publication, and two-replica convergence
  tests pass.
- Parser fixtures cover wikilinks, embeds, internal Markdown links/images,
  body/YAML tags, frontmatter refs, pipe aliases, headings, blocks, ambiguity,
  hidden/control paths, traversal, external links, comments, and code examples.
- Every implementation phase ends with focused pytest plus Ruff; integration
  ends with full backend pytest/Ruff/Mypy, plugin Vitest/build, spec sync,
  version consistency, and zero-vulnerability `npm audit`.
- Testbed validation uses a temporary copy of the current ResNet Dynamics
  scenario and leaves the user's production vault and active testbed unchanged.

## 4. Locked Design Decisions (Arena Consensus)

- Reuse schema-v13 `graph_entities` and `graph_relations`; no migration is
  planned.
- Add one focused deterministic extractor/resolver module. It computes a closed,
  immutable result before any graph mutation.
- Supported endpoint types are `vault_note`, `vault_asset`, and `tag`; supported
  relation types are `links_to`, `embeds`, `tagged_with`, and `property_ref`.
- Strip presentation-only pipe aliases, heading/block fragments, and embed
  sizes from endpoint identity.
- Resolve only exact visible vault targets using: vault-root path,
  source-relative path, unique filename/stem, then unique frontmatter alias.
  Ambiguity or unsafe/unresolved input emits no edge.
- `aliases` aid exact target resolution but create neither a relation nor a
  general semantic alias record.
- F9-created entity/relation ids are deterministic hashes of portable canonical
  keys. Existing extracted graph identity behavior is unchanged.
- Authored relations use `edge_class='authored'`,
  `assertion_source='source_states'`, current compiler `generation_id`, and an
  edge-class-specific structural lifecycle rule.
- Reconcile prior and current source-owned authored relations inside the
  existing successful compiler publication transaction. A failed compile leaves
  the last published set untouched.
- Active authored relations may shape components and explore paths. Community
  reports cite only verified extracted relation supports, while their
  dependency identity includes authored edges that shaped membership.
- Materialized/searchable diagnostic rows may retain labeled non-active
  relations; authoritative traversal may not use them.
- Relabel unrelated later Plan C “F9” prose/comments so canonical Failure Atlas
  F9 has one meaning.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: chat compaction, storage governance, PDF annotation, web
  search, fuzzy entity resolution, and broad graph performance work remain
  separate milestones.
- **Stop if a schema change becomes necessary.** Record the evidence, revise the
  contract, and obtain approval before migration work.
- **Stop if deterministic portable identity conflicts with existing sync
  semantics** in a way that cannot be proven by two-replica tests.
- **Stop if a consumer cannot separate topology membership from factual
  evidence** without changing a public report contract beyond this plan.
- **Stop if validation would require mutating the production vault or replacing
  the user's active testbed.**

## 6. Evidence Ledger

- **Current repository**: clean `release/v0.39.0` from rollback anchor
  `f7f0b08`; v0.38.0 is merged as PR #100.
- **Current schema/build reality**: schema v13; backend/plugin manifests are
  v0.38.0 before implementation. Existing relation columns are sufficient.
- **Baseline oracle**: focused F9 run is one pass plus one strict xfail; the
  oracle currently bypasses the real compiler and must be corrected first.
- **Lifecycle evidence**: generic lifecycle and graph audit treat zero-support
  authored rows as unsupported; this must branch by edge class without relaxing
  extracted corroboration.
- **Consumer evidence**: connected components read active relations, community
  reports assume factual supports, and explore neighborhood currently does not
  filter lifecycle.
- **Measured user-vault patterns**: 17 notes, 54 wikilinks, 27 embeds, 18
  heading targets, 7 block targets, 15 pipe aliases, 10 body tags, and 56
  internal Markdown links. Scan was read-only.
- **Testbed**: current ResNet Dynamics testbed has three sources and no graph
  entities/relations; validation must occur on a temporary copy.
- Full pre/post evidence lives in
  `.agents/plans/02_authored_note_topology_evidence.md`.

## 7. Execution Phases (Follow TDD and CI at Each Phase)

- **P0 — Research & Measured Baseline** (**COMPLETE FOR PLANNING**)
  - Confirm official Obsidian internal-link, embed, tag, and property forms.
  - Inspect actual vault syntax read-only, schema v13, compiler transactions,
    lifecycle, consumers, deletion, and DB sync.
  - Reproduce canonical F9 and record the oracle gap.
  - Gate: no application changes; evidence ledger complete.

- **P1 — Contract Specification**
  - Update all four static spec titles to v0.39 and reconcile the behavior in
    system, schema, plugin, and search specs as applicable.
  - Define authored-vs-extracted lifecycle, supported syntax/resolution,
    atomic ownership/reconciliation, active traversal, report-evidence split,
    sync identity, and failure semantics.
  - Update the relevant English guides first, then faithful `_KR.md` pairs.
  - Relabel unrelated Plan C “F9” references.
  - Verify: docs parity/spec-sync focused tests plus Ruff.

- **P2 — Failing Contract Tests**
  - Re-pin the strict F9 oracle to the real deterministic compiler/publication
    boundary before implementation.
  - Add parser/resolver tests and integration tests for exact authored relation
    fields.
  - Add edit/delete/rename/failure/idempotence/two-replica convergence tests.
  - Add lifecycle, active-only explore, and community evidence-separation tests.
  - Verify: new tests fail for the intended missing behavior; unrelated focused
    tests and Ruff remain green.

- **P3 — Deterministic Extraction and Identity**
  - Implement the focused authored-topology module, safe masking, YAML/body
    parsing, visible inventory, exact-one resolution, normalization, and stable
    ids.
  - Extend graph upsert helpers with optional explicit ids/authored fields while
    preserving extracted defaults.
  - Verify: parser/resolver/DB focused pytest passes plus Ruff/Mypy on touched
    modules.

- **P4 — Atomic Lifecycle and Reconciliation**
  - Stage authored topology in memory and publish it in the existing compiler
    transaction.
  - Implement edge-class-specific lifecycle and source-owned reconciliation.
  - Integrate source deletion and rename retirement.
  - Preserve prior topology on failed compile.
  - Verify: F9, lifecycle, compiler-generation, deletion, sync-convergence, and
    transaction rollback tests pass plus Ruff.

- **P5 — Authoritative Consumers**
  - Make ordinary relation-neighborhood/memory traversal active-only.
  - Count active relations for explore graph status.
  - Allow authored active topology to shape communities while keeping factual
    report relations/citations extracted-and-verified-only.
  - Include topology-shaping authored ids in dependency invalidation.
  - Verify: retrieval/explore/community/report focused pytest passes plus Ruff.

- **P6 — Testbed and Full Local CI**
  - Create an isolated temporary copy of the current ResNet Dynamics testbed and
    add fixture notes that cover supported syntax and stale-edge reconciliation.
  - Run the add/build/sync/lint/query paths that do not require unavailable
    external services; record exact blockers for any LLM gate.
  - Restore/verify the original active testbed and production vault are
    unchanged.
  - Run `scripts/backend-check pytest`, `ruff`, and `mypy`; plugin Vitest,
    production build, `npm audit`, docs/spec/version consistency.

- **P7 — Release Finalization**
  - Update backend/plugin/manifest versions to 0.39.0 and all four static spec
    titles to the v0.39 line.
  - Add `CHANGELOG.md` release notes, retire F9 case status/oracle deliberately,
    clean the live ROADMAP item, and delete completed plan artifacts.
  - Commit `chore(release): v0.39.0`, push, and open a detailed PR.
