# Domain Analysis: Backend CLI, Source Registry, and Pipeline Status

Date: 2026-06-25
Scope: reports 1, 3, 4, 8, 10, 11, 12.

## Design Constraints From Codebase

- `backend/src/curator/cli.py` owns `wiki jobs ...` and `wiki source ...`.
- `backend/src/curator/db.py` owns job state transitions and source layer status.
- `backend/src/curator/source_tools.py::derive_source_state` already derives
  user-facing states from L1-L4 status and pending jobs.
- `backend/src/curator/ingest_raw.py::remove_source` can delete original files
  when `delete_file=True`; `sources_rm_cmd` currently makes that the default.
- `backend/src/curator/vision.py::normalize_vision_latex` strips CLI banners but
  does not guarantee removal of `file://.../.cache/vision_render` image links.

## Docs / Specs Invariants

- `wiki source rm <id>` is documented as registration/generated-L1 removal, not
  source-file deletion.
- Source truth under `03_Notes/`, `04_Resources/`, and external Reference Mode
  paths is read-only from Incurator's perspective.
- Agentic CLI temp PNGs are transient and must not appear in durable generated
  content.

## Alternatives & Trade-Offs

- `source rm`: make deletion opt-in with `--delete-file`; default preserves
  source truth.
- `jobs rerun`: queued job rerun should be idempotent and precise; running jobs
  remain non-rerunnable until finished/cancelled/recovered.
- `source retry`: select rows where any `l*_status='error'` or `layer_error` is
  non-empty, not only `sources.status='error'`.
- VLM output: prompt hardening alone is insufficient; add defensive sanitizer.

## Final Decision

Backend implementation should first fix source safety and recovery:

1. Default `wiki source rm` to tracking/generated-state removal only.
2. Make `wiki source retry` find per-layer errors.
3. Make `wiki jobs rerun <queued-id>` idempotent and improve running/missing
   messages.
4. Sanitize VLM output so durable L1 never contains `file://` or `vision_render`.
5. Enforce English generated L2/KNU/Atom output with a programmatic language
   guard, not prompt wording alone, while preserving source evidence.
6. Treat L4 as automatic after global L3 in the current design. If no synthesis
   appears after build, diagnose whether there were no eligible community reports
   (valid empty result) or whether status/generation failed to mark L4 correctly
   (bug).

## Implementation Pseudocode

```text
test_source_rm_preserves_file_by_default
test_source_retry_finds_layer_error
test_jobs_rerun_queued_is_idempotent
test_vision_normalizer_strips_temp_file_image_links
test_l2_prompt_requires_english_generated_units
```
