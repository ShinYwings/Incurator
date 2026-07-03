# RELAY — v0.31.0 Pipeline State Integrity

## Goal

Repair the production-visible L1 count, cross-device layer-status convergence,
and L1 retry/reference-resolution defects without treating disposable
Collection Markdown as source truth.

## Plan Reference

- Branch: `release/v0.31.0`
- Master plan: `.agents/plans/07_pipeline_state_integrity.md`
- Arena: `.agents/plans/pipeline_state_integrity_arena/`
- Evidence: `.agents/plans/07_roadmap_evidence.md`

## Analysis & Reasoning

- `second_brain/state.sqlite`: 32 sources, 31 L1 done, 1 L1 error.
- `.curator/Collections/01_Contexts`: 65 CTX projections.
- Dashboard `runtime_state.build_status_snapshot()` counts Markdown files even
  though guides define layer counts as DB records.
- Source LWW timestamp is `COALESCE(last_ingested, added_at)`; layer mutations do
  not bump either field. A schema-v11 `sources.updated_at` is required.
- Source #5 (`zotero:PZBCB9LJ`) has `L1=error, L2=done, L3=done, L4=skipped`,
  no source spans, and no `CTX-8ace29c9.md`. The emitted reference stub uses
  `zotero_attachment_key`, while the direct resolver checks `zotero_key`.
- Global L3 currently records `done` based only on absence of exceptions. The
  production DB therefore has one `l3_status=done` source despite zero live
  community reports, zero graph entities, and zero active relations.

## Progress Status

- Triage complete.
- Release branch created.
- Arena and master plan authored.
- No application code, production DB, or generated vault state modified.
- Awaiting user plan approval as mandated before implementation.

## Critical Context / Blockers

- Preserve untracked user file
  `.agents/drafts/sidechat_ui_regression_v0.29.0.md`.
- Production repair must back up `state.sqlite` and synced JSONL first.
- If no peer snapshot retains the missing authoritative L2-L4 rows, stale ATM
  Markdown must not be reverse-imported; affected sources require a rebuild.
- Active testbed scenario is not yet confirmed. Existing candidates:
  `gaussian_splatting`, `resnet_neural_ode`, `testbed_template`.

## Immediate Next Action

After approval: finalize pre-change evidence, update specs/guides, write failing
schema/sync/status/reference-retry tests, then implement and validate.
