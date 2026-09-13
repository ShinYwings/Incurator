# Producer-to-Chat Handoff: Concrete Route Closure

Date: 2026-09-13 | Bounded follow-up to `04_session_producer_design.md`

The user chose: **"Protect saved chat links too; retain diagnostics while those
chats exist"**. This document closes the implementation shape at the actual
plugin/backend boundaries. It does not claim the new transport or protocol is
implemented, nor that provider subprocess environment forwarding has been
tested. No application code or live vault data was changed for this audit.

## Recommendation

Keep the existing full session representation and add a narrow, durable
diagnostic attachment channel. A chat turn is saved with its exact session ID,
assistant-message ID and a new turn ID **before** an Incurator-capable provider
is launched. A backend prompt producer publishes complete portable evidence
to that saved turn while its ordinary local producer scope is still alive.
That publication is a real diagnostic attachment of a saved chat, not an
unacknowledged delivery lease. The plugin renders the attachment's PTR links
and carries the same full evidence in its session representation.

This requires neither a permanent pin on every prompt nor an append-only log
of every full transcript revision. A narrow immutable evidence receipt is
needed for routes where the plugin cannot receive a full MCP result. Complete
capsules in structured direct responses remain useful, but cannot be the only
handoff mechanism across all current providers.

The receipt and its accepted session witness are the recoverable publication.
An eagerly inserted SQLite `session_id → trace_id` row alone is insufficient:
session JSON and SQLite/sync arrival are not atomic, and that row contains no
diagnostic bytes if retention has already evicted the remote copy. Eager DB
owners can be an index of accepted attachments, but they are not the sole
source of ownership or recovery.

## Audited route matrix

| Route | Actual boundary | Required implementation |
|---|---|---|
| Ollama/DeepSeek streaming with Incurator MCP | `LLMClient.streamChat` calls `mcpManager.callTool` at `LLMClient.ts:1438`; it currently keeps only `result.content[].text` | Pass trusted per-request chat context in MCP request `_meta`, consume typed evidence before flattening text, emit attachment metadata to the sidebar. |
| Claude CLI streaming | `processClaudeJsonLine` reads `tool_result` at `LLMClient.ts:1966`, then `formatMcpToolResultForDisplay` truncates its representation | Consume any typed evidence before formatting, and use the durable receipt as the authoritative handoff/recovery route. Claude's `--mcp-config` already gives a concrete per-invocation config path. |
| Codex CLI streaming | `processNativeLine` and `CliAnswerStream` expose answer text/status, not a complete MCP result | Use the scoped backend receipt. Pass Incurator MCP context through per-call `-c` configuration; never depend on a model repeating capsule JSON. |
| Antigravity CLI streaming | The same native-stream path summarizes tool status and answer; MCP registration is in shared `~/.gemini` registries | Use the scoped backend receipt. Process-specific context must be forwarded by the launched MCP process without putting a turn ID into the shared registry. Actual inherited-environment behavior is a required binary integration test below. |
| Non-streaming CLI completion | `complete` reaches `completeViaCli`; it can currently default to full tools | Carry the optional scoped context through this path too. Sidebar-owned calls attach to the sidebar's turn; ordinary inline/popover calls have no saved-chat owner. Existing non-`auto` tool policies remain authoritative. |
| Direct backend JSON calls | `IncuratorClient` normalizes known fields and otherwise drops new evidence; `BackendJsonRunner` currently accepts only args and stdin | Add an optional request context to the internal runner, pass it in per-process environment, and retain the complete evidence field in result normalization. Cover `plugin_api/query_api.py` and the `wiki plugin correction propose` result boundary. |
| Manual or legacy saved PTR links | Existing `ChatMessage` contains no structured prompt-evidence attachment; links can occur in text | Preserve the text, resolve complete evidence when available, and represent genuinely missing historic evidence explicitly. Do not infer a new run's successful protection from a bare ID. |

`shouldUseCli` currently returns false only for Ollama and DeepSeek. Claude,
OpenAI/Codex and Antigravity take the CLI path even though older API adapter
code remains in this file. The implementation must test reachable routes, not
assume every provider uses the direct MCP tool loop.

No external, unrelated MCP server becomes an Incurator diagnostic producer
merely because its name contains "incurator". The protocol requires the
configured Incurator backend to advertise and validate the attachment contract.

