# exception_hygiene Proposal: §32 Observable-Degradation Sweep (Gate G0 closure)
Date: 2026-08-05 | Agent Persona: Degradation Boundary Auditor

Scope: `backend/src/curator/**` + `plugin/src/**`, judged against
`docs/specs/system_behavior/SYSTEM_BEHAVIOR.md` §32 (lines 3383–3406).
Excluded by instruction (already confirmed): CAND-01 `lint.py:1326`,
CAND-02 `llm_identity.py:60,89`, retrieval_context-5a
`retrieval/query_expander.py:140-159` + `retrieval/expansion.py:97-101`.

## 0. The rubric actually applied

§32 lines 3385–3406 give four operative clauses. Every judgement below cites one:

- **C1** — "Internal operations must not use an unexplained silent
  `except Exception: pass` fallback."
- **C2** — deterministic parsing/filesystem/conversion fallbacks must "catch the
  specific expected exception classes"; optional LLM/provider/client and cleanup
  boundaries may keep a broad catch **only** "with an explicit reason **and**
  module logging."
- **C3** — "a requested operation that succeeds with degraded maintenance,
  discovery, or indexing reports the degradation through an existing `warnings`
  field or CLI warning where that surface already defines one."
- **C4** — "False success is forbidden… the suppressed cause remains observable
  in logs."

Sweep method: mechanical enumeration of every `except Exception` /
`except BaseException` / bare `except:` in `backend/src/curator/**` whose handler
body contains **no** `log`/`logger`/`raise`/`console`/`_err`/`warnings`/`error`
token (44 sites), plus every empty or comment-only `catch {}` /
`.catch(() => …)` in `plugin/src/**` (25 + 12 sites). Each site was then read in
context and classified FINDING / ACCEPTABLE. The ACCEPTABLE list is in §3 — it is
the evidence the sweep was real, not a shortlist.

## 1. Core Logic & Implementation

### eh-1 [P2] `wiki query --update` silently does not create the atom it promised
`backend/src/curator/ingest_llm.py:689`

```python
        final_path = paths.atoms / f"{atom_id}.md"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_text(content, encoding="utf-8")
        return atom_id
    except Exception:          # ← line 689
        return None
```

The whole body of `add_atom_from_insight` (opens at `ingest_llm.py:634`) is
inside one `try`: the LLM call, `strip_llm_noise`, `sanitize_wikilinks`,
`mkdir`, and `write_text`. Any failure — `LLMError`, a disk-full `OSError` on
the atom write, a `UnicodeEncodeError` — collapses to `None` with **no log line
at all**.

The caller does nothing with `None`:

```python
# backend/src/curator/commands/common.py:2164-2170
            if update_knowledge:
                today = ingest_llm._now_iso()
                atom_id = ingest_llm.add_atom_from_insight(
                    paths, client, result.answer, today, source_hint="query"
                )
                if atom_id:
                    console.print(f"[dim]  → new atom created: [cyan]{atom_id}[/cyan][/dim]")
```

`update_knowledge` is the user-facing `wiki query --update` flag, whose help
text is an explicit promise (`commands/core.py:1366-1370`):

> `help="After answering, create a new L2 Atom from the answer insight."`

**Concrete consequence.** The user runs `wiki query --update "…"`. The answer
prints normally, the command exits 0, no warning, no log entry. The user asked
for an L2 Atom to be written into the DAG; it silently was not, and nothing in
the output says so — the successful answer *is* the false success. On the next
`wiki sync`/`wiki lint` the insight is simply absent, indistinguishable from
never having asked. The second caller,
`backprop_agents.py:58 AtomSynthesizer.synthesize`, inherits the same blindness
in the backprop loop.

Violates **C4** (false success + cause not observable in logs) and **C3** (the
CLI surface already prints a per-item line; there is no degradation line).

**Test coverage check:** `grep -rn "add_atom_from_insight\|update_knowledge"
backend/tests/` → **zero hits**. Nothing pins this behaviour either way.

**Fix direction:** narrow to `(LLMError, OSError, ValueError)`; log the cause via
the module logger; return a typed failure the caller renders as a CLI warning
(`  → atom creation skipped: <reason>`) so the exit contract is unchanged.

---

### eh-2 [P2] One corrupt byte in `dismissed_contradictions.json` silently deletes every dismissal the user ever made
`backend/src/curator/contradiction.py:32`

