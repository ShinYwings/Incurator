# Critique on Backend + Plugin Proposals

Date: 2026-06-07 | Agent Persona: Edge-Case / Security Auditor

## 1. Vulnerabilities & Flaws

### F1 — `wiki plugin version` must NOT require a vault
The plugin calls `wiki plugin version` to compute `needsUpdate`. If
`detect_repo_root()` or the version command path now touches
`_resolve_root_or_die()` or `load_config()`, it will crash when run outside a
vault (e.g. before a vault is selected, or in the update-check phase). The
version+repo_path command MUST be vault-independent — it only reads `__file__`
and `__version__`. **Verify the version command does not resolve a vault.**

### F2 — Symlinks and `parents[N]` fragility
`Path(__file__).resolve().parents[2]` assumes the source layout
`backend/src/curator/__init__.py`. `.resolve()` follows symlinks — if someone
symlinks the curator package into site-packages, `.resolve()` correctly lands on
the real source. Good. But if the layout ever changes (e.g. `src/` flattened),
the index breaks silently. **Mitigation:** detect_repo_root() must validate
markers (setup.sh + plugin/manifest.json) and return None on mismatch rather than
returning a wrong path. The backend_architect proposal already does this — keep it.

### F3 — repo_path could still leak if cached wrong
The plugin caches repo_path into `devices.json`. `devices.json` lives in the
GLOBAL cache (`.cache/config/devices.json`), which is per-device and NOT synced.
Confirmed safe. BUT: double-check `devices.json` is genuinely outside the synced
vault tree and in `.stignore` if it ever sits under `.curator/`. (It moved to
global cache in v0.4.1 — verify it stays there.)

### F4 — Override field that "looks empty but isn't"
The plugin_expert UX shows the detected path as a placeholder. If a user types
then clears the field, an empty string must mean "use backend answer", not
"override with empty". `settings.incuratorRepoPath?.trim() || ...` handles this
(empty string is falsy). Keep the `.trim()`.

### F5 — Cross-device update correctness
Scenario: device A (Linux) and device B (macOS) share a vault via Syncthing.
User runs `./setup.sh` on device A. Device B's Obsidian still shows old plugin.
With "current vault only" scope, device B updates ONLY when its OWN backend is
updated and its OWN Obsidian reopens. This is CORRECT — you must not copy device
A's Linux-built `main.js` onto device B (it's the same JS, but the trigger must
be device B's own backend version bump). **The update is driven by each device's
local backend_version vs the plugin's bundled manifest — not by a synced flag.**
This is already how needsUpdate works. Confirm no synced "update needed" flag.

## 2. Suggested Alternatives

- **A1 (F1):** Make `detect_repo_root()` a pure function in `device_registry.py`
  with NO config/vault imports. Add a test that calls `wiki plugin version` with
  `cwd` set to a non-vault temp dir and asserts exit 0 + valid JSON + repo_path key.
- **A2 (F2):** Keep marker validation strict (setup.sh AND plugin/manifest.json).
  Add a unit test for detect_repo_root() that monkeypatches `__file__`-derived
  root to a temp dir with/without markers.
- **A3 (F5):** Add an explicit test/assertion that no `repo_path` or
  `needs_update` value is ever written into `.curator/` (synced). Only
  `.cache/config/devices.json` (global) and plugin `data.json` (.stignore'd).
