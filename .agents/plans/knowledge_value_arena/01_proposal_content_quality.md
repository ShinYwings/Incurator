# Proposal: `content_quality` inspector

Domain: judge the ACTUAL content of `q1.json`–`q4.json` (not the plumbing).
Read-only throughout. DB queried via the read-only vault cache
`.cache/vaults/13ed51f8b06cb88e/state.sqlite` (`?mode=ro`), confirmed as the
DB backing these packs by matching `canonical_name`/`description` text for
`QuadricSLAM`/`ellipsoids` verbatim against `q1.json`. `second_brain/.curator/state.sqlite`
itself is a 0-byte placeholder — the real state lives in the sync cache, not
the vault-local file. No writes were made to either.

---

## Finding 1 — Entity descriptions are measurably circular; the extraction prompt gives the model no way to avoid it

**Severity: P2** (contract/quality gap — the layer exists and runs, but the
content it produces frequently fails to say anything).

**Criterion (applied consistently):** a `description` is circular/tautological
if, after removing generic scaffolding words ("a", "an", "method", "system",
"pattern", "function", "using", etc.) and every word already present in the
entity's own name, **zero or one genuinely new content word remains** — i.e.
the description only re-parses the name into a sentence, or describes the
entity's *bibliographic role* ("the title of...") instead of what it *is/does*.

**Pack-level count (manual, all 34 entity items across q1–q4):** 12/34 = 35%
meet this criterion. Verbatim examples, one per pack:

- q3: `"2D Gaussian Splatting (2DGS)"` → `"A method using 2D Gaussian Splatting."`
- q3: `"2D Gaussian Splatting for Geometrically Accurate Radiance Fields"` → `"The title of the scientific paper proposing 2D Gaussian Splatting."`
- q4: `"Warp Reduce"` → `"Warp reduction operation pattern"`
- q4: `"apply_jt_kernel"` → `"Kernel function inside 3DGS-LM"` (never says what it computes)
- q4: `"cub::WarpReduce"` → `"A CUB library warp reduction function."`

Contrast with the *good* entities in the same packs, which is why the
criterion isn't vague pattern-matching: q1's `"Absolute Dual Quadric"` →
`"A degenerate dual quadric in projective 3D space represented by a rank 3
homogeneous symmetric matrix."` — this teaches something not implied by the
name. 6/6 of q1's entities clear the bar; q2 (0/2, though one is thin);
q3 (4/8); q4 (8/18). The failure is concentrated, not uniform — worth noting
for triage.

**DB-wide measurement (all 965 rows in `graph_entities`, not just the packs):**
An automated conservative proxy for the same criterion (description tokens
minus genus-scaffolding minus name-tokens ≤ 1) flags **102/965 = 10.6%** as
pure restatement. This is a **lower bound**, not the true rate — it only
catches descriptions that add literally nothing; it does not catch the
"role-only" tautologies like `apply_jt_kernel`'s (that example adds one novel
token, "3DGS-LM", so the automated proxy doesn't flag it, but a human reading
it learns nothing about what the kernel computes). The manual, human-judged
rate on the smaller pack sample (35%) is the more trustworthy number; treat
10.6% as "at least this bad, DB-wide."

```
$ sqlite3 "file:.cache/vaults/13ed51f8b06cb88e/state.sqlite?mode=ro" \
    "SELECT COUNT(*) FROM graph_entities;"
965
```

**Root cause — the extraction prompt asks for a description but never says
what makes one good.** `backend/src/curator/prompting/families/entities.py:31-34`:

```python
class ExtractedEntity(BaseModel):
    canonical_name: str
    entity_type: EntityType
    description: str = ""
    source_span_ids: list[str] = Field(default_factory=list)
```

The system prompt (`entities.py:53-82`) has seven "Hard rules," all about
`relation_type`, `assertion_source`, `confidence`, and span-id citation
discipline. **None govern `description` content.** The one worked example in
the prompt (`entities.py:71-82`) shows the field as a literal ellipsis:

