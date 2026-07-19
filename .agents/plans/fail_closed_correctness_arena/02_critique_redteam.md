# Critique on Explicit Correctness Boundaries
Date: 2026-07-19 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

1. Treating every missing file as corruption would break legitimate first-run
   device setup. Absence and read-race failure must remain distinct.
2. Raising after peer A commits but peer B fails could mislead users into
   thinking nothing changed. Error text and tests must describe partial progress
   and idempotent retry semantics.
3. If the JSON CLI exits before emitting a parseable object, the plugin converts
   the failure to an unhelpful “Empty response”. The known-error envelope must be
   printed before human-only exit behavior is applied.
4. Merely removing `_archive_conflict`'s catch is insufficient if `autosync()`
   still populates `result.conflicts` before processing and UI labels every
   detected name “merged”. Only completed archives may enter the success list.
5. A tombstone delete can affect zero rows without error. That is legitimate
   when the row is already absent; tests must not equate rowcount zero with
   failure.
6. Centralizing policy resolution without semantic validation still allows an
   unknown route or contradictory policy to compile into defaults.
7. Strictly requiring list-only include/exclude would unnecessarily break the
   existing accepted scalar-string form.
8. A malformed `curate.yml` must fail before trace creation in both direct
   ContextService and QueryOrchestrator surfaces; testing only the private helper
   is too weak.
9. The 60-second plugin poll will retry a persistent failure. It must not create
   an overlapping/tight loop or repeatedly claim successful merges.
10. The existing composite-PK tombstone branch is itself a false-success smell.
    Ignoring it without recording a follow-up would undermine the stated
    stability objective.

## 2. Suggested Alternatives

- Make absence the only `{}` path and convert read/decode/shape failures to a
  typed error that includes a safe actionable message.
- Track `detected_conflicts` separately from successfully merged/archived names,
  or append to the existing `conflicts` success list only after completion.
- Emit `{ok:false,error}` for JSON mode and use non-zero exit only for human mode.
- Run `validate_curate_spec()` before compilation and add direct public-surface
  tests proving retrieval never starts.
- Preserve scalar strings, reject mappings/numbers/nested values for source
  pattern fields.
- Queue composite-key tombstone encoding as a separate schema-contract item.

