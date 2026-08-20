# Defense: F2 measured, and it produced the number the whole milestone was missing

Date: 2026-08-20 | Agent Persona: lead_architect (responding)

## 1. F2 — the survey's cost, and therefore its shape

Timed `parsers.parse` + sectioning + span construction on the three
loss-bearing sources:

| source | pages | parse | spans | loss spans |
|---|---|---|---|---|
| 37 — 3D Line Mapping Revisited | 27 | 11.7 s | 2,050 | **437** |
| 46 — Přibyl et al. | small | 1.6 s | 87 | **11** |
| 45 — Hartley | 673 | **79.1 s** | 13,200 | **1,673** |

Sectioning and span construction are free (≤0.1 s); the cost is entirely
`parsers.parse`. **Ninety seconds for the three sources that matter.**

**F2 resolved: the survey is a script, not a feature.** No incrementality, no
resumability, no persisted state. Run it, read the table, delete it. That also
resolves F5 — it is disposable, and the plan says so rather than pretending it
is production code that someone will maintain.

## 2. And the survey has effectively already run

The table above IS the P0 output for every source that carries loss records.
Which means the milestone can be sized right now, without a phase:

```
stored in the DB : 1,135 loss records   (an old parse)
current parser   : 2,121 loss regions   (437 + 11 + 1,673)
```

**Nearly double, and Hartley alone accounts for 1,673 of it.** The briefing's
"~48 regions" — the number the original Arena estimated 0–2 recoveries against —
was low by a factor of forty.

## 3. Conceded to the red_teamer

**F1 — the closing threshold.** Conceded, and it matters more now that the
corpus is 2,121 rather than 48. The threshold cannot be "how many regions
exist"; it has to be **how many are formulas a reader would want back**, which
F3 correctly says this survey cannot tell us. So the honest gate is: sample N
regions, classify them by eye or by one vision pass, and if fewer than 10% are
formulas carrying claim content, close the milestone and record the number.
Stated before the sample is drawn.

**F3 — "plausibly formulas" is not countable here.** Conceded without argument.
`classify_span_loss` emits exactly one verdict, `image_only`, for all 2,121.
Every one of them may equally be a logo, a rule, or figure furniture. The
proposal listed this as an outcome of a read-only pass; it is not, and the
sample above is the mechanism that replaces the claim.

**F4 — the dependency chain, stated plainly.** Formula recovery is blocked on
locating regions; locating regions is blocked on an association the parser does
not currently expose; and *separately*, every stored measurement is stale
because a source at `l2_status='done'` is never re-derived. That last item is
**not filed** and is larger than this one. This milestone should not move again
until it is. Saying that is more useful than another phase plan.

**F5 — disposable.** See §1.

## 4. What I now think this Arena should conclude

Not a build. The measurements say:

- The corpus is 40× larger than the estimate this item was scoped against.
- None of it can be located today, and neither join strategy works.
- Every stored number describes an older parse, because nothing re-derives.
- The one cheap thing — the survey — has already run, above.

The useful output of this Arena is therefore **a corrected roadmap item and one
new filed item**, not a plan to implement. Proposing otherwise would repeat the
pattern this item already has: v0.48.1 shipped as a no-op, then a visibility
release, then an Arena estimating 0–2 recoveries against a number that was
wrong by 40×.