## Exact request and response surfaces

These names define new APIs, not existing functions:

```typescript
interface ChatDiagnosticContext {
  contractVersion: 1;
  vaultId: string;
  sessionId: string;
  turnId: string;
  assistantMessageId: string;
  launchId: string;
}

// Add an optional `chatDiagnostics` field to the existing options, preserving
// the current Promise<string> result and the current abort/tool-policy behavior.
LLMClient.streamChat(messages, onChunk, {
  toolPolicy, signal, chatDiagnostics,
});
LLMClient.complete(messages, {
  model, toolPolicy, signal, chatDiagnostics,
});

// This is transport metadata, not an LLM-controlled tool-schema argument.
MCPManager.callTool(server, tool, args, { chatDiagnostics });
MCPClient.callTool(tool, args, { chatDiagnostics });
// Emit params._meta["incurator/chat-diagnostics"] in tools/call.
```

The installed Python MCP SDK supports this shape: `RequestParams.Meta` allows
extra fields, and `Context.request_context.meta` exposes them. Backend tool
handlers can therefore accept an injected `Context` and derive a request-scoped
value without changing the public LLM argument schema. Do not mutate a module
global "current session": a persistent MCP server may receive concurrent calls.
Use an explicit argument into the producer scope, or a properly reset
`ContextVar` at the request boundary, with tests for concurrent isolation.

For direct backend process calls, extend `BackendJsonRunner` with a third
optional options argument holding this context. This keeps normal CLI arguments
and stdin data separate. Do not splice context JSON into a shell command.

The backend's narrow attachment APIs are:

```python
validate_chat_diagnostic_context(paths, context) -> AcceptedChatTurn
capture_prompt_evidence(conn, trace_ids) -> list[PortablePromptEvidence]
publish_chat_diagnostic_receipt(paths, accepted_turn, operation_id, evidence)
```

Validation binds the context to the already-saved turn and resolved vault,
rejects terminal session deletion, and validates IDs before constructing any
path. The plugin creates an opaque launch descriptor under the scoped local
cache so external processes can carry a small token/path instead of arbitrary
chat content in environment variables. Its descriptor identifies the saved
turn; it contains no provider credentials. A descriptor for vault A cannot
silently attach a result from the globally configured server for vault B.

`PortablePromptEvidence` is the shared fleet/lifetime representation, including
all recorded diagnostic fields and explicit provenance identity information.
It is not the smaller camelCase projection returned today by
`wiki plugin prompt trace`. The database does not currently store raw prompts
or raw model output, so "full" here means all actual recorded diagnostics;
this change must not claim to reconstruct those absent raw bodies.

## External provider launch configuration

1. Add one explicitly named environment key, for example
   `INCURATOR_CHAT_DIAGNOSTIC_CONTEXT`, to the environment of this specific
   provider child. `getAugmentedEnv` already merges per-command environment
   values; use that existing boundary. Do not change the plugin process's
   environment globally.
2. Claude: make its MCP config file unique per launch and give only the
   configured Incurator server the context explicitly in its `env`. The current
   fixed `claude_mcp.json` file must not become a shared mutable carrier for a
   per-turn ID. Keep the file through child/MCP shutdown, then clean up the
   non-authoritative launch files.
3. Codex: local `codex --help` confirms that `-c key=value` overrides nested
   configuration. Build per-call MCP environment overrides (or an explicit
   `env_vars` allowlist for this key) for the configured Incurator server. Do not
   write the context into `~/.codex/obsidian.config.toml`. Quotes/server-name
   segments must be encoded as TOML values/keys, not shell interpolation.
4. Antigravity: local `agy --help` and `agy mcp add --help` show shared registry
   registration and static `--env KEY=value`; there is **no documented per-call
   MCP config flag in this installed binary**. The viable first implementation
   is process-environment forwarding into the registered stdio Incurator
   launcher, with no per-turn registry mutation. Add a backend initialization
   receipt proving the effective launch token and resolved vault. If the actual
   CLI/daemon strips or caches that environment, this design must be revised
   before claiming route coverage; a mock `spawn` test does not establish it.

