# Critique on the --asset-dir + "Added" badge proposal

Date: 2026-06-11 | Agent Persona: red_teamer (+ schema_guardian / source_pair_analyst)

## 1. Vulnerabilities & Flaws

### R1 — Path traversal / vault escape via `--asset-dir`
A crafted or mis-typed `--asset-dir` (`../../etc`, `/abs/path`) could write images
outside the vault. **Resolution:** `_safe_vault_subdir` must `Path(asset_dir)`-join
under `paths.root`, `resolve()`, and assert the result is within `paths.root`
(`os.path.commonpath`); on violation fall back to `05_Assets` and log. Tested with
`..`, absolute, and empty inputs.

### R2 — Embedded image path must match where the file was written
If `_save_pdf_images` writes to `<asset_dir>/<slug>/` but the L1 `![[...]]` embed is
still computed as `05_Assets/<slug>/`, images break. **Resolution:** derive the
`obsidian_path` from the SAME resolved root used for writing (single source of
truth). Test asserts the returned `obsidian_path` prefix equals the write dir.

### R3 — "Added" must not hide a stale/moved/changed source (data-staleness trap)
If we map too many states to a non-clickable "Added", a source that later moves or
its hash drifts would look "Added" and the user couldn't re-bind. **Resolution:**
ONLY `l1_ready/l2_ready/l3_ready/l4_ready/ready` map to "Added"; the status refresh
(`refreshIncuratorStatus`, polling) re-derives state, so `stale/moved/hash_drift`
flip the badge back to its clickable actionable label. Test the label map per state.

### R4 — `l1_ready` is "Added" but L2/L3 still building — misleading "done"?
"Added" at `l1_ready` is correct (the source IS tracked/ingested), but L2/L3 may be
queued/running. **Resolution:** acceptable per user intent ("added = 들어갔으면");
optionally render a subtle layer hint (e.g. "Added · L1") — but keep the click
disabled. Do NOT block on full L4.

### R5 (schema_guardian) — `--asset-dir` is a new plugin-API contract
`wiki plugin source import --asset-dir` is a new hidden-CLI argument. It must be
documented in PLUGIN_SCHEMA §1 command list and default to None (older plugin →
omits it → backend unchanged; newer plugin + older backend → argparse must not hard
fail, so the backend adds the optional arg before the plugin sends it, or the plugin
feature-detects). **Resolution:** ship backend arg first within the same release;
both are in one repo/version, so no cross-version skew in practice.

### R6 (source_pair_analyst) — No L1–L4 provenance change
Asset routing only changes WHERE the binary lands and the `obsidian_path` string in
L1; `source_spans`, knowledge_units, and the DAG are unaffected. Image embeds are
already non-authoritative display metadata. ✅ no backprop/provenance impact.

### R7 — Slug collisions across different source folders
Two PDFs with the same stem under different asset dirs now share `<asset_dir>/<slug>`
only if asset_dir is identical; with per-profile dirs collisions shrink, but within
one dir the existing slug behavior is unchanged. Acceptable (pre-existing behavior).

## 2. Adjustments folded into the Master Plan

1. `_safe_vault_subdir` with traversal/abs/empty guards + fallback (R1) — tested.
2. `obsidian_path` derived from the actual write root (R2) — tested.
3. Exactly the 5 ready/built states → "Added"; refresh re-derives staleness (R3) —
   label-map test per state.
4. Backend `--asset-dir` (default None) shipped with the plugin in one release (R5).
5. Optional "Added · L1" layer hint is a nicety, not required; click stays disabled.
