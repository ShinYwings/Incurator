# Briefing: agy shells out, and one denial kills the whole compile

Date: 2026-08-21 | ROADMAP 5b | Agent Persona: main (briefing)

## 1. The symptom, on three unrelated surfaces

The Antigravity CLI decides to run a shell command mid-turn. In `-p` (print)
mode there is no one to approve it, so agy exits 1 and the caller sees:

```
Antigravity CLI exited 1: permission check failed for command "python3 …":
user denied permission to run command
```

Observed at three places that share no prompt, no contract, and no code path:

| surface | what it tried to run |
|---|---|
| chat / read (2026-08-09 P0, still untriaged) | the tool the model reached for was denied |
| compile — `curator.entity_relation_extract@v2` | `python3 …/brain/<id>/scratch/extract_knus.py` |
| compile — same contract, second attempt | `python3 -c '… transcript_full.jsonl … content.find("Knowledge units:")'` |
| query against a Zotero PDF (2026-08-21 report) | `python3 -c 'import PyPDF2 … open(pdf_path) … re.search("Pl[uü]cker")'` |

Two of the four are the model trying to **recover its own prompt input** by
reading agy's transcript log off disk. That is a strong hint about *why* it
shells out, and it is not addressed by anything below — see §6.

## 2. Why it is fatal rather than annoying

`extract_graph_data` (`graph_index.py:123`) loops batches and guards **validation**
failures only:

```python
if not (result.ok and result.parsed is not None):
    all_ok = False
    ...
    continue
```

There is no `try` around `prompting.run_prompt`. And `run_prompt` closes the
prompt-run row and then **re-raises** (`runner.py`, `except Exception as exc: …
finish_prompt_run(…); raise`). So a provider exception is not the `continue`
path — it propagates out of `compile_source_l2`'s staging block and the whole
compile dies.

Measured consistency: with a per-call denial rate of 43%, the expected number of
batches completed before the first abort is 1/0.43 ≈ **2.3**. The live run
aborted after **2**.

## 3. The scale that makes it unpublishable, not unlucky

Publishing needs **every** graph batch to succeed.

| | |
|---|---|
| units for source 45 | 5,358 |
| approx graph prompt chars | 1,551,159 |
| batches at `optimal_chunk_chars = 18000` | **~87** |
| observed agy success rate (2026-08-21) | **57%** — 4 `ok` / 3 `failed` |
| P(all 87 succeed) | **≈ 7×10⁻²²** |

Any source past roughly a dozen graph batches is effectively unpublishable.
That is every large reference in the vault. Retrying the compile as it stands
cannot help; this is arithmetic, not luck.

## 4. What the backend does NOT do that the plugin already does

`AntigravityCliClient._build_cmd` (`llm.py:1063`) assembles
`[agy, --log-file, --model, --effort, (--json-schema …), --print, <prompt>]`.
**It never passes `--sandbox`.**

The plugin does, and `LLMClient.ts:2311` says exactly why:

> Keep `--sandbox`: in -p mode it auto-proceeds without the permission [prompt]

So the plugin's agy calls do not die on a permission request; the backend's do.
`CodexCliClient` (`llm.py:1285`) passes `--sandbox read-only`; `ClaudeCodeClient`
passes nothing. The backend is the only agy caller with neither.

**But `--sandbox` does not contain anything.** `plugin/src/agent/sandboxWrapper.ts`
records a measured P0: *"Agentic CLIs — `agy` especially — ignore their own
`--sandbox` flag (under `agy --sandbox` the agent still ran `echo > /tmp/file`
and the file was created)."* The plugin therefore wraps the subprocess in an OS
sandbox — `sandbox-exec` with an inline Seatbelt profile on macOS, `bwrap` on
Linux — denying `file-write*` outside the vault, the Zotero roots and the CLIs'
own state dirs, while leaving reads allowed. **The backend has no equivalent.**

So adding `--sandbox` alone would stop the failure by letting the model actually
execute `python3` on the user's machine, uncontained. That is a capability
widening, not a bug fix, and it is the decision this Arena exists to make.

## 5. What has already been tried and rejected

- **`--dangerously-skip-permissions`**: two plugin tests assert it is never used
  (`llmClient.test.ts:862`, `:954`). Treat as settled unless overturned here.
- **Writing `permissions.allow` into agy's `settings.json`**
  (`syncAgyHeadlessReadPermission`): **agy deletes the key on its very next
  invocation**, reproduced 3/3 in the 2026-08-09 report. The grant survives zero
  model calls. Any fix that persists a file is dead on arrival.
- **Changing the prompt so the model is less likely to reach for a tool**
  (v0.48.4): the same report calls this "a mitigation of a symptom; the tool is
  still denied whenever the model does reach for it."

## 6. The question nobody has asked yet

