# Critique on the Architecture Proposal

Date: 2026-06-29 | Agent Persona: schema_guardian (The Validator)

## 1. Contract / Spec Integrity Concerns

### S1 — §26.2a is a hard contract, not prose; the rewrite must be surgical
SYSTEM_BEHAVIOR §26.2a "Interactive routing" explicitly says the Cmd+Shift+X crop
path MUST call the backend transcribe resolver and MUST NOT attach the crop image
to the main chat model's vision path. This plan inverts BOTH clauses for the
vision-capable case. The rewrite MUST:
- Scope the inversion to the **chat snip path only**. The sentence binding
  `latex_extract_model` to "interactive surfaces (Cmd+Shift+X snip, Convert-to-
  LaTeX)" must be edited to drop the snip and keep Convert-to-LaTeX.
- Preserve every other §26.2a clause verbatim (ingest always-on, resolver
  discipline, raise-on-failure, cache invalidation, cost rail, temp-png cleanup).
- State the new decision rule (`modelSupportsVision(mainModel)` → direct vs
  transcribe) and the scoped-Read grant for image turns.

### S2 — No DB/SCHEMA change → SCHEMA.md must NOT be touched for behavior
This is a plugin transport/routing change. There is NO new node prefix, no
frontmatter change, no DB column. `docs/specs/curator_schema/SCHEMA.md` content
stays as-is. Do not invent schema artifacts.

### S3 — PLUGIN_SCHEMA must document the new image-channel contract
`docs/specs/plugin_schema/PLUGIN_SCHEMA.md` is the plugin API contract. It must
record: (a) chat image parts are written to `<repo>/.cache/cli/chat_images/<run>`
and referenced by path; (b) image-bearing CLI turns enable scoped `Read` +
`--add-dir <imagedir>` (denylist-minus-Read, not allowlist, to preserve MCP); (c)
text-only turns keep the hardened no-Read denylist; (d) the `ContextRef`
`pendingCropBase64` lifecycle change (kept-as-image vs transcribed by
`modelSupportsVision`).

### S4 — Minor bump ⇒ MANDATORY spec-title sync (test_spec_sync gate)
v0.27.x → v0.28.0 crosses the MAJOR.MINOR line. Per CLAUDE.md Step 10 +
`backend/tests/test_spec_sync.py`, ALL FOUR static spec titles must bump to the new
`vX.Y` line:
- `docs/specs/curator_schema/SCHEMA.md`
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`
- `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`
- `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`
…AND all three build manifests (`backend/pyproject.toml`, `plugin/package.json`,
`plugin/manifest.json`) must agree on `0.28.0`. The CI `version-consistency` job
blocks otherwise. (Also bump `plugin/package-lock.json` — currently the only dirty
file, already at 0.27.9, will need 0.28.0.)

### S5 — Convert-to-LaTeX / ingest invariants must be provably untouched
`externalPdfView.ts:1336` (`transcribePdfRegion({text})`) and `add source`
(`vision_model` page-VLM) must keep calling the backend resolver. Add a guard test
asserting the Convert-to-LaTeX call site is unchanged so the snip change does not
bleed into it.

### S6 — KR/EN guide parity
Any guide touched (PLUGIN_GUIDE, the PDF/LaTeX workflow sections) must update the
English source first, then the `_KR.md` faithfully — same commit.

## 2. Suggested Alternatives / Required Guards

1. **§26.2a edit is additive-surgical** (S1): invert only the two snip clauses;
   keep the rest. Add a dated "v0.28.0" note rather than deleting the v0.23.0
   history of the section.
2. **Four-spec-title + manifest + lockfile bump as one release commit** (S4).
3. **Regression guard for Convert-to-LaTeX + ingest** (S5).
4. **PLUGIN_SCHEMA gains an "Interactive image channel" subsection** (S3).
5. **No SCHEMA.md behavior edit** (S2) — title-line version bump only.
