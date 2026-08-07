# Synthesis — Does the Knowledge System Deliver What It Promises?

Date: 2026-08-07 | master @ `02faa0a` (v0.46.0)
4 inspectors + 2 red-team critiques, complete. Every headline re-verified by me
directly rather than accepted from an agent.

## Corrections to my own earlier measurements — read this first

The red team caught two errors in the evidence *I* gathered. Both are recorded
here rather than quietly dropped, because the conclusions I drew from them were
partly wrong.

1. **`sufficiency: partial` on all four packs was a harness artifact, not a
   system property.** Every pack carried
   `vector_unavailable: no embedder configured (FTS5-only)` and
   `no reranker configured`. `context_service.py:653` sets `partial` whenever
   any warning exists. My `wiki plugin context fetch` invocation ran **degraded**
   — the vault's real config has both embedder and reranker, and a properly
   configured rerun returns `sufficiency: "sufficient"` with real rerank scores.
   `search_embeddings` holds 5,635 rows; the corpus was embedded all along.
   **I reported "the system self-reports partial on every query" — that was my
   harness, not the system.**

2. **`policy_hash: ""` / `workspace_id: "default"` was also my harness.** I ran
   without `--workspace-path`. Passing the real workspace yields
   `workspace_id: "COLMAP free GS"`, `policy_hash: "61598094d334e434"` —
   verified. **The curation-lens mechanism works.** The plugin defect below is
   real and separate; my measurement was not evidence for it.

What survived both corrections is below.

## 1. [P1] 61% of the vault's knowledge never enters the search index

This is the deepest finding and it supersedes the "ranking failure" framing I
first reported.

Measured directly:

| | count |
|---|---|
| live `knowledge_units` | 2,799 |
| indexed in `search_documents` | 1,098 |
| **never indexed** | **1,701 (61%)** |

The causal chain, each link verified:

1. A PDF-extracted span carries the formula as plain text without `$…$`
   delimiters.
2. The deterministic formula match in claim support therefore fails.
3. `support_status` stays `unchecked` / `uncertain` rather than `verified`.
4. `materializer.py:237` gates knowledge-unit indexing on
   `support_status='verified'`.
5. The unit is absent from `search_documents` — so **no route, no ranking, and
   no reranker can ever retrieve it**.

The concrete user-visible consequence: for Q1 — *"ellipsoid 형태의 quadric 은
어떻게 매트릭스로 표현되나?"*, a question the user actually asked — the exact
answer (`Q* = Z Q̆* Z^T`, "Q̆* is an ellipsoid centred at the origin") exists in
the DB as 4 duplicate units at confidence 1.0, from a source the pack already
drew 12 other items from. It appeared in **0 of 39** returned items, and still
does not appear in a fully-configured rerun.

**The designed fix for step 2 is built and never called.** SYSTEM_BEHAVIOR §26.2
specifies formula recovery; `pipeline/formula_recovery.py` implements
`recover_formula()` and `classify_formula_loss()`; `compile.py` imports and
re-exports them. Production call sites: **0**. Test call sites: 14.

## 2. [P1] Route selection is English-only, so Korean questions can never reach L3/L4

`retrieval/router.py:20-29` selects the route with ASCII keyword regexes. Run
directly:

| question | `global` | `explore` |
|---|---|---|
| `ellipsoid 형태의 quadric 은 어떻게 매트릭스로 표현되나?` | False | False |
| `2D GS가 3D보다 …여러 논문을 종합해서 설명해줘` | False | False |
| `Summarize across all papers how kernel fusion…` | **True** | False |
| `What are the overall themes in my vault?` | **True** | False |

An explicit request to synthesize across papers routes `local` in Korean and
`global` in English. The registered LLM router (`curator.query_router`) that
would resolve ambiguous cases is **never called**; `choose_route` always resolves
by regex or default. `seed_terms()` and `_report_score()` are ASCII-only too, so
a pure-Korean query also gets zero entity-seeded evidence regardless of route.

SYSTEM_BEHAVIOR claims language handling is "deterministic… not merely a prompt
instruction". For routing that is false.

**The `global` route itself works.** Forcing `mode="global"` on Q3 returned
10 of 233 community reports and 4 of 4 synthesis nodes, correctly capped — the
defect is entirely on the selection side.

