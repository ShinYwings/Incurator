# Critique on "make the corpus knowable first"

Date: 2026-08-20 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

### F1 — CRITICAL. The proposal's own Cons contain the argument that kills it, and it does not answer them

The proposal admits: it ships nothing visible, it defers an item already flagged
as "first by how much finished work sits unused", and the table may show the
corpus is too small to be worth building. Then it proposes doing it anyway.

**If the survey can conclude "close this milestone", that outcome must be
declared acceptable BEFORE the survey runs**, with a stated threshold. Otherwise
P0 is not a decision gate, it is a delay with a report attached — and this item
has already absorbed one Arena, one visibility release, and a no-op shipped as
v0.48.1.

**Required:** name the number. Below N recoverable formula regions, the
milestone closes and says so in the roadmap. Without that line, P0 cannot fail,
and a phase that cannot fail is not a gate.

### F2 — Re-parsing every PDF is unmeasured, and the proposal knows the corpus contains a 673-page book

"That cost is unmeasured" appears in the Cons and nowhere else. Source 45 was
just measured elsewhere in this session at **277 extraction batches** and hours
of wall clock for L2; a full re-parse is a different operation, but nobody has
timed `parsers.parse` on it.

If the survey takes 40 minutes, it is a script someone runs once. If it takes
four hours, it needs to be incremental and resumable, which is a different piece
of software.

**Required:** time `parsers.parse` on the largest source before writing the
survey. One number decides its shape.

### F3 — "How many are plausibly formulas" is smuggled in as if it were countable

§1.3 lists it as an outcome. It is not. `classify_span_loss` returns exactly one
verdict — `image_only`, on all 1,135 stored records — so the survey can count
**image-only regions** and nothing finer. Distinguishing a formula from a logo,
a rule, or figure furniture requires reading the image, which is the vision
model, which is the expensive thing this milestone was supposed to justify.

**Required:** drop the claim or state the mechanism. If the mechanism is "run
the vision model over N regions to classify them", that is a second cost and
belongs in the phase plan, not in a bullet describing a read-only pass.

### F4 — The staleness defect is filed as "not this milestone" while the proposal depends on it entirely

§1.4 says a shipped parser fix reaches only sources ingested after it, calls it
"bigger than formula recovery", and defers it. But §1.1's whole argument is that
the stored data is untrustworthy *because of that defect*. So the milestone is
blocked on something it declines to own.

That may be correct sequencing, but then P0's table is not the input to formula
recovery — it is the input to the staleness item, and formula recovery stays
blocked behind *that*. The proposal should say so plainly instead of implying
P0 unblocks the thing it is filed under.

**Required:** state the dependency chain explicitly, including the possibility
that this milestone does not move again until re-derivation exists.

### F5 — The survey reuses pipeline internals, which is right, and makes it fragile in a way the proposal calls a Pro

`_extract_structural_sections` and `spans_from_sections` are private. Reusing
them guarantees agreement with ingest today and guarantees the survey breaks the
next time either is refactored — silently, if it is a signature change that
still runs.

**Required:** either pin the agreement with a test that fails when the survey
and the ingest path diverge, or accept a one-off script that is deleted after
the number is recorded. The proposal treats it as production code without
committing to maintaining it.

## 2. Suggested Alternatives

- Keep P0. The argument for measuring before designing is sound and this
  session has four examples of why.
- **Add the closing threshold (F1)** — the number below which this milestone is
  retired rather than built.
- **Time the largest parse first (F2).** It decides whether the survey is a
  script or a feature.
- Drop the formula-vs-furniture claim (F3) or price its mechanism.
- Write the dependency chain down (F4): formula recovery is behind
  re-derivation, and re-derivation is not filed yet.
- Decide whether the survey is disposable (F5). If it is, say so and delete it
  when done.
