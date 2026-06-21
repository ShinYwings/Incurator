# Backend Proposal: vision_model slot + VLM-PDF ingest path

Date: 2026-06-21 | Agent Persona: lead_architect (Backend/Ingest)

## 1. Core Logic & Implementation

### 1.1 Two first-class config slots (`provider::model`, empty = disabled)
- In `config.py` DEFAULT `llm` block, add as siblings of
  `primary`/`fallback`/`embedding`/`reranker`:
  - `"vision_model": ""` — heavy, full-page ingest + image description.
  - `"latex_extract_model": ""` — light region OCR for interactive surfaces.
- STOP stripping `vision_model` in `_migrate_llm_config`; preserve BOTH keys
  (remove `vision_model` from the pop loops, do not add `latex_extract_model`).
- Reuse `split_provider_model` / `join_provider_model`.
- Render/cost knobs (defaults chosen for reliable cloud ingestion):
  - `vision_render_dpi` = 170 (target DPI for `get_pixmap`).
  - `vision_max_image_px` = 1600 (hard cap on longest edge; downscale past it).
  - `vision_max_pages_per_run` = 300 (total-spend rail for one `add` run).

### 1.2 Resolver with explicit fallback chain (decoupled from main)
Two resolution helpers, both building an INDEPENDENT client via the same provider
factory the main client uses (antigravity/claude/openai/ollama all supported).

**CRITICAL fallback rule (reviewer correction):** the chain advances to the next
model ONLY when a slot is **empty / unconfigured**. A **configured** slot that fails
(non-vision model, unreachable, auth failure, build error) RAISES an explicit error
and HALTS — it must NOT silently fall through to a heavier model. Silent fall-through
on failure would cause surprise latency/cost spikes (a failing light model quietly
escalating to the heavy `vision_model`) and mask broken config.

```python
def _resolve_vision_client(config, main_client):
    """Heavy ingest model. Empty → next; configured-but-bad → raise."""
    vm = (config["llm"].get("vision_model") or "").strip()
    if vm:                                   # configured → MUST succeed or raise
        p, m = split_provider_model(vm)
        return _require_vision(build_llm_client(p, m, config), slot="vision_model")
    if getattr(main_client, "supports_vision", False):   # empty → legacy main
        return main_client
    return None                              # empty + no vision main → pymupdf4llm

def _resolve_extract_client(config, main_client):
    """Light interactive model. Empty → next; configured-but-bad → raise."""
    lm = (config["llm"].get("latex_extract_model") or "").strip()
    if lm:                                   # configured → MUST succeed or raise
        p, m = split_provider_model(lm)
        return _require_vision(build_llm_client(p, m, config), slot="latex_extract_model")
    return _resolve_vision_client(config, main_client)   # empty → fall to vision chain
```
- `_require_vision(client, slot)` RAISES `ConfigError(f"{slot} '<model>' is not
  vision-capable / unreachable")` when the configured client cannot do vision; it
  never returns None for a configured slot. Empty-slot fall-through is the ONLY
  silent path.
- **Ingest config-failure vs per-page runtime fallback** are distinct:
  - A configured-but-broken `vision_model` raises UPFRONT and halts `add source`
    (the user must fix config) — it does NOT silently degrade the whole doc to
    pymupdf4llm.
  - During a VALIDATED run, a transient per-page timeout/error falls back to
    pymupdf4llm text **for that page only**, logged + recorded in provenance
    (`metadata.parser_text`) — visible, never silent.
- **Ingest** (PDF page extraction + image description) uses `_resolve_vision_client`
  ONLY — never borrows `latex_extract_model` (R10).
- `_build_vision_client` is renamed/replaced by `_resolve_vision_client`; the
  standalone-image and md-linked-image paths switch to it, behavior-identical when
  both slots are empty (legacy main-client-if-vision).

### 1.2a Per-provider vision call & image transport (P0 outcome — NO API keys)
`describe_image(image_bytes, prompt)` is implemented per client according to its
transport. Cloud vision uses the existing CLI **subscription auth** — NO provider
API keys (direct vision-API clients are a non-goal).
- **Ollama** (already implemented): in-memory `base64` over httpx `/api/chat`
  `images` — **no temp file**.
