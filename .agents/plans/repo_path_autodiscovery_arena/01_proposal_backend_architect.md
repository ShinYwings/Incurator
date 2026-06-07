# Backend Proposal: repo_path detection + JSON surface

Date: 2026-06-07 | Agent Persona: Backend Architect

## 1. Core Logic & Implementation

### repo_path detection (verified working)

```python
# device_registry.py — new helper
def detect_repo_root() -> str | None:
    """Return the Incurator repo root if running from an editable/source
    checkout, else None (regular site-packages install with no repo to update)."""
    backend_root = Path(__file__).resolve().parents[2]   # .../Incurator/backend
    repo_root = backend_root.parent                        # .../Incurator
    # Proof markers: a repo we can actually run setup.sh + copy plugin from
    markers = (repo_root / "setup.sh", repo_root / "plugin" / "manifest.json")
    if all(m.exists() for m in markers):
        return str(repo_root)
    return None
```

Verified on this machine:
- `curator.__file__` = `.../Incurator/backend/src/curator/__init__.py`
- `parents[2]` = `.../Incurator/backend`, `.parent` = `.../Incurator`
- `setup.sh`, `.git`, `plugin/main.js` all present → returns the repo root
- A `pip install incurator` (no -e) would land in site-packages, markers absent → None

I deliberately do NOT require `.git` — a tarball checkout without git history
should still be updatable as long as `setup.sh` + `plugin/` exist. `.git` is too
strict.

### JSON surface

Add `repo_path` to `backend_launcher()` output (already in `devices.json`):

```python
def backend_launcher(command=None, args=None) -> dict[str, Any]:
    backend_root = Path(__file__).resolve().parents[2]
    ...
    return {
        "command": command,
        "args": args,
        "backend_root": str(backend_root),
        "repo_path": detect_repo_root(),   # NEW — null when not a repo
        "uv_fallback": {...},
    }
```

ALSO expose it in `wiki plugin version` JSON (the call the plugin already makes
to compute `needsUpdate`), so the plugin gets it on the same round-trip:

```python
# cli.py plugin version command
_print_json({
    "ok": True,
    "version": __version__,
    "repo_path": device_registry.detect_repo_root(),   # NEW
    "build": build,
})
```

## 2. Pros & Cons

**Pros:**
- Zero new dependencies, pure stdlib `pathlib`.
- `__file__` is authoritative — no guessing, no user input.
- Editable-install detection is a natural byproduct (markers absent → None).
- Rides existing surfaces (`devices.json` backend block + `plugin version` JSON).

**Cons:**
- If a user has a weird layout (backend installed -e from a path where the
  sibling `plugin/` was deleted), markers fail → None. Acceptable: that's not a
  vault we can safely update anyway.
- `wiki plugin version` and `devices.json` now both carry `repo_path` — minor
  duplication. Mitigation: `devices.json` is the cache, `plugin version` is the
  live truth; plugin prefers live and writes through to cache.