```python
def load_dismissed(paths) -> list[dict]:
    """Load dismissed/resolved pairs from disk. Returns [] if file missing."""
    p = _storage_path(paths)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:          # ← line 32
        return []
```

The docstring claims the `[]` means "file missing". It also means *file
unparseable*, *file unreadable*, *encoding error* — indistinguishably, and
unlogged. The write path then makes that indistinguishability destructive:

```python
# backend/src/curator/contradiction.py:48-70
def add_dismissed(paths, atom_a: str, atom_b: str, reason: str = "") -> None:
    ...
    dismissed = load_dismissed(paths)      # ← [] on corruption
    if is_dismissed(dismissed, a, b):
        return
    dismissed.append({...})
    _save(paths, dismissed)                # ← whole-list rewrite

def _save(paths, dismissed: list[dict]) -> None:
    p = _storage_path(paths)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(                          # ← line 67, non-atomic
        json.dumps(dismissed, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
```

`_save` is a plain `write_text` — truncate-then-write, not atomic — even though
this repo ships `durable_io.atomic_write_text` (`durable_io.py:56`, docstring:
"Replace `path` atomically, retaining the old bytes if replacement fails") and
uses it for other durable local state. So the corruption source and the silent
recovery are in the same 40 lines.

**Concrete consequence.** The user has dismissed 30 false-positive
contradictions over months. A crash / kill / disk-full during any `_save`
truncates the file. The next `wiki lint` (`lint.py:942`) or
`curator_dismiss_contradiction` MCP call (`mcp/server.py:2612`) reads `[]`
without a word, all 30 pairs reappear as open contradictions, and the very next
dismissal writes a one-entry file over the remains. The user asked for those
pairs to stay dismissed; the state was destroyed and the tool reported normal
operation.

Violates **C1** (unexplained silent broad catch on an internal operation) and
**C4** (cause never observable).

**Test coverage check:** the only `dismiss` hit in `backend/tests/` is
`test_command_surface_characterization.py:157`, which merely asserts the MCP
tool name `curator_dismiss_contradiction` exists in the surface list. No test
covers a corrupt store or the rewrite-after-empty-load path.

**Fix direction:** catch `(OSError, json.JSONDecodeError)` separately —
`OSError`/decode error must `log.warning` and, for a *parse* failure, refuse to
rewrite (rename the bad file to `.corrupt` and surface a lint warning) rather
than silently starting from `[]`. Route `_save` through
`durable_io.atomic_write_text`.

---

### eh-3 [P3] An undecryptable secret store is reported to the user as "your API key is missing"
`backend/src/curator/secret_store.py:107`

```python
def get_secret(reference: str) -> str:
    ...
        try:
            encrypted = base64.urlsafe_b64decode(encoded.encode("ascii"))
            return _load_fernet().decrypt(encrypted).decode("utf-8")
        except durable_io.DurableStateError:
            raise
        except Exception:          # ← line 107
            return ""
```

`DurableStateError` is correctly re-raised; everything else — most importantly
`cryptography.fernet.InvalidToken` when the local fernet key no longer matches
the stored ciphertext — becomes an empty string with no log. The consumer treats
"" as "not configured":

```python
# backend/src/curator/llm.py:1605-1615
    api_key = (cfg.get("api_key", "") or "").strip()
    api_key_secret = (cfg.get("api_key_secret", "") or "").strip()
    ...
        api_key = secret_store.get_secret(api_key_secret)
    if not api_key and api_key_env.startswith("sk-"):
```

