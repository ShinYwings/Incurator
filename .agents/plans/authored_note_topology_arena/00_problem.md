# F9 Briefing: Authored-Note Topology Is Absent

Date: 2026-07-30
Target: v0.39.0
Canonical case: `docs/specs/failure_atlas/cases/F09.yml`

## 1. User Outcome

Incurator must treat the structure a human explicitly writes in a Markdown note
as graph topology. Wikilinks, note/asset embeds, tags, and frontmatter
references must influence graph traversal without being confused with
LLM-extracted factual claims.

The desired end-to-end behavior is:

1. compile a registered visible Markdown source;
2. resolve only exact, unambiguous vault targets;
3. persist deterministic `edge_class='authored'` relations atomically with the
   successful compiler generation;
4. use active authored relations for graph topology and navigation;
5. keep factual support, citations, and corroboration rules extracted-only;
6. retire stale authored relations after edits, renames, or source deletion;
7. converge to one logical topology when the same vault is compiled or synced
   by more than one device.

## 2. Reproduced Defect

The canonical F9 baseline and strict xfail oracle are in
`backend/tests/test_failure_atlas_repro.py`. The focused run on 2026-07-30
reported one passing baseline and one expected failure: authored wikilinks
produce no topology record.

The current oracle is weaker than the intended contract. It stores L1 spans and
then counts rows without invoking the real compiler. A correct production
implementation would therefore not necessarily make the oracle pass. The
oracle must be re-pinned to a real deterministic compiler boundary before F9 is
retired.

## 3. Current Architectural Constraints

- Schema v13 already distinguishes `graph_relations.edge_class` values
  `authored` and `extracted`, and already stores lifecycle, topology weight, and
  compiler generation. No schema migration is justified by the defect.
- `graph_relation_supports` represents extracted KNU-backed corroboration. It
  must not be populated merely because a human wrote a link.
- The existing lifecycle compiler requires two independent verified source
  lineages for an active relation. That rule is correct for extracted claims
  but wrong for an exact authored structural edge.
- Connected components consume active graph relations, while community reports
  currently assume every active relation has extracted factual supports.
- Explore paths currently traverse relations without a lifecycle filter, so
  quarantined or retired rows can affect user-visible paths.
- DB sync identifies `graph_entities` and `graph_relations` by row id. Random
  ids would allow two devices to create duplicate authored topology.
- A failed staged compile must leave the previously published graph unchanged.

## 4. Syntax and Resolution Scope

The compiler must cover Obsidian core structures that have deterministic vault
meaning:

- body `[[wikilinks]]`;
- note and asset `![[embeds]]`;
- internal Markdown links and image embeds;
- body tags and YAML `tags`;
- quoted or list-valued frontmatter wikilinks.

Pipe display text, heading and block fragments, and image sizing are presentation
details, not separate graph endpoints. `aliases` may resolve a target but do not
create edges by themselves. Backlinks are derived from incoming traversal, not
stored as duplicate reverse edges.

Plugin-specific citation grammars such as Pandoc `[@key]` are outside this
slice unless they resolve through an ordinary internal vault link.

## 5. Measured Vault Evidence

A read-only scan of the user's `03_Notes` directory found 17 Markdown files:
54 wikilinks across 7 files, 27 embeds, 18 heading targets, 7 block targets,
15 pipe aliases, 10 body tags, 56 internal Markdown links, and frontmatter
`tags`/`aliases` in 13 files each. No frontmatter wikilinks or Pandoc citation
groups were observed. These measurements define fixtures; production files will
not be modified for validation.

## 6. Required Planning Questions

1. How can authored topology be exact and deterministic without creating a
   second graph subsystem?
2. How should authored lifecycle differ from extracted factual corroboration?
3. How do edits, renames, deletion, failed compilation, and cross-device sync
   converge without orphan or duplicate edges?
4. Which downstream consumers may use authored topology, and which must remain
   extracted-only?
5. How can the parser fail closed on code examples, hidden/control paths,
   ambiguity, traversal attempts, and unresolved external targets?
