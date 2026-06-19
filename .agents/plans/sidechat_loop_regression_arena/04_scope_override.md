# Round 4 — User Scope Override (2026-06-19)

The Arena consensus (rounds 01–03) landed on a **minimal, prompt-only** fix:
add a pure prompt helper, append it for latest-turn Markdown edit requests, no
hard enforcement, no UI changes, no wider triggers. The user reviewed that plan
and explicitly **rejected the minimal scope**, selecting all four expansions:

1. **Add parser / hard enforcement** — the loop must be enforced at runtime, not
   merely requested in the prompt. A response that proposes edits without the
   review loop must not flow straight into the Diff Viewer.
2. **Widen trigger conditions** — apply the contract beyond "latest-turn
   Markdown edit with an editable target": any editable selection, any open
   Markdown target, edit-intent requests, and multi-turn edit continuations.
3. **Make phases user-visible UI** — render Analysed/Reviewed/Updated/Reviewed
   as distinct observable sections in the sidechat, not just text the model emits.
4. **Rethink scope/approach** — treat this as a vertical slice of the broader
   prompt-architecture refactor (roadmap item 6) rather than a throwaway patch.

## Resolution

The red-team's original objection (round 02) was that hard enforcement risks
trapping providers that cannot comply, and that UI work balloons scope. Both are
addressed in the revised master plan:

- Enforcement is **firm but escapable**: the default Review/Apply path is
  blocked for non-conforming responses, but an explicit **Override & review
  anyway** action prevents a dead end, and a **Re-run with loop** action lets the
  user cheaply retry. This satisfies "explicitly halt before mutating files"
  without bricking non-compliant providers.
- Scope is bounded to **one composable prompt block + one validator + one
  renderer hunk + a gated Diff Viewer entry point**. The full prompt
  registry/builder refactor and popover inheritance stay deferred to item 6.

Consequence: this is no longer a patch. It is a **Minor** feature release
(**v0.14.0**) with new user-facing behavior, UI, and runtime enforcement. The
master plan's non-goals that previously forbade hard-blocking, wider triggers,
and UI changes are intentionally reversed by this override.
