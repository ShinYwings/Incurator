# Defense of the Revised Authored-Topology Design

Date: 2026-07-30 | Agent Persona: System Synthesizer

## 1. Vulnerabilities Resolved

The proposal is accepted only with the following revisions:

1. `active` means “authoritative for its edge class,” not one universal proof
   rule. Extracted relations retain the independent-lineage threshold; authored
   relations require an exact visible source structure, canonical endpoints,
   and the current successful generation.
2. Authored relations can influence topology but never populate extracted
   factual supports. Community reports must separate partition dependencies
   from cited factual relation ids.
3. The implementation is incomplete until ordinary explore traversal excludes
   quarantined/retired relations and graph status uses the same authoritative
   view.
4. Deterministic ids are mandatory for F9-created entities and relations.
   Existing extracted identity behavior is not broadened.
5. The parser is a closed syntax set with masking and an exact-one resolver.
   Ambiguity and unsupported forms emit no edge.
6. Reconciliation occurs only inside the successful compiler publication
   transaction. Failed compilation preserves the previous generation.
7. The real production boundary replaces the row-count-only F9 oracle.
8. Source edit, delete, rename, unchanged rebuild, and two-replica convergence
   are release gates, not follow-up polish.
9. General entity alias lifecycle, plugin-specific citation grammars, fuzzy
   resolution, and a new graph table are explicitly excluded.
10. Unrelated uses of “F9” are renamed so the canonical case remains
    unambiguous.

## 2. Final Consensus

Implement a deterministic note-native compiler inside the current graph schema.
The feature owns four relation types (`links_to`, `embeds`, `tagged_with`,
`property_ref`) and three endpoint types (`vault_note`, `vault_asset`, `tag`).
It is source-owned by compiler generation, reconciled atomically, and consumed
only through lifecycle-aware topology views.

No schema migration is planned. If implementation proves that source ownership
cannot be made correct with existing `generation_id` and source-generation
joins, stop and return to contract approval instead of adding a hidden schema
workaround.
