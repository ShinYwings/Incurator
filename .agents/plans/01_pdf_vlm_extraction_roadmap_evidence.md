# Evidence Ledger — v0.22.0 Dedicated PDF-extraction (VLM) model

Date: 2026-06-21

## Branch / Rollback Anchor
- **No merge-first** (user decision 2026-06-21). Continues on the EXISTING branch
  `feature/chat-decay-quick-wins`; PR #45 grows into one combined `v0.22.0`.
- `latexModel` is unreleased on this same branch → removed/reshaped in place, no
  migration.
- Rollback anchor: last commit before VLM work (the v0.21.0 release commit
  `74169bd` is the clean pre-VLM state on this branch). `vision_model` empty default
  makes the feature inert, so a partial rollback degrades cleanly to pymupdf4llm.

## Current Repository Reality (verified by reading code)

| Claim | Evidence |
|---|---|
| PDF ingest uses pymupdf4llm, no LLM | `backend/src/curator/parsers/pdf.py:137`, `parser_used="pymupdf4llm"` `:200` |
| Hybrid VLM placeholder exists | `parsers/pdf.py:135` ("if config enables VLM … route here") |
| Vision client infra exists (images only) | `ingest_raw.py:1365` `_build_vision_client`, `:469` `_describe_images_with_vision`, used `:1440-1490` |
| `_build_vision_client` only reuses main client if vision-capable | `ingest_raw.py:1365-1376` |
| `llm.vision_model` key is stripped (half-migrated) | `config.py:447-452` `_migrate_llm_config` pop loops |
| Ingest error already references `llm.vision_model` | `ingest_raw.py:1453` |
| Config has first-class provider::model slots | `config.py` primary/fallback/embedding/reranker; `split/join_provider_model` `:286-294` |
| Dashboard edits backend model config via wiki config | `plugin/src/ui/incuratorDashboardModal.ts:582`+ (LLM Provider card, Primary/Fallback/Embed) |
| Vision capability known per model | `plugin/src/types.ts:224` `modelSupportsVision`, `:47` `supportsVision`; `utils/bundledModelCatalogue.ts:28` |
| Plugin per-call model override exists | `plugin/src/agent/llmClient.ts:962` `complete(messages, opts?: { model })` (v0.21.0) |
| Cmd+Shift+X attaches crop to chat (main model interprets) | `plugin/main.ts:443-472` snip-pdf-to-chat; chat vision gate `chatSidebar.ts:1297` |
| Convert-to-LaTeX uses text latexModel (to be retired) | `plugin/src/ui/externalPdfView.ts:1294` + v0.21.0 `latexModel` |
| §26 rejects whole-corpus/every-page VLM (to be revised) | `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:1670` |

## Reviewer corrections (2026-06-21) — folded into plan
- **R12 cache key**: per-page VLM cache key = `(page_content_hash, resolved_model)`,
  not content hash alone, so a Dashboard model switch invalidates stale L1.
- **R13 fallback-only-on-empty**: resolver chain advances only for an EMPTY slot; a
  configured-but-bad model RAISES and halts (no silent escalation to a heavier
  model). Ingest config-failure raises upfront; only transient per-page errors
  degrade to pymupdf4llm for that page (logged + provenance).
- **R14 render bound**: `vision_render_dpi`=170 + `vision_max_image_px`=1600
  longest-edge cap w/ downscale (P0 pins exact per-provider caps).
- §26 STOP gate at P1: reviewer verified as the correct procedural control.

## P0 findings (2026-06-21)
- ✅ Independent client per provider: `_make_by_key(provider, {"model": m, ...})`
  (`llm.py:1451`). Add thin `make_client_for(provider_model, config)`.
- ✅ Vision primitive: `client.describe_image(bytes, prompt)` + `client.supports_vision`
  (`llm.py:307,296`); raises `LLMError` on non-vision (the R13 raise primitive).
