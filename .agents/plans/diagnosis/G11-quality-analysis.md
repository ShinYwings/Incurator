# Diagnosis: G11-quality-analysis
Coverage: `backend/src/curator/lint.py`, `backend/src/curator/contradiction.py`, `backend/src/curator/backprop_classifier.py`, `backend/src/curator/backprop_agents.py`, `backend/src/curator/insight_lifecycle.py`, `backend/src/curator/intent.py`, `backend/src/curator/curate_yml.py`, `backend/src/curator/inspection/synthesis_audit.py`

Category coverage: (a) G11-1/G11-2/G11-4/G11-5/G11-6/G11-7/G11-8/G11-9/G11-13/G11-16/G11-17; (b) G11-18; (c) G11-3/G11-19; (d) G11-12/G11-15/G11-18; (e) G11-10/G11-15; (f) G11-5/G11-6/G11-7/G11-12; (g) G11-11/G11-14/G11-15/G11-17; (h) G11-1/G11-2/G11-3/G11-4/G11-10/G11-13/G11-14; (i) G11-12/G11-13.

## Findings

### [G11-1] (a,h) S2 - Insight promotion can escape `02_Wiki/` when `subdir` is provided
- Loc: `backend/src/curator/insight_lifecycle.py:111`
- Evidence: `promote_insight` builds `target_dir = wiki_root / subdir` and `rel = f"02_Wiki/{subdir}/..."` without rejecting absolute paths, `..`, or normalized paths outside `02_Wiki/`. The guard only searches for `03_Notes/`, `04_Resources/`, and `06_Archives/` substrings, so a value such as `../.curator/Collections/04_Synthesis` can write outside the promised promotion area. `out_path.write_text(...)` also overwrites any same-slug note.
- Fix sketch: Add a shared safe-vault-subdir helper for `02_Wiki`, reject absolute and escaping paths, resolve the final path and assert it is relative to `paths.root / "02_Wiki"`, and allocate collision-resistant filenames.
- Blast radius: `wiki insight promote`, plugin `insight promote`, MCP `curator_promote_insight`, and any future caller that exposes the `subdir` parameter.
- Suggested PR: `fix/insight-promotion-path-safety`.

### [G11-2] (a,h) S2 - Contradiction resolution is marked resolved even when no atom was changed
- Loc: `backend/src/curator/contradiction.py:104`
- Evidence: `apply_resolution` skips empty revised bodies and missing atom files, but always calls `add_dismissed(..., reason="resolved")` at the end. A malformed LLM proposal or deleted atom can therefore suppress future contradiction detection without applying a resolution.
- Fix sketch: Track successful writes for both requested atoms; only mark resolved when the required edits were applied. Return a structured result or raise on partial resolution, and leave the pair flagged for review on failure.
- Blast radius: CLI contradiction resolution, MCP contradiction resolution, and repeated deep-lint contradiction scans.
- Suggested PR: `fix/contradiction-resolution-atomicity`.

### [G11-3] (c,h) S2 - Dismissed-contradiction storage silently hides corruption, then can crash on valid-but-wrong JSON
- Loc: `backend/src/curator/contradiction.py:25`
- Evidence: `load_dismissed` catches every exception and returns `[]`, losing the signal that `.curator/contradiction_dismissed.json` is corrupt. If the file parses as a dict or as a list with entries missing `pair`, `is_dismissed` later indexes `e["pair"]` without validation.
- Fix sketch: Validate the loaded shape as `list[{"pair": [str, str], ...}]`, ignore only invalid entries with an explicit warning, and save atomically via temp file plus replace.
- Blast radius: Deep lint, MCP flagged-atom listing, dismiss/resolve flows, and any workspace with a hand-edited or partially-written dismissed file.
- Suggested PR: `fix/contradiction-store-validation`.

### [G11-4] (a,h) S1 - `curate.yml` parser silently changes boolean and source-scope policy
- Loc: `backend/src/curator/curate_yml.py:276`
- Evidence: Boolean fields are parsed with `bool(value)`, so YAML strings like `"false"` become `True` for `allow_external`, `require_rebind_approval`, `exploration_enabled`, `require_source_spans`, `allow_general_knowledge`, and `backprop.enabled`. List fields use `_str_list_from`, which returns `[]` for scalar strings; a mistaken `sources.include: "03_Notes/**"` becomes "include all sources" because an empty include list means no filter.
- Fix sketch: Add strict typed parsers for bool/list/float/int fields, reject wrong scalar types with contextual `ValueError`, and add regression tests for string booleans and scalar include/exclude values.
- Blast radius: Workspace KRS enforcement, Reference Mode, source privacy, general-knowledge policy, backprop enablement, MCP validation, and query/retrieval policy compilation.
- Suggested PR: `fix/curate-yml-strict-types`.

