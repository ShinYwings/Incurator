# Diagnosis: G10-config-runtime
Coverage: `backend/src/curator/config.py`, `backend/src/curator/constants.py`, `backend/src/curator/runtime_state.py`, `backend/src/curator/secret_store.py`, `backend/src/curator/device_registry.py`, `backend/src/curator/git_manager.py`; caller/test/doc context read from `backend/tests/test_config_machine_local.py`, `backend/tests/test_runtime_state.py`, `backend/tests/test_v021_device_registry.py`, `backend/tests/test_git_manager.py`, `backend/tests/test_cli_deepseek_config.py`, `backend/tests/test_deepseek_provider.py`, `backend/src/curator/cli.py`, `plugin/src/utils/deviceRegistry.ts`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`, `docs/guides/USER_GUIDE.md`, `docs/guides/MCP_USER_GUIDE.md`, `docs/guides/PLUGIN_GUIDE.md`, and ignore templates.

## Findings

### [G10-1] (a,h,i,e) S2 — Device registry is global but keyed by no vault identity
- Loc: `backend/src/curator/device_registry.py:239`, `backend/src/curator/device_registry.py:244`, `backend/src/curator/device_registry.py:260`, `backend/src/curator/device_registry.py:267`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:861`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:867`, `docs/guides/PLUGIN_GUIDE.md:977`
- Evidence: `registry_path(vault_root)` ignores `vault_root` and always returns `cfg.get_global_config_dir() / devices.json`. `sync_device_registry(vault_root, ...)` then overwrites the same singleton with Syncthing folders for whichever vault was synced last. The spec/guide describe the registry as metadata for the current/active vault's Syncthing shared-folder registry, but the persisted shape has no `vault_root`, `vault_id`, or per-vault namespace.
- Fix sketch: Decide whether `.cache/config/devices.json` is a single active-vault cache or durable multi-vault registry. For stability, prefer a top-level map keyed by normalized vault root hash or a `devices.<vault-hash>.json` file, and include `vault_root`/`vault_id` in the payload. Update plugin `getGlobalRegistryPath` and backend tests to prove two vaults do not clobber each other.
- Blast radius: `wiki devices sync/status`, plugin startup registry refresh, dashboard Overview device list, per-device backend launcher/repo path fallback.
- Suggested PR: `fix/device-registry-vault-scope`

### [G10-2] (a,e,h) S2 — Config loading uses shallow nested merges and can drop sibling defaults
- Loc: `backend/src/curator/config.py:397`, `backend/src/curator/config.py:403`, `backend/src/curator/config.py:424`, `backend/src/curator/config.py:481`, `backend/src/curator/config.py:488`, `backend/tests/test_config_machine_local.py:34`
- Evidence: `load_config` deep-copies `DEFAULT_CONFIG`, but both global and vault config merges use `{**merged[key], **val}` for only one level. A partial nested block such as `search.chunking.target_tokens` replaces the whole `chunking` dict and loses `max_tokens`, `overlap_tokens`, and `min_tokens`; a partial `llm.deepseek-api.api_key_secret` can replace default `base_url`, `api_key_env`, and `timeout`. `save_global_config` already has a recursive merge helper, so load/save semantics differ.
- Fix sketch: Promote one recursive deep-merge helper and use it for global config, vault config, and save-time global merges. Add tests for partial nested overrides under `search.chunking`, `llm.deepseek-api`, and `external.zotero`.
- Blast radius: LLM provider config, search chunking/model defaults, Zotero roots, plugin dashboard config display, MCP tools that read machine-local config.
- Suggested PR: `fix/config-deep-merge`

### [G10-3] (a,h) S2 — Runtime status snapshots expose the full LLM config without redaction
- Loc: `backend/src/curator/runtime_state.py:318`, `backend/src/curator/runtime_state.py:340`, `backend/src/curator/config.py:447`, `backend/src/curator/config.py:456`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:571`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:573`
- Evidence: `build_status_snapshot` copies `config.get("llm", {})` verbatim into `status.json`. `_migrate_llm_config` strips old top-level fields but does not remove legacy nested `llm.deepseek-api.api_key`; the system behavior spec still allows legacy plaintext API keys while requiring newly stored secrets to stay outside shared config. If a legacy plaintext key exists, `write_runtime_snapshots` persists it to `.curator/runtime/status.json`.
- Fix sketch: Add a redaction helper for runtime/plugin-facing config snapshots. Remove or mask keys named `api_key`, `api_key_secret`, `token`, `secret`, and similar sensitive leaves before writing/returning status. Keep non-sensitive provider/model fields so the dashboard still works. Add a regression test with legacy `llm.deepseek-api.api_key`.
- Blast radius: Plugin dashboard LLM card, `wiki status --json`, runtime snapshot cache, DeepSeek provider migration.
- Suggested PR: `fix/runtime-status-redact-secrets`

### [G10-4] (a,c,i) S2 — Missing `git` is not a structured public error
- Loc: `backend/src/curator/git_manager.py:16`, `backend/src/curator/git_manager.py:262`, `backend/src/curator/git_manager.py:268`, `backend/src/curator/git_manager.py:280`, `backend/src/curator/git_manager.py:287`, `backend/src/curator/cli.py:6207`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:1549`
- Evidence: `_run` and `_git_bytes` raise `FileNotFoundError("git")` when `git` is absent. Public methods such as `status()` do not catch this; hidden CLI commands catch broad exceptions and return `{"ok": false, "error": "git"}` without the contract-style blocker. The spec says git push/status paths should refuse missing git as a safe structured state.
- Fix sketch: Add a `_missing_git()` response and have public methods check `shutil.which("git")` once before calling subprocesses. Return `error: "missing_git"` plus a user-facing message from status/log/diff/history/push/commit. Add tests by monkeypatching `shutil.which` to `None` rather than skipping when git is absent.
- Blast radius: Plugin sidechat Git status/history/push/commit commands and user-facing blocker messages.
- Suggested PR: `fix/git-manager-missing-git-contract`

