# Critique on Deterministic Authored Topology

Date: 2026-07-30 | Agent Persona: Red Teamer / Schema Guardian

## 1. Vulnerabilities & Flaws

1. **“Human-authored” is not equivalent to “factually true.”** Activating an
   authored relation under the extracted two-lineage rule would either
   quarantine every useful link or falsely promote it as corroborated evidence.
2. **The current F9 oracle can give a false sense of completion.** It never
   invokes the production compiler, so adding real logic alone cannot retire
   the strict xfail.
3. **Random graph ids are a sync trap.** Independent replicas can compile the
   same link into distinct rows, which survives ordinary last-writer-wins sync.
4. **Parse-before-publish is not enough.** If old relations are retired before
   the enclosing compiler transaction succeeds, a provider failure can erase
   the last known-good topology.
5. **Naive regex parsing creates false edges.** Code examples, comments,
   external URLs, `../` escapes, ambiguous basenames, and hidden `.curator`
   paths must fail closed.
6. **Heading/block/pipe variants can fragment identity.** Treating
   `[[A#H]]`, `[[A^b]]`, or `[[A|label]]` as different notes would create
   duplicate entities.
7. **Existing community reports assume active means corroborated.** Letting
   authored rows flow unchanged into reports would cite a structural link as a
   factual source.
8. **Lifecycle drift can leak stale rows.** Explore currently reads relations
   without filtering lifecycle. Retirement is meaningless if consumers ignore
   it.
9. **Alias semantics can balloon scope.** Creating `entity_aliases` or semantic
   merges for every frontmatter alias entangles F9 with the unresolved general
   entity-resolution program.
10. **Deletion and rename are more dangerous than insertion.** A happy-path
    compile test does not prove stale outgoing edges disappear, incoming edges
    resolve safely, or source deletion remains transactional.
11. **A new relation table would duplicate graph truth.** It would require
    parallel traversal, sync, lifecycle, and materialization implementations.
12. **The term F9 is overloaded in later Plan C prose.** Leaving unrelated F9
    labels in hierarchy/fallback comments will corrupt future audits of the
    canonical Failure Atlas case.

## 2. Suggested Alternatives

- Keep one relation table but define two explicit lifecycle proof rules:
  structural presence for authored topology and verified independent lineage
  for extracted claims.
- Re-pin the oracle to the same publish function used by production and assert
  exact relation class/type/endpoint/lifecycle rather than a non-zero row count.
- Derive deterministic ids from canonical portable keys; do not change generic
  extracted ids.
- Compute the full authored set in memory and reconcile it inside the existing
  generation publish transaction.
- Build a resolver inventory that returns exactly one target or none. Never
  guess.
- Keep frontmatter aliases local to target resolution in this slice; defer
  semantic alias lifecycle.
- Split community topology inputs from report-evidence inputs and make that
  distinction explicit in tests and docs.
- Add edit/delete/rename/failure/sync convergence cases before the happy-path
  xfail is removed.
- Relabel unrelated later “F9” comments as their Plan C section identifiers.
