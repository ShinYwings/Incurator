# Critique on Versioned Canonical Composite Keys

Date: 2026-07-30 | Agent Persona: Red Teamer

## 1. Vulnerabilities & Flaws

- Merely parsing JSON can still delete the wrong row if extra/missing fields are
  accepted or if source ids are copied directly.
- Applying tombstones first does not prevent a stale peer file imported later
  from resurrecting the target.
- `source_pages` and `source_pdf_pages` cannot use remote integer source ids.
- A remote source delete can be blocked by local non-cascading dependents.
- Recording every pre-delete key during a clear-and-rebuild operation can leave
  tombstones for rows reinserted in the same transaction.
- Silently dropping a legacy malformed composite tombstone loses deletion
  intent; keeping it in a v13 export can poison every peer import.
- `json.dumps(sort_keys=True)` is not full RFC 8785 for arbitrary numbers and
  Unicode; documentation must not overclaim.

## 2. Suggested Alternatives

- Validate exact table-specific field sets and scalar types.
- Use portable `source_sync_key` and resolve it locally.
- Add row-side tombstone checks and an explicit newer-row supersession rule.
- Make live-row reinsertion clear only its exact older tombstone.
- Fail closed on unsupported legacy composite tokens with an actionable error
  while preserving the local record.
- Restrict the canonicalization claim to the actual string/integer key domain.
- Add a three-peer resurrection test, not only one exporter/importer test.

