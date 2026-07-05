# Critique on Portable Keys, Local Replicas
Date: 2026-07-05 | Agent Persona: red_teamer / schema_guardian

## 1. Vulnerabilities & Flaws

1. `logical_source_id` is not always portable; its generic fallback hashes an
   absolute path. A source key cannot blindly reuse it.
2. Source tombstones are applied before source rows, so the importer cannot
   depend on a remote-id mapping to delete the local source.
3. Child rows with `source_id` must all be remapped, including composite-key
   rows. Missing one silently reintroduces cross-source corruption.
4. `INSERT OR REPLACE` can delete and recreate rows, triggering cascades. Source
   merge must use an explicit `UPDATE` that preserves local `id`.
5. Wall-clock LWW is still unsafe after a peer with a future clock. Mutable rows
   need monotonic per-row revisions.
6. Automatic DB relocation can destroy data if both locations contain a DB.
7. Plugin cache fallback into `.curator/runtime` would violate the new boundary;
   unavailable repo discovery must fail visibly instead.
8. Moving Collections out of `.curator` would break Obsidian links and is not
   required by the user's device-dependency rule.
9. A profile deletion cannot be inferred from an absent item in a stale list.
   The UI mutation must record an explicit tombstone.

## 2. Suggested Alternatives

- Define `sync_key` independently: portable external locator first, otherwise
  vault-relative path.
- Special-case source tombstones by `sync_key`.
- Discover source FK columns from a frozen allowlist backed by tests against
  every synchronized table.
- Use explicit source insert/update helpers and validate unknown tables/columns
  before generating SQL.
- Use monotonic `updated_at` triggers for mutable source/generation rows and a
  deterministic row digest tie-break only for equal revisions.
- Abort relocation when both DB paths exist and preserve a timestamped backup.
- Keep `.curator/Collections`; only remove machine-specific singleton writers.
- Add `deletedProfileNames` with timestamps and record it at the profile-delete
  action.

