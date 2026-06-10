# Frontend/Architecture Proposal: Edge-Hardening, Not a Rewrite

Date: 2026-06-11 | Agent Persona: lead_architect (The Proposer)

## 1. Core Logic & Implementation

The DiffViewer engine stays. We add a small pure-helper layer and re-wire four call sites.

### A. Resilient SEARCH matching — new pure module `plugin/src/utils/editMatch.ts`
A single matcher used by ALL three apply paths (kills the divergence). Tiered, deterministic, no fuzzy-magic that could mis-target:

```ts
export interface MatchResult { start: number; end: number; matchedText: string; strategy: "exact" | "trimmed" | "whitespace-normalized" | "anchored"; }

export function findSearchBlock(haystack: string, search: string): MatchResult | null {
  // Tier 0 — exact (preserve today's behavior when it works)
  // Tier 1 — line-wise leading/trailing trim: compare search lines vs file lines
  //          ignoring each line's leading/trailing whitespace, but require the
  //          SAME NUMBER of lines and identical trimmed content in order.
  // Tier 2 — whitespace-normalized: collapse runs of intra-line whitespace to a
  //          single space for comparison only (apply still replaces the real span).
  // Tier 3 — anchored (multi-line search ≥ 3 lines only): match on the first and
  //          last non-blank trimmed lines as anchors; accept exactly one candidate
  //          span between them. AMBIGUITY GUARD: if >1 candidate, return null.
  // Returns the REAL character span [start,end) in haystack so replacement uses
  // the file's own text, never the normalized form.
}
```

Key invariants: (1) never guess when ambiguous (return null → today's honest "couldn't find" Notice, not a wrong edit); (2) replacement always splices the *original* span text, preserving the file's real whitespace; (3) one match per proposal — if the same SEARCH legitimately recurs, that is the caller's existing `split`-count concern, unchanged.

### B. Robust parsing — extend `extractMultiEditProposals` + a sanitizer
- Make markers tolerant: allow `>>>>` OR `>>>> REPLACE` OR EOF-of-block as the closer; tolerate `=======`/`====`. Trim a single trailing/leading blank line consistently.
- Add `stripDanglingEditMarkers(rendered: string): string` (pure, in `textUtils.ts`) run in the post-stream render path: removes any orphan `<<<<`, `====`, `>>>>` lines that survived a failed parse, so they never display as note text (symptom 2).
- Strengthen `collapseStreamingEditBlocks` to also cut on a lone `<<<<` / `>>>>` opener variant during streaming.

### C. Immediate diff — drop the click gate
- In `renderInlineMultiDiff`, after the message finishes streaming and proposals parse, **auto-invoke `reviewAssistantEdit(msg)`** once (guarded by a `msg.diffAutoOpened` flag to avoid re-opening on re-render). Keep the pill, but relabel it "Re-open diff" / "Opened" — it becomes a re-entry affordance, not the only entry. Auto-open only when the target file can be resolved to an open/openable `MarkdownView`; otherwise fall back to the pill (no surprise tab-steal).

### D. Retire the on-disk artifact (default)
- Flip `DEFAULT_SETTINGS.editArtifactEnabled` to **false** and relabel the setting "Also save a diff note under 00_System/Agent Diffs/ (legacy)". Default path writes nothing; the in-memory DiffViewer is the source of truth. Keep the helper + setting for users who relied on it (no hard removal, no data loss).

### E. Edit scope — prompt constraint (cheap, high-leverage)
- Add one rule to the edit instruction block in `systemPrompt.ts`: "The REPLACE body MUST contain only the minimal changed region plus the few surrounding context lines needed to anchor it. When the user references a specific section/number/heading of your previous answer or the note, target ONLY that section. Never paste an entire chat answer as a REPLACE." Mirror in `editableSelectionInstruction`.

### F. Always-visible hunk counter
- In `buildToolbar`, render the `n/total` counter even when `hunks.length === 1` (show "1/1"); keep arrows disabled/hidden for a single hunk.

## 2. Pros & Cons
- **Pros**: minimal blast radius; all new logic is pure + unit-testable; no DiffViewer rewrite; ambiguity guard prevents *wrong* edits (the worst outcome); reversible (artifact kept behind a flag).
- **Cons**: tiered matcher adds complexity; anchored tier could still mis-bound on pathological repeats (mitigated by the >1-candidate → null guard); prompt-only scope fix depends on model compliance (accepted: it's the only lever short of post-hoc diffing the answer, which is out of scope).
