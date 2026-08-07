# Product Honesty Proposal: Say What Was Lost, Where, And What To Do About It
Date: 2026-08-08 | Agent Persona: Product Honesty Advocate

## 1. Core Logic & Implementation

### 1.0 Where I stand relative to the RAG analyst's proposal

I read `01_proposal_rag_analyst.md` in full. Its P0 (deterministic
`_classify_omitted_region` on the placeholder's pixel dimensions,
`pipeline/source_spans.py`) and P0b (one-shot SQL backfill of
`source_spans.metadata` for the 130 existing placeholder spans, no re-parse,
no LLM) are the correct foundation and I build my surfaces directly on their
output contract: `metadata.omitted_region = {width, height, kind}` per span,
`kind ∈ {equation_band, figure, glyph}`. I do not re-derive that
classification; I specify *when* and *in what words* four different surfaces
report it, and I found one costed trap in the RAG proposal's own retrofit
path that changes what "minimum" can honestly mean (§1.5).

My territory is briefing §2.4 and the four surface/moment questions in my
brief. I measured every claim below against the same files the briefing and
the RAG proposal cite; line numbers are current as of 2026-08-08.

### 1.1 The four surfaces, in the order the user actually hits them

**Surface 1 — `wiki add` / "add resource" (ingest time, the first possible
moment).**

`backend/src/curator/commands/core.py:736-762` is the L1 loop. Today the only
output per source is:

```
_ok(f"  L1 [{context_id}] ← {row['relpath']}")
```

Nothing downstream of `generate_l1_structural_context` inspects what was
lost. It should, because P0's classification runs during that exact call
(`_extract_structural_sections` → `spans_from_sections`, `ingest_raw.py:1470`)
— the count is already computed by the time this line prints; nothing new
needs to be computed to report it, only surfaced. Add, immediately after the
`_ok` line, gated on `n_equation_band > 0` for that source only (silence for
the ~majority of PDFs with no image-only regions — this must never fire on a
PDF that lost nothing):

```python
if region_counts.equation_band:
    _warn(
        f"    {region_counts.equation_band} equation-like region(s) on "
        f"{region_counts.pages} page(s) of {row['relpath']} could not be "
        "read (rendered as images, not text). Run `wiki lint` for the full "
        "list, or see `wiki add --help` note below to recover them."
    )
```

Measured wording constraint: this must name a *count and a location class*
("N regions on M pages"), not just "some formulas may be missing" — a vague
warning trains users to ignore it. It must NOT say "images were discarded"
in a way that implies data loss beyond what happened; "could not be read" is
accurate (pymupdf4llm never had text to lose — see RAG §1.1 step 1) and
"rendered as images, not text" is the actual, verifiable mechanism.

**Surface 2 — `wiki lint` (standing health signal, every run).**

I endorse the RAG proposal's `check_image_only_regions` (§1.5 P1) as the
correct *category and severity*: reuse `CheckId.COMPILER_INTEGRITY`
(`lint.py:61` — already the non-DAG-breaking source-fidelity bucket),
`Severity.WARNING`. I am prescribing the exact user-facing text, because
`lint.py`'s existing checks (e.g. `check_missing_source_files`,
`lint.py:694-745`) set the bar: every message names a count, every
suggestion names a runnable command. Mine must match that bar:

```python
LintIssue(
    check=CheckId.COMPILER_INTEGRITY,
    severity=Severity.WARNING,
    page=f"{consts.LAYER_L1}/{context_id}.md",
    message=(
        f"Source #{source_id} ({relpath}): {n_regions} region(s) on "
        f"{n_pages} page(s) render as images and were not read by the "
        f"text-layer parser ({n_equation} look like equations)."
    ),
    suggestion=(
        "These regions are not in the vault and cannot be searched or "
        "cited. To transcribe them, set `llm.vision_model` (Obsidian "
        "Dashboard → LLM → \"PDF ingest (vision)\") and re-ingest this "
        "source. If these are figures/diagrams you don't need answered "
        "from text, no action is needed."
    ),
    fixable=False,
    context={"source_id": source_id, "pages": [...], "counts": {...}},
)
```

The explicit "if these are figures you don't need, no action is needed"
clause matters: it is the honest acknowledgment that not every image region
is a loss the user cares about, and it is what stops this from reading as
an alarm the user must dismiss 130 times. This is a WARNING, never an ERROR
— it is a source property, not a broken DAG, matching `lint.py`'s existing
severity discipline (`ERROR` = "breaks linking or makes pages unusable").

