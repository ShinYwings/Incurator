# Critique on the Architect Proposal

Date: 2026-06-19 | Agent Persona: red_teamer + schema_guardian

## 1. Vulnerabilities & Flaws

**C1 — "Big bang" extraction of a 2057-LOC file is a regression magnet.** Moving
registration/persistence/Zotero out of `externalPdfView.ts` in one phase risks
silent breakage of persisted-doc rehydration (`loadPersistedDocs` runs at module
load and races Obsidian startup — see the comment in `externalPdfState.ts`). If
the moved registry initializes in a different order, persisted PDFs vanish.
→ Must be incremental, each extraction behind its own passing test, and must
preserve module-load timing.

**C2 — Backend-delegated Zotero resolution can break the offline/headless path.**
The plugin sometimes resolves a Zotero PDF when the backend command is not
available (`client.available === false`). Deleting the plugin resolver outright
strands those users. → Keep the local resolver as an explicit fallback, do not
delete; "single resolver" means "single *entry point*," not "single
implementation."

**C3 — `AssetIdentity` frozen dataclass hides partial-resolution states.** Many
real inputs resolve only partially (key but no path when the file moved; hash but
no row). A frozen all-fields dataclass invites callers to assume non-null. →
Every field stays `Optional`; add an explicit `resolution_status` enum
(`resolved | path_unresolved | untracked`) so callers branch on state, not on
`None` guessing. This mirrors the existing `locator_status` discipline.

**C4 — Schema risk on `import_source` unification.** The Reference Mode branch
and the copy branch in `ingest_raw.import_source_file` have *different* dedup
semantics (logical_source_id / external_path vs relpath). Collapsing them risks
mis-dedup (a copied PDF and its reference stub treated as the same row, or
duplicates created). → schema_guardian veto on any change that alters dedup keys.
The resolver may *feed* the existing branches but must not merge their dedup
SQL in the same phase. Add dedup regression tests FIRST.

**C5 — Cross-reference resolver (511 LOC) and pdfCapture (439 LOC) are out of
scope but coupled.** They read PDF identity indirectly. If `AssetSource` changes
the shape they consume, they break. → Freeze their public inputs; this plan does
NOT refactor them, only ensures the new model is adapted at their boundary.

**C6 — Item 3 might be a non-bug; spending a phase "fixing" it is waste.** The
audit already downgraded it. → Phase must first attempt a concrete repro test; if
it cannot reproduce, close item 3 as wontfix and only land the unified key as a
*structural* improvement, not a "fix."

## 2. Suggested Alternatives

- **Sequence**: P0 measure + characterization tests → P1 contract (AssetIdentity /
  AssetSource + resolution_status, docs-first) → P2 backend resolver as a *facade*
  over existing functions (no dedup SQL changes) → P3 plugin resolver + single
  status key + remove `as any` → P4 incremental renderer extraction (registry
  first, one move per commit) → P5 testbed E2E for all three flows.
- **Strangler pattern, not rewrite**: introduce the resolver, route call sites to
  it one at a time, delete the old private resolver only when no caller remains.
- **Net-LOC gate**: the plan claims simplification — enforce a measured net LOC
  decrease in PDF modules as a release gate, else the "simplification" is fake.
- **Keep `_resolve_reference_source` callable** during transition (delegate to
  the resolver internally) so build-time reference resolution never regresses.