### [G11-5] (a,f) S2 - Search query boosting ignores canonical KRS knowledge fields
- Loc: `backend/src/curator/curate_yml.py:185`
- Evidence: `boost_query` claims to append domain/topic terms but only reads legacy `persona.domain`, `persona.subdomain`, and `persona.disambiguation_keywords`. The current KRS fields are `knowledge.domains`, `knowledge.topics`, and `knowledge.disambiguation_keywords`; the schema also states old `persona.*` to KRS auto-mapping is not maintained.
- Fix sketch: Make boosting use `knowledge.*` first, optionally append persona fields only as documented legacy fallback, and add tests with a KRS-only `curate.yml`.
- Blast radius: MCP `search_curator` KRS lens and any workspace relying on structured KRS topics instead of legacy persona fields.
- Suggested PR: `fix/krs-query-boost-fields`.

### [G11-6] (a,f) S2 - Invalid routes can silently broaden into all valid routes
- Loc: `backend/src/curator/curate_yml.py:508`
- Evidence: `compile_curate_policy` filters `allowed_modes` to known routes, but if none remain it sets `allowed = VALID_ROUTES`. That means `allowed_modes: ["locla"]` compiles as every route. `validate_curate_spec` can report the typo, but several runtime paths call `compile_curate_policy` directly; the behavior spec says invalid specs should surface errors instead of silently using defaults.
- Fix sketch: Make `compile_curate_policy` refuse invalid specs or return a typed result with errors; ensure all query/plan call sites validate before compiling and do not record plans when errors exist.
- Blast radius: Query routing, `curator_plan_workspace`, plugin curation planning, and source-section/explore availability.
- Suggested PR: `fix/curation-policy-invalid-routes`.

### [G11-7] (a,f) S2 - Documented directory include patterns do not match descendants
- Loc: `backend/src/curator/curate_yml.py:29`
- Evidence: The `CurateSources.include` docstring gives `02_Wiki/ml/` as an example directory pattern. `_matches_any` converts that to an exact regex for `02_Wiki/ml/`, so `02_Wiki/ml/foo.md` does not match. Users who follow the documented shorthand get an empty source scope for that directory.
- Fix sketch: Normalize trailing-slash patterns to `pattern + "**"` or switch to `pathlib.PurePosixPath.match`/`fnmatch` with explicit tests for directory, file, and glob patterns.
- Blast radius: KRS source selection, `CurationPolicy.allows_source`, retrieval evidence filtering, and workspace-specific search.
- Suggested PR: `fix/curate-source-patterns`.

### [G11-8] (a) S2 - Cross-layer lint emits the `dataclasses.field` function instead of the frontmatter field name
- Loc: `backend/src/curator/lint.py:896`
- Evidence: `check_cross_layer_links` formats `f"Update `{field}`..."` and stores `"field": field`, but `field` is the imported `dataclasses.field` function. The loop variable is `fm_field`. Wrong-layer findings therefore produce unusable guidance and non-domain context.
- Fix sketch: Replace both uses with `fm_field`; add a unit test that creates an L4 `concept_ids` wrong-layer link and asserts the issue context field is `concept_ids`.
- Blast radius: `wiki lint` terminal output, saved lint reports, sync preflight review guidance, and any future machine consumer of lint issue context.
- Suggested PR: `fix/lint-cross-layer-field-context`.

### [G11-9] (a,i) S2 - Saved lint reports are written as invalid L4 pages that future lint runs will flag
- Loc: `backend/src/curator/lint.py:1483`
- Evidence: `render_report_markdown` emits frontmatter with `type: synthesis`, `concept_ids`, and `confidence_score`, but omits required L4 fields checked by `check_frontmatter`: `id`, `community_report_ids`, and `source_span_ids`. `_build_inventory` only skips names starting with `lint-report-`, while the CLI save path writes `SYN-lint-...md`, so the report becomes part of the Collections inventory and contaminates later health checks.
- Fix sketch: Save diagnostics outside `.curator/Collections`, or give lint reports a separate skipped filename/type, or emit a fully valid diagnostic schema and exclude it from DAG integrity checks.
- Blast radius: `wiki lint --save`, health-score stability, CI/testbed lint gates, and user trust in "clean" reports.
- Suggested PR: `fix/lint-report-storage`.