**Surface 3 — opening the PDF in the plugin (the moment the user is looking
at the exact page).**

This is the surface I measured most carefully, because it is the one the
RAG proposal's backend-only P0-P3 does not automatically reach. The user's
reported scenario — "open page 4, ask about equation 26 on page 22" — is
served by `backend/src/curator/plugin_api/pdf.py:pdf_context()`, NOT by
`wiki query`. For a tracked source with `l1_status == 'done'` (source 37
qualifies), `pdf_context` calls `_durable_l1_projection()`
(`plugin_api/pdf.py:62-117`), which parses the **already-written L1 CTX
markdown file's body** (`page_writer.read_page`,
`_CTX_SECTION_RE.finditer(parsed.body)`) — not a fresh PDF re-parse, not
`source_spans` directly.

That CTX body is exactly what `ingest_raw.py:1094`'s `_section_preview`
produces, and the RAG proposal's own trace (§1.1 step 5, §1.2 table) already
proved: for a large source on the non-inline branch (`source_37`, 27 pages,
`_should_inline_source_sections` → False, `ingest_raw.py:1124-1128`), *every*
section's text is `_section_preview` output — the exact function that erases
`intentionally omitted` down to a single space. **This means the plugin's
own PDF-context surface — the one actually driving the reported chat turn —
is fed the erased text today, and would be fed the fixed text automatically
once `ingest_raw.py:1094` stops stripping to blank and instead writes a
compact marker.** No plugin code change is required for this surface. That
is the "minimum change" headline of this proposal (§1.3).

Concretely, once P1's fix lands (`ingest_raw.py:1094`):

```python
cleaned = re.sub(
    r"\*\*==>.*?intentionally omitted.*?<==\*\*",
    lambda m: f"[image region, not extracted — see `wiki lint`]",
    cleaned,
)
```

(exact bracket text open to bikeshedding; the requirement is that it is
non-empty, is not the raw parser apology string — which is meaningless to a
reader who doesn't know pymupdf4llm — and is short enough not to visually
dominate the CTX page), `_section_preview`'s output changes, the CTX `.md`
file changes, `_durable_l1_projection` reads the new text, `pdf_context`
returns it in `pages_out[].text`, and the plugin's chat context — and a
*human* reading the CTX page directly in Obsidian, unprompted by any
chat turn at all — both see it. One string change, two readers fixed.

**Surface 4 — the chat answer itself.** Covered in §1.2 below; it is really
two different answers depending on whether the location is known.

### 1.2 What the assistant should say — grounded specificity, never a
guessed page

The brief asks me to take a position on "equation 26 on page 22 is an image
and was not transcribed" versus v0.48.4's "I could not retrieve it," and
whether specificity "leaks implementation detail."

**My position: naming the page, dimensions, and mechanism is not an
implementation-detail leak — it is a citation, in the same category as
naming a page number for any other fact this system answers from.** A user
who is told "page 22, 182×24px region, not transcribed" can go look at page
22 and verify the claim, exactly as they can verify a normal citation. A
user told only "I could not retrieve it" cannot verify anything and cannot
distinguish "you never had this," "you have it but the retriever missed
it," and "you have it but chose not to show me" — three very different
trust failures that read identically in the vague phrasing. Specificity is
strictly more honest *when it is true*.

The qualifier is load-bearing: **it must never be stated unless the system
actually resolved the location.** `crossReferenceResolver.ts`'s current
`UNRESOLVED_NOTE` (lines 716-722) is deliberately hedged — "commonly
because... or because it lies outside the pages loaded" — precisely because
today the resolver has no location signal for an unresolved reference; it
genuinely does not know which of several causes applies. Replacing that
hedge with a fabricated page number would be a worse failure than the
current vague one: a wrong specific claim is more damaging than an honest
"I don't know," because it looks verifiable and isn't. **So this is not a
single wording fix; it is two answers gated on whether resolution
succeeded, and the gate must not be relaxed to "guess the nearest page."**

- **Tier 0 (today; ungrounded; zero backend change).** Keep
  `UNRESOLVED_NOTE`'s shape but tighten it to name the general mechanism
  without inventing specifics, and to make the recovery path concrete
  instead of implicit:

  ```
  The text behind these references could not be found anywhere in this
  document's extracted text. If this PDF renders its equations or figures
  as images (common for typeset math), the text layer never captured them
  and no search will find them. Answer from the context already provided
  and say plainly that you could not retrieve the referenced item; do not
  attempt to open, read, or search the source file yourself. If the user
  asks how to fix this, tell them: enable vision-based PDF extraction
  (Obsidian Dashboard → LLM → "PDF ingest (vision)") and re-add the source.
  ```

  This is a same-file, same-function change (`UNRESOLVED_NOTE`,
  `crossReferenceResolver.ts:716-722`) — it does not depend on any backend
  work and can ship on its own. It keeps the existing, correct "don't try
  to open the file" and "answer from context" clauses verbatim; those are
  right and I am not touching them.

