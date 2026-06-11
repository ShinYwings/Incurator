# TDD And Quality Proposal: Boundary Fixtures Before Recovery

Date: 2026-06-11 | Agent Persona: qa_runner / evaluation_specialist

## 1. Core Logic & Implementation

Build deterministic fixtures that isolate every source-pair boundary before
changing compiler behavior.

### Gold fixture matrix

| Fixture | Required oracle |
|---|---|
| Markdown display/inline math | exact delimiters and semantic signature survive |
| PDF preserved formula | parser and L1 preserve locator and signature |
| PDF fragmented glyph formula | classified as fragmented; no invented repair |
| Image-only formula | recovery candidate is additive and uncertain |
| Central formula claim | formula retained or linked; omission fails |
| Incidental formula | omission allowed only with recorded reason |
| Wrong real span citation | support validator rejects source-supported claim |
| Multi-span derivation | smallest sufficient ordered support set retained |
| Contradictory spans | contradiction status retained, not merged away |
| Long statement formula tail | downstream input cannot truncate central formula |
| Unchanged rebuild | identical authoritative ids/hashes/counts |
| Edit/delete/split | only expected dependency closure changes |
| Prompt/provider failure | no partial authoritative state |

### Oracle hierarchy

1. Deterministic identity/hash/locator assertions.
2. Expected minimal-support span ids and formula signatures.
3. Human-labeled claim support/centrality samples from Program 1.
4. Calibrated model validator only as a secondary signal.

### Required test surfaces

- Unit tests: source spans, support validator, claim identity, reconciliation,
  formula classifier, recovery adapter, prompt contracts.
- Integration tests: source compile staging/commit, projection/search
  materialization, graph input handoff, audit traversal.
- Testbed: rewrite `complex_math_backprop` around current L1-L4 DB-native
  architecture and Reference Mode external PDF behavior.

## 2. Pros & Cons

### Pros

- Prevents a VLM feature from hiding downstream distillation defects.
- Gives every migration/reconciliation rule a deterministic oracle.
- Makes provider unavailability a documented blocker rather than a false pass.

### Cons

- Gold support labels and formula centrality labels require careful review.
- Exact formulas need semantic-signature comparison, not brittle whitespace
  equality.
- Full PDF recovery quality cannot be proven without representative documents.
