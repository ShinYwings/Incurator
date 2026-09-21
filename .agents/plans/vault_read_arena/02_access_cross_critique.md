# Access adversary cross-critique of CLI launch proposal

Date: 2026-09-21. Reviewed `01_launch_proposal.md` against the current command
builder, outer sandbox profile, installed CLI help, and independent native nesting
probe recorded in `01_access_adversary.md`.

## Agreement after independent comparison

The proposals independently converge on one native Codex sandbox, preserving
`workspace-write` for sidechat and `read-only` for ephemeral surfaces. The measured
failure occurs during the second sandbox application, while a single outer
profile can read the same note. Neither loosening vault read permissions in the
outer profile nor changing a filename addresses that failure.

The launch proposal correctly treats removal of the outer wrapper and replacement
of Codex's current broad `--add-dir` set as inseparable. Otherwise Zotero becomes
writable. Clearing inherited writable roots and excluding broad `/tmp` are also
part of preserving the existing boundary, not optional hardening unrelated to the
bug. Keeping `approval_policy=never` prevents permission prompts without enabling
an otherwise denied operation.

The proposal explicitly preserves native editing, reference reads, ephemeral
semantics, and the separate lifetime worktree. I agree this is the smallest
stable design that repairs the measured launch defect without silently reducing
the product's existing capability.

## Required clarifications and adversarial checks

### 1. Dispatch on the actual launch implementation

The root cause belongs to the `codex` executable path. The current switch shares
that path across OpenAI, DeepSeek, and Ollama CLI modes. A guard written only as
`provider === "openai"` leaves the identical nesting bug in the other two paths.
Behavior tests should exercise those labels explicitly, in addition to confirming
that Claude/AGY still receive their outer wrapper. This is an implementation
constraint within the proposed design, not an additional product feature.

### 2. Image roots must not become a new permission expansion

The proposal allows the scoped chat image directory as a write root "when
necessary". Image files are already under the CLI cache cwd, and native reads do
not require a writable root. Therefore this flag is normally redundant. Keeping
it for compatibility is acceptable only if it stays a plugin-created scoped cache
directory and never derives from an arbitrary attached source-image path.
Ephemeral image turns must still get no added write directories. Do not generalize
image attachments into external-source write grants while removing the wrapper.

### 3. Native-only is a boundary change that must be stated accurately

The previous outer profile constrained the whole child process tree. Native Codex
containment constrains tool execution. The proposal acknowledges this distinction;
the final docs must also do so and must not continue saying that every CLI process
is OS-wrapped or that native `--add-dir` is only read visibility. Existing external
MCP servers remain their documented separate trust boundary. No global bypass flag
is needed to remove the incompatible redundant layer.

### 4. Native enforcement evidence is a release gate, not a string assertion

Both agents found that the diagnostic `codex sandbox` invocation does not establish
the required `exec` policy. One invocation rejected absent named profiles; another
continued to deny a write despite a workspace-write argument. Neither result is
proof that the intended actual launch will retain vault editing.

The parent should run the bounded actual `codex exec` probe already proposed,
using disposable inputs, the generated launch argv, and a disposable inherited
configuration containing an unrelated writable root. Inspect tool outcomes and
actual fixture state. The model saying "writes are blocked" is not sufficient;
a denied write should have an attempted operation with a failed result, and the
outside files should remain unchanged. Likewise a real vault write must be
observed in the allowed fixture and a read must return a unique source marker.
Do not regard a claimed correct final answer with no successful native tool as
proof of this sandbox repair. The parent should avoid repeating the diagnostic
subcommand experiment as if adding more legacy flags resolves the evidentiary gap.

### 5. Reference nesting is a pre-existing topology caveat

The proposal correctly notices that a Zotero directory inside the allowed vault
would overlap the vault write grant. The old outer wrapper also allowed that
layout. The fix must preserve the common external-reference topology, but cannot
honestly promise that every possible nested or overlapping configured reference
is read-only. Inspect the actual configured roots before making a user-facing
unqualified claim. A new arbitrary carve-out system is out of scope for this
launch hotfix unless the user's actual topology requires it.

### 6. The user's broad read expectation remains accepted work

The quoted error is the current Codex failure, so a Codex patch can close that
incident. Claude's explicit text-only native Read prohibition is nevertheless
known to violate the user's broader expectation. The follow-up is not optional
wording: record it as an actionable provider-parity item in the roadmap and make
clear that the present release fixes the measured Codex launch. AGY's prompt
wording should also be examined because it currently directs missing-evidence
retrieval to MCP and only explicitly authorizes native image reads.

Do not defer indefinitely by calling the old Claude restriction merely a
contract that cannot change; the latest user request authorizes vault access.
The repository's release criteria justify a separately planned capability change,
with preserved shell/write denials and actual native-read qualification. They do
not justify ignoring the requirement or requiring the user to repeat it.

## Disposition

Accept the launch proposal subject to the concrete runtime release gates above.
No unresolved architectural fork requires user input. The remaining uncertainty
is empirical: whether the installed native `exec` applies the explicit roots and
flags exactly as intended. A failing probe should stop shipment and identify the
configuration or runtime cause; it must not trigger a retry with unrestricted
permissions. This critique proposes no application edits or production changes.