### [G11-10] (e,h) S2 - Deep lint mutates atom files during an audit command
- Loc: `backend/src/curator/lint.py:1000`
- Evidence: `check_contradictions_deep` writes `is_flagged_for_agent: true` to both atoms as soon as the LLM returns a contradiction. `run_lint(deep=True)` therefore has write side effects even when the user did not request `--fix`; other lint/graph audit surfaces are described as read-only audit gates.
- Fix sketch: Split contradiction detection from flag persistence. Emit `LintIssue` only during lint, then persist flags only through an explicit resolve/flag/apply command, or document and test deep lint as a mutating command.
- Blast radius: `wiki lint --deep`, sync preflight, testbed reproducibility, and concurrent users inspecting `.curator/Collections`.
- Suggested PR: `fix/deep-lint-readonly-or-explicit-apply`.

### [G11-11] (g) S2 - Contradiction pair generation is quadratic before `max_pairs` is applied
- Loc: `backend/src/curator/lint.py:948`
- Evidence: Deep contradiction detection compares every L2 atom pair, computes overlap, sorts the full list, and only then slices to `max_pairs`. Large vaults pay O(n^2) time and memory even when the user asks for a tiny pair cap.
- Fix sketch: Build an inverted index from shared link target to atoms, count overlaps only for atoms sharing a target, and maintain a bounded heap of top pairs.
- Blast radius: `wiki lint --deep`, sync deep checks, large vault responsiveness, and LLM preflight cost.
- Suggested PR: `perf/deep-lint-pair-index`.

### [G11-12] (d,f,i) S3 - Lint guidance still refers to retired EXH/Exhibition concepts
- Loc: `backend/src/curator/lint.py:435`
- Evidence: Orphan guidance says L3 pages should be linked from "L4 Exhibition" and L4 pages from an "EXH entry"; deep-check comments also say "L4 Exhibitions". Static EXH files were removed and valid L4 nodes are `SYN-` synthesis nodes.
- Fix sketch: Replace EXH/Exhibition wording with Synthesis/SYN language and align the orphan guidance with current routing/index behavior.
- Blast radius: User-facing lint suggestions, saved lint reports, and docs-code consistency.
- Suggested PR: `fix/lint-synthesis-wording`.

### [G11-13] (a,h,i) S2 - Intent parsing is substring-based and its public contract omits `promote`
- Loc: `backend/src/curator/intent.py:58`
- Evidence: `IntentResult.intent` is documented as only `wiki` or `chitchat`, while the prompt and implementation also return `promote`. Parsing uses substring checks, so responses like `NOT PROMOTE` or explanatory text containing `PROMOTE` become promotion intents. The query pipeline only special-cases `chitchat`; promote is only handled by the interactive CLI path.
- Fix sketch: Define an explicit enum/`Literal["wiki", "chitchat", "promote"]`, parse only the first normalized token or exact full response, and make all call sites either handle or intentionally ignore `promote`.
- Blast radius: Interactive query promotion, plugin/query intent telemetry, accidental retrieval on promotion requests, and false promotion prompts.
- Suggested PR: `fix/intent-contract-and-parser`.

### [G11-14] (g,h) S2 - Intent timeout parameter is unused
- Loc: `backend/src/curator/intent.py:67`
- Evidence: `classify_intent` accepts `timeout_seconds=10.0`, and the module doc says this is a fast pre-retrieval call, but the value is never passed to `client.chat` or otherwise enforced. `generate_chitchat_reply` has no timeout control either.
- Fix sketch: Plumb timeout support through the LLM client interface, enforce it around the call, or remove the parameter and rely on a documented client-level timeout.
- Blast radius: `wiki query`, interactive chat, plugin quick query, and any path that blocks retrieval behind intent classification.
- Suggested PR: `fix/intent-timeout-enforcement`.

### [G11-15] (d,e,g) S2 - Generative backprop agents are placeholder architecture but still live on the sync path
- Loc: `backend/src/curator/backprop_agents.py:26`
- Evidence: `TimePerformanceEvaluator.evaluate_atom_quality` always returns `True`, `WorkspaceController.commit_and_update_routing` is `pass`, and `ConceptClusteringAgent.recluster` ignores its `atom_ids` argument and reruns L3 clustering over all atoms. `sync.apply_generative_backprop` instantiates and calls these classes.
- Fix sketch: Either remove this legacy multi-agent layer from the active sync path and route through `backprop_classifier`/`insight_lifecycle`, or implement real quality/routing behavior with tests and bounded reclustering.
- Blast radius: `wiki sync` generative backprop, logical-gap repair, incremental build cost, and correctness of generated atoms after backprop.
- Suggested PR: `refactor/backprop-agents-lifecycle`.