### [G10-5] (c,h) S2 — Config, secret, and registry writes are uncoordinated read-modify-write operations
- Loc: `backend/src/curator/config.py:315`, `backend/src/curator/config.py:321`, `backend/src/curator/config.py:339`, `backend/src/curator/config.py:340`, `backend/src/curator/config.py:481`, `backend/src/curator/config.py:493`, `backend/src/curator/secret_store.py:61`, `backend/src/curator/secret_store.py:63`, `backend/src/curator/device_registry.py:260`, `backend/src/curator/device_registry.py:263`, `backend/src/curator/runtime_state.py:40`
- Evidence: Runtime snapshots use an atomic temp-file replace, but the other machine-local state files do not. `save_global_config` reads, recursively merges, and writes `config.yml` directly; `save_config` writes `settings.yml` directly; `_write_store` writes `secrets.json` directly; `write_registry` writes `devices.json` directly. Concurrent plugin startup, `wiki config provider`, `wiki config set`, and `wiki devices sync` can lose updates or leave truncated JSON/YAML on process interruption.
- Fix sketch: Reuse an atomic write helper for YAML/JSON state and add a per-file lock around read-modify-write sections. Keep lock scope small and local to `.cache/config/*.lock` / `.curator/*.lock`. Add tests that simulate interrupted writes and adjacent key updates.
- Blast radius: Provider settings, model/search paths, Zotero roots, encrypted secret references, device launchers, runtime dashboard consistency.
- Suggested PR: `fix/local-state-atomic-writes`

### [G10-6] (c,h,i) S3 — Device registry parsing failures can crash the repair/status path
- Loc: `backend/src/curator/device_registry.py:42`, `backend/src/curator/device_registry.py:54`, `backend/src/curator/device_registry.py:68`, `backend/src/curator/device_registry.py:74`, `backend/src/curator/device_registry.py:278`, `backend/src/curator/device_registry.py:279`, `backend/src/curator/device_registry.py:285`, `backend/src/curator/cli.py:3558`
- Evidence: `read_syncthing_status` treats malformed/unavailable GUI state as best-effort, but `sync_device_registry` calls `parse_syncthing_config` without catching `ET.ParseError`, and `parse_args_text` can raise `ValueError` for malformed shell text. A bad `config.xml` or typo in `--backend-args` turns the manual repair command into an exception instead of a structured "unknown/unavailable" device state.
- Fix sketch: Catch XML/argument parse errors at the device-registry boundary, preserve the previous registry when available, and record `syncthing.error` / `backend_args_error` in the returned payload. Add tests for malformed XML and unmatched quotes.
- Blast radius: `wiki devices sync`, plugin startup device refresh parity, dashboard device Overview, supportability when Syncthing is partially configured.
- Suggested PR: `fix/device-registry-error-states`

