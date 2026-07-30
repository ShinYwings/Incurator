# PR #101 Review Briefing: Authored-Topology Correctness Gaps

Date: 2026-07-30
Source: `.agents/USER_REPORT.md` deep-review item
Target: draft PR #101 on `release/v0.39.0`

## Problem

The first v0.39 review passed the happy path but missed adversarial syntax and
cross-path lifecycle failures. Read-only reproductions against the current head
confirmed:

1. Removing a comment/code region with `""` can concatenate surrounding text
   into a wikilink or tag the author never wrote.
2. Escaped wikilinks/tags and numeric-only pseudo-tags emit topology.
3. Valid parent-relative and balanced-parenthesis Markdown destinations are
   missed, ambiguous filename resolution may fall through to a unique alias,
   and `.markdown` sources/targets bypass or misclassify the feature.
4. A DB-only compiler republish leaves authored rows owned by the discarded
   generation; changing a registered source from Markdown to non-Markdown
   leaves its old edge active.
5. Under replica clock skew, the authoritative generation winner can differ
   from the LWW `graph_relations` row winner. Reconciliation then retires a
   deterministic edge present in both replicas.
6. Adding an authored edge can change community membership without retiring
   the pre-addition report. Source deletion retires the relation but does not
   refresh its already-materialized search document.

## Required Outcome

Close these gaps without a schema migration, fuzzy resolution, a general
Markdown AST, or changes to extracted factual corroboration. Every fix needs a
failing regression first, synchronized EN/KR/spec wording, focused and full CI,
and an isolated testbed check.
