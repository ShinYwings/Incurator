# Critique on 04_g0_exception_hygiene.md (§32 Observable-Degradation Sweep)
Date: 2026-08-05 | Agent Persona: Red-Team Critic (Exception Boundary Adversary)

Target: `.agents/plans/system_defect_audit_arena/04_g0_exception_hygiene.md`
Rubric: `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md` §32 (lines 3383–3406).

**Survival bar applied.** §32 explicitly *permits* three broad-catch shapes:
outer transport boundaries preserving an exit/JSON contract (3385–3387),
optional provider/cleanup boundaries with reason + logging (3394–3396), and
deterministic fallbacks that keep output while the cause stays in logs
(3405–3406). A syntax sweep for `except Exception` therefore over-collects by
construction. A finding survives here only if **a user-requested operation
silently fails, or a result falsely claims success**. "The handler lacks a
`log.` call" is, on its own, a spec-letter nit — not a defect.

Verdict summary:

| id | inspector | verdict | final |
|---|---|---|---|
| eh-1 | P2 | **confirmed** | P2 |
| eh-2 | P2 | **downgraded** | P3 |
| eh-3 | P3 | **confirmed** (rationale replaced) | P3 |
| eh-4 | P3 | **downgraded** | P4 (nit) |
| eh-5 | P3 | **refuted** | — |

---

## 1. Vulnerabilities & Flaws

### eh-1 — CONFIRMED (P2), but the inspector localised the defect to the wrong line

**Code re-verified as current.** `ingest_llm.py:685-690` is quoted exactly;
`commands/common.py:2164-2170` is quoted exactly; the `--update` help string at
`commands/core.py:1366-1370` is real, and `core.py:1483` wires
`update_knowledge=update` into `_run_query_repl`, so the **one-shot**
`wiki query --update "…"` path (not just the REPL) runs this code.
`grep -rln "add_atom_from_insight" backend/tests/` → zero files. No test pins it.

**Attacks attempted, all failed:**
- *Is `None` reported anywhere else?* No. `common.py:2169` is `if atom_id:` with
  no `else`; `_warn(...)` is in scope in the same function (used at
  `common.py:2146`), so §32's "where that surface already defines one" (C3) is
  satisfied — the CLI warning channel exists and is simply not used.
- *Is the failure rare enough to be theoretical?* No. The broad catch at :689
  wraps `client.chat_stream(...)`; provider 429/timeout is the single most common
  runtime failure in this project (see the DeepSeek/Antigravity 429 history).
  This fires in normal operation.
