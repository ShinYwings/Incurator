# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

## 📝 User Inbox
### 2026-08-05 — [P2] `wiki jobs list` cannot distinguish "working" from "hung", and names a PDF as `.md`

User observation during the post-v0.43.0 build: job 37 (MVG book) sat at "10%"
with no visible movement, and both jobs are PDFs but display a `.md` name.

**(a) The `.md` name is correct data, misleading display.** Both sources are
`file_type='pdf'`, `is_reference=1`, `logical_source_id='zotero:<key>'` — i.e.
Reference Mode. Per SYSTEM_BEHAVIOR §3.1 the backend keeps the PDF in place and
writes a lightweight markdown STUB under `04_Resources/`, storing the stub path
in `sources.relpath`. `wiki jobs list` renders that `relpath`, so a PDF job
shows the stub's `.md` filename. Fix direction: for `is_reference` sources
display the PDF/Zotero identity (or mark the row as PDF) rather than the stub
path. Cosmetic but actively confusing.

Noticed alongside: the generated stub names carry a trailing empty field —
`"MultipleViewGeometryHartley - .md"`, `"3D Line Mapping Revisited2023 - Liu et
al. - .md"` — so the stub filename template renders a separator for a metadata
field it did not fill.

**(b) The job was NOT hung; the progress number is a fixed marker.** Measured
3.7 minutes after start:

- `progress = 0.1` comes from `ingest_worker.py:180`, written **once** when L2
  begins. The next update is `progress=0.5` at `:195`, only after the whole L2
  extraction returns. Nothing moves in between.
- `progress_current / progress_total = 0 / 1` — the real counters are never
  advanced, so the "10%" is not derived from work done.
- `job_events` for that job: **0 rows**. SYSTEM_BEHAVIOR §6 says "Running jobs
  should publish phase/progress in `ingest_jobs` and `job_events`" — nothing is
  published, so there is no per-batch trace either.
- `input_tokens/output_tokens = 0/0`: no provider call had completed yet.

Scale explains the wait rather than a hang: **source 36 alone holds 8,692
source_spans — 79% of the entire vault's 11,052.** With a measured CLI provider
round-trip of 8–12 s, a batched L2 extraction over that source is inherently a
long job.

This is the same defect class as the Quick Query "Thinking…" fix (PLUGIN_SCHEMA
§1.4.3): a long operation that emits no progress is indistinguishable from a
hang. Fix direction: advance `progress_current/progress_total` per L2 batch and
emit a `job_events` row per batch, so `wiki jobs list` and the dashboard show
real movement and a stall becomes diagnosable.

### 2026-08-05 — [P1/DESIGN] The `local` route never descends L4→L3→L2→L1, so most queries read raw L1

User design intent, stated 2026-08-05: *"When querying, shouldn't it search
L4 → L3 → L2 → L1 → source in that order? Part of why I split L1–L4 in the first
place was that searching L1 every time would be enormously expensive.
Zettelkasten works that way too."*

**Measured against the code (`retrieval/evidence.py:364-447`), the descent is
implemented in only two of four routes:**

| Route | Evidence assembly | Descends? |
|---|---|---|
| `global` | L4 `_synthesis_items` → L3 `_report_items` → search only if both empty | yes |
| `explore` | memory paths + L4 synthesis primer + L3 report primer + entities | yes |
| `source-section` | every span of one source | n/a by design |
| **`local`** | **entities + their spans + `_add_search_hits`** | **no** |

`local` (`evidence.py:440-447`) never consults `synthesis_nodes` or
`community_reports` at all. It resolves query entities, attaches their L1 spans,
and appends flat search hits. A formula query in this vault routed `local`,
which is why it returned 9 bare entity names and 17 L1 spans (mostly
bibliography lines and headings) with one LaTeX-bearing item.

This matches SYSTEM_BEHAVIOR §17's own wording for `local` ("resolve query
entities… expand to related claims/concepts/spans"), so **the code conforms to
the spec and the SPEC diverges from the stated design intent** — the same shape
as the v0.43.0 corroboration finding.

**Two consequences:**

1. **Cost.** The layering was meant to avoid scanning L1 for every query, but
   `local` searches the full index where L1 spans are 11,052 of 12,435
   documents (89%). The distilled layers carry no retrieval-cost benefit on the
   route most factual questions take.
2. **Quality.** Descending from L4/L3 would surface distilled statements
   (which retain formulas in their claim text) ahead of raw spans, instead of
   letting bibliography lines outrank equations on lexical overlap.