- ⚠️ `describe_image`/`supports_vision` exist ONLY on `OllamaClient`. CLI clients
  (`agy`/`claude`/`codex`) pass text via stdin (`llm.py:637,737`), CLI-subscription
  auth, no API keys. → cloud vision via agentic-CLI file-path→Read (no API keys).
- ✅ **LIVE image-read test PASSED for ALL THREE agentic CLIs** (2026-06-21, distinctive
  tokens `q_47=√1337`, `0.90210`, `Θ_xyz`, `Ω` rendered via fitz, transcribed back
  exactly → true OCR, not hallucination):
  - **claude** `claude -p "…" --allowedTools Read --add-dir <.cache>`: ✅ cleanest,
    output-only LaTeX. Best.
  - **agy** `agy --print "…" --print-timeout 90s`: ✅ clean LaTeX, wraps in `$$…$$`.
    (NOTE: `--dangerously-skip-permissions` is BLOCKED by the harness/policy — must
    NOT be used; plain `--print` worked without it.)
  - **codex** `codex exec "…"`: ✅ correct transcription BUT **noisy** — echoes cwd
    files + a "tokens used: 36,967" line, and is agentic over the working dir.
    Requires strict output extraction + cwd isolation; heaviest token cost.
  → Per-provider **output normalization** is REQUIRED (strip `$$` wrappers, codex
    banners/token lines, any commentary) before the transcription becomes L1.
    Provider invocation must NOT pass unsafe auto-approve flags.
- ✅ Dashboard IO: `wiki config set llm.<key>` (`cli.py:2516`); dashboard reads
  `llm.primary/fallback` from the config object (`incuratorDashboardModal.ts:889`).
- ⚠️ Convert-to-LaTeX uses text-only `getSelectionTextWithinView` (`externalPdfView.ts:1254`);
  region image needs a bbox render (or selection-image+text fallback) — P5 detail.
- ✅ PDF→PNG: PyMuPDF `fitz` already a dep (`pdf.py`); `page.get_pixmap(dpi=170)` →
  `.tobytes("png")` (Ollama, in-memory) / `.save(path)` (CLI temp file). No new dep.
- ✅ Temp PNG dir: project cache `<repo>/.cache` (gitignored `.gitignore:39`);
  `get_global_config_dir()` = `<repo>/.cache/config` (`config.py:304`, const
  `DIR_GLOBAL_CACHE=".cache/config"`). Temp PNGs go in `.cache/vision_render/<run-id>/`,
  NOT system `/tmp` (user requirement); cleaned in `finally` + per-run wipe + startup sweep.

## Open Investigations Before Coding (P0)
1. Can the provider client factory build an INDEPENDENT vision client (separate
   auth/state) for each provider? (Backend client design gate, applies to both slots.)
2. `fitz` `get_pixmap` render path; pin `vision_render_dpi`=170 + per-provider
   longest-edge caps for `vision_max_image_px` (R14).
3. Confirm the plugin runtime snapshot exposes BOTH resolved model ids
   (`vision_model`, `latex_extract_model`) for plugin-side region flows.
4. Region-image capture for a right-click TEXT selection (Convert-to-LaTeX) vs a
   Cmd+Shift+X crop — is a rendered region image available, or fall back to
   selection-image+text?

## Decisions captured from user (2026-06-21)
- A: always-on when `vision_model` is set (default empty = pymupdf4llm).
- B (revised): TWO slots + fallback. `vision_model` (heavy, ingest) +
  `latex_extract_model` (light, interactive snip/convert; empty → vision_model →
  main-vision). The unreleased text `latexModel` is reshaped in place into
  `latex_extract_model` (image-based light vision), no migration. Rationale: region
  OCR and full-page layout parsing are different task/capability classes (Mathpix/
  Nougat full-doc engines vs pix2tex/texify region specialists), and interactive
  snips are latency/cost-sensitive while ingest is accuracy-first.
