# Source-Pair Analyst Proposal: Evidence-Preserving Distillation

Date: 2026-06-11 | Agent Persona: source_pair_analyst

## 1. Core Logic & Implementation

The primary failure mode is not one missing backprop function. It is loss of the
source/evidence pair at transformation boundaries. Stabilization must validate
each boundary independently:

1. original Markdown/PDF page → source span;
2. source span → knowledge unit;
3. knowledge unit → graph entity/relation;
4. graph community → report;
5. reports → synthesis;
6. canonical records → search documents/chunks;
7. retrieved chunk → user-visible evidence link.

For each boundary, create fixtures with a distinctive claim, equation, block id,
and negative distractor. The output must retain:

- exact allowed `source_span_ids`;
- page or vault anchor locator;
- enough statement/formula content to identify the evidence;
- a reason when promotion is intentionally skipped.

### Obsidian block references

Markdown ingest should recognize block ids without changing user notes:

```markdown
The residual block preserves an identity path. ^residual-identity
```

The source span metadata records `block_id=residual-identity`. Answer evidence may
then render `[[Note#^residual-identity]]`. Heading anchors use
`[[Note#Heading]]`. Unknown anchors fall back to the file link; invalid guessed
anchors must never be emitted.

### Formula preservation

Use equation signatures in tests, not brittle exact whitespace:

- normalize display delimiters and whitespace;
- compare key operators/symbols and source-span citation;
- reject outputs that preserve prose but omit the equation's semantic variables.

L2/L3 should not blindly duplicate every formula. Promotion is required when the
formula is central to the extracted claim; otherwise an explicit skip reason is
acceptable and auditable.

## 2. Pros & Cons

### Pros

- Finds the exact transformation boundary where evidence disappears.
- Supports both PDF page provenance and Obsidian note/block provenance.
- Avoids a misleading all-or-nothing "backprop works" assertion.

### Cons

- Boundary fixtures require careful maintenance as prompt contracts evolve.
- Formula semantic comparison is harder than string equality.
- Existing stale testbed scenarios must be rewritten, not merely extended.
