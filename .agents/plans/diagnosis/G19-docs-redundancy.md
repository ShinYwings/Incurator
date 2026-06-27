# Diagnosis: G19-docs-redundancy
Coverage: `docs/guides/*.md` (+ `_KR.md` pairs), `docs/README.md`/`_KR.md`, `docs/philosophy/about.md`/`ABOUT_KR.md`, `docs/specs/failure_atlas/*`. Method: EN/KR line + structural parity (`wc`, H2/H3/code-fence counts), cross-doc duplication probes (`grep -l` for shared topics: `curate.yml` fields, `wiki update` lifecycle, CLI command references), and stale/one-time-artifact scan.

Category coverage: (b) redundancy: G19-1, G19-2; (d) legacy/dead docs: G19-3, G19-4; (f) docs drift: G19-2. Severity S2/S3 — maintenance-cost and discoverability issues, not runtime risk.

## Findings

### [G19-1] (b,e) S2 — `curate.yml` field reference is duplicated across 6 guides + 2 specs with no canonical home
- Loc: `docs/guides/USER_GUIDE.md`, `docs/guides/WORKFLOW_GUIDE.md`, `docs/guides/MCP_USER_GUIDE.md`, `docs/guides/CONTRIBUTION_GUIDE.md`, `docs/guides/DEV_SCRIPTS_GUIDE.md`, `docs/guides/AGENT_WORKFLOW_GUIDE.md` (all explain `curate.yml` fields like `sources.include` / `min_confidence`), plus `docs/specs/curator_schema/SCHEMA.md` and `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`
- Evidence: `grep -l` for `min_confidence|sources.include|curate.yml` matches six separate guides (and both KR mirrors). Each restates the Knowledge Requirement Spec field set inline. There is no single "curate.yml reference" section that the others link to, so a schema change to `curate.yml` (new field, renamed key, changed default) requires synchronized edits to 6 guides × 2 languages + 2 specs — exactly the kind of fan-out that drifts (e.g. a field added to USER_GUIDE but not WORKFLOW_GUIDE).
- Fix sketch: designate one canonical curate.yml reference (the natural home is `SCHEMA.md` for the contract + a single USER_GUIDE section for usage), reduce the other five guides to a one-line pointer/link, and keep only context-specific notes inline. Do this additively (don't lossy-compress the canonical copy — see CLAUDE.md anti-compression rule).
- Blast radius: every curate.yml change, EN↔KR sync burden, agent confusion over which doc is authoritative.
- Suggested PR: `docs/curate-yml-single-source`

### [G19-2] (b,f) S3 — The `wiki add → build → embed → sync` lifecycle and CLI command reference are triplicated
- Loc: `docs/guides/USER_GUIDE.md` (§"Core Commands (CLI Reference)", 123 `wiki …` lines), `docs/guides/WORKFLOW_GUIDE.md` (§4 "Core Workflows", 69 `wiki …` lines), `docs/guides/PLUGIN_GUIDE.md` (`wiki update` references)
- Evidence: all three guides document the core ingest lifecycle and the `wiki update` one-shot. USER_GUIDE's "Core Commands (CLI Reference)" and WORKFLOW_GUIDE's "Core Workflows" overlap heavily in the command set and the curate.yml example block. When a command's flags/behavior change (as in the v0.27.2 work just shipped), all three can drift independently; there is no single CLI-reference table that the workflow narrative links into.
- Fix sketch: make USER_GUIDE's "Core Commands (CLI Reference)" the canonical command table; have WORKFLOW_GUIDE narrate the *workflow* and link to that table for exact flags rather than re-listing commands; PLUGIN_GUIDE links for the `wiki update` definition. Keep each guide's unique framing, remove the verbatim command re-statements.
- Blast radius: CLI changes, command-flag accuracy across guides.
- Suggested PR: `docs/cli-reference-single-source`

### [G19-3] (d) S3 — `failure_atlas/` mixes frozen test fixtures and a historical handoff doc under `docs/specs/`
- Loc: `docs/specs/failure_atlas/PROGRAM_HANDOFFS.md`, `docs/specs/failure_atlas/EVALUATION_BASELINE.md`, `docs/specs/failure_atlas/FAILURE_ATLAS.md`, `docs/specs/failure_atlas/{D2_HOLDOUT_RESULT,fixture_corpus,qrels,support_labels,plan_b_compiler_gold}.yml`, `docs/specs/failure_atlas/cases/*.yml` (13 files)
- Evidence: this directory holds three distinct kinds of artifact in one place: (a) **live test fixtures** that 8 test files hash/read as frozen oracles (`test_failure_atlas_d2.py`, `test_failure_atlas_eval.py`, `test_plan_b_*`, `test_research_spikes_*`, etc. — confirmed via grep; we just re-armed `D2_HOLDOUT_RESULT.yml`'s db.py hash this session), and (b) a **one-time historical handoff** — `PROGRAM_HANDOFFS.md` opens "# Program 1 Final Handoffs (D2, v0.7.0) … final Program 1 handoff after D1 diagnosis, Plan E research, and D2 observatory work." None of these are linked from any guide, README, or spec index (`grep` for their names across `docs/**` outside the folder returns nothing). They are load-bearing for tests (NOT deletable), but their placement as `docs/specs/` content with zero navigational entry conflates "frozen test fixture" with "authoritative spec."
- Fix sketch: do NOT delete (tests depend on the YAMLs and oracle docs). Instead: (1) add a short `docs/specs/failure_atlas/README.md` index explaining each file's role and that the `.yml` files are test-frozen oracles (change ⇒ atlas-version decision); (2) clarify whether `PROGRAM_HANDOFFS.md` is a frozen oracle (keep) or a historical artifact that could move to git-history-only; (3) consider relocating the pure fixtures (`fixture_corpus.yml`, `qrels.yml`, `support_labels.yml`, `cases/*.yml`) under `backend/tests/` if nothing but tests consumes them.
- Blast radius: doc discoverability, test-fixture coupling clarity; touching the YAMLs is high-risk (frozen hashes) so this is documentation/placement only.
- Suggested PR: `docs/failure-atlas-index-and-roles`

### [G19-4] (d) S3 — Version annotations accumulate as inline `(vX.Y.0)` section tags in guides
- Loc: `docs/guides/USER_GUIDE.md` (e.g. "Claim-Level Support & Compiler Integrity (v0.8.0)", "Graph Quality (v0.9.0)"), and ~40 `v0.14–v0.26` inline refs across guides
- Evidence: guides carry "added in vX" suffixes on section headers and feature notes (10× v0.24.0, 8× v0.19.0, 6× v0.21.0, 6× v0.14.1, …). These are useful as changelog breadcrumbs but accrete indefinitely on a pre-1.0 project; some refer to versions far enough back that the "new in" framing no longer helps a reader. This is not drift (the features exist) but a slow legibility erosion — section titles increasingly read as a version archaeology layer.
- Fix sketch: low priority. When next editing each guide, drop the `(vX.Y.0)` suffix from section *titles* (keep a single CHANGELOG as the version history) while retaining genuinely useful "behavior changed in vX" inline notes. Do not mass-edit purely to strip tags — fold into other edits to avoid churn.
- Blast radius: guide readability only.
- Suggested PR: defer; fold into per-guide edits

## Positives (keep / do-not-break)
- **EN↔KR structural parity is healthy** — verified, not assumed. PLUGIN_GUIDE EN/KR: H2 18/18, H3 25/26, code-fences 26/26 (the −197-line EN/KR delta is Korean prose density, not lossy compression). MCP_USER_GUIDE H3 10/10; README EN/KR 98/102. The anti-compression guardrail (CLAUDE.md §6) is being honored: KR guides mirror EN structure rather than summarizing it.
- The MCP guide documents the removed `curator_search_source` alias as removed (not silently dropped), in both EN and KR at the same line — good deprecation discipline.
- The docs tree is otherwise lean: only `README`, `philosophy/about`, `guides/*`, `specs/*` — no abandoned `archives/` folders (matches the "no spec archives; use git history" rule).
- The failure-atlas `.yml` oracles being frozen and hash-checked by tests is a genuine strength (reproducible evaluation); the only issue is their discoverability/placement, not their existence.

## Open questions for the human
- Should `curate.yml` and the CLI command reference each get a single canonical home with the other guides linking in, or is the current duplication an accepted cost for self-contained guides?
- Is `PROGRAM_HANDOFFS.md` still a live oracle that tests pin against, or a historical v0.7.0 artifact that can move to git-history-only?
- Should the pure test fixtures under `docs/specs/failure_atlas/` move to `backend/tests/`, keeping only the human-readable atlas/baseline docs under `docs/specs/`?
