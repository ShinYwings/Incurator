# Critique: Domain Specialists (schema_guardian + source_pair_analyst)

Date: 2026-06-20 | Agent Personas: schema_guardian, source_pair_analyst

## schema_guardian — DB / contract integrity

### S1 — No DB schema change; spec surface is plugin-only
This milestone touches `plugin/` prompt assembly and the LLM client call
signature only. There is NO change to `state.sqlite`, node prefixes
(`CTX/ATM/CON/SYN`), frontmatter, or `db.py`. Therefore:
- No migration script is required (the ROADMAP "Major/Minor migration" rule is
  satisfied vacuously — there is no breaking schema change).
- The authoritative spec to update is `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`
  (prompt-construction contract + the `streamChat` tool-policy argument), NOT
  `curator_schema/SCHEMA.md` or `system_behavior/SYSTEM_BEHAVIOR.md` unless the
  MCP tool-exposure contract is described there.
- **v0.19.0 is a minor line bump** → per the spec-line-sync rule, the
  `(vX.Y.Z)` suffix in all four `docs/specs/*` titles must move to `v0.19`.
  `backend/tests/test_spec_sync.py` will enforce this even though the change is
  plugin-only.

### S2 — Guard against re-introducing duplication
Add a guard test (or lint) asserting `quickQueryContext.ts` imports its boundary
text from the shared registry rather than re-declaring a "no filesystem access"
literal. Otherwise the duplication silently regrows in a future edit.

## source_pair_analyst — RAG / L1–L4 impact

### R1 — Incurator MCP usage path must stay intact for sidechat
`EXTERNAL_INCURATOR_MCP_ADDENDUM` instructs the agent to call
`curator_check_workspace` / `curator_query` / `curator_fetch_context`. The
registry refactor must keep this block ON the sidechat auto-tool path. The
popover's `toolPolicy: "none"` correctly means the popover will NOT run
`curator_query` — confirm this is desired: the popover is a pure reading
assistant over the SELECTED passage + current page, never a RAG synthesis
surface. (Agreed: popover answers from injected context only; RAG belongs to
sidechat / `wiki query`.)

### R2 — Provenance / source-trace untouched
v0.18.0's `db.sources_for_spans` and the Sources & Trace panel are backend +
sidechat features. The popover does not promote or cite DAG nodes, so this work
does not regress the v0.18.0 source-trace contract. No action needed beyond a
note that popover answers carry no source trace by design.

### R3 — Recency anchor vs. resolved cross-references
The popover already resolves POINTER selections via
`<resolved_cross_references>` (`pdfReferenceContext.ts`). The recency anchor's
"answer ONLY about the primary selection" line must NOT override the existing
"when the selection is a pointer, answer about the referenced TARGET" rule.
Anchor wording must defer to the pointer rule (e.g. "answer ONLY about the
primary selection or, if it is a pointer, its resolved target").

## Consensus asks to the synthesizer
1. Drop "mathematical sandbox" claim; scope F2 to popover-zero-tools + prompt
   boundary; document the external-MCP caveat.
2. Anchor: separate trailing block, `allowEdits`-gated, pointer-rule-aware.
3. Update `PLUGIN_SCHEMA.md` + bump all four spec titles to `v0.19`.
4. Add anti-duplication guard test.
5. No DB migration; no backend logic change.
