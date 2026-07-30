# Compiler Proposal: Small Deterministic Scanners and Explicit Generation Sets

Date: 2026-07-30 | Agent Persona: Lead Architect

## 1. Core Logic & Implementation

- Replace destructive regex deletion with length-preserving masking.
- Use a small fenced-code scanner that accepts a closing fence of the same
  character with at least the opening length and masks an unclosed fence to EOF.
- Keep the closed syntax set; add a bounded inline Markdown-link scanner only
  for balanced destination parentheses and angle destinations.
- Reject matches whose opener is backslash-escaped and reject numeric-only tags.
- Make exact-resolution stages tri-state: absent, unique, ambiguous. Ambiguity
  stops resolution rather than falling through to a later alias.
- Normalize parent-relative candidates lexically and reject only candidates
  that escape the vault.
- Treat `.md` and `.markdown` as Markdown note suffixes in extraction,
  inventory, endpoint typing, and compiler dispatch.
- Store the deterministic authored relation-id set in the existing generation
  `audit_json`. On DB-only republish, carry the set only when the source
  fingerprint is unchanged; otherwise retire it fail-closed.
- During sync, reconcile against the winner generation's recorded relation set:
  reassign shared rows to the winner and retire only loser-exclusive rows.
- Record newly active relation ids/endpoints so affected community reports can
  retire before serving; refresh search after explicit source deletion.

Pseudocode:

```python
winner_ids = set(parse_audit(winner).authored_relation_ids)
for relation_id in winner_ids & existing_authored_ids:
    set_generation(relation_id, winner.id)
    compile_lifecycle(relation_id)
retire((loser_owned_ids - winner_ids))
retire_reports_touching(endpoints_of(newly_active_ids))
```

## 2. Pros & Cons

Pros:

- No schema change and no parallel authored-edge store.
- The winner generation becomes the durable source of truth for exact relation
  membership, eliminating row-clock/generation-clock disagreement.
- Scanner scope remains limited to the already-documented syntax.

Cons:

- `audit_json` gains an internal field and needs backward-safe parsing.
- Length-preserving masking and balanced destination scanning add more code than
  the original regexes, so tests must pin the closed boundary tightly.
- Precise report invalidation needs endpoint membership lookup.
