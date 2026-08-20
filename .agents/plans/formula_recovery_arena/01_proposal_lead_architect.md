# Core Proposal: stop planning recovery; make the corpus knowable first

Date: 2026-08-20 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### 1.1 Why this proposal is not about recovery

Four measurements, four overturned premises (briefing §2, §5a, §5b, §5c). The
last one is the reason this proposal refuses to design a recovery mechanism yet:

**Nothing in the database describes the current parse.** Source 37 stores 646
spans; the same PDF yields 2,050 today. Its 4 loss records date from before
v0.49.0 taught the parser to emit them. `l2_status='done'`, so nothing will ever
re-derive it.

Every number this milestone would be scoped against — how many regions, how many
are formulas, how many can be located — is therefore a measurement of an old
parse of three files. Designing against it is designing against a ghost.

### 1.2 P0 is a re-derivation, and it is the whole first phase

```python
# a read-only pass; writes nothing, decides nothing
def survey_extraction_loss(paths) -> dict:
    """Re-parse every tracked PDF and count what the CURRENT parser reports."""
    for source in tracked_pdf_sources(paths):
        parsed = parsers.parse(resolve(source))
        sections = _extract_structural_sections(parsed)
        spans = source_spans.spans_from_sections(sections)
        yield {
            "source_id": source.id,
            "stored_spans": stored_count(source.id),
            "current_spans": len(spans),
            "stored_loss": stored_loss_count(source.id),
            "current_loss": sum(1 for s in spans if classify_span_loss(s.text)),
        }
```

The output is a table with one row per source and two columns that should be
equal. Where they are not, the stored view is stale and by how much.

**That table is the deliverable of P0.** Not a fix — a number nobody has.

### 1.3 What it will let us answer, that we cannot answer now

- How many image-only regions exist across the vault, as of the parser that
  ships today.
- How many of them are plausibly formulas rather than logos, rules, and figure
  furniture. The briefing's "~48" predates everything.
- How many sources are stale, which is the input to a separate decision: does a
  parser improvement re-derive existing sources, or only reach new ones?

### 1.4 The re-derivation gap is its own item, not this one

A source at `l2_status='done'` is never re-parsed, so **a shipped parser fix
reaches only sources ingested after it**. v0.49.0 improved extraction-loss
reporting on 2026-08-08 and source 37, added 08-04, has never seen it.

That is a real defect and it is bigger than formula recovery. But it is not this
milestone, and folding it in would make an already-blocked item unbounded.
P0's table is what turns it from a suspicion into a filed item with a number.

### 1.5 Only then, the three blockers — re-ordered by what P0 reveals

Blocker 3 (locate the region) remains the gate: with 0 of 1,135 stored records
carrying coordinates, and neither a size join (6/1,135) nor a per-page
positional join (3/158) able to re-associate them, the association has to come
from the parser itself. Whether `pymupdf4llm` can expose it is an experiment,
not a design decision, and P0's re-parse is where that experiment lives.

Blockers 1 and 2 stay parked. Fixing an acceptance gate for recoveries that
cannot be produced is work with no observable outcome.

## 2. Pros & Cons

**Pros.**

- Replaces four contradicted assumptions with one measured table.
- Read-only: no schema change, no writes, nothing to roll back.
- Reuses the exact functions ingest uses, so the counts are the pipeline's own,
  not a reimplementation that could disagree.
- Surfaces the staleness defect with evidence instead of leaving it as a
  footnote in an Arena nobody reads again.

**Cons / limits.**

- It ships **nothing a user can see.** A phase whose output is a table is hard
  to justify if the milestone is judged by features.
- Re-parsing every PDF costs real time — source 45 is 673 pages — and that cost
  is unmeasured.
- It defers the actual objective again, on an item already noted as "first by
  how much finished work sits unused".
- The table could show the corpus is tiny (say, 20 real formula regions), in
  which case the honest conclusion is to close this milestone rather than build
  it — and the proposal has no answer for whether that is an acceptable outcome.