```
{"canonical_name": "ResNet", "entity_type": "method", "description": "...",
 "source_span_ids": ["SPAN-..."]}
```

There is no instruction to state what the entity *is or does* rather than
what it's *called*, no prohibition on restating the name, no requirement to
pull a distinguishing fact (a number, a formula, a named difference) from the
source span. Given a low-signal span — e.g. `2D Gaussian Splatting (2DGS)` is
first introduced in running prose as just an acronym expansion, with the
substantive definition sentences elsewhere — the model has nothing in its
instructions pushing it toward finding a better-signal source_span or
synthesizing across the units_block; it satisfies the schema with the
shortest legal string, which is exactly `"A method using 2D Gaussian
Splatting."`

**Failure scenario:** A user browsing entities for `2D Gaussian Splatting
(2DGS)` — one of the vault's most central concepts (6 duplicate entity
records exist for variants of this name, see note below) — reads "A method
using 2D Gaussian Splatting" and learns nothing they didn't already know from
the name. This is not a rare edge case; it is what the prompt's schema
produces by default when the prompt gives no positive content contract.

**Related, not double-counted:** the same four packs show `2D Gaussian
Splatting` extracted as 4–6 *separate* entity records with overlapping names
(`2D Gaussian Splatting`, `2D Gaussian Splatting (2DGS)`, `2D Gaussian
splatting`, `2D Gaussian primitives`, `2D Gaussian Splatting for
Geometrically Accurate Radiance Fields`, `3D Gaussian Splatting`) — an entity
resolution/dedup problem, not a description-quality problem, but it compounds
Finding 1: several of these near-duplicates are also the circular ones, so
the pack spends multiple item-slots restating the same non-fact.

---

## Finding 2 — Better content existed in the DB for at least 2 of 4 questions and was never retrieved. This is the highest-value finding: it is a ranking failure, not a thin-content problem.

**Severity: P1** (the product fails its stated purpose for a real user
question, with a concrete, reproducible counter-example).

### Q1 ("ellipsoid 형태의 quadric 은 어떻게 매트릭스로 표현되나?" — a real user question)

The DB contains the literal answer, duplicated four times as separate
`knowledge_units` (evidence the extraction ran repeatedly over the same
source and found it each time — this is not a subtle fact):

```
KNU-e9ec6538 | equation | Dual Quadric Parametrization
"A dual quadric Q* is parametrized as Q* = Z Q̆* Z^T where Q̆* is an
ellipsoid centred at the origin and Z is a homogeneous transformation
accounting for rotation and translation."
```
(duplicates: `KNU-013768ee`, `KNU-3702df54`, `KNU-279bc9a6`, all `confidence:
1.0`, all citing the same two spans)

Its source spans are the literal answer to the question, verbatim from the
source PDF:

```
SPAN-6259d5a6: "where Q̆* is an ellipsoid centred at the origin, and Z is a
homogeneous transformation that accounts for an arbitrary rotation and
translation."
SPAN-be04bc31: "NICHOLSON et al.: QUADRICSLAM } error Q∗= Z Q̆∗ZT where
Q̆∗is an ellipsoid centred at the origin..."
```

Both spans belong to **`source_id: 34`** — the exact same document (`04_Resources/References/QuadricSLAM...Nicholson et al....md`) that q1.json
already draws 12 other items from. Both are indexed and embedded
(`DOC-source_span-SPAN-6259d5a6` and `DOC-source_span-SPAN-be04bc31` exist in
`search_documents`; `search_embeddings` has 5,635 rows, so vector indexing
ran over this vault). Neither span, and neither `KNU-e9ec6538` nor its three
duplicates, appears anywhere among q1.json's 39 items (`grep -c` = 0). No
`graph_entity` links to any of these four knowledge units either
(`knowledge_unit_ids LIKE '%e9ec6538%'` → 0 rows) — the fact is unreachable
via the entity route too.

**This is not an indexing gap or a content gap. The precise, well-formed,
high-confidence answer is sitting in the same source document already being
mined, correctly extracted four separate times, fully indexed — and the
retrieval/ranking step chose 39 other items instead of it.**