- *Is this the permitted "optional LLM boundary" shape?* No. Atom creation here
  is not optional enrichment — it is the entire thing the user typed `--update`
  to get. §32 line 3403 ("a response must not claim that a requested … action
  completed when it was skipped after an exception") is exactly on point: the
  command prints an answer and exits 0, and nothing distinguishes "atom written"
  from "atom silently dropped".

**Correction to the inspector's write-up (factual error).** The claim that "the
whole body … is inside one `try`: the LLM call, `strip_llm_noise`, …" is wrong.
There are **two** try blocks: `ingest_llm.py:646-650` already catches narrowly
(`except (ValueError, LLMError): return None`) around the summary call, and only
the second block (:669-690) is broad. This matters for the fix: narrowing :689
alone does **not** fix the bug, because the narrow handler at :649 is *equally*
silent. The defect is the **missing failure channel out of
`add_atom_from_insight` and the caller's missing `else`**, not the width of one
`except`. A patch that only edits :689 would close the finding while leaving the
user-visible symptom fully intact on the most common failure (`LLMError` from the
first call).

**Second caller re-verified.** `backprop_agents.py:56-60` (`AtomSynthesizer.synthesize`)
returns the same `Optional[str]` straight through — same blindness, confirming the
failure channel belongs in the function's return type, not in the CLI.

### eh-2 — DOWNGRADED to P3: real mechanism, inflated blast radius, and two different defects welded together

**Code re-verified as current.** `contradiction.py:25-33` (silent `[]`),
`:48-61` (`load_dismissed` → append → `_save`), `:64-70` (plain non-atomic
`write_text`) are all quoted accurately. `durable_io.atomic_write_text` exists.
Consumers `lint.py:942` and `mcp/server.py:2612` confirmed — both consume the
list with no way to tell `[]`-because-empty from `[]`-because-corrupt.
`grep -rln "load_dismissed\|add_dismissed" backend/tests/` → **zero files**;
the "no coverage" claim holds.

**Why the severity does not survive at P2:**
1. **No user-requested operation silently fails.** The requested action —
   "dismiss this pair" — *succeeds* and is reported. What is lost is previously
   stored state, and only when that state was *already* corrupt or unreadable.
   The tool never claims to have done something it did not do.
2. **The trigger is pre-existing corruption, not the handler.** For the silent
   `[]` to destroy anything, the JSON must already be truncated/unparseable. The
   handler's sin is failing to *report* damage it did not cause.
3. **The destroyed data is advisory and regenerable.** Dismissals suppress lint
   noise; they are not DAG content. The user re-dismisses. Compare eh-1, where an
   L2 Atom the user explicitly asked to create never enters the graph.
4. **Contrast with the project's own P2 bar:** `test_durable_state.py:25`
   (`test_corrupt_secret_store_is_preserved_and_blocks_mutation`) shows the
   codebase already treats *credential* store corruption as must-block-and-raise.
   Contradiction dismissals are not in that tier.

**The finding conflates two defects and should be split.** The non-atomic
`_save` at `:67` is a **durability** defect (should route through
`durable_io.atomic_write_text`, per the repo's own `durableJsonStore.ts:62`
precedent the inspector cites) and is not a §32 exception-hygiene violation at
all. Only the silent `except Exception: return []` at `:32` is a §32 C1 breach.
Filing them as one P2 lets the exception-hygiene batch smuggle in an unrelated
I/O change; filing them separately keeps each fix reviewable.

**What survives:** `:32` is a genuine C1 breach — an unexplained silent broad
fallback on an internal operation whose docstring actively misdescribes it
("Returns [] if file missing"). P3.

### eh-3 — CONFIRMED (P3), but the entire reachability argument is wrong and must be replaced

**Code re-verified as current.** `secret_store.py:102-108` is exact.
`llm.py:1605-1615` (`_make_deepseek_api`) is exact.

**The inspector's headline scenario is refuted on two independent grounds:**
1. **`api_key_secret` is never read from a synced vault config.**
   `config.py:452` defines `MACHINE_LOCAL_CONFIG_KEYS = frozenset({"llm",
   "search", "external"})`, and `load_config` (`config.py:485-497`) *skips* the
   `llm` key when it appears in the vault config file **and logs a warning**
   naming the file. `api_key_secret` lives under `llm.*`. The "user syncs
   `config.yml` carrying `api_key_secret` to a second machine" story therefore
   cannot happen through the sync path as described.
2. **Even if it could, it would not reach line 107.** On machine B the store
   would not contain that name, so `get_secret` returns at `:101`
   (`if not encoded: return ""`) — the documented not-configured path, *before*
   the try block. The finding's own code is not executed by its own scenario.

**Also refuted:** the inspector's honest-gap #3 worry. `_read_store()`
(`:51-68`) and `_load_fernet()` (`:24-42`) both raise `durable_io.DurableStateError`
on unreadable/corrupt store or key, and those are re-raised at `:105`. So every
*store/key corruption* mode is already loud. `test_durable_state.py:25` pins it.

**What actually survives (narrower, still real).** The residual reachable path is
key/ciphertext **divergence**: `_load_fernet()` at `:33-36` silently
**generates a fresh key** when `secret.key` is absent while `secrets.json`
survives (partial restore of `~/.<global config>/secrets/`, a backup that omits
the 0600 key file, a wiped key). Every stored ciphertext then raises
`fernet.InvalidToken`, is swallowed at `:107`, and returns `""`; `llm.py` falls
through to the `sk-` misconfiguration recovery and the user is told the key is
missing. This breaches C2 (a *crypto decrypt* has enumerable expected classes —
`InvalidToken`, `binascii.Error`, `UnicodeDecodeError` — so the "arbitrary
implementations" licence does not apply) and C4 (cause not observable).
Tests: `test_deepseek_provider.py:94-97` pins only the round-trip and the
post-delete `""`; nothing pins the `InvalidToken` contract.

P3 stands — the fix is a one-line `log.warning` plus a narrowed tuple, no
control-flow change — but the plan text must be rewritten, because a fix
justified by a scenario that provably cannot occur will be reverted by the next
reviewer who checks it.

### eh-4 — DOWNGRADED to P4 (nit): §32 permits this shape; only the logging half is missing

**Code re-verified as current.** `search.py:32-41` is exact, and
`grep -n "getLogger\|^import logging" backend/src/curator/search.py` returns
**nothing** — the module has no logger at all, so "add a `log.warning`" is not a
one-liner but a new module logger. Fine either way.

**Why it does not clear the bar:**
- §32 line 3394-3396 names "cleanup boundaries" as a place a broad catch **may**
  be retained. This is literally a cleanup boundary calling an optional provider
  (`model_setup.unload_configured_ollama_models`), guarded by a pre-check that
  returns early unless llama-cpp is actually in use.
- **No user-requested operation fails silently.** A failed Ollama unload does not
  skip anything the user asked for. If it causes a downstream llama-cpp load
  failure, that failure is *already* surfaced: the inspector's own appendix
  documents `retrieval/engine.py:180` reporting `reranker_failed:` through the
  `warnings` field, pinned by `test_engine.py:165-177` and `:189-211`.
- **No false success.** Nothing claims the VRAM was freed.

This is "reason present, logging absent" — half of C2's conjunction, at a
boundary the same sentence explicitly licenses, with zero observable user impact.
It is worth doing while the batch is open (free, no risk), but shipping it as a
P3 *defect* inflates the audit's defect count with a style fix. Reclassify as a
nit, not a finding.

### eh-5 — REFUTED: three of the four claims are false, and the escalation is inverted

The inspector's own honest-gap #2 asked the red-teamer to trace
`cfg.update_config_file` and warned this could escalate to P1/P0. Traced. It
**de**-escalates to nothing.

1. **"Reports the migration as successfully applied" — FALSE for the corruption
   cases.** `set_vault_schema_version` (`migrate.py:87-93`) →
   `cfg.update_config_file` → `_read_config_mapping_for_update`
   (`config.py:372-385`), which **raises** `durable_io.DurableStateError` on
   `OSError`/`yaml.YAMLError` and on a non-mapping root. So on an unreadable or
   invalid-YAML config, `run_migrations` does not quietly finish — it raises out
   of line 214 and the run fails loudly. There is no false success.
2. **"With no log line at all" — FALSE.** `migrate.py:187` calls
   `cfg.load_config(paths)` on the *same file, one line later*, and
   `config.py:499-508` logs **two** warnings covering both invalid YAML
   (`"Vault config '%s' has invalid YAML — using defaults"`) and any other read
   failure (`"Vault config load failed for '%s': %s"`). The suppressed cause **is**
   observable in logs, which is precisely what §32 line 3406 requires. The
   inspector presented this as its "asymmetry proof"; read correctly, it is the
   refutation — §32 requires the cause to be in the logs, not in *this module's*
   logs.
3. **"Every migration step v0→v3 re-runs" — FICTIONAL.** `constants.py:54`:
   `VAULT_SCHEMA_VERSION = 1`. `_MIGRATION_STEPS = {0: _migrate_v0_to_v1}` —
   exactly one step, whose own docstring (`migrate.py:146-152`) states it is
   idempotent by construction: "load_config() and save_config() already
   auto-migrate this on every call. This explicit step just ensures the vault
   config is clean and the version is recorded." Re-running it on a migrated
   vault is a no-op re-save. There is no v0→v3 ladder to re-run.
4. **"Writes back a bogus `current + len(steps_run)`" — FALSE today.** With
   `current=0` and one step run, `new_version = 0 + 1 = 1 = VAULT_SCHEMA_VERSION`.
   The write-back lands on the *correct* value. (The `current + len(steps_run)`
   arithmetic is genuinely fragile if a gap ever appears in `_MIGRATION_STEPS`,
   since `steps_skipped` is not counted — but that is a latent arithmetic issue
   independent of any exception handling, and belongs in a different finding.)
5. **Coverage claim missing.** eh-5 is the one finding with no test check, and it
   is the one with tests: `backend/tests/test_migrate.py` imports and asserts
   `get_vault_schema_version` at :34, :39, :47, :84, :96, :139 and exercises
   `run_migrations` end to end.

**Residue:** a non-`int` `vault_schema_version` (valid YAML, e.g. a hand-typed
`"three"`) does read as `0` unlogged, and that is a real if trivial C1 breach on
a machine-managed key. Consequence: one idempotent no-op re-runs and the correct
version is rewritten. No silent failure of a requested operation, no false
success, no data loss. Below the bar. Fold the one-line log into the eh-4 nit
sweep if the batch is open; do not carry it as a P3 defect.

---

## 2. Suggested Alternatives

### 2.1 Rewrite eh-1 as a caller-contract fix, not an `except` width fix

Editing `ingest_llm.py:689` alone leaves the bug live on the most common failure
mode. The minimum correct change:

- Give `add_atom_from_insight` a failure channel instead of a bare `Optional[str]`
  — e.g. return `tuple[str | None, str | None]` (`atom_id`, `reason`) or raise a
  typed `AtomCreationError`. Both the `(ValueError, LLMError)` handler at
  `ingest_llm.py:649` and the broad handler at `:689` must populate it.
- Narrow `:689` to `(LLMError, OSError, UnicodeEncodeError, ValueError)` and add
  a module `log.warning` naming the failed stage.
- `commands/common.py:2169` gets the `else`:
  `_warn(f"  → atom creation skipped: {reason}")`. Exit code contract unchanged
  (this is a degradation, not a failed query).
- `backprop_agents.py:56-60` propagates the reason to its caller rather than
  flattening to `None`.

**Test (no LLM needed):** monkeypatch `client.chat_stream` to raise `LLMError`,
run the `--update` path, assert the CLI output contains `atom creation skipped`
and that `caplog` holds the cause. Second test: monkeypatch `Path.write_text` to
raise `OSError`, same assertions. This is the first test to ever touch
`add_atom_from_insight`.

### 2.2 Split eh-2 into a §32 fix and a durability fix

- **§32 half (this batch):** `contradiction.py:30-33` →
  `except OSError as exc: log.warning(...); return []` and
  `except json.JSONDecodeError as exc:` → log, rename the file to
  `*.corrupt-<ts>`, return `[]`. Fix the docstring, which currently lies. Do
  **not** attempt a lint-issue surface in this batch; `load_dismissed` has no
  `warnings` channel and inventing one is scope creep.
- **Durability half (separate item):** `_save` at `:64-70` →
  `durable_io.atomic_write_text`. This is the same class as
  `plugin/src/utils/durableJsonStore.ts:62` and should be reviewed against
  `durable_io` policy, not against §32.
- **Tests:** write `0xff`-garbage into `contradiction_dismissed.json`, assert
  `load_dismissed` returns `[]`, `caplog` has a warning, and the original bytes
  are preserved under `.corrupt-*` — i.e. `add_dismissed` cannot silently
  overwrite them.

### 2.3 Re-justify eh-3 against the real trigger

Replace the cross-device-sync narrative (refuted above) with the reachable one:
**`_load_fernet()` regenerating a key at `secret_store.py:33-36` while
`secrets.json` survives**. Fix:

```python
except durable_io.DurableStateError:
    raise
except (InvalidToken, binascii.Error, UnicodeDecodeError):
    log.warning(
        "secret %r exists but cannot be decrypted with the local key at %s "
        "(re-enter the secret with `wiki config provider`)", name, _secret_dir() / KEY_FILE
    )
    return ""
```

Return value unchanged, so `llm.py` and every other consumer are untouched.
Consider (separate item, not this batch) making `_load_fernet` refuse to
silently mint a new key when a non-empty `secrets.json` already exists — that is
the actual root cause, and §32 is only the symptom.

### 2.4 Demote eh-4 and eh-5 to a single "logging nits" line item

Both are one-line `log` additions at boundaries §32 already permits, with no
behavioural change and no test worth writing beyond `caplog`. Ship them inside
the eh-1/eh-2/eh-3 commit as a trailing "add module logging at three permitted
broad-catch boundaries" hunk (`search.py:40`, `migrate.py:83`, plus
`commands/common.py:385` from the inspector's own ACCEPTABLE list, which has the
identical shape). Do not carry them in the defect ledger as P3 findings — a
defect count inflated with style fixes is what makes the next audit's P3 tier
unreadable.

### 2.5 Process note for the sweep itself

The sweep's ACCEPTABLE appendix is genuinely good work and its self-withdrawal of
the `retrieval/engine.py:180` claim (ground rule 4) is the right instinct. Two
method gaps produced the three bad findings above, and both are cheap to close:

1. **Trace the consumer, not just the handler.** eh-3 and eh-5 both died on the
   consumer trace (`MACHINE_LOCAL_CONFIG_KEYS`; `_read_config_mapping_for_update`
   raising). A handler that returns a degraded value is only a defect if some
   consumer *acts* on it — read the consumer before filing.
2. **Run the test-coverage grep on every finding, not most.** eh-5 skipped it and
   was the one finding with an existing test module (`test_migrate.py`).

Both gaps are the same failure: filing on handler shape before confirming the
blast radius. §32's permitted shapes make that failure mode systematic, not
incidental.