The descriptor is read at Incurator server startup, then held as immutable
process context. An explicit direct-MCP `_meta` context is request-scoped and
must agree with any fixed launch context. Missing context on a normal standalone
MCP call remains legitimate; an explicitly scoped plugin launch that loses its
context must produce a visible integration error instead of claiming the chat
was protected. An ephemeral/no-tools request must never acquire a chat owner
implicitly from a previous foreground request.

Do not manufacture a fallback by asking the model to remember `sessionId`,
guessing the active session from the most recently modified file, walking a PID
tree to choose an owner, serializing all global provider work, or rewriting a
shared registry with the latest turn ID. Those approaches do not preserve exact
ownership for two simultaneous vaults/requests.

## Durable attachment choreography and recovery

1. The sidebar snapshots **its own** session identity and persists the user
   message plus an assistant placeholder carrying the turn ID. A successful
   saved-turn commit is the prerequisite for launching trace-producing tools.
   The existing send path already persists before launch; extend it to include
   the assistant/turn witness and make save failure observable to the caller.
   Continue/retry rounds get new launch IDs under the same saved turn, or a new
   explicitly saved turn when that is the actual user operation.
2. The backend validates the supplied turn and enters the ordinary local
   producer scope. All recursive or multi-prompt runs remain protected by that
   scope through completion and attachment publication. Completing a run does
   not release its local ownership early.
3. Before returning a trace-bearing tool response, capture its complete
   evidence while protected, then atomically publish a uniquely named immutable
   receipt under the vault's session-evidence namespace. The receipt contains
   version, vault/session/turn/message identity, operation ID, evidence, and a
   digest. It need not duplicate the entire transcript or the model's final
   answer. A raw temporary file is not a publication.
4. The receipt is a diagnostic attachment of that saved turn. The plugin loads
   it, exposes PTR links in that message's existing trace affordance, and merges
   the complete evidence into its session-scoped capsule map before its normal
   save resolves. A hidden provider result is therefore still inspectable and
   correctly associated with its chat, including after a provider crash.
5. The DB owner index is installed from accepted saved-turn attachments under
   the shared fleet rules. The producer scope may end after durable publication;
   there is no wait for a plugin acknowledgement, no timeout-based pin expiry,
   and no permanent pin on an unidentifiable response.
6. Session readers, GC, sync import and prompt lookup reconcile the diagnostic
   attachment channel. A receipt arriving after a retention eviction restores
   its complete row if the session/turn owner is accepted; an ordinary explicit
   prompt deletion keeps the separate precedence defined by the fleet plan.

The saved-turn attachment is a deliberate ownership boundary: each completed
Incurator diagnostic used in that turn becomes inspectable saved chat evidence,
including a tool result omitted by the provider's final prose. This is stronger
than preserving only IDs a model happens to repeat. It does not attach unrelated
background compiler runs or a whole MCP server's lifetime to the chat.

An unfinished provider turn with already-published receipts is not an abandoned
execution pin: the saved user turn and its inspectable diagnostic attachments
are real retained data. Deleting the session releases them through the same
terminal deletion witness as other saved links. A descriptor/placeholder with
zero published traces owns zero prompt records. Backend process death before
receipt publication leaves only the ordinary producer scope, which the local
liveness protocol can reap. This is the critical distinction that permits a
finite unreferenced-prompt cap without expiring saved diagnostics by age.

On restart, a receipt is matched to its explicit saved turn. It is never copied
into whichever session is currently selected. A deleted session rejects late
receipts and releases its attachments. A malformed or missing session snapshot
does not prove deletion; preserve the receipt and report recovery failure. A
valid snapshot that lacks the original turn is a whole-session merge/disposition
case governed by the session consensus, not an excuse to invent a replacement
assistant message under an unrelated turn.

Receipt compaction is permitted only after its complete evidence and identity
are durably represented in an accepted session capsule/attachment snapshot with
the necessary winner witness, or after terminal session deletion. Compaction
must not delete the last copy when a later snapshot can overwrite the capsule
map. The session consensus must preserve the attachment set monotonically for
the life of a session, or retain the independent receipt as authority. This is
bounded by actual saved diagnostics, not the number of transient file revisions.