### Q3 ("2D GS가 3D보다 표면 재구성에 유리한 이유를 여러 논문을 종합해서 설명해줘")

Same pattern. The DB holds the direct mechanistic comparison:

```
KNU-791618ad | definition | Comparison of primitives between 3DGS and 2DGS
"3DGS represents primitives as 3D ellipsoids using a 3×3 covariance matrix Σ
..., whereas 2DGS represents them as 2D planar disks using a 3×3
transformation matrix T ..."
```
plus a supporting chain (`KNU-18954103` "2DGS Normal Consistency",
`KNU-738726d1` "2DGS Depth Fusion Enhancement") — this is exactly the "why"
the question asks for, expressed as a synthesizable claim rather than a raw
figure caption.

`KNU-791618ad`'s source span (`SPAN-50e90a41`) does **not** appear in
q3.json (0 hits). What q3.json got instead, from the *same paper*
(`source_id: 32`), are two **figure captions** —

```
SPAN-9cfc91de: "Fig. 8. We visualize the depth maps generated by MipNeRF360
..., 3DGS ..., and our method."
SPAN-fd05639e: "Fig. 9. Comparison of surface reconstruction using our 2DGS
and 3DGS [Kerbl et al. 2023]. Meshes are extracted by applying TSDF to the
depth maps."
```

— both marked `"freshness_state": "stale"`. The pack contains a *pointer to
the existence* of the comparison (a caption saying "see Fig. 9") but not the
sentence that explains the comparison. A competent agent handed this pack
would have to either hallucinate the mechanism or refuse to answer the "why"
half of the question; the actual mechanism was extracted, worded correctly,
and discarded before reaching the pack.

**Failure scenario:** the user asks a real, specific technical question in
their own words. The system's own L2 layer already contains a clean,
citable, correctly-worded answer sitting in the same source file the pack
already sampled 12 other times from — and the user gets 39 items that talk
around the answer instead of the answer. Whatever is scoring/ranking
candidates for `local` route pack assembly is not surfacing exact-match
formula/definition units over generic prose or figure captions, even when
they come from the identical source and section neighborhood already deemed
relevant.

---

## Finding 3 — `sufficiency: partial` is a static config flag, not a measurement of the pack. It cannot currently reach "sufficient" regardless of content quality.

