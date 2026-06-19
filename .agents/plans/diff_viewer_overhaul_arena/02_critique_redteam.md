# Critique on both proposals

Date: 2026-06-19 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

### Against the lead_architect (triage-first)

- **The triage table is a hypothesis dressed as a plan.** If P0 reproduction
  shows Bug 1/6 are NOT actually fixed in some provider/OS combo, the whole phase
  list is wrong. The plan must make P0 a HARD GATE that can re-scope P1+, not a
  formality. Require the triage table to be committed and the user to confirm the
  LIVE set before any fix code — otherwise we'll "fix" Bug 11 and discover Bug 1
  regressed under a long document.
- **Bug 5 "it's just CSS" is optimistic.** The added lines are `block:true`
  widgets injected via `coordsAtPos`/decoration. A true unified gutter where the
  green line aligns to the same wrap/indent as buffer text is NOT free — widget
  blocks don't inherit CM6 line-number gutters. Claiming "CSS-bounded" risks a
  rabbit hole. Either commit to the widget look-and-feel as-is (and tell the user
  it's not pixel-vscodium) or budget real CM6 work. Don't pretend it's trivial.
- **Bug 11 docked-fallback** changes the toolbar's positioning model
  (`document.body` fixed → editor-relative). That touches teardown: the current
  `close()` removes `toolbarEl` from body. A relative bar parented to the CM
  scroller can be destroyed when the leaf re-renders, leaking listeners. Any
  re-parenting MUST reuse the singleton teardown, with a test.

### Against the state_sync_specialist (proposal state machine)

- **Stable proposal id via `hash(filepath|search|replace)` is fragile.** The
  matcher (`findSearchBlock`) deliberately tolerates whitespace drift, so the
  SEARCH text the agent emitted ≠ the text actually matched. If you hash the
  emitted search but later re-parse a slightly different emission (streaming
  re-render, LaTeX normalization), the id changes and the pill loses its status.
  Hash must be computed ONCE at finalize and stored, never recomputed from
  re-parsed content.
- **New persisted `ChatMessage.editProposals` is a schema change.** This pulls a
  "Minor update with migration" obligation into what could be a fix release. Old
  sessions in `sessions.json` lack the field; any code that assumes it exists
  will throw on reload. Must be strictly optional + derived-on-demand, and the
  plan must say so as a release gate.
- **Bug 4 "it's just framing" is half-true but under-tested.** The claim "agent
  reads on-disk truth so no desync" ignores the multi-turn case: the agent
  proposes edits in turn 1, the user accepts in the Diff Viewer, then turn 2's
  context is rebuilt — does the rebuilt context reflect the *accepted* file? If
  the open-tab content snapshot is cached from turn 1, the agent edits stale
  text. P0 must reproduce the accept→next-turn cycle, not just the propose step.

## 2. Suggested Alternatives

- **Make P0 a gated checkpoint with user sign-off on the LIVE set.** No fix code
  until the triage table is approved. This is the single most important guard
  against churning a stabilized module.
- **Split the milestone explicitly.** Tier A = reproduced LIVE defects with
  surgical fixes (3, 11, 2/9 race, 7). Tier B = the "redesign" asks (5 unified
  polish, 8/10 prompt determinism) that are either deferred to item 6 or need
  their own budget. Ship Tier A; only enter Tier B if P0 proves it necessary and
  the user approves the extra scope.
- **For Bug 4, prefer a derived (non-persisted) proposal status** computed from
  the live file content + matcher at render time (does the SEARCH still match? →
  pending; does the REPLACE already appear? → applied). This avoids the schema
  change entirely and is self-healing across reload. Only persist if the derived
  approach proves too slow on large messages.
- Reject any whole-module rewrite. The 675-line engine carries 34 documented bug
  fixes; a rewrite's regression surface dwarfs the LIVE defect set.