Offline saving of an already-received reply uses capsule bytes/receipts and the
Obsidian adapter only; it must not require a live backend process merely to save
the transcript. Starting a new Incurator tool call naturally requires its
backend, but an unavailable backend must not prevent ordinary no-tool chat
saves. Manual/historical links with genuinely absent evidence remain text plus
an explicit unresolved diagnostic state; no hidden background fetch fabricates
their payload or blocks all other chat content from saving.

## Precise implementation files

- `plugin/src/types.ts`: typed portable evidence, attachment identity and saved
  turn metadata; `MCPToolResult` metadata and `StreamChunk` attachment event.
- `plugin/src/ui/chat/ChatSidebarView.ts`: save explicit owner/turn before launch,
  pass scoped options through `streamOneRound`/continuations, attach metadata
  before rendering and save by the view's captured session ID.
- `plugin/src/agent/llm/LLMClient.ts`: propagate options through both stream and
  complete branches, capture direct/Claude metadata before display conversion,
  per-launch CLI context and config, harvest durable receipts on completion,
  error and cancellation without reassigning them to another request.
- `plugin/src/agent/mcpClient.ts`: optional per-call `_meta` transport; never set
  mutable manager-wide context for a persistent connection.
- `plugin/src/agent/incuratorClient.ts` and the backend JSON runner wired in
  `plugin/main.ts`: preserve response evidence and pass per-invocation context.
- `plugin/src/utils/sessionData.ts` / `sessionStore.ts`: preserve capsule and
  attachment identity in sanitization, merge, clone and save. Reconcile immutable
  receipts using the same accepted session/tombstone rules as backend pruning.
- `backend/src/curator/mcp/server.py`: request-context binding for actual
  `curator_query`, `curator_explore`, `curator_propose_correction`, prompt-trace
  lookup and any response returning an existing PTR. Read-only `fetch_context`
  does not automatically manufacture a prompt record; inspect its actual
  returned closure. The shared response helper covers existing references too.
- `backend/src/curator/plugin_api/query_api.py` and
  `backend/src/curator/commands/plugin.py`: full diagnostic capture at direct
  JSON query/correction/trace boundaries, before producer ownership ends.
- The planned backend prompt-lifetime/session-state modules: shared capture,
  receipt validation/publication/reconciliation, and references used by
  `gc.py` / `db_sync.py`. A second independent capsule decoder is not permitted.

## Adversarial tests required before merge

1. Two sessions in two vaults issue concurrent direct MCP requests through one
   persistent manager; complete in reverse order and verify exact attachment
   owner identity. The Python Context metadata path must be exercised through
   real JSON-RPC, not direct function arguments alone.
2. For each external CLI route, prove the token reaches the real launched
   Incurator process and matches the vault. For Antigravity include two
   simultaneous launches, a pre-existing CLI/daemon, cancellation, and a second
   request reusing a registered server. A fake child accepting the injected env
   is insufficient to prove the provider forwards it.
3. Force CLI output to contain only an answer/status with no full tool result;
   verify the saved receipt still supplies every recorded diagnostic field.
4. Pause after provider completion, after capsule capture and after receipt
   rename; run local GC/import each time. Verify all fields survive when the
   accepted saved chat owns them, and ordinary abandoned local runs become
   reclaimable when their true liveness ends.
5. Terminate plugin/provider/backend independently before/after every handoff.
   Restart with another session selected; the original saved turn receives its
   own diagnostic links, and there are no ownerless durable execution pins.
6. Fail the initial saved-turn commit and verify no scoped provider launches.
   Fail the later backend/index process and verify a received transcript still
   saves offline with its complete capsule bytes.
7. Delete/prune the session while a tool runs; late receipt cannot resurrect it.
   Link one trace from two sessions, delete one, and verify the survivor retains
   full evidence. Delete the final session and verify cap reclamation resumes.
8. Exercise immutable receipt corruption, duplicate IDs with equal/different
   digests, missing session file, delayed owner/receipt arrival, and conflicting
   whole-session winners. Never translate an unreadable store into no owners.

The data-flow design is implementable with the existing Python/TypeScript
boundaries. The actual Antigravity environment-forwarding test is explicitly
unproven at this design stage. If it fails, the smallest viable alternative is a
provider-supported per-request MCP transport/configuration facility discovered
and tested on that binary; dropping Antigravity retention coverage or blocking
all offline chat saves is not an authorized substitute.
