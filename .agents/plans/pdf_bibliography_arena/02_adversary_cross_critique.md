# Adversarial cross-critique of proposal01

Read `01_proposal.md` after saving the independent adversarial proposal. Agree
with its diagnosis qualified as code evidence, native source binding, retryable
cache, and heading-anchored excerpts rather than a new bibliography parser.

Two corrections are acceptance gates, now also accepted by proposal author's
cross-critique: authoritative native page count and followup source preservation.
Path propagation alone cannot reach page11 when the DOM only contains page7;
successful first-turn lookup alone cannot answer a deictic second turn when only
assistant prose survives. Capture metadata through the existing context endpoint
and carry the real source evidence across same-document popover turns.

The implementation should keep these invariants explicit:

- `refreshActiveContext()`'s last content leaf and the document reader must be
  the same leaf. Looking up the current focused ExternalPdfView separately does
  not achieve pinning, even if each value is read before the first await.
- The immutable backend arguments must outlive every sequential page fetch.
  External fallback must check document identity after its awaited fetch as
  well as before; a view instance may be reused to display another document.
- A continuation read failure is incomplete success, not a permanent cache hit.
  The second turn must retry the missing page even if the first found entries.
- A raw References fallback needs true page attribution and an honest boundary.
  Known `SECTION_AFTER` headings should stop appendices from being presented as
  bibliography. Do not describe the bounded tail or first40 list as exhaustive.
- Evidence reuse is source-scoped. It should not revive A's references after
  switching to B or infer author tokens from previous assistant answers.
- At least one regression must invoke actual capture/preparation and final
  message formatting. Supplying a correct identity directly to a resolver would
  avoid the bug under test. Model mocking can prove supplied content only.

No additional full-document search or author-name index is required to repair
the existing contract. If source geometry remains unknown, report incomplete
coverage while still supplying any actual bibliography content retrieved.

Consensus: implement bounded source capture/metadata, heading-based bibliography
retrieval and retryable caching, same-document followup evidence, and source-
specific coverage. Use existing endpoint and preserve read-only popover tools.