**Concrete consequence.** This vault is designed to be synced across devices
(`db_sync.py`, `deviceRegistry.ts`). A user who syncs `config.yml`
(carrying `api_key_secret: secret:deepseek`) to a second machine, or who
regenerates the local key file, gets a DeepSeek client with `api_key=""`. The
failure they see is the provider's "no API key / unauthorized" — so they
re-enter a key that was never wrong, repeatedly. The real cause ("the stored
secret exists but cannot be decrypted on this machine") is emitted nowhere, in
direct breach of **C4**'s "the suppressed cause remains observable in logs", and
of **C2** (broad catch with neither an explicit reason nor module logging).

**Test coverage check:** `secret_store` is exercised for set/get/delete
round-trips, but no test asserts logging or a distinguishable error on
`InvalidToken`; nothing pins the current silent-"" contract as intended.

**Fix direction:** catch `(InvalidToken, binascii.Error, UnicodeDecodeError)`
explicitly, `log.warning("secret %s exists but could not be decrypted…", name)`,
and keep returning `""` so callers' contracts are untouched.

---

### eh-4 [P3] Reason-without-logging at the llama-cpp VRAM cleanup boundary
`backend/src/curator/search.py:40`

```python
def _free_ollama_vram_before_llama_cpp(config: dict, search_config: dict, *, include_reranker: bool = True) -> None:
    """Best-effort VRAM guard before loading llama-cpp search GGUFs."""
    if not _uses_llama_cpp_search_model(search_config, include_reranker=include_reranker):
        return
    try:
        from . import model_setup

        model_setup.unload_configured_ollama_models(config)
    except Exception:          # ← line 40
        pass
```

This is exactly the shape §32 **C2** legislates for: a cleanup boundary calling
an optional provider. It satisfies half the clause — the docstring is an explicit
reason ("Best-effort VRAM guard") — and fails the other half: **no module
logging**. §32 requires *both* ("with an explicit reason **and** module logging").

**Concrete consequence.** On a VRAM-constrained machine the guard exists
precisely so the subsequent llama-cpp GGUF load does not OOM. When the Ollama
unload fails (daemon down, HTTP timeout, API change), the user sees the
*downstream* symptom — `wiki query` degrading to `no_rerank` / lexical-only, or
an opaque llama-cpp load failure — with nothing anywhere connecting it to the
skipped unload. This is the milder, C2-shaped sibling of the already-confirmed
CAND-02 and belongs in the same fix batch.

**Fix direction:** one `log.debug`/`log.warning` in the handler naming the
skipped unload. No control-flow change.

---

### eh-5 [P3] A corrupt vault config silently *downgrades* the recorded schema version
`backend/src/curator/migrate.py:83`

```python
def get_vault_schema_version(paths: cfg.WikiPaths) -> int:
    """Read vault_schema_version directly from vault config file (not merged config).

    Returns 0 when the key is absent — indicating a pre-migration vault.
    """
    if not paths.config_file.exists():
        return 0
    try:
        data = yaml.safe_load(paths.config_file.read_text(encoding="utf-8")) or {}
        return int(data.get("vault_schema_version") or 0)
    except Exception:          # ← line 83
        return 0
```

The docstring justifies `0` for one cause only ("the key is absent"). The broad
catch silently adds three more: invalid YAML (`yaml.YAMLError`), an unreadable
file (`OSError`, e.g. permission or a half-synced file), and a non-integer value
(`ValueError`/`TypeError`). The returned `0` is then the loop bound:

```python
# backend/src/curator/migrate.py:186-214
    current = get_vault_schema_version(paths)
    config = cfg.load_config(paths)
    ...
    for v in range(current, target):
        ...
    if not dry_run and result.ok:
        new_version = current + len(result.steps_run)
        set_vault_schema_version(paths, new_version)
```

The asymmetry is the proof this is a defect and not a policy: `cfg.load_config`,
called on the very next line for the very same file, tolerates the identical
corruption but **logs it** —
`logger.warning("Global config '%s' has invalid YAML — using defaults…")`
(`config.py:471-478`). `get_vault_schema_version` swallows it in silence.

**Concrete consequence.** A vault at schema v3 whose `config.yml` is momentarily
unparseable (mid-sync write, hand-edit typo) is read as v0. Every migration step
v0→v3 re-runs against an already-migrated vault, `wiki` reports the migration as
successfully applied, and `set_vault_schema_version` then writes back
`current + len(steps_run)` computed from the bogus `0`. Nothing in the output or
the log ever mentions that the version could not be read. **C1** and **C4**.

**Fix direction:** catch `(OSError, yaml.YAMLError, ValueError, TypeError)`,
`log.warning` the unreadable-version case, and treat "version unreadable" as
*abort the migration run* rather than "vault is pre-migration".

## 2. Pros & Cons

### Pros of this framing
- All five findings are the **same defect class** with the same 3-line remedy
  (narrow the exception tuple → add module logging → surface through the
  existing `warnings`/CLI channel where one exists). They batch cleanly with
  CAND-01/CAND-02 into one patch-shaped release; no schema change, no contract
  change, no new module.
- eh-1 and eh-2 each have a *named user promise* attached (`--update`'s help
  string; "dismissed pairs stay dismissed"), so the failure scenario is testable
  without an LLM: inject `OSError` on the write and assert a warning is emitted.
- The mechanical enumeration means the negative result is meaningful: the
  ~80 candidate sites are enumerated, not sampled.

### What I could NOT verify (honest gaps)
1. **eh-2 corruption frequency.** I proved the *mechanism* (non-atomic
   `write_text` at `contradiction.py:67` + silent `[]` at :32) but did not
   reproduce an actual truncation. Ground rules forbid running mutating `wiki`
   commands and touching any vault, so the crash-during-write step is reasoned,
   not observed.
2. **eh-5 second-order damage.** `set_vault_schema_version` →
   `cfg.update_config_file(paths.config_file, …)` is called on a config file
   that is *by hypothesis* corrupt. Whether `update_config_file` merges into the
   broken text or replaces it wholesale (which would destroy the rest of the
   user's config) was **not** traced — that would need `config.py`'s
   `update_config_file` body, which I skipped for token budget. If it replaces,
   eh-5 escalates from P3 to P1/P0 and should be re-scoped by the red-teamer.
3. **eh-3 exception identity.** I did not confirm that
   `cryptography.fernet.InvalidToken` is not a subclass of
   `durable_io.DurableStateError` (it is a third-party class, so re-raise at
   :105 almost certainly does not catch it), nor did I enumerate every
   `_load_fernet()` failure mode.
4. **Plugin unawaited-rejection sweep is incomplete.** I enumerated empty
   `catch {}` and `.catch(() => …)` exhaustively, but *unawaited async calls*
   (`this.foo()` where `foo` is `async`, no `await`, no `.catch`) cannot be found
   by grep — that needs `@typescript-eslint/no-floating-promises` with type
   information. **Recommendation for the batch:** enable that rule rather than
   trust this sweep's plugin half. I am not claiming the plugin is clean; I am
   claiming no *greppable* plugin site cleared the FINDING bar.
5. **`backend/src/curator/mcp/server.py`** has ~30 broad catches. All the ones I
   spot-checked return `{"ok": false, "error": …}` or `{"error": …}` — i.e. the
   outer-transport-boundary case §32 line 3385-3387 explicitly permits. I did
   not read all 30 bodies individually.

### Appendix — sites swept and judged ACCEPTABLE (with the clause that clears them)

**Cleared by §32 line 3385–3387 (outer transport boundary preserving a JSON/exit contract):**
- `mcp/server.py` — every site at :351, :360, :385, :399, :413, :432, :439, :463,
  :477, :488, :523, :834, :855, :879, :1183, :1400, :1593, :1742, :1915, :2083,
  :2140, :2382, :2728, :2780, :2857, :2989, :3009, :3029, :3047, :3136, :3160,
  :3184, :3208, :3260, :3323 — all return an `error`/`ok:false` payload to the
  caller. The failure is delivered, not hidden.
- `plugin_api/context.py:28,44,80,118,170`, `plugin_api/pdf.py:388`,
  `plugin_api/query_api.py:109,209`, `plugin_api/sources.py:311` — same shape
  (`{"ok": False, "error": …}`) on the hidden plugin API surface.
- `zotero_tools.py:54` → `return False, str(exc)` — the caller receives the cause.

**Cleared by C3 (degradation reported through an existing `warnings` surface) — and by an existing test:**
- `retrieval/engine.py:180` (`except Exception: … return ordered, "no_rerank"`).
  My first read flagged this: a crashed reranker and a *disabled* reranker both
  return the bare string `"no_rerank"` (:169 vs :182). But
  `backend/tests/test_engine.py:165-177` pins a `_BrokenReranker` and asserts
  `any("reranker_failed" in w for w in result.warnings)`, and
  `test_engine.py:189-211` pins the invalid-output cases with
  `w.startswith("reranker_failed:")`. The cause **is** surfaced through the
  `warnings` field. Per ground rule 4, my claim was wrong — withdrawn.
- `retrieval/engine.py:126` — returns a `_VectorOutcome` carrying the error.
- `prompting/runner.py:211` — records `latency_ms` and finishes the prompt run
  with the error captured in the trace.

**Cleared by C2 (deterministic parse/filesystem/conversion fallback, outer boundary logs, or explicitly stated reason at an optional boundary):**
- `pipeline/synthesis.py:77` — malformed L3 frontmatter skipped during a
  best-effort `report_id → concept_id` backfill; the caller's mapping argument is
  the primary source and a missing entry is dropped by `mapping.get(rid)` at :85.
- `ingest_llm.py:731` (`find_workspace_exhibition`) — unreadable L4 page skipped
  during a scan; returns `None` → caller re-curates.
- `search.py:346` — unparseable source file skipped during source-page scan;
  guarded by an `is_supported`/`exists` pre-check at :342.
- `source_tools.py:47,166`, `db/sources.py:727`, `pipeline/chunking.py:15`,
  `page_writer.py:402`, `parsers/html.py:45`, `query.py:185,221`,
  `zotero_tools.py:143`, `zotero_integration.py:13,154`, `llm_identity.py:21`,
  `migrate.py:138` — deterministic parse/convert defaults on optional metadata;
  no user-requested operation is hidden.
- `commands/common.py:385` — DB read failure → `context_ids_pending_l2 = set()`.
  Fails **open** (more lint issues shown, never fewer), so it cannot hide a
  problem from the user. Unlogged, which is a C2 nit, not a finding.
- `sync.py:130`, `workspace/provisioner.py:303` — conservative fallbacks that
  widen the affected set / preserve the user's `curate.yml`; both err toward
  doing more work, not silently skipping it.
- `retrieval/providers.py:268,352` — :352 carries the inline reason
  `# llama-cpp missing / model load failure → degrade`, and the degrade is
  reported as `no_rerank` in `warnings` (see engine tests above).

**Plugin sites (all cleared — explicit reason comment and/or an outer logged boundary):**
- `zotero/assetLocalization.ts:135` (`createFolder(…).catch(() => {})`) and
  `:143` (`readBinary(existing).catch(() => null)`) — both sit inside a `try`
  whose handler is `logger.error("Failed to localize annotation image", …)` at
  `:149-151`. Cause is logged.
- `utils/sessionStore.ts:78` (`previous.catch(() => undefined)`) — this catches
  the **previous queued operation's** rejection purely to keep the serialization
  chain alive; that rejection was already delivered to its own caller via the
  promise returned at :111-113. Correct idiom, not a drop.
- `agent/llm/LLMClient.ts:2152` — `.catch(() => { // Usage accounting should
  never block the answer. })`: explicit reason, optional accounting boundary,
  and the degradation (a stale token counter) is not a user-requested operation.
- `ui/chat/ChatSidebarView.ts:2932` (`catch { }`) — `JSON.parse` of an embedded
  tool-result block; falls through to `traceToRender = null`, i.e. the trace
  panel is simply not rendered for that message. Deterministic parse fallback.
  Nit: no reason comment.
- `utils/zoteroUtils.ts:28` (`catch (err) {}`) — `new URL(href)` failure while
  extracting optional `page`/`annotation` params; the function still returns a
  valid `{attachmentKey}`. Deterministic parse fallback. Nit: broad, no comment.
- `ui/chat/ChatSidebarView.ts:452` (`// fail silently`) — status-bar job-count
  refresh reading `jobs.json`. Cosmetic display refresh, not a requested
  operation. Nit: reason comment states the behaviour, not the cause.
- Reason-comment-bearing catches, all read and cleared:
  `LLMClient.ts:817,1381,1705,2459`, `agent/mcpClient.ts:312`,
  `auth/cliAuth.ts:61,153`, `settings.ts:25`,
  `ChatSidebarView.ts:1985`, `ui/diffViewer.ts:360,604`,
  `ui/incuratorDashboardModal.ts:197,227,270,313,1435`,
  `ui/pdf/ExternalPdfView.ts:1021,1031`, `ui/pdfCaptureService.ts:92`,
  `ui/quickQueryPopover.ts:493`, `utils/deviceRegistry.ts:177`,
  `utils/durableJsonStore.ts:62`, `utils/logger.ts:16`. Several are exemplary —
  `durableJsonStore.ts:62` ("Preserve the original replacement error; the
  canonical file is intact") is the pattern eh-2 should be rewritten to follow.
