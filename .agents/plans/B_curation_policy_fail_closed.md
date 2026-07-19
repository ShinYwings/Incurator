# Domain Analysis B: Workspace Curation Policy Integrity

Date: 2026-07-19

## Design Constraints From Codebase

- ContextService and QueryOrchestrator duplicate the same broad-catch resolver.
- Default policy is legitimate for empty workspace context and absent
  `curate.yml`.
- An existing file can affect source include/exclude, allowed routes, evidence
  requirements, and general-knowledge allowance.
- `load_curate_spec()` currently normalizes a wrong-shaped `sources` block to an
  empty/unrestricted scope.
- MCP and plugin plan surfaces validate inconsistently and can persist a
  normalized plan even when the semantic KRS is invalid.

## Docs/Specs Invariants

- Explicit workspace queries use that workspace's KRS-biased lens.
- Invalid specs surface errors rather than using defaults.
- A plain note outside any workspace uses `workspace_id=default`.
- One root query trace cannot claim a policy hash for a policy that was not
  actually loaded.

## Alternatives & Trade-Offs

1. **Log and default**: rejected; leaks out-of-scope evidence.
2. **Return an empty evidence pack**: rejected; hides configuration failure as
   recall zero.
3. **Duplicate narrow catches in both callers**: rejected; drift caused the
   current inconsistency.
4. **Shared validated resolver**: selected; one authority for missing vs invalid.

## Final Decision

- Add one shared resolver in `curate_yml`.
- Default only when workspace context is empty or the file is absent.
- Propagate read, parse, shape, compile, hash, and semantic validation errors.
- Reject wrong-shaped source-scope containers/pattern values while preserving
  accepted string and string-list inputs.
- Assert no retrieval/trace work occurs after policy failure.
- Require validated spec before both `record_curation_plan()` call sites; invalid
  planning returns failure and records no row.

## Implementation Pseudocode

```python
if not workspace_path:
    return default_policy(), ""
spec = load_curate_spec(path)
if spec is None:
    return default_policy(), ""
errors = validate_curate_spec(spec)
if errors:
    raise ValueError("invalid curate.yml: " + "; ".join(errors))
return compile_curate_policy(spec, path), curate_spec_hash(path)

# Plan surfaces
spec = load_validated_curate_spec(path)
if spec is None: fail("no curate.yml")
policy = compile_curate_policy(spec, path)
record_curation_plan(policy)  # only reachable after validation
```