- **Agentic CLI — ALL THREE CONFIRMED by live P0 test (claude, agy, codex)**:
  the CLI reads a file path with its built-in vision-capable Read tool, so the
  rendered page is written to a temp PNG and its path referenced in the strict
  transcribe prompt. Per-provider invocation (P0-verified):
  - `claude -p "<prompt>" --allowedTools Read --add-dir <.cache>` — cleanest,
    output-only.
  - `agy --print "<prompt>" --print-timeout <t>` — clean, wraps output in `$$`.
  - `codex exec "<prompt>"` — correct but NOISY (echoes cwd files + token banner;
    agentic over cwd); needs strict output extraction + a clean/isolated cwd.
  - **NEVER pass auto-approve/unsafe flags** (`--dangerously-skip-permissions` is
    policy-blocked and unnecessary — plain print/exec works).
  - **Output normalization (REQUIRED)**: strip `$$` wrappers, codex banners/
    "tokens used" lines, code fences, and any commentary before the transcription
    becomes L1. A per-provider normalizer + a strict "output ONLY LaTeX" prompt.
- **Temp PNG location = project `.cache` (user requirement):** temp PNGs are written
  under the project cache, NOT system `/tmp`. Use `<repo>/.cache/vision_render/`
  (sibling of `.cache/config` + `.cache/models`); resolve via the existing
  `get_global_config_dir().parent` (= `<repo>/.cache`) and a dedicated
  `vision_render/` subdir. `.cache/` is already gitignored (`.gitignore:39`), so the
  byproducts never leak into the repo or `~` (consistent with the "no byproducts
  leak into ~" cache policy in `config.py:304`).
- **Temp PNG lifecycle (MANDATORY — user requirement):** every temp PNG MUST be
  deleted after use, **guaranteed even on exception, timeout, or process kill
  mid-page**. `try/finally` `os.unlink` in `finally`; never rely on the happy path.
  Use a single per-run subdir under `.cache/vision_render/<run-id>/` removed
  wholesale at run end as a backstop; on startup also sweep any stale
  `.cache/vision_render/*` left by a previously killed run. No temp PNG survives a
  run. A test asserts the dir is empty after BOTH success and failure paths.

### 1.3 VLM-PDF ingest path (always-on when set)
PDFs are parsed by the pure `parsers/pdf.py` (pymupdf4llm) for structure/ToC/images
as today. Then, in `ingest_raw.py` where `file_type == "pdf"` and a vision client
exists, run a **page-by-page VLM transcription pass** that becomes the L1 text:

```python
if parsed.file_type == "pdf" and has_vision:
    resolved_model = vision_client.model            # for the cache key (see below)
    page_images = _render_pdf_pages(file_path, dpi=VISION_RENDER_DPI)  # bounded; see 1.4
    vlm_pages = _transcribe_pdf_pages_with_vision(
        vision_client, page_images,
        prompt=PDF_LATEX_TRANSCRIBE_PROMPT,   # "Transcribe to Markdown; math as $..$/$$..$$"
        per_page_timeout=..., max_concurrency=...,
    )
    # Per-page fallback: a failed/empty VLM page keeps the pymupdf4llm text for that page.
    source_text = _merge_vlm_with_parser(vlm_pages, parsed.metadata["pdf_pages"])
    parser_used = "vlm"
else:
    source_text = parsed.text   # pymupdf4llm
```
- `parser_used` recorded as `"vlm"` so provenance shows which path produced L1.
- pymupdf4llm output is retained as the **per-page fallback** and as structural
  metadata (ToC, images, page map) — never discarded.

### 1.3a Cache key MUST include the resolved model (reviewer correction)
The per-page transcription cache key is **`(page_content_hash, resolved_vision_model)`**,
NOT the content hash alone. Changing `vision_model` in the Dashboard MUST invalidate
prior extractions; otherwise the system silently serves the previous model's L1 for
already-ingested PDFs. The resolved id (provider::model) is part of the key, so a
model switch forces re-extraction on the next `add`/build; the prior entry remains
cached under its own key for cheap revert. (Also store `parser_used`/model in the
source metadata so an audit can see which model authored each page's L1.)

### 1.4 Optimal pipeline + cost/time guardrails (always-on, but safe)
- **Optimal-over-minimal principle (user directive):** choose the best-performing
  implementation, not the smallest diff or fewest deps. For PDF→image that is
  PyMuPDF `get_pixmap` (in-memory, C-speed) — poppler/`pdf2image`/Ghostscript are
  slower external-binary paths and are rejected on merit, not dependency-avoidance.
  Add a dep (e.g. Pillow LANCZOS) ONLY if P0 shows fitz's own `Matrix` downscale is
  visibly worse.
- **In-memory where possible:** page render is in-memory; Ollama sends base64 with
  no disk I/O; only the agentic-CLI path touches disk (temp PNG, cleaned per 1.2a).
- **Bounded concurrency:** render + transcribe pages with a bounded worker pool
  (Ollama HTTP / CLI subprocess pool), not sequentially — wall-clock ≈ slowest pages
  / concurrency, not the sum.
- **Bounded render resolution (reviewer correction)**: rendering must NOT use an
  unbounded/high DPI — dense pages would exceed model image-payload/token limits.
  Config knob `vision_render_dpi` (default **170**, range ~150–200) AND a hard
  **max-longest-edge pixel cap** (`vision_max_image_px`, default ~1600px to fit the
  tightest cloud vision limit, e.g. Claude's 1568px longest edge); after
  `get_pixmap` at the target DPI, downscale if the longest edge exceeds the cap.
  This guarantees every page render is a reliably-ingestible image regardless of
  physical page size. (P0 confirms exact per-provider caps.)
- **Content-hash cache**: key VLM page transcription by
  `(page_content_hash, resolved_vision_model)` (see 1.3a) so re-`add`/re-build of an
  unchanged source on the SAME model never re-pays, while a model switch correctly
  invalidates. (Reuse the existing per-page `content_hash` in `pdf_pages`.)
- **Concurrency + per-page timeout**: bounded parallel page calls; a page that
  times out falls back to pymupdf4llm text for that page (no hang).
- **Large-PDF notice**: log/emit a progress line per N pages and an upfront warning
  when `page_count` is large, so a slow local VLM is visibly progressing.
- **Failure isolation**: any whole-pass VLM failure degrades to pymupdf4llm for the
  whole doc with a logged reason — ingest never hard-fails because of the VLM.

### 1.5 Spec revision (mandatory, P1)
- SYSTEM_BEHAVIOR §26: revise the "whole-corpus/every-page VLM rejected" rule to:
  *whole-corpus VLM is rejected as an automatic/implicit default, but a
  user-elected `llm.vision_model` makes page-level VLM transcription the chosen L1
  extractor for `add source`; the selective measured-loss recovery path remains the
  behavior when no vision model is configured.*
- SCHEMA: document both slots (`vision_model`, `latex_extract_model`) + their
  fallback chain + `parser_used: "vlm"` semantics + per-page `parser_text`
  provenance retention.

## 2. Pros & Cons

**Pros**
- Resurrects existing, half-built vision infra rather than inventing a parallel one.
- Pure parser stays pure; VLM lives at the ingest orchestration layer (matches the
  existing image-description pattern).
- Provider-agnostic via the existing client factory; per-page fallback keeps ingest
  robust and never worse than today.
- Content-hash caching makes re-builds free, blunting the always-on cost.

**Cons / limits**
- VLM transcription can hallucinate/alter math (red-team §). Need cross-checks and
  honest provenance, not blind trust.
- Cloud vs local image payload + auth differences must be handled in the client
  factory (likely already partly handled for chat vision).
- Always-on bulk ingest is genuinely expensive/slow; guardrails mitigate but do not
  eliminate. Documented, user-accepted.
