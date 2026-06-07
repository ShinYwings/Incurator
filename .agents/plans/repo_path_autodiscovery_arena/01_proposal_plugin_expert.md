# Plugin Proposal: repo_path resolution + settings UX

Date: 2026-06-07 | Agent Persona: Plugin/Frontend Expert

## 1. Core Logic & Implementation

### Resolution precedence (repo path)

```
1. settings.incuratorRepoPath        — explicit user override (if non-empty)
2. backend-reported repo_path         — from `wiki plugin version` JSON, live
3. devices.json backend.repo_path     — cached from last successful backend call
4. null                               — no repo → update disabled
```

The plugin already follows this exact pattern for `backendCommand`
(settings → devices.json cache → auto-discover → "wiki"). We mirror it for repo path.

### Wiring into the existing version check

`incuratorClient.checkBackendVersion()` already calls `wiki plugin version` and
reads `result.version`. Extend it to also capture `result.repo_path`:

```typescript
// incuratorClient.ts
public repoPath: string | null = null;
...
const result = await this.callBackendJson(["plugin", "version"]);
this.backendVersion = readString(result, "version");
this.repoPath = readString(result, "repo_path") || null;   // NEW
```

Then `main.ts` caches it to devices.json (same place backendCommand is cached)
so a later offline session still knows where the repo is.

### updateIncuratorBackend() change

```typescript
async updateIncuratorBackend() {
  const repoPath =
    this.settings.incuratorRepoPath?.trim() ||   // explicit override
    this.incuratorClient?.repoPath ||            // live backend answer
    getLocalBackendRepoPath(registry);           // cached fallback
  if (!repoPath) {
    new Notice("This backend is not an editable install — nothing to update from.");
    return;
  }
  // ... existing copy logic (copies into getBasePath() vault) unchanged
}
```

### Settings UX

Change the "Repository path" field from a required input to an **optional
override** with an auto-detected hint:

```
Repository path  (advanced)
Auto-detected from backend: /home/shin/Workspace/Incurator
Leave blank to use the backend's reported path. Set only to override.
[ <empty placeholder showing detected value> ]
```

And gate the update toast: only show "Update available" when
`needsUpdate && repoPath != null`. A site-packages user sees a version mismatch
note but no broken update button.

## 2. Pros & Cons

**Pros:**
- Reuses the exact precedence pattern already proven for `backendCommand`.
- Manual field becomes optional → fresh device needs zero config.
- Update button auto-hides for non-repo installs → no more dead button.
- `data.json` already .stignore'd, so override stays device-local.

**Cons:**
- `incuratorClient.repoPath` is only populated after the first
  `checkBackendVersion()` round-trip. Before that, falls back to devices.json
  cache or override. Acceptable — version check runs on load.
- Slight risk a stale devices.json cache points at a moved repo. Mitigation:
  live `plugin version` answer always wins over the cache.
