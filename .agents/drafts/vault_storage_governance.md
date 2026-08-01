# Vault Storage Governance & Quota Visibility

Status: DEFERRED — retained as an unplanned roadmap draft; no implementation is
authorized from this document alone.

## Context

RAG & Knowledge Quality Stabilization must measure duplicate amplification,
derived-artifact growth, and rebuild size, but disk quota and storage UI do not
prove that prior knowledge is correct. This requirement is preserved as a
separate milestone so it does not distort the RAG/DAG quality program.

## Preserved Requirements

- Default logical vault capacity guidance of 200 GB, configurable during
  `wiki init`.
- Distinguish authoritative source, durable human artifact, derived projection,
  cache, local asset, and external Reference Mode bytes.
- Never count external Reference Mode source files as managed vault bytes.
- Display storage usage and category breakdown in CLI status and the Obsidian
  dashboard.
- Warn before capacity pressure becomes destructive.
- Never silently delete source truth, human notes, or durable promotions.
- Reclaim recommendations target disposable projections and caches first.

## Required Arena Questions

1. Is quota an informational policy, an admission-control limit, or both?
2. Which byte categories are authoritative and portable across devices?
3. How are external references, duplicated assets, DB pages/WAL files, and synced
   artifacts counted?
4. Which operations may be blocked at a hard limit without corrupting an active
   compile or sync transaction?
5. How are warnings rendered consistently in CLI and plugin surfaces?

## Dependency

Schedule after RAG Program 2 has measured real compiler growth and rebuild
behavior. Storage policy must use those measurements rather than speculative
artifact counts.
