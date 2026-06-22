# Active Relay State

**STATUS: ACTIVE — PR pending merge**

**Branch**: `feature/diff-viewer-ui-ux`

**Active Task**: Diff Viewer UI/UX — Multi-Model Robustness (v0.24.0)

**Progress**: Implemented and validated. Plugin tests 560 green, tsc clean, build OK,
spec_sync 10 green. Plan artifacts deleted (history in Git). PR opened; awaiting user merge.

**What shipped (v0.24.0)**:
- Edit-review 4-phase loop demoted from hard gate → quality hint (valid edit always reviewable).
- Output-token truncation detected (`StreamChunk.finishReason`/`truncated`, all 4 adapters) +
  auto-continue ≤3 with fence-safe overlap stitch; no premature finalization; manual Continue.
- Diff Viewer keyboard shortcuts focus-gated (chat-Enter no longer Accept-Alls); `show()` focuses
  the editor; typed `{opened,reason}` return → no silent failures.
- Multi-edit matched against original text (order-independent) + same-file review coalesce.

**Next Action**: User reviews/merges the PR. After merge, truncate RELAY to IDLE.
