# Defense and Revision: User-Report Stability Plan

Date: 2026-06-25
Agent Persona: System Synthesizer

## 1. Revisions Accepted

- The domain analysis files were moved under the arena folder.
- VLM sanitizer placement is now locked to post-generation/pre-persistence.
- L2 English output now requires a programmatic guard and capped retry.
- `source rm` now requires an internal caller audit before default behavior is
  changed.
- L4 behavior is now defined as current architecture, not a product ambiguity.

## 2. Revised Decisions

- **VLM sanitizer**: implement a helper in the vision/ingest boundary and call it
  immediately after `normalize_vision_latex(...)` returns model text, before the
  chosen page text is assigned to `pdf_pages[i]["text"]`, cached as durable
  extracted content, written to CTX, or converted into source spans. It removes
  only Markdown image/link destinations whose parsed URL has `file:` scheme or
  whose resolved/normalized path is under the configured `vision_render_dir()`.
  `http(s)://`, vault-relative, and ordinary absolute paths outside the temp render
  directory are left intact.
- **L2 English guard**: validate generated KNU/Atom fields such as
  `canonical_name`, `statement`, and projected Atom titles/bodies. Raw quoted
  evidence and source spans may remain Korean. If generated fields fail the guard,
  retry with a stricter repair prompt; after capped retries, mark the layer error.
- **Source removal**: audit `remove_source(` and CLI/plugin callers with `rg`
  before implementation. Any intentional file-delete caller must pass an explicit
  destructive argument after the CLI/API default changes.
- **L4**: `wiki add` creates L1 and queues L2/L3; it does not wait for L4.
  `wiki build --wait`, `wiki jobs run`, or an active worker should run global L3
  and attempt L4 synthesis automatically. If no community reports exist, zero SYN
  nodes can be valid and should be surfaced as `skipped`/clear status rather than
  infinite pending. If synthesis exists or was attempted successfully, source
  `l4_status` must not remain `pending`.
