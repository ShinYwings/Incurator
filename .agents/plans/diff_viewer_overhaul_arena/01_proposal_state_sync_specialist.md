# State/Sync Proposal: A Message-Scoped Proposal State Machine

Date: 2026-06-19 | Agent Persona: state_sync_specialist (Bugs 2, 4, 6, 9)

## 1. Core Logic & Implementation

The root cause uniting Bugs 2, 4, 6, and 9 is **the absence of an authoritative,
message-scoped record of each edit proposal's lifecycle.** Today:

- Proposals are re-parsed from `msg.content` on every render
  (`extractMultiEditProposals`), so there is no stable identity per proposal.
- `reviewFileEditProposals` re-applies *all* file proposals into a fresh
  `modifiedFullText` each call; the diff is recomputed from disk each time.
- The DiffViewer is a singleton with no back-reference to *which* proposal(s) it
  represents — so a second pill click silently re-points it.

### Proposed: `EditProposalState` per assistant message

Add a message-scoped map (keyed by a stable proposal id = hash of
`filepath|search|replace`) tracking:

```ts
type ProposalStatus = "pending" | "reviewing" | "accepted" | "rejected" | "not_found";
interface ProposalRecord {
  id: string;
  filepath: string;
  status: ProposalStatus;
}
```

Stored on the `ChatMessage` (new optional field `editProposals?: ProposalRecord[]`,
persisted), built once when the message finalizes. Pills read/write status from
this record, not from re-parsing. The DiffViewer is opened with the set of ids it
is reviewing, and on Accept/Reject it calls back to mark those ids.

### Bug 2 / 9 — strict 1:1 mapping + no race

- Each pill owns its proposal id(s). Clicking pill B opens the DiffViewer for
  B's file only (already filtered) AND marks B `reviewing`; the displayed hunks
  are exactly B's file's proposals.
- A module-level `reviewInFlight: Promise | null` guard serializes opens so the
  singleton can't be re-pointed mid-`show()`.

### Bug 4 — agent reads truth, never assumes

- The agent's belief that edits "applied" comes from the conversation lacking a
  signal. Two coordinated fixes:
  1. **Prompt wording** (reuse v0.14.0 post-edit REVIEWED phase): the assistant
     states edits are *proposed and pending human review*, never "applied."
  2. **Read-back tool truth**: when the agent later reads the file (via MCP /
     context), it sees the on-disk (un-accepted) content — which is correct,
     because nothing was written. The desync only existed when older code wrote
     to disk early; the inverted model already removes the disk-write race. The
     residual is purely conversational framing.

### Bug 6 — already structurally fixed; add a regression test

The inverted model never writes on open. The remaining "could not find" is a
*matcher* outcome (`findSearchBlock` returns null on drift/ambiguity), correctly
surfaced as a notice. Add tests pinning: (a) no `editor.replaceRange` is called
in `show()`; (b) a null match increments `failedCount` and writes nothing.

## 2. Pros & Cons

**Pros:** gives proposals stable identity → kills the whole Bug 2/9 class at the
root rather than patching symptoms; persisted status survives re-render and
session reload; agent-desync fix is framing + the already-correct no-write model.

**Cons:** adds a persisted schema field to `ChatMessage` (migration-light but
must be back-compat for old sessions: treat missing as derived-on-load);
proposal-id hashing must be stable across whitespace normalization or status
will desync from the pill; more state to tear down on session delete.
