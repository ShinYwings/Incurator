# System Stability Overhaul — Active Evidence Ledger

Updated: 2026-07-31

## Historical Anchor

- The exhaustive G01–G19 diagnosis and completed release evidence were removed
  from the active workspace after consolidation. They remain available in Git
  history before this cleanup commit.
- Shipped stability work through v0.39.1 is merged on `master` at `bc61fab`.

## Live Evidence Sources

- Release-chain findings and rollback state:
  `.agents/plans/02_v032_regression_evidence.md`
- Provider/retrieval/process decisions:
  `.agents/plans/C_retrieval_provider_analysis.md`
- Session/secret persistence decisions:
  `.agents/plans/D_plugin_persistence_analysis.md`
- Current hotfix evidence:
  `.agents/plans/03_v0392_equation_reference_evidence.md`

## Remaining Claims To Prove

- Corrupt durable state is preserved byte-for-byte and cannot be overwritten by
  an ordinary save.
- Concurrent state writes are serialized and atomic.
- Runtime snapshots recursively omit credentials.
- Cancellation and process lifetimes are request-local and settle once.
- MCP exposed names dispatch bijectively to original server/tool identities.
- Retrieval degradation is explicit; provider outputs have exact finite
  cardinality; prompt traces identify the successful provider/model.
- Performance changes show a repeatable speedup without retrieval-quality loss.
- Prompt v2 measurably reduces cross-provider output-shape divergence.

## Evidence Discipline

Each release records its merge-base, failing test, post-fix gates, testbed or
Reference Mode result, and rollback command before it is considered complete.
