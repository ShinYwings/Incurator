# Provenance And Locator Proposal: Verifiable Evidence, Rendered At The Boundary

Date: 2026-06-11 | Agent Persona: source_pair_analyst
Status: DRAFT PROPOSAL

## 1. Core Logic & Implementation

### Provenance contract

Every source-supported evidence item carries:

- stable record id/kind/layer/hash;
- truth/authority and freshness status;
- minimal supporting `source_span_ids`;
- immediate derivation dependencies;
- structured locator;
- snapshot identity;
- retrieval/selection explanation;
- expansion and verification handles.

Serving preserves Program 2 support. It never replaces minimal support with a
larger, more convenient upstream set.

### Structured source locator

A locator supplements source-span ids and is rendered only at client/interface
boundaries:

```json
{
  "source_id": 42,
  "source_kind": "vault_markdown",
  "relpath": "03_Notes/Residual Learning.md",
  "heading": "Optimization",
  "block_id": "residual-identity",
  "page_number": null,
  "toc_id": null,
  "external_uri": null,
  "locator_status": "exact"
}
```

Source kinds may include vault Markdown, managed PDF/resource, external
Reference Mode file, and promoted Wiki artifact. `projection_path` remains a
display locator only and is never promoted to source truth.

### Resolution and fallback

Resolution order is source-kind specific:

- Markdown block within the declared vault-relative file;
- Markdown heading within the declared file;
- Markdown file;
- PDF physical page or verified printed-page mapping;
- PDF section/TOC target where verified;
- external Reference Mode target through approved resolver;
- valid broader source target with warning.

Rules:

- block ids are file-scoped and duplicate/stale ids are detected;
- do not edit user notes to insert block ids;
- do not guess anchors;
- do not emit a working-looking invalid link;
- fallback is broader but valid and carries a machine-readable warning;
- link resolution is tested against real vault/testbed targets.

### Claim verification

`context_verify` returns:

- target record and claim identity;
- exact minimal source spans and excerpts;
- derivation chain;
- contradictions/provisional state;
- freshness/snapshot status;
- locator-resolution result.

### Answer citation rendering

Backend synthesis returns structured claim/evidence associations. Clients render
human-readable Sources & Trace and links from structured locators. Free-form
answer text is not parsed to invent provenance.

## 2. Pros & Cons

### Pros

- Makes evidence actionable without weakening source-span authority.
- Supports Markdown headings/blocks, PDF pages, and external references.
- Prevents fabricated anchors and misleading links.

### Cons

- Exact locators depend on Program 2 preserving note/PDF structure.
- External Reference Mode resolution can be device-specific.
- Printed vs physical PDF page mapping needs explicit validation.