### [G10-7] (g,i) S3 — Runtime status refresh does repeated full scans on the dashboard hot path
- Loc: `backend/src/curator/runtime_state.py:47`, `backend/src/curator/runtime_state.py:53`, `backend/src/curator/runtime_state.py:177`, `backend/src/curator/runtime_state.py:264`, `backend/src/curator/runtime_state.py:337`, `backend/src/curator/runtime_state.py:338`, `backend/src/curator/runtime_state.py:339`, `backend/src/curator/ingest_raw.py:2317`, `backend/src/curator/ingest_raw.py:2328`
- Evidence: `build_status_snapshot` recursively counts all files under every raw dir and calls `build_jobs_snapshot`; `write_runtime_snapshots` then calls `build_jobs_snapshot` again. `build_sources_snapshot` loads every source row via `ingest_raw.list_sources`, reverses the full list, and only then applies the display limit. Large `04_Resources/` trees or large source registries can make `wiki status`, plugin refresh, and dashboard load slow.
- Fix sketch: Query aggregate counts from `state.sqlite` when possible, fall back to bounded filesystem scans only before DB initialization, add a `list_sources(limit, order="desc")` DB helper, and pass the already-built jobs payload through status/write calls instead of recomputing it.
- Blast radius: `wiki status --json`, plugin dashboard Overview/Sources/Jobs, background worker status refreshes.
- Suggested PR: `perf/runtime-snapshot-bounded-refresh`

### [G10-8] (c,h) S3 — Config and secret readers silently downgrade corruption to defaults/empty stores
- Loc: `backend/src/curator/config.py:323`, `backend/src/curator/config.py:328`, `backend/src/curator/config.py:348`, `backend/src/curator/config.py:352`, `backend/src/curator/config.py:414`, `backend/src/curator/config.py:436`, `backend/src/curator/secret_store.py:54`, `backend/src/curator/secret_store.py:56`, `backend/src/curator/secret_store.py:86`, `backend/src/curator/secret_store.py:89`
- Evidence: Several config paths catch broad exceptions and either `pass` or continue with defaults; `_read_store` returns `{}` for unreadable/corrupt `secrets.json`; `get_secret` returns `""` for any decrypt/read failure. The next successful write can overwrite the evidence of corruption with an empty or partial store, leaving users with provider failures but no clear cause.
- Fix sketch: Preserve fail-open behavior for normal commands but emit structured warnings and quarantine corrupt files to `*.corrupt.<timestamp>` before rewriting. Narrow exception handling where possible. Add a health/status warning so the dashboard can show "local config unreadable" or "secret store locked/corrupt".
- Blast radius: Provider setup, DeepSeek auth, last-root resolution, dashboard LLM/account status, supportability after partial writes or permission changes.
- Suggested PR: `fix/config-secret-corruption-diagnostics`

### [G10-9] (b,e) S3 — File-name constants have duplicate aliases with unclear ownership
- Loc: `backend/src/curator/constants.py:14`, `backend/src/curator/constants.py:18`, `backend/src/curator/constants.py:21`, `backend/src/curator/constants.py:59`, `backend/src/curator/constants.py:60`, `backend/src/curator/constants.py:63`, `backend/src/curator/config.py:126`, `backend/src/curator/lint.py:141`
- Evidence: `constants.py` defines both `FILE_INDEX_MD` and `INDEX_FILE`, `FILE_OVERVIEW_MD` and `OVERVIEW_FILE`, `FILE_LOG_MD` and `LOG_FILE`, `FILE_LEDGER_MD` and `LEDGER_FILE`, plus `FILE_SETTINGS_YML` and `SETTINGS_FILE` for the same literal values. Callers split across both naming families. This is low-risk today but increases accidental drift and makes future file-layout changes harder to audit.
- Fix sketch: Pick one naming convention per file class, migrate callers in one mechanical PR, and leave temporary aliases only if needed for an immediate deprecation window. Add a small constants smoke test for unique semantic values where duplication is intentional.
- Blast radius: Path construction, lint noise-page filtering, CLI init template selection, docs/spec references.
- Suggested PR: `chore/constants-file-name-canonicalization`

