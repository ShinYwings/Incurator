# Domain Specialist Validations + Architect Defense

Date: 2026-06-11 | Personas: schema_guardian, source_pair_analyst, lead_architect (defense)

## schema_guardian
- **No DB schema, no DAG, no migration.** This milestone is 100% plugin-side (TS): `chatSidebar.ts`, `diffViewer.ts`, `editArtifact.ts`, `systemPrompt.ts`, `textUtils.ts`, new `editMatch.ts`, `types.ts` (a default flag flip). No `state.sqlite`, no `SCHEMA.md`, no prefixes (`CTX/ATM/CON/SYN`) touched. ✅ No schema risk.
- **`00_System/` invariant preserved.** `00_System/` is NOT a `raw_dir`, so artifact notes were never ingested as Curator sources; turning the artifact off (vs. moving it elsewhere) keeps that invariant trivially. No EXH/qmd resurrection. ✅
- **One concern**: the default-flag flip in `DEFAULT_SETTINGS` only affects NEW installs / unset values; existing users keep their saved `true`. That's the safe direction (no surprise data deletion) but means the user's own vault may still write artifacts until they toggle it. → Plan must call this out and the CHANGELOG must tell existing users to toggle it off if desired. Acceptable.

## source_pair_analyst
- **No RAG/L1–L4/backprop impact.** The edit flow operates on human-space Markdown (e.g. `02_Wiki/`, open notes) AFTER retrieval; it does not feed L1 ingestion or synthesis backprop. Robust matching does not change what `wiki add`/`sync` see. ✅
- **Selection/`<selection>` semantics unaffected.** The scope-prompt rule reinforces existing `<selection>`/`<open_markdown_edit_targets>` handling; no retrieval contract changes. ✅
- Flag: ensure the "large replacement" warning (red_teamer V6) does not block legitimate large refactors a user explicitly asked for → keep it a non-blocking Notice. Agreed.

## lead_architect — Defense / Revisions accepted
- **V1 accepted**: **Drop Tier 2.** Final matcher tiers = exact → line-trim → anchored (≥3 lines, ambiguity + max-span guards). Line-trim handles the dominant real drift (indentation), without intra-line whitespace hazard. Tier-1 line-trim will also be code-fence-agnostic-safe because it requires identical line COUNT and identical trimmed content per line, preserving structure.
- **V2 accepted**: auto-open hard-gated (single resolvable target that is already active or no focused MarkdownView; never force a new tab). `msg.diffAutoOpened` per-message, reset when the active session changes.
- **V3 accepted**: anchored tier uses minimal non-overlapping spans; >1 minimal candidate → null; reject span > 3× search line count.
- **V5 accepted**: `stripDanglingEditMarkers` operates ONLY on the rendered HTML pass, code-fence-aware, exact marker grammar, on-its-own-line; stored `msg.content` untouched (copy stays faithful).
- **V6 accepted**: add non-blocking "large replacement" warning Notice in the apply path as a model-independent net, in addition to the prompt rule.
- **V7 accepted (promoted to core)**: `reviewAssistantEdit` MUST construct modified text via the same `editMatch` splice, so the previewed diff equals what apply would do. This unifies all three paths on one matcher.

## Consensus reached
Edge-hardening, no DiffViewer rewrite, no schema/RAG impact, ambiguity-safe matcher (3 tiers), hard-gated auto-open, faithful marker stripping, artifact off-by-default (reversible), prompt + non-blocking-warning for scope. Proceed to Master Plan.