**Severity: P2/P3** (contract says "sufficiency," but the field name promises
a judgment about coverage that the code isn't making).

`backend/src/curator/context_service.py:653`:

```python
coverage = "partial" if pack.warnings or omitted_counts else "sufficient"
```

All four packs report `omitted_counts: {}` (nothing was cut for budget) — so
in every case here it's `pack.warnings` alone deciding the verdict. All four
packs carry the **identical two warnings**, verbatim:

```
"vector_unavailable: no embedder configured (FTS5-only)"
"no reranker configured: returned RRF order"
```

These come from `backend/src/curator/retrieval/engine.py:311-316` and
`:325-331` — they fire whenever `self.has_embedder` (`engine.py:93-95`,
`self.embedder is not None`) or reranker availability is false for *this
engine instance*, independent of the question asked or how good the assembled
evidence turned out to be. Since this is the same warning on all 4 packs
regardless of question language, topic, or item count, it is a **vault/session
config state**, not a per-query sufficiency signal — `sufficient` is
structurally unreachable for any query run through this code path until the
session wires up an embedder and a reranker.

Notably this is not even because the vault lacks vectors: `search_embeddings`
has 5,635 rows (`SELECT COUNT(*) FROM search_embeddings` = 5635), i.e. `wiki
reindex --embed` has run. `has_embedder` is about whether *this engine
instance* was constructed with an embedder client, not whether the corpus has
vectors — the `wiki plugin context fetch` path apparently doesn't wire one in,
even though the data exists. That wiring gap is adjacent plumbing (better
suited to `router_and_layers` or a follow-up), but it's the direct reason
"sufficient" never appears: the two warnings are two-thirds config problem
and structurally can't be resolved by better retrieval logic alone.

**What would make it "sufficient":** as coded, only (a) an embedder wired into
the engine at call time, AND (b) a reranker configured — both session/config
concerns unrelated to whether the retrieved items actually answer the
question. A pack could contain the exact right answer (as in Finding 2) and
still report `partial`; a pack could contain nothing useful and, with an
embedder+reranker present, report `sufficient`. The label is disconnected
from the thing a user would call "sufficient."

---

## Finding 4 — 7 of Q2's 19 items are sub-40-character sentence fragments; traced to a paragraph-splitter with no minimum-length floor, and a fixed 8-slot search_hit quota with no score floor

**Severity: P2** (quality gap — these items occupy pack budget while
contributing nothing).

Exact 7 items in `q2.json` under 40 characters, verbatim:

| item | kind | text |
|---|---|---|
| SPAN-8e663fee | source_span | `"Then"` |
| SPAN-d65bc222 | source_span | `"- 또는 비례 등식으로:"` ("- or as a proportional identity:") |
| search_hit (CTX-4de012f6.md) | search_hit | `"는"` — a single Korean topic particle, 1 char |
| search_hit (CTX-4de012f6.md) | search_hit | `"RHS는"` |
| search_hit (CTX-4de012f6.md) | search_hit | `"그러므로"` ("therefore") |
| search_hit (CTX-4de012f6.md) | search_hit | `"\bThen"` |
| search_hit (CTX-4de012f6.md) | search_hit | `"이라서 LHS는"` |

**Root cause, source_spans:** `backend/src/curator/pipeline/source_spans.py:46-79`
(`_block_spans`) pulls `$$...$$` blocks out as separate `equation` spans, then
splits everything else on blank lines into `paragraph` spans via `_emit_prose`
(lines 62-68):

```python
def _emit_prose(chunk: str) -> None:
    for para in re.split(r"\n\s*\n", chunk):
        para = para.strip()
        if para:
            spans.append(
                SpanRecord("paragraph", para, _hash(para), page, title, toc_id)
            )
```

The only guard is `if para:` — non-empty after `.strip()`. No minimum length,
no merge-into-neighbor. In a math-derivation note written with one connective
word per line between display equations (confirmed directly against the DB —
`SELECT ... FROM source_spans WHERE id IN (...)` returns these five rows with
`span_type='paragraph'` and text exactly `"는"`, `"그러므로"`, `"Then"`, etc.,
`start_char`/`end_char` both `NULL`), each connective becomes its own
permanent, independently-retrievable span forever.

**Compounding cause, retrieval:** all four packs (q1–q4) contain **exactly 8**
`search_hit` items each — a fixed quota, not a score-filtered set. The four
single-word search_hits above score `0.015–0.016` (RRF-tail scores, the
weakest possible non-zero rank), and are pulled in anyway to fill the quota.
`SPAN-9e88f847` in the same q2 pack — a CUDA ray-tracing kernel snippet about
Gaussian Splatting rendering — is also present despite the question being
about camera auto-calibration (Kruppa equations); it's a `search_hit`
apparently included on the same fill-the-quota basis, unrelated to the
question's domain.

**Failure scenario:** a user asks about Kruppa equation constraints and 7 of
19 pack items are single words/particles carrying zero standalone meaning,
plus one item from an unrelated CUDA rendering note — meaning roughly 40% of
the pack's item count is either content-free or off-topic, silently
consuming budget slots that a real fact (see Finding 2's pattern) could have
filled instead.

---

## What was NOT counted as a finding (checked, ruled out)

- Whether `sufficiency` is reachable at all for a *well-served* query was not
  directly tested (would require a query where an embedder+reranker are
  actually wired in) — Finding 3 is about the mechanism, not a claim that
  "sufficient" never appears anywhere in the system.
- I did not re-derive the L3/L4 routing miss (233 community reports, 4
  synthesis nodes, 0 served) — that's `router_and_layers`' finding, already
  established in `STATUS.md`; I only used it as background, not as my own
  evidence.