- **Tier 1 (once Surface 3's fix lands; grounded; zero *additional*
  backend or plugin code — falls out of §1.1's marker fix).** When the
  resolver *does* land on the right page — because the user is viewing it,
  because an outline/adjacency hit succeeds, or once the RAG proposal's P2/P3
  make the region's title lexically matchable — the page text the model
  reads already contains the marker verbatim
  (`[image region, not extracted — see 'wiki lint']`, or whatever exact
  string P1 settles on, at the correct page and position). A general-purpose
  chat model reading that marker in context needs no special-cased prompt
  instruction to describe it accurately; this is exactly what these models
  already do with any other piece of context. **The only prompt-side
  requirement is: do not strip the marker before it reaches the model** —
  which is a re-statement of "don't add a new filter that erases it," not a
  new capability to build. The honest, specific answer ("page 22 contains an
  image region here that wasn't transcribed") is a natural consequence of
  correct context hygiene, not a new sentence someone has to write and
  maintain.

I am explicitly **not** proposing that the resolver or the LLM guess a page
when no evidence points to one. `len(cands) != 1` in the RAG proposal's
locator (§1.5 P2) already encodes this discipline on the backend side; the
same discipline — resolve or say "not found," never "probably here" — must
hold on the plugin's cross-reference resolver too, and it already does
(`resolveReferences` either returns a match or nothing; there is no
"nearest guess" branch in `crossReferenceResolver.ts` today, and none
should be added).

### 1.3 `_resolve_vision_client(_vcfg, None)` — should `main-if-vision` fire
silently at ingest?

**No.** I read the RAG proposal's con #8 (it independently flags the same
defect and declines to fix it) and I agree with the conclusion but want to
state the honesty argument for it plainly, because "should this fire" is
squarely a trust question, not just a cost question.

SYSTEM_BEHAVIOR §26.2a is unusually explicit that `vision_model` is a
**deliberate, costed, opt-in** choice at ingest: "A configured-but-broken
`vision_model` raises upfront and halts... it does not silently degrade the
whole document to pymupdf4llm" (§26.2a, "Resolver discipline"). That
sentence exists specifically to stop ingest from silently changing behavior
underneath the user. Auto-firing `main-if-vision` merely because the user's
*main chat model* happens to be vision-capable — a fact about a completely
different decision (which CLI they chat through) — violates that same
principle in the opposite direction: it would silently turn ingest from "a
few seconds of structural parsing" (`add()`'s docstring: "L1 is generated
immediately... without an LLM call") into a full-page VLM pass over every
page of every PDF (`vision_max_pages_per_run` default ~300), for every user
whose chat provider happens to support vision — which is most of the
supported CLI providers (Antigravity, Claude, Codex, per §26.2a's "Cloud
vision uses CLI subscription auth"). That is not a narrow fallback; for the
majority default configuration, it is **effectively always-on VLM ingest,
turned on by a coincidence of an unrelated setting, with no moment where the
user agreed to the cost or the latency.**

Compare this to the *interactive* main-if-vision tail, which the spec keeps
distinct on purpose (§26.2a, "Cmd+Shift+X"): that path fires once, per
user-initiated click, on one page, visibly, inside a turn the user is
already watching. Ingest's `add` is unattended and batch; firing the same
fallback there multiplies the blast radius by up to 300 pages with no
click, no visibility, and no per-invocation consent. The two are not the
same "fallback" merely because they share a resolver function name, and
treating them as interchangeable is exactly the kind of code-level
equivalence that produces a UX-level surprise.

My recommendation is the same shape as §1.1's detection-and-prompt, not a
resolver change: fix the `_resolve_vision_client(_vcfg, None)` call site so
its behavior matches what it is actually meant to do — collapse to
`vision_model → None` explicitly, with a comment saying why
`main_client` is intentionally not passed at ingest — and let Surface 1/2's
warning be the mechanism that gets a vision-capable user to *opt in*
deliberately (§1.1's `wiki lint` suggestion already names
`llm.vision_model`; it should also mention, only when the user's configured
main model is vision-capable, "your chat model can already read images —
enabling this only requires flipping one setting" as an extra nudge, still
requiring the user's own action). Turning the silent gap into a silent
auto-fire is trading one invisible behavior for a more expensive invisible
behavior; turning it into a nudge that names the exact cost-free reason it
would be cheap for *this* user is the honest version of the same insight.

### 1.4 Is `vision_model` reachable as shipped? — Abdication, not a fix

Measured, not asserted:

- `load_config` (`config.py:454-510`) merges `DEFAULT_CONFIG` with whatever
  is on disk but **never writes new default keys back to
  `.curator/settings.yml`**. Any vault initialized before `vision_model` was
  added (v0.22.0) has no `llm.vision_model` line in its actual settings
  file — confirmed structurally: the merge is one-directional
  (disk overrides defaults; defaults never get persisted).
- `wiki status`'s config table (`commands/core.py:422-465`) prints Primary,
  Fallback, Account, Ollama host, Search backend, Reranking, Embedding,
  Search engine. **No `vision_model` row exists.** A user running the one
  command whose entire job is "show me my config" gets no signal this
  feature exists.
- No `wiki config` subcommand lists it either; `wiki config set
  llm.vision_model <value>` works if you already know the exact key name,
  which is not a discovery path, it's a typing target for someone who
  already read the source or the spec.
- It **is** reachable through the Obsidian Dashboard
  (`incuratorDashboardModal.ts:947-956`, row labelled "PDF ingest
  (vision)") — so "fully implemented and simply unset" is technically true
  but materially misleading as a characterization of the user's experience.
  Implemented-and-configurable-if-you-already-know-where-to-look is not
  discoverable; it is buried one settings modal away from a feature nobody
  is told exists at the one moment it would matter (the ingest that just
  lost 158 images).

**Verdict: shipping "the user should have configured it" is an abdication.**
The feature exists to solve exactly this problem (§26.2a's own stated
motivation: "pymupdf4llm text-layer extraction cannot reliably reconstruct
LaTeX for math") and the product never once, in four candidate moments
(ingest, lint, status, dashboard-on-open), tells the user that their exact
situation is the one this setting was built for. "It's in the Dashboard" is
not a defense; a setting nobody is pointed to is equivalent to a setting
that doesn't exist, from the user's vantage point.

The detection-and-prompt trigger, precisely, so it cannot become the nagging
banner the brief warns against:

- **Fires**: at `wiki add`/"add resource" completion, only for the specific
  source(s) just processed in *this* run, only when that source's
  `equation_band` region count (P0's classifier) is `> 0`. A PDF with zero
  image-only regions — the common case — triggers nothing, ever.
- **Does not fire**: on `wiki status`, on re-running `wiki add` with no new
  sources, on sources that already have zero image-only regions, on
  non-PDF sources (parsers other than `parsers/pdf.py` don't emit this
  placeholder). `wiki lint`'s WARNING is the *standing* record (it reports
  every run, like every other lint check) — the ingest-time nudge is a
  one-shot notice at the moment of discovery, not a repeating alarm. This
  split — "told once when it happens, findable forever after via lint" — is
  the same shape `check_missing_source_files` already uses for a different
  problem, so it is not a new UX pattern, just a new application of one
  that already ships.

### 1.5 The minimum change — and a cost trap I found in getting there

**Minimum honest-failure change, in priority order, each shippable alone:**

1. `ingest_raw.py:1094` marker fix (§1.1 Surface 3) — one regex
   replacement string. Fixes the CTX page (human-readable in Obsidian) and
   `pdf_context`'s projection (the plugin PDF-chat surface actually
   involved in the reported bug) simultaneously, for **every source ingested
   from this point forward**, with no LLM cost.
2. `crossReferenceResolver.ts`'s `UNRESOLVED_NOTE` tightened per §1.2 Tier 0
   — a string constant, no logic change, ships independently of the
   backend.
3. `wiki add`'s per-source nudge (§1.1 Surface 1) and `wiki lint`'s new
   WARNING check (§1.1 Surface 2), both consuming P0/P0b's
   `metadata.omitted_region` — these depend on the RAG proposal's P0/P0b
   landing first, but add no LLM cost of their own.

Even if `recover_formula()` is never wired up and no equation is ever
recovered — Route C alone, permanently — a user who adds source 37 tomorrow
gets: a `wiki add` line naming "95 equation-like regions on 17 pages," a
`wiki lint` entry every run until they act or dismiss it, a CTX page in
Obsidian that says "[image region, not extracted]" instead of nothing, and
(when the resolver lands on the right page) a chat answer that names the
page and says so. That is the full distance between "it was added
correctly, and the system still doesn't work" and "it was added correctly,
and here is exactly what didn't come along and why." No recovery is
required to close that gap — only refusing to erase the evidence that
already exists.

**The trap: `wiki add --force` is not a safe way to retrofit the 4 already-
ingested sources' CTX pages.** I traced this because I assumed, going in,
that re-running `add --force <file>` on source 37 would be the obvious way
to pick up the item-1 fix for already-ingested sources, the same way the RAG
proposal frames P0b as "no re-ingest." It is not obvious, and it is not
free:

- `commands/core.py:693-704`: `add --force` sets, for every targeted
  source, `l1_status='pending', l2_status='pending', l3_status='pending',
  l4_status='pending'` — not just `l1_status`.
- `add()` itself only regenerates L1 in the same invocation (Phase 2,
  `core.py:736-762` — no L2/L3/L4 code runs inside `add()`).
- But `build()`'s default (non-force) source selection
  (`commands/core.py:806-812`) is `l1_status = 'done' AND (l2_status IN
  ('pending','error') OR l3_status IN ('pending','error'))`. A source that
  was `add --force`'d for the L1 fix now matches that clause on the very
  next plain `wiki build` — even one the user runs for an unrelated newly
  added source — and gets **fully re-processed at L2/L3**: a real LLM pass,
  re-extraction of all 171 units on source 37, exactly the "two orders of
  magnitude more expensive" cost the RAG proposal's §1.3 warns about for
  Route B, arrived at through a completely different door.

This means: for the 4 already-ingested sources, item 1's CTX-page fix
cannot honestly be presented as free the way P0b's SQL metadata backfill
is. Regenerating the *already-written* CTX markdown file requires either
(a) a narrow code path that calls the L1-writing logic directly without
going through `add()`'s force-flagging (so `l2_status`/`l3_status` are never
touched), which does not exist today and is real, if small, new work — a
`schema_guardian`/`lead_architect` call, not mine to design — or (b)
accepting that those 4 sources' CTX pages and plugin PDF-context stay stale
until they are next legitimately re-ingested, while `wiki lint` (which reads
`source_spans.metadata` directly via P0b's SQL backfill, not the CTX file)
is the honest, immediately-accurate surface for them in the meantime.

I am flagging this as a **constraint on what "minimum" can mean for already-
ingested sources**, not reversing my recommendation: item 1 should still
ship for all future ingests without qualification. For the 4 existing
sources specifically, the master plan must pick (a) or (b) explicitly and
price whichever it picks — silently assuming `--force` solves it would be
exactly the kind of unpriced re-ingest cost briefing constraint 5 forbids,
and I would rather hand the Arena this landmine now than have it discovered
during implementation.

### 1.6 Definition of done, in this proposal's terms

Measurable on source 37, without requiring `recover_formula()` to ever run:

- `wiki add <path-to-source-37>` (re-run, or on a fresh vault) prints a
  warning naming a count of regions and pages.
- `wiki lint` lists one `COMPILER_INTEGRITY` WARNING for source 37 naming
  95 regions / 17 pages / 48 equation-like, every run, until acted on.
- Opening source 37 page 22 in the CTX markdown file
  (`.curator/Collections/01_Contexts/CTX-f3a44022.md`) shows a non-empty,
  legible marker at the equation's position instead of nothing (for
  sources ingested after item 1 ships; source 37 itself per §1.5's
  (a)/(b) decision).
- Asking "explain equation 26" when the plugin's resolver lands on the
  containing page returns an answer that states the page number and that
  the content is an unextracted image region — not a bare "I could not
  retrieve it," and not a guessed page when the resolver has no hit.

## 2. Pros & Cons

### Pros

1. **Closes the honesty gap named in briefing §2.4 without waiting on any
   recovery route.** Every item here ships and is user-visible whether the
   Arena ultimately adopts Route A, B, C, or a staged combination — this is
   the "surface it" work every route needs as a prerequisite, so it is not
   at risk of being cut if recovery turns out to be harder than expected.
2. **Surface 3's fix is a one-line, one-string change that repairs two
   readers at once** (the human reading the CTX page in Obsidian, and the
   plugin's chat context for that exact page) because both draw from the
   same `_section_preview` output — I traced the actual call path
   (`pdf_context` → `_durable_l1_projection` → CTX body) rather than
   assuming the plugin surface needed its own new logic.
3. **The specificity-vs-hedge question is resolved with a testable rule**
   ("name it only when resolved, never guess"), not a vibe — this keeps the
   fail-closed content guarantee `crossReferenceResolver.ts` already
   enforces (labels only, never a fabricated snippet, never a fabricated
   location) fully intact while still improving the common case where the
   system genuinely does know where the content is.
4. **The vision-model discoverability trigger is scoped tightly enough not
   to become alarm fatigue**: it fires once, only for sources that actually
   lost something, never on the ~majority of PDFs with clean text layers,
   and never repeats outside of `wiki lint`'s standing (expected,
   dismissible-by-action) report.
5. **I found a real, previously unstated cost trap** (`add --force`
   cascading into an unwanted full L2/L3 rebuild via `build()`'s
   `l2_status='pending'` selection) before it could be shipped as a
   "cheap" retrofit path — this is exactly the kind of unpriced-recovery-
   cost failure mode briefing constraint 5 and the RAG proposal's own §1.3
   are trying to prevent, caught from a different angle than either
   document considered.
6. **No new schema, no new command, no new UI surface required for the
   minimum tier.** Items 1-2 in §1.5 are string/regex edits to existing
   code paths; item 3 is new lint/CLI text following an existing pattern
   (`check_missing_source_files`). This keeps the honesty fix cheap to
   review and cheap to revert if the Arena's synthesis changes shape.

### Cons & Limitations

1. **I did not design the vision-model nudge's exact UI chrome** — whether
   it is a plain `_warn()` line, a Rich panel, or ties into the plugin's
   Notice system on "add resource" completion (`ChatSidebarView.ts:2727`
   already shows a Notice at that exact moment for Zotero registration,
   which is a natural place to append a second, conditional Notice) is left
   to whoever implements Surface 1/2; I specified wording and trigger
   conditions, not pixel-level design.
2. **Tier 1 of §1.2 is not actually guaranteed by this proposal alone** — it
   is a *consequence* of Surface 3's marker fix plus the RAG proposal's
   P2/P3 (title-labelling, materializer re-entry) for the cases where the
   resolver currently returns zero hits because the label itself is
   rasterized (RAG §1.4 Fact 3). Without P2/P3, Tier 1 only helps when the
   user is already looking at (or the resolver already independently finds)
   the right page — it does not, by itself, make "equation 26" findable
   from a cold search. I have been explicit above about which tier requires
   what; a reader skimming only my pros could overestimate what ships from
   my items alone.
3. **§1.5's (a)/(b) choice for the 4 already-ingested sources is
   unresolved by design** — I identified the constraint (no free regen
   path exists today) rather than picking a side, because building a new
   narrow "regenerate L1 projection without touching l2-l4 status" code
   path is implementation work outside a product-honesty brief; I would
   defer to `lead_architect`/`schema_guardian` on whether that path is
   worth building now or whether "lint carries it, CTX catches up on next
   real re-ingest" is an acceptable interim state.
4. **The `wiki add` per-source warning could still read as noise to a user
   who genuinely does not care about formulas** (e.g., a vault used purely
   for prose sources that happens to ingest one image-heavy PDF as an
   aside). I mitigated this by gating strictly on count-of-loss-this-run
   rather than "PDF ingested," but I did not design a per-vault or
   per-workspace opt-out, and one may be warranted if usage shows this
   still fires too often for users who never ask formula questions.
5. **I did not verify whether the Obsidian Dashboard's existing "PDF
   ingest (vision)" row already surfaces *any* contextual hint** (e.g., a
   badge showing "N sources have unread image regions") — if it does not,
   my proposal's Dashboard-facing recommendation in §1.1/§1.4 is text-only
   (point users there via `wiki lint`'s suggestion string) rather than a
   richer in-Dashboard indicator, which a UI-focused reviewer might argue
   under-uses a surface I already know exists and is reachable.
6. **Explicitly NOT in scope**: any change to `recover_formula()`,
   `classify_formula_loss()`, the §26.2 acceptance/threshold contract, the
   materializer/search re-entry work (RAG §1.5 P3), the locator/anchoring
   logic (RAG §1.5 P2), or a decision on whether `main-if-vision` should
   ever auto-fire under some *different*, more explicit opt-in setting than
   today's silent collapse — I named that as a real open question in §1.3
   but the specific shape of an opt-in toggle is a `lead_architect` design
   call, not a product-honesty one.
