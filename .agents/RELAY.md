# RELAY — IDLE

The v0.63.0 goal shipped: **Hartley is published.**

## Last shipped

**v0.63.0 (#171) — graph extraction that can finish.** Resumable graph
extraction (`graph_batch_results`), a batch sent only the span ids it can cite
(7.4x smaller prompts), deterministic unit ordering, and a refreshed model
catalogue.

Live proof on the real vault:

```
attempt=1  staged 0->24  calls=44  job=failed
attempt=2  staged 24->0  calls=0   job=done   <- PUBLISHED
```

Source 45 now has one `authoritative` generation, all 5,358 units attributed,
`graph_entities` 1,347 -> 2,196.

## Open, in priority order

1. **Source 45 `l3_status` / `l4_status` are still `error`.** L2 and the graph
   publish; concepts and synthesis do not. Separate cause, never diagnosed.
2. **ROADMAP 11 — workspace notes invisible to retrieval.** Decided (shape A:
   spans without projection), deferred, and the user asked for a **multi-agent
   Arena** when it is planned.
3. **ROADMAP 12 follow-ups** are closed; the quota matcher was fixed in v0.62.5.
4. **Codex catalogue entries (`gpt-5.6-*`) are unverified** — the CLI cannot
   authenticate here and no authoritative source was reachable.

## Environment note

`.venv` (the runtime venv) is an **editable install pointing at the working
tree**, so every `wiki` call on this machine — including the plugin's backend —
runs whatever is checked out. It matched master at merge time.

The vault DB is at `SCHEMA_VERSION 14`. A peer device's export in
`.curator/sync/` is at v12 and was already being skipped before this release
(local was 13).