Two of the four observations show the model reading agy's own transcript to
recover *"Knowledge units:"* — i.e. it behaves as though its input were not
fully present. Nobody has checked whether the prompt is being truncated or
garbled on the way in. `AntigravityCliClient` passes the entire prompt as a
single **argv element** (`--print <prompt>`), alongside a `--json-schema` that is
itself large. If argv is being clipped, every fix below treats a symptom.

**This must be measured before the Arena picks a direction.**

## 7. Candidate directions (for the proposal to argue, not settled here)

- **A — pass `--sandbox`.** Smallest diff, matches the plugin, and lets the model
  run shell commands on the host with no containment.
- **B — A plus an OS sandbox in the backend.** Ports `sandboxWrapper.ts`'s
  Seatbelt/bwrap approach to Python. Matches the plugin fully; largest diff; must
  answer what happens on a platform where neither is available.
- **C — make a denial non-fatal.** Guard `run_prompt` in `extract_graph_data` and
  retry the batch, as `_run_batch_with_retry` already does for L2. Expected cost
  87/0.57 ≈ **153 calls** instead of 87. Does not stop the shelling; makes it
  survivable. Per CLAUDE.md this is symptom-level and needs justifying against a
  root-cause fix.
- **D — route the contract to another provider.** `llm.yml` currently has
  `fallback: ''`, so there is nothing to fall back to today.

## 8. Constraints any proposal must respect

- The fix must not persist a permission file — agy wipes it (§5).
- A test must run a **real `agy` call** and assert the outcome. The 2026-08-09
  report is explicit: *"a unit test that only checks we wrote the file would have
  passed every time while the bug shipped."*
- The Zotero **attachment** directory (iCloud) is a separate macOS TCC grant from
  the Zotero **data** directory (`~/Zotero`). A granted shell command can still be
  denied there. Any sandbox profile must not conflate them.

---

## 9. MEASURED (2026-08-21). Two of the four directions are already dead.

Everything below is a real `agy` invocation on this machine, agy as installed at
`~/.local/bin/agy`, model `gemini-3.5-flash`. The probe prompt is *"Run exactly
this shell command and then reply DONE: printf ok > <scratch file>"*, and the
check is whether the file appeared.

| invocation | denied? | command executed? |
|---|---|---|
| no flag — **what the backend does today** | **yes** | no |
| `--sandbox` | **yes** | no |
| `--mode accept-edits` | **yes** | no |
| `--dangerously-skip-permissions` | no | **YES** |

**The failure is now deterministically reproducible on demand.** This whole class
has been "intermittent" since v0.30; it is not. Ask agy for a shell command in
`-p` mode without that one flag and it fails, every time.

### 9.1 `--sandbox` does nothing, and the plugin's comment is wrong

`LLMClient.ts:2311` says *"Keep `--sandbox`: in -p mode it auto-proceeds without
the permission [prompt]"*. Measured: it does not. `--sandbox` produces the
identical `permission check failed` error as no flag at all.

This matters beyond this Arena. **The plugin is built on that belief**, so the
plugin's agy calls die on any tool request too — which is exactly the standing
2026-08-09 P0 (*"jetski 'no output produced'… reported repeatedly since v0.30,
declared fixed each time, never verified"*). The two reports are one bug, and the
reason it kept surviving "fixes" is that the flag everyone relied on was inert.

### 9.2 Direction A is dead; B has to be restated

- **A (pass `--sandbox`)** — dead. It changes nothing.
- **B (A + an OS sandbox)** — the `--sandbox` half is inert, so B is really
  **`--dangerously-skip-permissions` + real OS containment**. That is a different
  proposition from what §7 described, and a materially bigger security decision:
  the flag auto-approves *everything*, so containment stops being defence in
  depth and becomes the only defence. Note `sandboxWrapper.ts` deliberately
  **allows all reads** — it only denies writes — so under B' a model could still
  read any file the user can, including the Zotero attachment tree and anything
  else on disk.
- **C (make a denial non-fatal)** — untouched by these measurements and now
  testable, because the failure reproduces on demand.
- **D (route to another provider)** — untouched.

### 9.3 What §6 asked, answered: the input is NOT being truncated

A 23,835-character prompt (larger than a real 18,000-char graph batch) passed as
a single argv element, with a sentinel on the final line, came back with the
sentinel echoed correctly. `ARG_MAX` is 1,048,576 here. So the model reading
agy's transcript to recover *"Knowledge units:"* is not compensation for a
clipped prompt. §6 is closed: it shells out because it chooses to.

### 9.4 Consequence for scope

C fixes the **ingest** surface only. The user's 2026-08-21 report is a **query**
against a Zotero PDF, and the 2026-08-09 P0 is the **chat** surface; neither is
helped by retrying a batch. A fix that only makes graph extraction survivable
leaves two of the three observed surfaces broken, and should say so plainly
rather than be presented as closing 5b.