### [G11-16] (a) S2 - Synthesis audit dependency checks do not support all schema-valid dependency types
- Loc: `backend/src/curator/inspection/synthesis_audit.py:174`
- Evidence: `_current_dependency_hash` only knows `source_span`, `community_report`, and `synthesis_node`. The schema allows `knowledge_unit`, `entity`, `relation`, and `community_report`, and report compilation records relation dependencies. Unsupported valid dependency types return `None`, which `_dependency_warnings` reports as `missing dependency`.
- Fix sketch: Add current-hash lookups for every `depends_on_type` allowed by the schema, or emit a distinct "unsupported dependency type" audit warning. Add a report audit test with relation dependencies.
- Blast radius: Synthesis/report/answer audit payloads, stale-dependency triage, and user confidence in provenance diagnostics.
- Suggested PR: `fix/synthesis-audit-dependency-types`.

### [G11-17] (a,g) S2 - Answer audit hydrates only the first synthesis node and summary listing fetches all rows before limiting
- Loc: `backend/src/curator/inspection/synthesis_audit.py:380`
- Evidence: `build_answer_audit` reads `synthesis_node_ids` but only loads `synthesis_ids[0]`, so answers backed by multiple synthesis nodes omit additional synthesis payloads and dependency warnings. Separately, `list_synthesis_summaries` calls `db.list_synthesis_nodes(db_path)[:limit]`, fetching all synthesis nodes before slicing.
- Fix sketch: Represent `syntheses` as a list in answer audits, hydrate dependencies for every synthesis id, warn on every missing id, and add a DB-level `LIMIT` path for summaries.
- Blast radius: Query trace inspection, plugin detail views, large-vault audit performance, and debugging of multi-synthesis answers.
- Suggested PR: `fix/answer-audit-multiple-synthesis`.

### [G11-18] (b,d) S3 - Redundant and unused helpers increase drift risk
- Loc: `backend/src/curator/backprop_classifier.py:21`
- Evidence: `CLASSIFICATIONS` duplicates the prompt contract literal but is not used for validation. `load_curate_spec` defines an inner `_str_list` that is never called. `synthesis_audit._decode_report` duplicates DB report decoding but is unused by the audit hydration path.
- Fix sketch: Remove unused helpers, or wire them into validation with tests. Prefer one authoritative enum/decoder per contract.
- Blast radius: Prompt-contract drift, curate parser maintenance, and audit JSON decoding behavior.
- Suggested PR: `chore/remove-quality-dead-helpers`.

### [G11-19] (c) S3 - Audit JSON decoding drops corrupt provenance without surfacing warnings
- Loc: `backend/src/curator/inspection/synthesis_audit.py:16`
- Evidence: `_loads_list` and `_loads_obj` return `[]`/`{}` on decode failure. Since audit payloads exist to prove provenance, corrupt JSON in DB fields can disappear as "no source spans" or empty metadata rather than a targeted corruption warning.
- Fix sketch: Thread the audit warning list into decode helpers or return `(value, warning)` so malformed provenance fields are explicit in the final audit payload.
- Blast radius: Synthesis audits, answer audits, source-span metadata, prompt validator errors, and debugging corrupted DB rows.
- Suggested PR: `fix/audit-json-corruption-warnings`.

## Positives (keep / do-not-break)
- `lint.is_safe_fixable` correctly distinguishes deterministic safe fixes from LLM-assisted relinks, preventing unresolved broken links from being deleted by the deterministic fixer.
- `_build_inventory` includes curated frontmatter wikilink fields such as `parent_source` and `concept_ids`, while intentionally excluding `source_path` from broken-link checks to avoid false positives on raw source files.
- `contradiction.is_dismissed` uses order-insensitive pair comparison after atom-id normalization, which is the right behavior for ATM-pair decisions.
- `insight_lifecycle.plan_action` keeps `writes_source_truth` false for every classification and filters correction targets to generated node prefixes.
- `CurationPolicy.allows_source` mirrors `CurateSpec.matches_sources`, giving retrieval code a compact runtime policy object instead of re-reading YAML.
- `synthesis_audit` is read-only and already assembles community reports, graph entities/relations, source spans, prompt runs, and dependency warnings in one inspectable payload.

## Open questions for the human
- Should `wiki lint --deep` be allowed to persist `is_flagged_for_agent`, or should lint stay read-only and contradiction flagging move behind an explicit apply command?
- Is legacy `persona` still a supported runtime input for search boosting, or should KRS `knowledge.*` be the only canonical source?
- Should `promote_insight(..., subdir=...)` remain part of the backend API, or should insight promotion always write to a flat `02_Wiki/` path?
- Should malformed `curate.yml` fail during `load_curate_spec`, or should loading stay permissive with every runtime caller required to check `validate_curate_spec` first?
- Should saved lint reports be durable vault artifacts, or should they be out-of-band diagnostics under `.curator/` and excluded from DAG linting?
