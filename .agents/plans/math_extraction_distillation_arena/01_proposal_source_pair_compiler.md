# Source-Pair Compiler Proposal: Immutable Evidence Plus Additive Recovery

Date: 2026-06-11 | Agent Persona: source_pair_analyst

## 1. Core Logic & Implementation

Treat a source-pair as a compiler contract, not merely a list of span ids:

```text
source revision
  -> exact raw evidence region
  -> optional additive recovery candidates
  -> atomic semantic claim
  -> support verdict against minimal evidence
  -> downstream compiler dependencies
```

### Evidence classes

- `raw`: parser/source text exactly as observed; authoritative L1 evidence.
- `recovered_candidate`: additive formula/structure recovery with page,
  bounding box or crop hash, provider/model, confidence, and validator result.
- `derived_context`: deterministic surrounding context used for extraction or
  retrieval; never source truth.

Use `source_spans.metadata` for low-volume recovery/locator metadata unless
Program 1 measurements prove indexed candidate lookup is required. Never
overwrite `content_hash` or raw evidence with recovered LaTeX.

### Loss-boundary classifier

Before recovery, classify each gold formula:

```python
classify_formula_loss(
    original_locator,
    parser_output,
    source_span,
    knowledge_units,
    graph_input,
    report_findings,
    synthesis,
    search_documents,
)
```

Allowed verdicts: `preserved`, `fragmented`, `image_only`, `parser_omitted`,
`l2_omitted`, `downstream_omitted`, `uncertain`.

### Selective recovery

Attempt VLM/OCR recovery only for measured `image_only`, `parser_omitted`, or
unusable `fragmented` cases. Recovery remains uncertain until deterministic
syntax checks and a sampled human/approved semantic check pass.

### Formula centrality

A formula is central when a generated claim cannot remain semantically complete
without its operators/variables/result. Central formulas must be represented in
the claim statement or explicitly linked as formula evidence. Incidental
formulas may be omitted with an auditable reason.

### Stable claim identity

Derive a claim fingerprint from normalized unit type, normalized claim
statement, source identity, and sorted minimal supporting evidence hashes.
Reconciliation matches exact fingerprints first, then records changed claims as
new revisions while retiring stale source-derived units.

## 2. Pros & Cons

### Pros

- Preserves source truth while allowing targeted recovery.
- Diagnoses actual loss instead of assuming PDF parsing is the only defect.
- Makes formula omission explicit and auditable.
- Gives reconciliation a deterministic anchor.

### Cons

- Formula semantic signatures require domain-sensitive fixtures.
- Claim fingerprint normalization must avoid collapsing materially different
  equations.
- Some PDF cases remain uncertain without a vision provider or human review.
