# Critique on latency, provider and source lifecycle proposals
Date: 2026-09-10 | Agent Persona: System synthesizer / adversarial reviewer

## 1. Vulnerabilities & Flaws
Latency: overlap alone cannot explain away the new 300-second generation timeout. Measure provider execution independently. Starting optional knowledge early must not leave rejected promises unobserved or read changed active file identities. Workspace consultation off must not remove explicitly selected references. Avoid unrequested backend ranking changes.
Provider: a prompt requesting no shell still lets an agent select a denied shell. Investigate native custom-agent tool whitelist and actual startup tool list; only adopt proven flags. Buffered output is a distinct cause of perceived latency. Do not present a 300-second partial timeout as successful completion.
Codex: reconciliation of a partially streamed final must avoid duplicate edit fences; item identity, cumulative same-item updates, no-newline EOF and final output file require integration tests. Canonical path fix is valid but proposal user acceptance remains required.
Sync: source ids are machine-local, so preserving a dangling integer across machines could accidentally bind to another source. Retained audit records need a detached nullable reference, not source reconstruction or row deletion. Historic snapshots need semantics at the importer boundary as well as corrected future exports. Only proven retired/discarded audits can detach; live rows with missing parents must still fail atomically. Late peer snapshots must never resurrect a deleted source.

## 2. Suggested Alternatives
Proceed with independent phases under a single urgent user batch. Finalize concrete source lifecycle and agy tool contracts after probes; test legacy orphan snapshots and fresh source removal→export→import plus valid-id collisions. Stream agy native events if current runtime verifies answer/status separation. Catalogue uses current verified CLI snapshot and existing unavailable-model normalization. No live database mutation, vault reindex or snapshot file edit.
