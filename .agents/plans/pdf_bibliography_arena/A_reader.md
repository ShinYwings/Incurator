# Bound PDF reader implementation contract

The reader captures a PDF context and backend identity before asynchronous
preparation. Backend arguments never read mutable active workspace state.
Native PDFs prefer their absolute active-context path; ExternalPdfView keeps
its captured hash, attachment key and file path. All arrays of captured page
text and metadata are copied so subsequent context refreshes cannot change a
reader already preparing a turn.

`prepare()` fetches the current page through the existing context endpoint with
radius zero and maxPages one. A positive backend totalPages supersedes the
native DOM page maximum. Current/window text and image/selection metadata remain
available; returned backend pages enrich this snapshot and backend outline
metadata supersedes its initial outline. If the endpoint fails, captured
context remains usable and the reader may use the captured external viewer.

`fetchPage(n)` requests only the captured document. External viewer fallback
requires the same document identity before and after asynchronous completion.
Changing focus may not substitute a different document or its returned text.
Invalid page numbers are rejected without backend or viewer work. The helper
does not ingest a document or mutate application context, runtime, or vault.

Tests precede implementation: native page7 with DOM count7 adopts backend11,
then fetches11; mutate outer context after capture and verify immutable identity;
change viewer identity during awaited fetch and reject returned foreign text;
backend failure uses a stable captured viewer; undefined identity performs no
backend request; captured arrays are not modified by preparation.

Validation: seven focused Vitest tests pass. Initial test-first run failed on
the missing reader module. A further blank-page regression failed before its
fix: a successfully returned empty string must remain distinguishable from
an unavailable page (`undefined`), or callers cannot classify complete scans.
TypeScript check reached only pre-existing worktree generation errors for
`src/generated/buildManifest.json`; no reader/type errors were reported.
