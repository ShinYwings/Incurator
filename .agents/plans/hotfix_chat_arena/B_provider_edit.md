# Provider Runtime Proposal: Preserve final edits and prevent unnecessary shell choices
Date: 2026-09-10 | Agent Persona: Provider Runtime / Edit Integrity Reviewer

## 1. Core Logic & Implementation

### Verified Codex defect

`plugin/src/agent/llm/LLMClient.ts` streams every Codex `agent_message` as though
it were another cumulative snapshot of the same message. Both the complete-line
handler and EOF-buffer handler compare the new text's length with the previous
text and emit `answerText.slice(codexAnswerText.length)`. Distinct item IDs are
ignored. A progress message followed by a shorter final answer therefore loses
the entire final answer; a longer final answer loses its prefix. Losing the
opening `ai-agent-edit` fence or SEARCH marker makes `extractMultiEditProposals`
return no proposal. The actual final output file is read at process close but
never sent to the UI when any earlier message was seen. This fully explains a
Codex-specific missing-diff path without relying on model noncompliance.

Implement a small item-aware Codex message accumulator. Deduplicate cumulative
updates within one message ID; append independent completed message items in
order without subtracting unrelated lengths. Exclude reasoning/tool/command
items from answer text. At close, reconcile the output-last-message text: if it
has not been emitted intact as the last assistant message, emit the intact final
text once. Returned completion text and visible final text must agree. Prefer
native event phases (when present) to surface commentary as status, but do not
assume every installed CLI supplies a phase.

`maybeAutoOpenDiff` also resolves an absolute/URL-encoded target to a vault file,
then incorrectly compares the active file's canonical vault path to the RAW
proposal filepath. Compare to `file.path` once resolution succeeds. This fixes
automatic opening; the original source already preserves review pills.

Do not convert failed prose to guessed patches or auto-apply edits. The
SEARCH/REPLACE contract and user Accept remain authoritative. Native Codex
workspace-write remains a design risk because the prompt says all modifications
must be proposals. Tightening this deserves a documented tool-policy decision;
the concrete streaming bug can be fixed without inventing an edit-intent router.

### Antigravity denial: verified scope and evidence gap

Installed CLI is agy 1.2.0. `agy --help` exposes `--mode`, `--sandbox`, output
format/schema, and slash-command disabling, but no `--tools`/tool-choice flag.
The plugin grants `read_file(*)`, `command(wiki)`, and `mcp(*)`; granting arbitrary
`command()` is expressly forbidden by existing contract and is not required to
explain equations from provided context. The user error proves an attempted
command was denied, but does NOT establish which command or missing context
caused it. Unlike the backend E4 draft, this request is a conversational answer,
not graph extraction, and E4 should stay queued.

The plugin currently gives an agent CLI a generic flattened prompt with an
embedded `System:` label. It never tells agy its precise permitted command
surface, nor how to handle insufficient context without running shell programs.
It also retains global MCP discovery in purported tool-free calls. Add a
provider-specific invocation policy describing actual supported operations:
answer directly from supplied context; use native read_file for explicitly
attached image paths; in search-enabled sidechat use curator/fetch MCP as needed;
never use shell commands, terminal, transcript/log recovery, or code execution
to inspect/compute the answer; missing evidence must be stated. For search OFF,
explicitly forbid vault retrieval and external calls while preserving supplied
images/current document. This prevention is useful but MUST NOT be described as
an enforced tool-free guarantee; agy offers no proven surface-removal flag.

A deterministic alternative to investigate before choosing: native
`--json-schema` with one `answer` string field on direct context-only turns, plus
`--output-format json`, returning that field to the existing stream callback.
Existing backend evidence shows a flattened native schema often yields one turn
without shelling out, but the E4 draft proves native schema is not a complete
tool exclusion. It also buffers prose until completion and could worsen the
user's perceived latency. Do not adopt without a measured live direct-context
answer and denied-command reproduction.

Reject blind full-turn retries as the primary fix: they consume latency and
only hide the same stochastic tool choice. Reject swapping providers to hide
permission denials or broad command grants. If actual shell capability is
required for a user request, preserve the explicit failure and document the
unsupported operation; do not claim that a prompt alone guarantees prevention.

## 2. Tests and Documentation

- Fake-process behavioral regression: two distinct Codex agent messages where
  final edit block is shorter than progress; longer final block; same-ID
  cumulative snapshots; duplicate item completion; EOF without trailing newline;
  output-last-message-only final content; no raw JSON leakage on event-only
  failures. Assert intact SEARCH/REPLACE in visible callback text and return.
- Diff auto-open regression: canonical, absolute and percent-encoded proposal
  path resolving to active note all open same note; another focused note remains
  untouched. Match actual review path, not source-string presence alone.
- Antigravity command-generation/prompt tests pin the exact permitted surface,
  search enabled/off behavior and image exception. Existing sandbox and required
  narrow permissions remain unchanged.
- Live agy validation is needed before claiming issue 2 resolved. Use only
  disposable files/context, retain current permissions, record answer/no-answer,
  tool denial and wall time. Do not edit the shared live settings to broaden
  grants during a probe. If not reproducible, report the coverage limit.
- Update PLUGIN_SCHEMA provider/tool-scope and edit stream contract, then English
  PLUGIN_GUIDE and its Korean translation. No database schema or migration.

## 3. Pros & Cons

The Codex fix is small, deterministic, and directly reproduces a user-visible
failure. Normalizing the active target fixes a separate reproducible diff gate.
The Antigravity prevention preserves capabilities and safety but remains model
instruction adherence until measured. A claim of complete resolution without
tool-choice enforcement or a reproduced denial would be unsupported.
