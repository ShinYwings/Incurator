# Proposal: `intent_vs_behavior` — about.md claims vs. measured packs

Inspector: `intent_vs_behavior` | Input: `docs/philosophy/about.md`, `docs/philosophy/ABOUT_KR.md`,
`docs/README.md`, `docs/README_KR.md`, `q1.json`–`q4.json` (measured, not re-derived) |
Read-only. No mutations performed. One code-reading pass through
`backend/src/curator/retrieval/{router,evidence,models}.py`,
`backend/src/curator/context_service.py`, `backend/src/curator/curate_yml.py` to locate mechanisms.

---

## Claim-by-claim verdict

| # | Claim (about.md) | Verdict | Basis |
|---|---|---|---|
| §4.3 | "The agent retrieves a **bounded, traceable** evidence pack selected from the **refined live DAG**." | **PARTIALLY FALSE** | "Bounded" = TRUE (`budget`/`omitted_counts`/`next` fields are real and populated in all 4 packs). "Traceable" = TRUE at the item level (every item carries `source_span_ids` + an exact `locator` with page/heading/zotero URI) but UNRELIABLE at the pack-summary level (Finding 3). "Selected from the refined live DAG" = FALSE as measured: 0/4 packs contain a single `community_report` or `synthesis` item; the "refined" layers L3/L4 are categorically absent (Finding 1). |
| §5.2 | "...providing **hallucination-free answers** by leveraging only the **refined essence** of curated knowledge." | **FALSE** | This is the central claim. See Finding 1. All four measured packs — including the two genuine user questions recovered from `sessions.json` — draw exclusively from `graph_entities` (a light L2-adjacent refinement) + raw `source_spans` (L1) + unranked flat FTS `search_hits`. None of the vault's 233 L3 community reports or 4 L4 synthesis nodes were served. This is not "refined essence"; it is closer to keyword search over L1 with an entity list glued on. |
| §4 | "...the Curator applies the workspace Knowledge Requirement Specification (`curate.yml`) as a **dynamic retrieval lens** over the live DAG." | **FALSE** (for every measured query) | `snapshot.policy_hash` is `""` and `workspace_id` is `"default"` in all four packs (Finding 2). The KRS lens was never resolved, let alone applied, for any of the four measured questions. |
| §5.6 | "Global Persona ... defines the identity of the Curator ... The Artist Persona (`curate.yml`) overlays workspace-specific context." | **Global Persona: UNVERIFIABLE** from these packs (no system-prompt/persona field is exposed in a `context_fetch` pack; needs `curation_lens_persona`'s trace from `.curator/settings.yml`). **Artist Persona: FALSE** — same `policy_hash=""` evidence as §4, since the Artist Persona *is* `curate.yml` by definition. |

---

## Finding 1 — P1 — "Refined essence" is unreachable for real questions by construction, not by accident

**Summary.** The `local` route — the *only* route any of the four questions ever received, including the two real user questions and one explicit cross-paper synthesis request — is coded to never touch `community_reports` or `synthesis_nodes`. This is a deliberate contract, confirmed by an existing test, not a bug.

**Evidence / file:line.**
- `backend/src/curator/retrieval/evidence.py:441-448` — the entire `local` branch of `build_evidence()`:
  ```python
  # local: entities + their spans + search hits.
  ent_items, span_ids = _entity_evidence(db_path, q)
  pack.items.extend(ent_items)
  pack.items.extend(_span_items(db_path, span_ids))
  pack.source_span_ids = span_ids
  _add_search_hits(pack, paths, q, limit)
  ```
  There is no call to `_report_items()` (community reports, `evidence.py:297`) or `_synthesis_items()` (L4, `evidence.py:330`) anywhere in this branch. Those two functions are called *only* inside the `global` branch (`evidence.py:394-412`) and, in a bounded primer form (limit 3 each), inside `explore` (`evidence.py:414-439`).
- `backend/src/curator/retrieval/router.py:84-87` — the routing default:
  ```python
  # 5. Default: local entity/fact answer.
  if not status.has_entities:
      return _pick("local", "graph incomplete → local DB-native retrieval")
  return _pick("local", "entity/fact question")
  ```
  and the two escape hatches that could have selected `global`/`explore` are ASCII-only regexes (`router.py:20-29`, `_EXPLORE_SIGNALS`, `_GLOBAL_SIGNALS`) matched against `request.working_query`. Q1 and Q2 — the two real user questions — are entirely in Korean and can never match these patterns; Q3's own phrasing ("여러 논문을 **종합**해서 설명해줘" — literally "explain by **synthesizing**") also cannot match, because "synthesize" only exists in the regex as the English token "summar(?:y|ize|ise)". This is corroborating mechanism for *why* every question routed `local`; the deep classifier fix belongs to `router_and_layers`, but it is the direct reason the `local`-only exclusion in Finding 1 was actually exercised on every measured question, real or synthetic.
- `backend/tests/test_query_orchestrator.py:439-483` (`test_global_route_uses_reports`, `test_global_route_surfaces_synthesis_layer`, `test_fetch_context_includes_synthesis_in_global`) confirm the team already knows and tests that only `global` (and, for synthesis, `explore`) ever surface L3/L4 — this is intended behavior for `local`, not an oversight.

**Measured proof (all four packs).**
```
q1.json: community_report_ids=0, synthesis_node_ids=0, route=local, reason="entity/fact question"
q2.json: community_report_ids=0, synthesis_node_ids=0, route=local, reason="entity/fact question"
q3.json: community_report_ids=0, synthesis_node_ids=0, route=local, reason="entity/fact question"  (explicit synthesis request)
q4.json: community_report_ids=0, synthesis_node_ids=0, route=local, reason="entity/fact question"
```
`kind` distribution across all four packs is `entity` / `search_hit` / `source_span` only — never `community_report`, never `synthesis`, and never even `atom` (L2 atoms are also never returned as a first-class evidence kind in *any* route; they only leak in via flat `search_hit` matches, e.g. `02_Atoms/ATM-2982af2e.md` in q1.json).

**Concrete failure scenario.** A user asks the real question "ellipsoid 형태의 quadric 은 어떻게 매트릭스로 표현되나?" (Q1). The vault has 233 curated community reports synthesizing exactly this kind of cross-source geometric-vision material, built specifically so the agent "doesn't get lost in massive datasets." The agent instead receives 6 entity blurbs, 25 raw L1 spans, and 8 flat search hits — no report, no synthesis, ranked with no semantic reranking (see Finding 4). The product's stated differentiator (refinement) never activates; the user gets the equivalent of `grep` across L1 with an entity index bolted on, at the cost of the full L1→L4 compile pipeline having run beforehand.

**What DOES work here (fairness).** The entity descriptions are genuinely synthesized, not verbatim-copied text (e.g. Q1's `ENT-197903f1` "ellipsoids (concept)" → "Closed 3D surfaces used as constrained landmark representations in SLAM" is a real abstraction over the source, not a quote) — so *some* L2-adjacent refinement does reach the user. And per-item provenance (`locator.page_number`, `heading`, `external_uri: zotero://...`) is precise and genuinely traceable; that half of §4.3's promise holds up well. Formula/LaTeX indexing also works (Q1 has 11 LaTeX-bearing spans, Q2 has 5) — reaching them, not storing them, is the gap.

---

## Finding 2 — P1 — The "dynamic retrieval lens" (§4, KRS/`curate.yml`) never activated for any of the four measured queries

**Summary.** `curate.yml` is the mechanism named in §4 and §5.6 as the thing that biases retrieval per-workspace. It was not resolved for any of the four measured questions.

**Evidence / file:line.**
- All four packs: `snapshot.policy_hash == ""` and `workspace_id == "default"` (`q1.json`–`q4.json`, `.snapshot`).
- `backend/src/curator/curate_yml.py:663-674`, `resolve_curate_policy()`:
  ```python
  if not workspace_path:
      if require_spec:
          raise ValueError("no curate.yml in workspace")
      return compile_curate_policy(CurateSpec(project="default")), ""
  workspace = Path(workspace_path)
  spec = load_curate_spec(workspace)
  if spec is None:
      if require_spec:
          raise ValueError(f"no curate.yml in workspace {workspace}")
      return compile_curate_policy(CurateSpec(project="default")), ""
  ```
  An empty `spec_hash` return value is only produced by these two silent-fallback branches — i.e. `workspace_path` was falsy, or no `curate.yml` was found at that path. Either way, the query ran under the hashless default policy, not a workspace-scoped KRS lens.

**Concrete failure scenario.** README.md lists "Specification-Driven Curation" as differentiator #1 and about.md §4 frames it as the Curator's fourth core responsibility ("Curation & Engagement"). A user who has authored a `curate.yml` in `01_Workspaces/<project>/` to bias retrieval toward their project's concerns gets no benefit from it on the measured query path — every pack ran identically to a vault with no `curate.yml` at all. This matches the prior audit referenced in the briefing ("sidechat always passes the vault ROOT as `workspace_path`"); I did not re-trace the call site (that is `curation_lens_persona`'s assignment), but the pack-level symptom (`policy_hash=""`, `workspace_id="default"`) independently confirms the KRS was never in effect for these four real retrievals, from data this domain was asked to use directly.

---

## Finding 3 — P2 — When L4 content does reach a pack, it is invisible to the pack's own provenance counters and unprioritized

**Summary.** L4 Synthesis content is not entirely unreachable — it can leak in through the generic flat-search path — but when it does, the pack's self-reported `synthesis_node_ids` (which about.md's "traceable" claim rests on) does not count it, and nothing ranks it any higher than an arbitrary keyword match.

**Evidence.** `q4.json`, item `04_Synthesis/SYN-e91665d4.md`:
```json
{
  "kind": "search_hit",
  "synthesis_node_id": "",
  "score": 0.016129032258064516,
  "title": "Kernel Fusion and Memory Optimizations in High-Performance Gaussian Splatting Pipelines",
  "locator": {"relpath": "02_Wiki/CUDA_GaussianSplatting_고급/.../06_논문별_CUDA_커널_상세_분석.md", ...}
}
```
This is a real, on-topic L4 synthesis statement — directly answering Q4 ("How does kernel fusion reduce bottlenecks...") — but it arrived via `_add_search_hits()` (flat FTS/vector match over the promoted-wiki copy of the SYN- file), not via `_synthesis_items()` (`evidence.py:330-350`, the function that actually sets `EvidenceItem.synthesis_node_id`). Because `synthesis_node_id` is left `""` on the `search_hit`-kind item, `q4.json`'s top-level `synthesis_node_ids` count is `0` even though L4 content is physically present in `items`. Its score, `0.016`, places it near the bottom of a 58-item pack — no boost is applied for being higher-layer content.

**Concrete failure scenario.** A developer or the user, trusting `synthesis_node_ids: []` in the trace, concludes "no synthesis was used, answer is grounded in raw evidence only" — but a synthesis statement *was* in the context the agent read, unlabeled and unprivileged. The self-report is not lying about the deliberate synthesis retrieval path, but it does not describe what evidence the agent actually saw, which undercuts the "traceable" half of §4.3 for anyone auditing from the pack summary rather than the raw item list.

---

## Finding 4 — P2 — The retrieval infrastructure backing even the fallback (`local`) path is itself running degraded on this vault

**Summary.** Independent of the L3/L4 exclusion (Finding 1), the search layer `local` actually depends on is not running at the fidelity §5.2 implies. Every one of the four packs carries the same two warnings:
```
"vector_unavailable: no embedder configured (FTS5-only)"
"no reranker configured: returned RRF order"
```
**Evidence / file:line.** `backend/src/curator/context_service.py:653`:
```python
coverage = "partial" if pack.warnings or omitted_counts else "sufficient"
```
Since these two warnings are unconditional for this vault's current provider configuration, `coverage.sufficiency` is structurally pinned to `"partial"` regardless of whether the DAG actually contained enough refined knowledge to answer well — the field conflates "the local search stack is degraded" with "the knowledge base is insufficient," which are different failure modes with different fixes (one is a config/model problem, the other is a content problem). This is adjacent to `content_quality`'s assigned question ("why is sufficiency always partial") but is cited here because it bears directly on §5.2's "High-Fidelity Knowledge Grounding" framing: with no embedder and no reranker, even the L1-span/entity/search-hit fallback the user actually receives is unranked RRF order over lexical-only candidates, not the hybrid vector+rerank pipeline the architecture (`engine.py`) is built to run.

---

## Finding 5 — P3 — Korean philosophy/README docs diverge from the English source: a different product promise is made, and the "hallucination-free" framing is dropped

**Summary.** `ABOUT_KR.md` and `README_KR.md` are not translations of `about.md`/`README.md` — they open with an entirely different "ultimate vision" that does not exist in English at all, and they drop the specific overclaim (§5.2's "hallucination-free") that this audit is testing.

**Evidence.**
- `docs/philosophy/ABOUT_KR.md:7-14` and `docs/README_KR.md:5-9` both open with a vision section absent from the English docs: *"궁극적인 비전: '노트 필기를 위한 Cursor (Ask Gemini for Obsidian)'"* — framing Incurator as an Obsidian-embedded chat agent that "mimics Chrome's 'Ask Gemini' system," reading the user's currently-open note/paper in real time. `docs/philosophy/about.md` and `docs/README.md` never make this comparison or promise anywhere in either file (confirmed by reading both in full above) — this is a UX/product claim about a live-context chat sidebar, not something these four evidence packs can test either way; it is simply a promise the English source never makes.
- `docs/README.md:5` tagline is **"Increment your knowledge, don't just search it."** and line 7 explicitly promises "...without token waste or **hallucinations**." `docs/README_KR.md:5` replaces the tagline outright with *"노트 필기를 위한 Cursor, 옵시디언 안의 Ask Gemini"* and — confirmed by `grep` — contains no occurrence of "환각" (hallucination) or an equivalent phrase anywhere in the file. Similarly, `ABOUT_KR.md §5` ("시스템의 핵심: 세 가지 차별점") restructures the English §5's six numbered points (Reviewed Knowledge Compiler, **High-Fidelity Knowledge Grounding/hallucination-free**, Token Optimization, Two-Track Directory, Ecosystem Diversity, Persona) down to three, and the "hallucination-free... refined essence" sentence under test in this audit has **no Korean-language counterpart at all**.

**Assessment.** This cuts both ways and is reported for fairness, not as an accusation of dishonesty: the Korean docs make the central claim under test (§5.2) *less* aggressively — a Korean-only reader is never told to expect "hallucination-free" answers, so Finding 1 does not falsify a promise made to them on that specific point. But they substitute a different, equally untested promise (a live-context "Ask Gemini for Obsidian" chat experience) that this audit's evidence packs (all `wiki plugin context fetch` calls, not sidebar-chat sessions) cannot confirm or refute. Per the project's own `CLAUDE.md` synchronization rule ("Implementation and docs must always be in sync... For paired English/Korean guides, edit the English guide first... do not use the Korean guide as the canonical source for new behavior"), this divergence is itself out of contract regardless of which version is more accurate.

---

## Verdict on the central question

**Is the product delivering its stated value, or is it currently an expensive way to do flat retrieval over L1?**

For the measured evidence — two real user questions and two representative ones, all four routed identically — it is closer to the second, but not entirely: it is flat retrieval over L1 **plus a genuinely useful entity layer and precise per-span provenance**, not raw grep. The compile pipeline (L1→L2→L3→L4) runs, costs tokens, and produces real artifacts (233 L3 reports, 4 L4 syntheses, extracted entities with synthesized descriptions) — but the query-time path a real user's question travels (`local`, unconditionally, because the router's signal detection is English-regex-only and because `curate.yml` never resolves for these calls) structurally cannot reach the two layers (L3, L4) that the "refined essence" and "dynamic retrieval lens" claims are actually about. The refinement work is real; it is simply almost never served. This is a routing/contract gap (Finding 1, `router_and_layers`'s primary territory) compounded by a curation-lens gap (Finding 2, `curation_lens_persona`'s primary territory) — both visible and independently confirmable from this domain's assigned pack data — not a fabricated feature. What functions well and should be preserved: per-item traceability/locators, bounded budgeting, entity-level abstraction, and LaTeX/formula indexing.