**Caveat before acting:** `global` already degrades to flat search when there
are no synthesis/report rows — exactly this vault's state today (3 synthesis,
6 reports). So the descent cannot be evaluated fairly until the v0.43.0
corroboration fix has repopulated L3/L4. **Sequence: merge PR #116 → `wiki
build` → re-measure → then decide whether `local` should descend.**

Open design question for the user: should `local` consult L4/L3 first and fall
through to L1 only when the distilled layers do not answer, or should the
router send more questions to `global`? The first changes a route's contract;
the second changes routing policy only.

### 2026-08-05 — [P1/DESIGN] Formula-bearing claims almost never serve: the prose gate overrides an exact formula match

User report: formulas in L1–L4 are not deductively analyzed, so sidechat/MCP
cannot cite them.

**Measured** (`13ed51f8b06cb88e/state.sqlite`, read-only). Of 1,055 live
formula-bearing knowledge units, **only 86 (8%) are `verified`** — i.e. served:

| formula_status | support_status | count |
|---|---|---|
| `preserved_in_text` | **failed** | **490** |
| `uncertain` | unchecked | 309 |
| `preserved_in_text` | verified | 86 |
| `missing` | failed | 85 |
| `preserved_in_text` | unchecked | 85 |

Every one of the 575 `claim_supports` failures carries the **same** reason:
`"the cited span does not minimally support the claim (no salient term
overlap)"`. And **all 237 `formula`-role supports are `unchecked`** — not one
was ever validated.

**Cause 1 — the formula carve-out is unreachable in practice.**
`pipeline/claim_support.py:361` grants `verified` on an exact ordered formula
match only when `not claim_terms` — the claim must contain NO salient prose at
all. An LLM-extracted claim about an equation nearly always carries prose
("The rendering equation integrates radiance…, $L_o = …$"), so it has both
prose and a formula and falls through to `:371`, where `max_cov <
_SUPPORT_FAIL` (0.25) fails it outright. The `formula_status` written on that
same branch is `preserved_in_text` when `formula_ok` — so the system records
*"the formula IS exactly present in the cited span"* and fails the claim anyway.
That is precisely the 490-unit bucket.

SYSTEM_BEHAVIOR §26.1 does sanction the combination ("an F6 textual-grounding
failure may still carry `formula_status='preserved_in_text'`"), so the code
conforms. **The contract is what needs revisiting**: an exact ordered formula
match is strong evidence, yet it currently counts for nothing unless the claim
happens to be prose-free. Proposed direction — treat an exact formula match as
support in its own right when the claim also carries prose, e.g. lower the
prose bar (or waive it) for `formula_ok` claims instead of requiring the
degenerate prose-free shape.

**Cause 2 — nothing adjudicates `uncertain`.** `claim_support.py:304` states
that with no `client` an `uncertain` unit "stays `unchecked` (never promoted)".
The machine-local config has `provider: ollama` with `model: None`, so no
calibrated validator is available and the 309 `uncertain` + 928 `unchecked`
units are stranded permanently. They are stored and audited but never served.

**Cause 3 (smaller) — equation spans are scarce.** Only 105 of 11,052
`source_spans` are `span_type='equation'` (0.95%) in a vault of math-heavy
papers. Worth checking whether display math is being recognized at L1 at all.

**CORRECTION 2026-08-05 — the support gate is NOT the binding constraint.**

The user reframed the requirement in outcome terms: *"when I ask a question, if
a related formula exists in the knowledge system, it just needs to be usable as
prior knowledge for the answer."* Measured against that, the diagnosis above is
misleading and the proposed fix would not have delivered it.

**All 11,052 L1 `source_spans` are in `search_documents`, including all 105
`span_type='equation'` spans — indexed regardless of `support_status`.** The
claim-support gate governs which L2 `knowledge_units` are served (628 of 2,131);
it never removed the formulas from retrieval. So loosening it would not, by
itself, put more formulas into an answer.

What actually happens, measured with a real query
(`wiki plugin context fetch --query "Gaussian splatting covariance"`, a
formula-dense topic): **27 evidence items returned, exactly 1 containing any
LaTeX.** The rest are 9 bare entity names plus L1 spans that are mostly
bibliography lines ("2019. Differentiable surface splatting… ACM", five times)
and section headings ("D ADDITIONAL RESULTS" x3, "📖 참고 자료", "심층 분석 완료").

DB-level duplication is not the cause: only 98 of 11,052 spans share a preview
(0%). The cause is **retrieval ranking** — lexical matching scores a paper title
in a reference list as highly as the equation that answers the question, and
headings/boilerplate spans (`---`, `{% persist %}` template residue) are indexed
as ordinary content.

**Revised priority.** To satisfy the stated requirement, work the retrieval
side, not the support gate:
1. Rank or filter out non-content spans (bibliography blocks, bare headings,
   template residue like `{% persist %}` / `---`) at materialization or ranking
   time.
2. Give `span_type='equation'` spans (and spans containing LaTeX — 391 of them)
   a retrieval affordance so a formula-seeking query can actually reach them.
3. Only then revisit the L2 support gate, which affects distilled-layer quality
   and cross-source synthesis rather than basic formula availability.

The original Cause 1/2/3 analysis stands as an accurate description of the L2
gate, but it answers a different question than the one the user asked.