## 3. [P1] `about.md` §5.2's central claim is not met today

> "providing hallucination-free answers by leveraging only the **refined
> essence** of curated knowledge"

Ruled **FALSE**, after the red team steelmanned it. The fair version of the
counter-argument — that entities and L2 units are also "refined" — is partly
right: 10.5–44.8% of pack content is genuinely L2-derived. But raw L1 is the
majority in every pack (55–90%), **L3 is 0/233 through any path**, and
about.md §1 defines the essence as the pipeline's endpoint (Concept/Synthesis),
not intermediate Atoms.

Related, and a one-line fix: real L4 content did leak into Q4 via flat search
carrying `synthesis_node_id: ""` and score 0.016 — `EngineHit.record_type` is
known internally but discarded when `search.py` builds the public `SearchHit`,
so the pack's own counters cannot see it.

## 4. [P1] The curation lens and the vault persona never reach the chat surface

The lens mechanism works when a workspace is passed (verified above). But
`ChatSidebarView.ts:1904` always resolves `workspacePath` to the Obsidian vault
root via `getBasePath()`, never `01_Workspaces/<project>`. `curate.yml` lives
only under the latter — the live vault has
`01_Workspaces/COLMAP free GS/curate.yml` — so the entire chat surface silently
falls back to the empty default policy. This is CAND-06, filed previously,
queued for batch B6, never shipped.

The **Global Persona** in `.curator/settings.yml` is consumed in exactly one
place system-wide: `sync.py:755-757`, feeding `wiki sync`'s DAG-verification
prompts. The query answer-synthesis contract has no persona field at all. So
about.md §5.6's "defines the identity of the Curator" does not reach any answer
the user reads.

Red-team narrowing accepted: MCP `curator_fetch_context` and the CLI
`--workspace` path do bind the lens correctly, so "never implemented" would be
overreach. It is the plugin chat surface specifically.

## 5. [P2] Entity descriptions are frequently circular

12 of 34 pack entities (35%) are tautological — *"A method using 2D Gaussian
Splatting"*, *"The title of the scientific paper proposing 2D Gaussian
Splatting"*. Two independent DB-wide automated proxies agree on a ~10% floor
across all 965 entities. Root cause: the extraction prompt
(`prompting/families/entities.py:31-82`) has seven hard rules covering
relations, confidence, and span citation, and **zero** instruction on what makes
a good description; its worked example literally shows `"description": "..."`.

## 6. [P2] Span segmentation isolates fragments

`pipeline/source_spans.py:62-68` splits prose on blank lines with only an
`if para:` non-empty check — no minimum length, no merge. One-word connectives
between LaTeX blocks become permanent standalone spans; Q2 returned 7 of 19
items under 40 characters, one of them a single Korean particle. Compounded by a
fixed 8-slot `search_hit` quota with no score floor.

## Refuted — do not re-file

- **"`local` structurally cannot reach L3/L4."** `materializer.py:429-472`
  indexes community reports and synthesis nodes unconditionally, and `local`'s
  search fallback passes `families=None`. L3/L4 **is** in the candidate pool.
  The 0/39 outcome is a ranking result, not structural exclusion — which
  materially weakens the case that changing `local`'s contract is the only fix.
- **"A bounded L3/L4 primer in `local` fixes all four questions."** For Q1 the
  answer is absent from all 233 reports for the same upstream indexing reason,
  so a primer cannot surface it. The primer argument holds for Q3, not Q1/Q2.

## Sequencing

1. **Wire up formula recovery.** It is already written, specified, and tested —
   it just is not called. This is the single highest-leverage change in the
   audit: it attacks the 61% indexing gap at its root.
2. **Make route selection language-independent**, or call the LLM router that is
   already registered. Until then the distilled layers are unreachable for the
   user's own language.
3. **Pass the real workspace from the chat sidebar** (CAND-06 / B6) — the lens
   works, nothing is plumbed to it.
4. **Give the entity prompt a description contract**, and add a minimum-length
   merge to span segmentation.
5. Re-run this exact four-question probe afterward as the acceptance test, with
   the embedder and reranker configured this time.