### [G10-10] (d,e) S3 — Legacy compatibility surfaces remain embedded in live config paths
- Loc: `backend/src/curator/config.py:90`, `backend/src/curator/config.py:447`, `backend/src/curator/config.py:456`, `backend/src/curator/lint.py:1176`, `backend/src/curator/lint.py:1291`, `backend/src/curator/cli.py:5599`
- Evidence: `WikiPaths.wiki` is explicitly documented as a backward-compatible alias and is still used by lint code; `_migrate_llm_config` strips many obsolete provider fields on every load; a CLI docstring still references old keys such as `claude_model`/`antigravity_model`. The project contract says legacy cleanup is in scope and no backward-compat shims should remain without an explicit reason.
- Fix sketch: Replace remaining `paths.wiki` callers with `paths.collections`, then remove the alias in the same PR if no external API depends on it. Convert obsolete LLM scrubbers into one documented migration/test path or remove them if current configs no longer need them. Update stale docstrings.
- Blast radius: Lint path resolution, config migration behavior, developer understanding of current provider schema.
- Suggested PR: `chore/remove-config-legacy-aliases`

### [G10-11] (f,i) S3 — Config storage docs disagree with the implementation and each other
- Loc: `backend/src/curator/config.py:309`, `backend/src/curator/config.py:367`, `backend/src/curator/config.py:481`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:949`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:954`, `docs/guides/USER_GUIDE.md:740`, `docs/guides/USER_GUIDE.md:742`, `docs/guides/USER_GUIDE.md:794`, `docs/guides/MCP_USER_GUIDE.md:137`
- Evidence: The system spec and much of the user guide say machine-local `llm`, `search`, and `external` live in `.cache/config/config.yml`, matching `MACHINE_LOCAL_CONFIG_KEYS` and `save_config`. But the User Guide later says `llm.primary_effort` / `llm.fallback_effort` are stored in `.curator/settings.yml`, and the MCP guide still points external resources at `~/.config/curator/config.yml`. `get_global_config_dir` also calls the path "project-local config directory (originally global)", which reflects the transition but leaves stale public docs.
- Fix sketch: Make `.cache/config/config.yml` vs `.curator/settings.yml` wording consistent across EN/KR guides and MCP guide. State whether "global" means repo-local project cache or OS-user config. Add doc tests or spec-sync grep checks for the old `~/.config/curator/config.yml` location if it is no longer valid.
- Blast radius: User setup expectations, plugin dashboard provider settings, external/Zotero root configuration, support docs.
- Suggested PR: `docs/config-storage-parity`

## Positives (keep / do-not-break)
- `WikiPaths` centralizes vault paths and keeps `.curator/Collections/` layer paths explicit.
- `save_config` already separates machine-local `llm`, `search`, and `external` blocks from portable vault settings, and `test_config_machine_local.py` covers migration out of `.curator/settings.yml`.
- Runtime snapshot writes use temp-file + `os.replace`, which is the right pattern to preserve for other local-state files.
- `GitManager` has useful guardrails for no repository, no upstream, conflicted worktrees, behind/diverged branches, and path-outside-vault history requests.
- `device_registry.sync_device_registry` preserves remote backend launcher profiles for devices still present in Syncthing and avoids fabricating `local` when Syncthing reports real devices but the local device cannot be identified.
- `secret_store` avoids storing new raw DeepSeek keys in YAML config and uses Fernet plus owner-only chmod for key/store files.

## Open questions for the human
- Should `.cache/config/config.yml` and `.cache/config/devices.json` remain repo-local for all installs, or should packaged installs use an OS-user config directory? Current docs still mention both models.
- Is `devices.json` intended to represent exactly one active vault, or should it support multiple synced vaults on the same machine?
- Should runtime status expose any raw config at all, or should the plugin get a deliberately redacted dashboard config contract?
- Are `paths.raw_dirs` and `paths.collections_dir` still supported user-facing overrides, or should Curator state be hard-constrained to `.curator/` for stability?
- Can the remaining `paths.wiki` alias be removed in Phase A, or is it part of an external/plugin API surface that needs a deprecation note first?
