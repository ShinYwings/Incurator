# Critique on the Backend + Plugin proposals

Date: 2026-06-21 | Agent Persona: red_teamer + schema_guardian + qa_runner

## 1. Vulnerabilities & Flaws

### R1 — VLM hallucination silently corrupts L1 (most serious)
A VLM transcribing a page can **invent or alter math/text** with full confidence.
If VLM output becomes L1 verbatim, a fabricated formula enters the knowledge graph
as ground truth — strictly worse than pymupdf4llm's honest-but-approximate text.
SYSTEM_BEHAVIOR §26 already warns "parseable LaTeX alone verifies nothing." The
proposal's per-page fallback handles *failure*, not *confident wrongness*.

### R2 — "Always-on" + bulk = the exact corpus blow-up §26 was written to prevent
A user who points `add` at a 500-PDF folder now triggers tens of thousands of VLM
calls. Cloud = real money; local = effectively a multi-hour hang. The guardrails
(concurrency/timeout) bound *per-page* pain but nothing bounds *total* spend. The
plan rewrites §26 to *allow* this — so the safety rail is gone by design.

### R3 — Non-vision or unreachable model chosen as the PDF model
If `vision_model` is set to a text-only model (or a cloud vision model with no
auth), every PDF ingest fails or returns garbage. The dropdown filter helps in the
plugin, but `config.yml` can be hand-edited and the backend must not trust it.

### R4 — Two clients, double cost on standalone images
`_build_vision_client` is also used for standalone image files + md-linked images.
If `vision_model` is set, those now use the dedicated model too — fine — but verify
we are not building a NEW client per file (perf) and that the main-client legacy
path still works when `vision_model` is empty.

### R5 — Plugin/backend model drift
The plugin "mirrors" the backend `vision_model`. If the mirror is a copied setting
(not a live read), Dashboard edits and `wiki config` edits desync, and Cmd+Shift+X
uses a stale model. Classic two-sources-of-truth bug.

### R6 — Latency UX on Cmd+Shift+X
Snip currently feels instant (attach image, done). Adding a blocking VLM round-trip
(seconds, or much longer on local) makes the snip feel broken without clear
feedback. Also: what if the user snips and immediately types — race on the chip.

### R7 — Migration of v0.21.0 `latexModel`
Retiring a field shipped one release ago: users who set it lose it silently;
`settings.test.ts` / DEFAULT_SETTINGS contracts must be updated; docs that just
documented `latexModel` must be rewritten, not left dangling.

### R8 — Schema/provenance: is "vlm" L1 reversible/auditable?
If L1 is VLM-authored, the DAG must record WHICH model and that it is VLM-derived
(not human-verified) so lint/audit can distinguish a transcription from a real
source span. `parser_used: "vlm"` on the source is necessary but maybe not
sufficient at the span/claim level.

### R9 — Two-slot fallback ambiguity (new, from the revised B)
With `latex_extract_model → vision_model → main`, the EFFECTIVE model for a snip is
non-obvious. A user who set only `vision_model` (heavy) will silently get slow/
expensive snips and not know why. Worse: a user sets a *text-only* model in
`latex_extract_model` (it's "light"!) and every snip fails or returns garbage.

### R10 — Ingest must NOT borrow the light model
If the resolver chain is applied uniformly, `add source` could accidentally resolve
to `latex_extract_model` (a tiny region model) and produce terrible full-page L1.
The two resolvers must be kept separate: ingest = `vision_model` only.

### R11 — Capability mismatch: a "light" model that can't do layout
The light region model (qwen2-VL-2B / pix2tex-class) is GOOD at isolated equations,
BAD at multi-column pages. If a user snips a large multi-column region expecting
full extraction, the light model underperforms. Scope of the light model must be
documented as region/equation-grade, not page-grade.

## 2. Suggested Alternatives

- **R1/R8 (anti-hallucination)** — do NOT treat VLM output as unconditionally
  authoritative:
  - Keep pymupdf4llm text per page as a **cross-check sibling**, stored in metadata
    (`metadata.vlm_transcription` + `metadata.parser_text`), so a later audit/lint
    can diff them. L1 uses VLM text but provenance preserves both.
  - Reuse the existing **formula token cross-check** (`_formula_tokens` /
    `_is_formula_subsequence` from `claim_support`): when pymupdf4llm DID yield a
    formula and the VLM formula diverges structurally, flag the page
    `formula_status` signal rather than silently trusting VLM.
  - Label VLM L1 clearly; never auto-promote VLM-only formulas to `verified`
    without the same evidence gate §26 already mandates.

- **R2 (total-spend rail)** — keep always-on *per source* but add a **batch
  guard**: before an `add` run that would VLM-transcribe more than N pages total
  (config `vision_max_pages_per_run`, default e.g. 300), require an explicit
  `--vision` / confirmation, or process the first N and report the rest as
  `vision_skipped` (logged, not silent). Always-on for a paper; guarded for a
  library. This honors the user's "그냥 vlm" for normal use while not removing the
  rail §26 cared about.

- **R3 (validate the model)** — backend validates `vision_model` advertises vision
  at client-build time; if not, log a clear error and fall back to pymupdf4llm
  (never garbage). Plugin dropdown already filters to `supportsVision`.

- **R5 (single source of truth)** — the plugin must **read** the backend-resolved
  `vision_model` from the runtime snapshot the Dashboard already fetches, NOT keep a
  parallel persisted copy. If a plugin setting is unavoidable, write-through to
  backend config on change and re-read on Dashboard open.

- **R6 (snip latency)** — show a "Transcribing region…" notice + keep the raw image
  attached immediately; replace with the transcription when it returns (progressive
  enhancement), so a slow model never blocks the chip from appearing.

- **R7 (latexModel) — SUPERSEDED by branch decision**: `latexModel` is unreleased on
  this same branch, so it is removed/reshaped into `latex_extract_model` in place —
  no migration code, no deprecation notice. Update settings tests + the v0.21.0 docs
  in the same change.

- **R9 (fallback transparency)** — the Dashboard light row shows the EFFECTIVE
  resolved model when empty ("↳ using <vision_model>"), and the light dropdown is
  filtered to vision-capable models so a text-only choice is impossible via UI;
  the plugin/backend also validate vision at use and fall back rather than fail.

- **R10 (resolver separation)** — TWO distinct resolvers: `_resolve_vision_client`
  (ingest: `vision_model`→main→None) and `_resolve_extract_client` (interactive:
  `latex_extract_model`→`vision_model`→main). Ingest calls ONLY the former. Covered
  by a unit test asserting ingest never selects `latex_extract_model`.

- **R11 (light-model scope)** — document `latex_extract_model` as region/equation-
  grade (isolated math, small crops), explicitly NOT a full-page parser; the snip
  prompt is scoped to "transcribe this region", not "parse this page".
