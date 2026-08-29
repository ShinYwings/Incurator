# Changelog

All notable changes to Incurator are documented here.

## [0.73.2] - 2026-08-30

### Fixed
- **The plugin deleted the curator MCP server from Antigravity's config on every
  turn, so the assistant had no way to search your vault.** `syncAgyMcpConfig`
  wrote `~/.gemini/settings.json` by replacing `mcpServers` wholesale. That was
  harmless only while agy ignored that file — it does not. `wiki init`/`wiki
  config` register the `incurator` server there, and every plugin turn removed it
  again, one second before agy started.

  The visible symptom was a denial that looks unrelated: asked to find a paper in
  their own literature notes, the assistant had no vault-search tool, reached for
  a shell `rg` instead, and `command(wiki)` correctly refused it — so the turn
  produced nothing and reported a permission error. The permission was not the
  problem; the missing tool was.

  All three files the plugin writes now reconcile through one function: keep what
  the plugin does not manage, drop only what it registered and has since retired,
  apply what it currently has. v0.71.0 fixed this for the two registry paths and
  left `settings.json` on the old wholesale write.

- **And `wiki status` now says when Antigravity cannot reach this vault's
  tools.** That is the point of this release, more than the one-line write fix.
  Four separate defects in this wiring reached a real session before anything
  complained — the registry written where the CLI does not read it, a permission
  whose scoped form grants nothing, a command name a spawned process cannot
  resolve, and now an entry deleted by the other writer. Every one of them was
  found by a person hitting it, never by the system.

  The check names the specific fault rather than returning a boolean: no
  registry, server absent, command that cannot start, registration pointing at a
  different vault, or the missing `mcp(*)` grant. Each has a test, because a
  check that cannot detect the failure it was written for is the shape this repo
  keeps repeating.

## [0.73.1] - 2026-08-30

### Fixed
- **A synced prompt run named another device's sources.** `sources.id` is an
  AUTOINCREMENT integer and deliberately replica-local; `sources.sync_key` is the
  portable identity, and import already resolves a peer's source by that key,
  keeps the receiving device's own integer, and remaps every child's `source_id`
  **column**. `prompt_runs.source_ids` is a JSON **array** of those integers, and
  a column remap cannot reach inside a JSON string — so the array arrived holding
  the peer's numbering, where each entry names whatever unrelated source happens
  to occupy that row number locally.

  Reproduced with two devices that registered the same two files in a different
  order: the array arrived as `[1]` while this device uses `2` for that file and
  `1` is a different source entirely. Silently wrong provenance, on 2,984 rows
  on the reference vault.

  An id with no local counterpart is now dropped rather than kept — keeping it
  leaves the array pointing at an unrelated source, and provenance that is
  honestly shorter beats provenance that is quietly wrong — **and the count is
  printed**, by both `wiki db import` and `wiki db autosync`.

  That last part matters more than it looks. An id is unmapped in two very
  different situations: the peer's source was rejected or tombstoned, where
  dropping is the whole point; or **the file simply did not carry it**, which is
  what `wiki db export --since` does by design for anything unchanged — so a
  device that already holds the source still loses the reference. The
  singular-`source_id` path raises for the same condition, aborting the import.
  That is right for a span, which is meaningless without its source, and
  disproportionate for provenance metadata. Dropping quietly would have been the
  one inconsistency; dropping and saying so is not.

  `SCHEMA.md` claimed the transport remaps "every synchronized child
  `source_id`". Until now it did not.

## [0.73.0] - 2026-08-30

### Fixed
- **A delete on one device could silently fail to apply on another — and a row
  you deleted could walk back in.** `claim_supports`,
  `entity_resolution_lineage`, and `artifact_dependencies` put a raw,
  device-local id into their composite tombstone token (`source_span_id`,
  `origin_entity_id`, and — polymorphically — `artifact_id`/`depends_on_id`),
  minted at deletion time on the deleting device. The receiver has never held that id, so the WHERE
  clause matched nothing, the delete was counted as applied, and the row
  survived. `source_pages`/`source_pdf_pages` never had this because they already
  transport `source_sync_key`, a value both devices compute identically.

  The mirror case is worse and was not in the original report:
  `_row_is_blocked_by_tombstone` builds an incoming row's token from that row's
  **own** ids — the peer's — while the local tombstone names the local id. So a
  row deliberately deleted here was re-inserted by the next sync, silently, with
  its own tombstone sitting beside it. Deleted data returning is a worse failure
  than a delete that quietly does nothing.

  Both are closed by translating between the two devices' ids: a pre-scan builds
  the peer-to-local map before anything is applied, incoming rows carry local ids
  before the tombstone check runs, and a peer's token is re-expressed in local
  ids before it is matched. An id this device does not know passes through
  unchanged, so a tombstone for a row it never had still matches nothing.

  Two of those pieces were wrong on the first pass and are worth recording,
  because both were the same mistake in different clothes. The row-translation
  step read only the name-keyed registry, so the polymorphic
  `artifact_dependencies` fell through it and a deleted dependency still walked
  back in — the third time that table slipped past a scan keyed on column names.
  And the token translation used a permissive `json.loads`, which put it in FRONT
  of the fail-closed decoder: a token with an unsupported version was
  re-canonicalized into a valid one and applied, deleting a row the gate existed
  to protect. Both now have tests that fail if the fix is reverted.

### Note
- **No `SCHEMA_VERSION` bump, and no change to the token format.** The roadmap
  called for swapping these transport fields to a portable form and warned this
  would need a version bump and a fleet-wide gate. It is not constructible today:
  `claim_supports`'s key also contains `knowledge_unit_id`, and `knowledge_units`
  has **no natural-key UNIQUE index**, so there is no portable form for that half
  of the key. Translating the ids that genuinely converge — which are exactly the
  ones that differ between devices — closes the gap without inventing an identity
  the schema does not have.

  This is the second release running where the roadmap's remedy was larger than
  the defect required. Both times the difference was found by measuring rather
  than by reading the entry.

  One limit, stated rather than papered over: the map is built from the rows in
  the import file, so a `wiki db export --since` snapshot that omits the
  referenced spans yields a smaller map and those tokens behave as before.
  Nothing regresses, and the hands-off autosync path always writes a full
  snapshot.

## [0.72.0] - 2026-08-29

### Fixed
- **A relation from another device could point at an entity this device has
  never had.** `graph_entities` and `source_spans` sync on their surrogate `id`,
  but both carry a natural identity — `UNIQUE(canonical_name, entity_type)` and
  `UNIQUE(source_id, content_hash)`. Two devices that independently extract the
  same thing mint different ids, so the peer's row collides on content and is
  correctly reported `skipped`; the data is already here. **Its children were
  not translated.** `graph_relations.source_entity_id` has no foreign key, so
  the relation was written verbatim, naming an id that exists nowhere locally —
  no error, no counter, invisible to anything but a join that comes back empty.

  This is not hypothetical. The reference vault's peer export carried 691
  entities, and one of them — `MipNeRF360` — already existed here under a
  different id. No relation broke that time **only because that export happened
  to contain no relation touching it.** Replaying the same collision with the
  relation present, against a copy of the real database and through the real
  `import_knowledge`, reproduced the dangling endpoint and then showed it
  repaired: `skipped=1 remapped=1`, endpoint re-pointed at the local id.

  Import now records the id this device already uses for each converged row and
  rewrites the references to it in four shapes, because they do not all look
  alike: **scalar columns**; **JSON arrays** of ids
  (`knowledge_units.source_span_ids`, `community_reports.entity_ids`, and eight
  more); **JSON arrays of objects**, where the id sits under a key
  (`memory_paths.path_json` hops); and **polymorphic columns**, where the id's
  kind is named by a sibling column (`artifact_dependencies`, 6,241 rows of it
  on the reference vault — a registry keyed on column *name* cannot see those,
  the same blind spot that hid `graph_batch_results.trace_id` in v0.71.0).

  `entity_resolution_lineage.rewrite_json` is rewritten too. It is a replay
  payload rather than a reference list: `reverse_entity_merge` reads it back
  verbatim, so leaving it stale would re-point a relation at the peer's id the
  next time a merge was reversed — the same defect, through a path nothing
  watches.

  A provenance array citing a span this device does not have is worse than a
  dangling scalar, not better: nothing ever flags it.

  The candidate scan is **chunked**. One `LIKE ?` per converged id in a single
  statement eventually raises SQLite's "Expression tree is too large", and how
  many is a build-time property rather than a constant — `SQLITE_MAX_EXPR_DEPTH`
  defaults to 1000, while the build measured here reports 10000. So a vault that
  syncs cleanly on one machine could crash on a distro build with the default,
  and it would not fail softly: the raise lands inside the import transaction,
  which commits only on a clean exit, so it would discard the entire import
  rather than skip the repair.

  `wiki db import` prints the count. A silent repair would be indistinguishable
  from no repair.

- **The test suite was running the developer's own provider CLI.**
  `cfg.DEFAULT_CONFIG` sets `llm.primary = "antigravity-cli::..."`, so every test
  that saved the default config and built a client spawned the real `agy` —
  against the user's account and quota. Confirmed by `ps` during a full run: real
  `agy` processes whose parent was pytest and whose `--log-file` pointed into
  `pytest-of-shin/pytest-1047/...`. The user noticed before the suite did,
  because nothing in the suite was watching.

  A conftest guard now fails any test that tries to run `agy`, `claude`, `codex`,
  `gemini`, or `ollama`, naming the test and saying to patch `subprocess.run`
  instead. Ordinary subprocess calls are unaffected.

  The side effect is large: the full backend suite went from **4,060 seconds to
  67**. Most of that hour was spent waiting on real provider responses inside
  tests that never meant to make them.

### Note
- **No schema change, and no `SCHEMA_VERSION` bump.** The roadmap described this
  as "a schema change touching every referencing column"; measuring it showed
  the referencing columns already hold the right data and the natural keys
  already exist as UNIQUE indexes. `sources` needed a separate `sync_key` column
  because `relpath` alone was not enough; these two tables do not. The export
  format is unchanged, so a device on this release and one on an older release
  still interoperate — the newer one repairs its imports, the older one keeps
  the defect.

  The alternative designs were rejected on evidence, not preference. Deriving
  the id from the natural key makes a delete tombstone the *natural key*,
  permanently blocking that entity from ever syncing again on any device. Adding
  a `sync_key` column means resurrecting the `ALTER TABLE` migration mechanism
  this project deliberately deleted in v0.33.0 — without it, adding a column to
  an existing table is a silent no-op that crashes on first read.

## [0.71.0] - 2026-08-29
### Added
- **A cap on the LLM call log — with a guard that is the whole point.**

  ```
  wiki config set gc.prompt_runs_keep 1000     # 0 = keep everything (the default)
  ```

  `prompt_runs` is the largest growing table: **4,406 rows, 17.39 MB** on the
  reference vault. The cap keeps the newest N **unreferenced** records.

  **Records an artifact still points at are kept regardless of the cap.**
  `community_reports.prompt_run_id` is what the L3 resume reads to decide a
  report's prose need not be regenerated — delete one and the lookup returns
  nothing, the skip fails, and finished reports are re-sent to the provider
  **silently**. Here that is **238** live reports carrying prose and a run — 238
  calls to rewrite them — undoing v0.69.5. Seven tables carry the column, `query_traces.prompt_trace_ids` is a
  JSON array a plain join would miss, and a test fails if a future table carries
  the column without joining the scan.

  | cap | removed | kept |
  |---|---|---|
  | off (default) | 0 | 4,406 |
  | 1,000 | 2,049 | 2,357 (incl. all 1,354 referenced) |

  Deletion writes a tombstone per record, so it **applies to every device you
  sync with** — `prompt_runs` is synced and exports are full snapshots, so a
  delete without one is undone by the next sync. A call record averages ~3,920
  bytes against ~126 for its tombstone, about 31×.

### Fixed
- **The Antigravity CLI could never call an Incurator tool, and three
  consecutive "permission fixes" all shipped granting nothing.** Two independent
  causes, both measured against agy 1.1.22 rather than reasoned about:

  1. **The MCP server was registered where agy does not look.** The plugin wrote
     `~/.gemini/settings.json`; the backend wrote that plus
     `~/.gemini/antigravity/mcp_config.json`. Driving `agy mcp add` and diffing
     `~/.gemini` shows the CLI's own registry is `~/.gemini/config/mcp_config.json`
     — which was **empty**. `agy mcp list` reported "No MCP servers configured"
     and the model answered that the tools were not available. Both writers now
     register there too, merging rather than replacing so servers the user added
     with `agy mcp add` survive — and pruning the ones Incurator itself
     registered and no longer has, so deleting or disabling a server in the
     plugin actually unregisters it. Neither merging nor replacing is correct
     alone: replacing deletes the user's own servers, merging leaves a deleted
     one registered and callable forever with its `env` credentials. Incurator
     records which names it manages and removes exactly those.
  2. **Calling any MCP tool needs an `mcp` permission, and only the wildcard is
     honoured.** With the server correctly registered, `mcp(incurator_fetch)` and
     `mcp(fetch_url)` were both auto-denied; `mcp(*)` let the call through and it
     returned a live value. This is the identical finding v0.56.1 recorded for
     `read_file` — a target-scoped rule is not a narrower grant, it is no grant.
     `mcp(*)` joins the required permission set.
  3. **The registered command was a bare `wiki`, which a spawned process cannot
     find.** It is a shell alias to the repo-root venv's console script;
     `command -v wiki` finds nothing in a clean PATH. So even once registered
     and permitted, the server failed to start: `agy mcp list` showed it and the
     model still reported that no MCP tools existed. `resolve_wiki_command()`
     already existed for exactly this reason on the Obsidian install path and
     simply was not used here.

  **Verified end to end, not reasoned about**: after all three fixes, headless
  `agy` called `curator_status` through the MCP server and returned this vault's
  real numbers — 3,512 pages, 3,171 atoms, 273 concepts, 68 contexts. That is the
  first time the Antigravity CLI has been able to call an Incurator tool.

  **What `mcp(*)` costs, stated plainly**: it is a wildcard over the MCP
  permission class, not a grant scoped to Incurator. It authorises headless calls
  into every server in agy's registry — including any the user added with
  `agy mcp add`, which the registration above deliberately preserves. It is still
  meaningfully narrower than the CLI's blanket permission-skip flag, which this
  codebase refuses: that approves every tool class including the shell, while
  this approves no class but MCP. There is no third option — the scoped forms
  were measured and grant nothing.

- **The test suite was rewriting the developer's real agy configuration.**
  `wiki init` registers the MCP server under `~/.gemini/`, so every test that
  ran `init` without patching home wrote the actual file. Found live: the real
  `~/.gemini/config/mcp_config.json` pointed `VAULT_ROOT` at a deleted
  `pytest-of-shin/pytest-1030/...` temp directory, leaving agy registered
  against a vault that no longer existed — and reproduced on the next run, which
  clobbered a correct registration again. A single autouse fixture now points
  `HOME` and `Path.home()` at a temp directory for the whole suite; patching the
  one offending test would have left the next one free to do it again. This
  mattered more after the registration fix above, which writes one more file.

  The plugin suite then did the same thing, which is how the guard's other half
  arrived: a test that spied on `os.homedir` **after** the module under test had
  already bound it wrote its fixture server into the real registry. A vitest
  setup file now fails the run if a test modified the real `~/.gemini`. It does
  not sandbox the write — it makes it loud, which is the part that was missing.
  Both leaks were found by chance, not by anything that would have complained.

- **The embedded fetch tool destroyed the very thing it was added to deliver.**
  It accumulated the response with `body += chunk`, coercing each Buffer to
  UTF-8. Measured on a 314-byte PDF: **132 replacement characters**, not
  recoverable. Binary responses are now saved to disk and the tool returns the
  path plus a pointer to `curator_get_pdf_toc` / `curator_get_pdf_context`,
  which read PDFs properly. The 100KB cap also stops the transfer now instead of
  downloading the remainder to discard it.

- **The fetch tool had no SSRF protection.** Verified by using it: it fetched
  `http://127.0.0.1` without complaint, on a machine that runs Ollama (11434)
  and Syncthing's unauthenticated REST API (8384). Since the model reads URLs
  out of ingested documents, "talked into fetching it" is the realistic input.
  Loopback, private, and link-local addresses are refused on the initial request
  **and** the redirect hop; IPv4-mapped IPv6 (`[::ffff:127.0.0.1]`, which Node
  normalises to hex and which matched no dotted-quad rule) is unmapped before
  filtering; and the **resolved** address is checked inside the DNS lookup, so a
  public hostname pointing at an internal address is refused too.

  The tests for all of this **spawn the server and speak JSON-RPC to it**. The
  tests that shipped with the feature only asserted the script string contained
  certain substrings, which is why none of these defects were caught — and the
  spawn-based tests immediately found one more: the server replied to JSON-RPC
  notifications, which a server MUST NOT do.
- **"Sign out" did not sign the user out.** The DeepSeek key lives in two
  places, and the button only cleared one. `restoreDeepseekKeyFromStore()` reads
  the encrypted machine-local store at every launch, so signing out and
  restarting silently signed the user back in — while the panel reported the key
  as cleared, and while the guide already promised "use **Sign out** to remove
  it". `secret_store.delete_secret` had existed the whole time with no command in
  front of it; `wiki plugin secret rm` is that command. Signing out with nothing
  stored is not an error, an unreachable backend does not abort the sign-out, and
  removal is per-name, so the backend's own key is untouched.
- **The mid-stream quota kill fired on ordinary prose.** It matched
  `"rate limit"` and `"too many requests"` anywhere in stderr and killed the
  child process — destroying an answer the user had already paid for. The
  close-time check can afford those phrases because it weighs evidence first and
  never treats a produced answer as proof of failure; the mid-stream check has no
  such protection, and `agy` can route answer text through stderr. It now matches
  only phrasings a provider error produces, plus HTTP 429.
- **A throwing snapshot wedged plugin persistence permanently.** The coalescing
  writer cleared its queued slot *after* taking the snapshot, so a throw left the
  slot occupied forever and every later write coalesced into a write that would
  never run — silently, for the rest of the session.
- **A source could be marked `l4_status='done'` in the same round it was marked
  `l3_status='error'`.** The status line read "did synthesis return any ids?",
  which was equivalent to "did this source reach L4" only under an invariant
  v0.69.6 deliberately removed: L4 used to run only when every report had prose.
  Since then synthesis skips prose-less reports, and returns the *existing* node
  ids on its unchanged-corpus path — so the check was true on almost every round,
  including for sources whose report was still a bare skeleton. Status now
  follows what the synthesis nodes actually cite.
- **A cleared `.cache/` made `wiki sync` overwrite an accurate ledger with
  "Last curated: never".** `db.connect` self-heals an empty schema into a missing
  database, so on a machine whose cache was cleared — or after a vault rename,
  which re-keys the cache — the rebuild read zero rows and wrote them into files
  headed "Auto-maintained by the Curator engine", where a human reads them.
  v0.69.2 had already built this detection but wired it only into `wiki status`.
  `finalize_routing_tables` now warns and refuses the write, per "false success
  is forbidden" (`SYSTEM_BEHAVIOR.md` §32).
- **Green success lines rendered as red.** Rich's auto-highlighter colors paths
  magenta, which reads as red on dark themes, so `setup` output looked like a
  wall of errors. Highlighting is off for the status lines.
- **A corrupt `.curator/sessions.json` crashed `wiki gc` instead of being
  reported.** A store that will not parse raised straight out of `wiki gc plan` —
  read-only reporting that should never fail — and took the unrelated cache sweep
  down with it. An unreadable store is now a first-class state: reported, and
  **left untouched**, because rewriting a file the backend cannot read would
  destroy whatever it still holds.

### Note
- `deleted_records` still has **no retention rule, deliberately.** Expiring a
  tombstone is not "deleting on every device" — it is the opposite: it lets a
  peer that was offline **restore** something you deleted. Nothing records
  whether every device has seen a given tombstone, so there is no safe window.

## [0.70.0] - 2026-08-24
### Added
- **`wiki gc` — reclaims what is safe, and tells you what it refuses to touch and
  why.**

  ```
  wiki gc plan     # what would go, and what grows but is deliberately kept
  wiki gc run      # delete it (asks first)
  ```

  Most of the growth **cannot be safely deleted**, and the report is the more
  valuable half. `prompt_runs`, `query_traces`, `compiler_generations` and
  `deleted_records` are all synced, and exports are full snapshots — so deleting a
  row either propagates to every device or is undone by the next sync.
  `deleted_records` (48,896 rows) is the tombstone table itself; expiring one
  silently restores data you deleted, on any device that was offline. `wiki gc
  plan` shows these numbers **with those reasons**.

  What it reclaims: per-vault cache directories that are provably debris — the
  recorded vault path is gone, **that path is under a temp prefix**, and the
  cached database holds zero sources. All three are required: "the path is
  missing" alone is a **mount test, not a liveness test**, and an unmounted
  external drive hashes to the same directory while holding `state.sqlite`.
  On the reference machine: **6.4 MB across 11 directories** — modest, and the
  1.5 GB repo cache is mostly 1.2 GB of models plus the 288 MB live database.

- **Chat retention, off by default.**

  ```
  wiki config set gc.sessions_retention_days 90     # 30 / 90 / 180 / 365
  ```

  Chats are your own writing, so nothing is removed unless you pick a window.
  When you do, `wiki gc run` states that removal takes effect on **every device
  you sync with** and cannot be undone. A session with no usable timestamp is
  kept; the active-session pointer never dangles; existing tombstones survive.

## [0.69.8] - 2026-08-24
### Fixed
- **The knowledge graph's community layer is flat, and nothing said so.**

  `SYSTEM_BEHAVIOR.md` §27.4 permits the degraded connected-components path on
  one condition — that it "is recorded in `config_hash` and surfaced by the
  audit, **not hidden**". It was hidden: `config_hash` is a 16-character digest
  of a config dict, irreversible where anyone reads it, and the graph audit
  returns relation-level violations only. No surface named the algorithm.

  `wiki lint` now says it, measured on your own graph. On the reference vault:

  ```
  Communities are built by the `connected_components` fallback
  (SYSTEM_BEHAVIOR §27.4), so the hierarchy is flat: 417 communities, all at
  level 0, largest holds 567 of 1921 memberships (30%), and 293 are bare pairs.
  ```

  This is a **permitted degraded path, not a fault**, so it is an INFO rather
  than a violation — a permanent violation would make the audit never clean and
  teach you to skip it.

  It applies **no giant-component threshold on purpose.** §27.4 gates that check
  on "the approved threshold" from a benchmark freeze that has never run, and no
  such constant exists in the codebase. Inventing one would be a hand-maintained
  number that goes stale unnoticed — the same shape as the prompt-contract
  version that has not been bumped in twelve commits of the prompt it versions.

  And it retires itself: the signal is a hash comparison against the fallback
  config, so the day an approved hierarchy algorithm ships, this line disappears
  without anyone remembering to delete it.

## [0.69.7] - 2026-08-24
### Fixed
- **`ledger.md` reported "Last curated: never" over a fully built knowledge
  graph.**

  On the reference vault: 44 sources, 37 contexts, 1,098 atoms, 233 concepts —
  and `sources.last_ingested` was **NULL on all 44 rows**, so the one line in the
  ledger that says when the vault was last curated said *never*. Since v0.69.1
  `wiki sync` rebuilds that file, so the wrong answer was being rewritten on
  every sync.

  The cause is structural, not historical. `run_l1_to_l3` selects only sources
  whose status is `pending`, `force_pending` or `error`, so the line that stamps
  `last_ingested` fires **at most once in a source's life** — when it first
  leaves the pending set. Every later recompile published a new authoritative
  generation and touched nothing.

  Publishing an authoritative generation now stamps the source, inside the same
  transaction as the publish it describes. A corpus-wide generation
  (`source_id IS NULL`) deliberately stamps nothing: it is the global L3/L4
  scope, and stamping every source from it would claim each had been
  individually re-ingested.

  For vaults curated before this release, the ledger falls back to the publish
  log, which has carried the real dates the whole time — so the line is truthful
  immediately, with no migration and no re-ingest. On the reference vault it
  reads `2026-08-22T20:06:14Z` instead of `never`.

## [0.69.6] - 2026-08-24
### Fixed
- **The top layer of the knowledge graph had never produced a single row.**

  Not "L4 failed recently" — across the vault's entire history:

  | | |
  |---|---|
  | `synthesis_nodes` rows | **0** |
  | `SYN-*` files | **0** |
  | sources at `l4_status='done'` | **0** |

  Three retrieval paths read `synthesis_nodes`. None had ever had a row to read.

  **One gate caused it.** Synthesis ran only when **zero** community reports had
  failed, and that error list takes one entry per failed report prose. Across 417
  reports with a provider that refuses on capacity, it was never empty — so one
  failed report out of 417 silently suppressed the entire layer.

  The gate was inherited rather than chosen: it was carried forward by a commit
  about status reporting, which split a shared error list and kept the condition.
  And it contradicted what it guarded — synthesis already hashes its corpus and
  skips when unchanged, so it is built to be re-run as the corpus fills. The gate
  prevented exactly that.

  L4 now synthesises over the reports that **have prose**, and re-runs when more
  gain it. A report without prose has not finished its own layer, so feeding those
  skeletons would make L4's output depend on how far L3 happened to get. A partial
  L3 now yields a partial-but-honest L4 that completes itself, instead of nothing.

- **`l4_status` no longer reports a layer that ran and succeeded as failed.** It
  had inherited the L3 error list; it now reflects L4's own outcome, the same
  principle already applied to L3.

## [0.69.5] - 2026-08-24
### Fixed
- **Every source in the vault was stuck at `l3: error`, and each retry made the
  same mistake before it could make progress.**

  L3 community-report generation is a **global** pass, so a single capacity
  refusal from the provider fails every source at once. That part is by design.
  What was not: the retry re-sent every report the provider had **already
  written**, so it exhausted its budget on finished work and was refused again
  long before reaching the reports that still needed writing.

  Measured on the reference vault:

  | | |
  |---|---|
  | sources at `l3_status='error'` | **36** (all of them) |
  | live community reports | **417** |
  | already had prose | **238** |
  | of those, byte-identical prompt → now skipped | **185** |
  | genuinely changed → correctly rewritten | **53** |
  | never written | **179** |

  A retry now spends its budget on **232 reports instead of 417**, which is what
  makes the 179 unwritten ones reachable at all.

  The skip is keyed on the **rendered prompt**, not on prose merely existing — a
  report whose membership or eligible support moved has a different prompt and is
  rewritten. This is what v0.62.0 gave L2 extraction and v0.63.0 gave graph
  extraction, one layer up, and unlike those it needed **no new table**: the
  report already stores the `prompt_run_id` whose `input_hash` is the same
  digest-of-the-rendered-prompt those two use as their resume key.

  Verified against the live vault with a client that raises if called, so the
  measurement above cost zero provider calls.

## [0.69.4] - 2026-08-23
### Fixed
- **Sending one chat message moved ~104 MB of disk I/O. It now moves ~7 MB.**

  Measured on the reference vault, where `.curator/sessions.json` had reached
  **17.3 MB**:

  | | before | after |
  |---|---|---|
  | `sessions.json` | **17.31 MB** | **7.24 MB** (58% smaller) |
  | full-file writes per message sent | **6** | **1** |
  | I/O per message | **~104 MB** | **~7 MB** |

  Three independent causes, all of them waste:

  1. **The file stored megabytes nothing ever reads.** A context ref captured
     automatically from your active tab keeps `content`, `outline` and
     `windowPages`. The prompt builder skips auto refs outright *before* reading
     any of it, and the next turn rebuilds them fresh from what is on screen.
     **7.8 MB of the file was written, synced to every device, and never looked
     at again.** Chip thumbnails (`imageBase64`) are still kept — the transcript
     renders those, so dropping them would remove something you can see.

  2. **Six full rewrites per message.** Each `persistCurrentSession()` deep-cloned
     the whole structure and did a read + parse + merge + stringify + write. They
     all persist the same object, so the last subsumes the rest; they are now
     coalesced into one. Writes still never overlap, and a save made *while* a
     write is in flight still gets its own write rather than being told it was
     persisted.

  3. **A 30-session cap that never capped.** It dropped sessions from the local
     list without tombstoning them, and the merge re-seeds from the file on disk —
     so every trimmed session came back on the save that follows moments later.
     Removed rather than "fixed": making it real means deleting your chat history
     on every device as a side effect of a display limit, which is a retention
     decision that needs your say-so.

  Nothing you can see changes. Chat text, chip labels and thumbnails are all
  untouched, and only the on-disk copy loses the unread payloads — the in-memory
  ref keeps everything for the turn it belongs to.

## [0.69.3] - 2026-08-23
### Fixed
- **The comment above the session-storage code said `sessions.json` is
  device-local. It is synced across devices.**

  Caught while measuring `sessions.json` for a planned size fix — the comment
  would have set the wrong risk level for that very change.

  `.curator/sessions.json` is **not** excluded by `.stignore` (which lists only
  `state.sqlite` and `runtime/` under `.curator/`), `SYNC_IGNORE_GUIDE.md`
  states it "may be synchronized because the plugin merges by session",
  `types.ts` calls it *sync-safe*, and `deletedSessionIds` exists so a deletion
  on one device propagates to another — which is meaningless for a local file.

  Every signal in the project said *synced* except the one comment sitting
  directly above the code that owns the file. That is the comment someone reads
  before changing its schema, and **a schema change to a synced file is a
  cross-device transport change** — an older plugin on another device reads what
  a newer one wrote. Rated device-local, that change looks routine.

  A test now fails if the claim comes back.

## [0.69.2] - 2026-08-23
### Fixed
- **An empty database was reported as an empty vault, while 89 MB of your
  knowledge sat recoverable in the same folder.**

  `state.sqlite` is machine-local and keyed by the vault's resolved path. Three
  ordinary events therefore mint a brand-new, empty database:

  - the repo's `.cache/` is cleared or not carried to a new machine;
  - you open the vault on a second device;
  - **you rename or move the vault.**

  `connect()` self-heals a schema into it and `wiki status` printed zeros — exactly
  what a vault nobody has ever ingested looks like. The natural next step is to
  re-ingest everything, which costs hours of provider time to rebuild what is
  already on disk.

  `wiki status` now says so, in text and in `--json` (the plugin dashboard reads
  the latter), naming the journal and the command:

  ```
  This vault's local database is empty, but 2 sync journal(s) are present
  (dev-28e419df29f2.jsonl, dev-bd8d7f0753da.jsonl; 86.2 MB). Your knowledge is
  not lost — the database is machine-local and is re-keyed when the vault moves
  or the repo cache is cleared. Recover with:
      wiki db import .curator/sync/dev-28e419df29f2.jsonl
  ```

  It is silent for a genuinely new vault, for a populated database, and for a
  zero-byte journal — a healthy vault writes a journal on every auto-sync, so
  keying the warning on the journal alone would fire always and train you to
  ignore it.

## [0.69.1] - 2026-08-23
### Fixed
- **`wiki sync` said it rebuilds four files and rebuilt two.**

  Its own docstring, `sync.py`'s module docstring, the `wiki sync` CLI help, and
  the CLI table in `CLAUDE.md` all say it rebuilds `index.md`, `ledger.md`,
  `log.md` and `overview.md`. It called `rebuild_index` and `append_log_entry`;
  `ledger.md` and `overview.md` were only ever written by `wiki build`.

  So correcting a source and running `wiki sync` gave you a fresh `index.md`
  beside a `ledger.md` reporting the previous build's counts — under a header
  reading *"Auto-maintained by the Curator engine."* Both writers are pure
  (directory globs, one COUNT query, a file write; no LLM), which is why sync can
  simply call them.

- **The docs put `state.sqlite` inside the vault. It has never been there.**

  `SYSTEM_BEHAVIOR.md` said *"repo-cache `state.sqlite`"* in a dozen places and
  *"`.curator/` — AI-Only Space: `state.sqlite` (source of truth)"* in §22.3. The
  vault tree in `CLAUDE.md` and both contribution guides showed the second one.

  It resolves to `<repo>/.cache/vaults/<sha256(resolved_vault_root)[:16]>/state.sqlite`
  (`config.py::WikiPaths.state_db`) — deliberately outside the vault, so Syncthing
  never has to reconcile two devices writing one SQLite file.

  This was not a cosmetic error. A **0-byte legacy stub** can sit at the
  documented path, so following the docs finds a file, opens it, reads zero rows,
  and concludes the vault was never ingested. On the reference vault the stub is
  0 bytes and the real database is **287 MB**. A test now fails if any of those
  documents places it in the vault again.

## [0.69.0] - 2026-08-23
### Fixed
- **A question asked in any language other than English could not reach a
  broad-synthesis or discovery answer. Ever.**

  The route signals are English-only by contract, and they match against
  `working_query` — which falls back to your raw question when nothing derived an
  English one. So "내 볼트 전체의 주제를 정리해줘" matched no signal and landed on a
  narrow `local` lookup **by construction, every time**, no matter what it asked
  for.

  This was fixed at one boundary in v0.47.0 — the Obsidian sidebar — and four
  other surfaces never caught up: `wiki query`, `curator_query`,
  `curator_fetch_context`, and `curator_explore`. The comment in `router.py` said
  it was "fixed at the boundary", which read as though that meant all of them.

  The derivation now happens **once, in the one place every surface passes
  through**, so a new surface cannot forget it.

### Changed
- **A non-English question now costs one extra model call; an English one costs
  nothing.**

  The derivation is skipped when the question is already >85% ASCII — the same
  threshold `translate_to_english` has always used, now extracted so the two
  cannot drift apart.

  This is deliberate, and measured. The deterministic fallback returns **1,508
  hits across the same 28 sources with the same top results** as the LLM's 1,500,
  *"for none of the LLM's 12-50 s"* — so derivation buys nothing on search terms.
  What it uniquely produces is the **intent**, and intent only changes an outcome
  where the English-only signals cannot work.

  And for an English question, `working_query` is **your own words**. Routing on
  what you typed beats routing on a paraphrase: the same question paraphrased
  eight times produced eight different phrasings and flipped the route 6-in-8.

### Note
- The Obsidian boundary still derives before calling in, because it also decides
  whether your message is a knowledge question at all — `"translate this
  paragraph:"` should not trigger retrieval. That is a judgment about what your
  *message* is, and it should not be made by the retrieval layer for four other
  callers. A request that already carries a derivation is not derived twice.

- The evidence pack now returns `english_query`: the query the system actually
  ran, rather than the raw question echoed back.

  This completes ROADMAP A8, which shipped as two releases — v0.68.0 fixed what
  `"derived"` means, because moving the derivation first would have spread that
  release's silent-failure mode from the plugin to the CLI and MCP.

## [0.68.0] - 2026-08-23
### Fixed
- **A dead LLM provider could make retrieval fail silently, with the warning
  built to catch it switched off by the caller.**

  Found by an adversarial agent during planning, then reproduced directly. The
  chain:

  1. the provider fails, so the search-query derivation falls back to scraping
     terms from the raw message;
  2. that fallback keeps the letters of **any** script — its docstring claimed
     "an honest empty for pure non-Latin input", and it never did that — so
     `'이 논문의 전체 주제를 요약해줘'` comes back as Korean;
  3. the result still looks like a question, so the boundary does not bail;
  4. the boundary then marked it `english_query_status = "derived"`
     **unconditionally**;
  5. the entity-seeding warning is scoped to `"unset"` — so it was **suppressed**.

  Net effect: English-only entity seeding matched nothing, and nothing was said
  about it. A status that can only say *derived* or *nobody derived* cannot
  express *somebody tried and failed*, so the caller had to guess — and guessed
  the value that disabled the alarm.

  `english_query_status` now has a third value, `"fallback"`, which warns exactly
  as `"unset"` does. `DerivedQuery` states how it was produced instead of leaving
  the caller to infer it.

- **`curator_query` no longer relabels the raw question as the English query.**

  It passed `english_query=question` — the user's untouched text, asserted to be
  the system's internal English query. `english_query` reaches past routing into
  entity seeding, the BM25/vector query string, and the HyDE prompt.

  `working_query` falls back to `question` when `english_query` is empty, so the
  two behave identically and the claim cost nothing to drop — which is also why
  the lie survived: nothing downstream could tell a real English query from a
  relabelled Korean one.

### Note
- `_fallback_search_terms` keeps every script on purpose — that is right for the
  mixed-script case that dominates this domain (`"ellipsoid 형태의 quadric"`). The
  code is unchanged; the docstring that promised otherwise is corrected, and the
  honesty now lives in `status` where a caller can act on it.

## [0.67.0] - 2026-08-23
### Added
- **Every query trace now says whether a search-query derivation ran, and what
  it found.**

  Two facts used to be stored identically: *"a derivation ran and legitimately
  found no search terms"* — which is normal for a whole-corpus question — and
  *"no derivation ran at all"*. Both leave `english_query` empty.

  Confusing them has a cost on record. Two single-run observations of one
  question showed an empty derived query, and a routing design was built on the
  premise that empty was a stable, deliberate signal. Running the same question
  eight times gave **0/8 empty** and a **6-in-8 route flip** instead — an
  entirely different bug. One sample was mistaken for a property, twice, because
  nothing stored enough to check afterwards.

  `retrieval_trace.context_service.derivation` now records `status`
  (`derived` / `unset`), `search_query_empty`, and `routing_intent`.
  `question_hash` already groups repeated runs of the same question, so the
  eight-run check that found the real bug is now something you can do from
  stored data.

- **`wiki inspect answer` prints it, along with the route reason.**

  Storing a fact in a JSON column that only `--json | jq` reaches is not
  visibility. The human summary previously printed `route=` and nothing else —
  not even *why* that route was chosen.

  ```
  Trace: QTR-1764bada route=global
  Route reason: derived intent: synthesis
  Derivation: derived - no search terms, intent=synthesis
  ```

  On the CLI and both MCP paths this reads `not run - routed on the raw
  question`, which is honest: those three surfaces never derive. That gap is
  real and tracked separately — this release makes it visible rather than
  assumed.

### Note
- The field is `routing_intent`, not `intent`, deliberately.
  `retrieval_trace["intent"]` already exists in the same document and means
  something else: the keyword-cue detector (`definition` / `comparison` /
  `procedure` / `default`) that steers query *expansion*. Different mechanism,
  different vocabulary — they must not share a key.

  Additive only. No schema migration, no change to routing behaviour, and the
  context-service fixtures assert subsets rather than exact shapes.

## [0.66.0] - 2026-08-23
### Removed
- **`curator.query_router` — a prompt contract that was promised for five months
  and never called once.**

  `SYSTEM_BEHAVIOR.md` §17 has said since v0.3.1 that "an LLM router
  (`curator.query_router`) is used only when deterministic signals are
  ambiguous". The contract was registered, required by the prompt-registry test,
  and listed in §15 — and had **zero production call sites**. The spec described
  behaviour the code did not have.

  It was deleted rather than implemented. The evidence that it had never run was
  inside the prompt itself: `ROUTER_SYSTEM` listed `source-section` **twice**,
  with two different descriptions, and the `allowed_routes_block` /
  `graph_status_block` strings its input model required appeared **nowhere else
  in the repository** — nothing had ever built them.

  | probe | result |
  |---|---|
  | production call sites | **0** |
  | `prompt_runs` rows, across all 29 databases in the repo | **0** |
  | readers of `ROUTER_CONTRACT` | **0** |
  | eval fixtures | none — `wiki prompt eval` runs a hand-listed set, not a per-contract sweep |

  The job it was invented for now happens in a call that already runs:
  `curator.query_search_terms@v2` states the message's **intent** from the step
  that reads your actual words (v0.65.0). A second round trip would read the
  question again and return a route that `choose_route` must still re-gate
  against `allowed_routes` and `GraphStatus` in Python. Its two unique outputs,
  `confidence` and `fallback_route`, were consumed by nothing.

  Routing is now documented as what it is: **deterministic, full stop.**

  No migration. Nothing stored referenced the id. The only user-visible change is
  one fewer row in `wiki prompt list --family query`.

## [0.65.0] - 2026-08-23
### Fixed
- **The same question no longer reaches a different corpus each time you ask it.**

  Routing matched keywords against the *English paraphrase* the system derives
  from your question — not against your question. Asking
  "내 볼트 전체의 주제를 정리해줘" eight times produced eight different paraphrases,
  and the route followed whichever synonym came out: `themes` and `summary` are
  in the pattern, `overview` is not.

  | | before | after |
  |---|---|---|
  | "summarise the themes of my whole vault" ×8 | **6 × `global`, 2 × `local`** | **4/4 `global`** |
  | "explain across several papers why 2D GS beats 3D" ×4 | consistently `local` — the wrong corpus | **4/4 `global`** |
  | a narrow fact question ×2 | — | **2/2 `local`** |

  The extractor now states the message's **intent** alongside the search terms,
  and routing reads that. It removes the lottery in both directions: a synthesis
  question no longer needs to be lucky with vocabulary, and a narrow question is
  no longer dragged to `global` because its paraphrase happened to contain the
  word "summary".

  **Intent is not route.** The model says what kind of question it is; the
  existing policy and graph gates still decide where it can go. A workspace whose
  `curate.yml` forbids `global` still degrades to `local` and records why, and an
  unrecognised value falls through to the previous behaviour rather than
  misrouting.

- **The warning the code has promised since v0.47.0 now exists.** `seed_terms`
  documents that "`context_fetch` warns about it rather than quietly returning
  nothing" when an underived question reaches entity seeding. Nothing anywhere
  inspected the derived query, so it never warned — a documented invariant with
  no implementation, which is why this item was diagnosed wrongly three times.

### Changed
- `curator.query_search_terms` gains **v2**, which adds the intent to v1's rules
  verbatim — a test asserts every v1 rule survives into v2, because those rules
  (the pasted-body case, notation preservation, the length cap) are load-bearing
  and a rewrite is how you lose one without noticing. **v1 stays registered** so
  historical prompt traces keep resolving.
- `derive_search_query` returns a `DerivedQuery` rather than a 3-tuple. Seven
  in-repo call sites; `mypy` catches every one.
- `QueryRequest.english_query_status` records only whether a derivation ran. A
  first draft carried a third value for "ran and found no search target"; once
  intent did the routing, nothing read it, and a vocabulary entry nothing
  consumes reads as a guarantee somebody can rely on.

## [0.64.0] - 2026-08-23
### Added
- **`wiki status` reports knowledge units that search cannot find.** The vault
  held **977 (11%)** units that had never entered the search index, and nothing
  said so — the only way to learn it was to query the database by hand. It was
  **61% of the corpus** when an audit first measured it.

  Deliberately narrow. A first version of this also listed per-layer error counts
  and "never produced anything", then the command was actually read: the
  **Pipeline Layer Status** table already prints `L3 | 0 done | 36 error`, and
  **Collections** already prints `L4 Synthesis/ 0`. Restating them made the
  output longer and less legible. The index gap is the one signal nothing showed.

- `get_stats` now carries `units_live`, `units_indexed` and `units_unindexed`.
  The gap is an **anti-join**, not `live - indexed`: a unit indexed twice, or an
  index row pointing at a retired or deleted unit, makes the subtraction cancel a
  real gap and report a healthy index.

  The unit count is scoped to **published** rows. Since v0.62.0 an interrupted
  extraction leaves durable unpublished ones — measured, a single source held
  **5,358** — and those are absent from the index *because they are not published
  yet*. Counting them would have inflated the gap and fired this warning through
  every long ingest.

### Fixed
- **Query expansion no longer fails silently.** Three sites returned `{}` on any
  exception with no logging at all: the expander LLM call, parsing its
  completion, and the expander as a whole. A dead expansion model meant search
  ran unexpanded — recall dropped and nothing anywhere said why.

  This was `RC-5(a)` in the 2026-08-04 defect audit, the **one survivor of ~29
  findings**. It outlived the batch meant to fix its class because the synthesis
  said "expect a duplicate and merge rather than fix twice", and the batch fixed
  two of the three sites.

## [0.63.0] - 2026-08-22
### Added
- **Graph extraction now survives an interruption.** Every graph batch must
  succeed for a source to publish, and results were held in memory until the
  publish gate — so a single capacity deferral discarded the whole run. Measured
  on the reference vault, the largest source completes **at most ~3 usable
  batches per capacity window**; it could never converge, no matter how many
  times it was retried.

  Each validated batch is now staged in `graph_batch_results` and replayed at
  publish time, keyed on the same rendered-prompt digest that L2 resume uses. A
  fully staged source makes **zero provider calls** on a second run; a run
  interrupted after one of two batches re-pays exactly one.

  Copy-on-stage is unchanged: nothing reaches `graph_entities` or
  `graph_relations` before the publish gate, and the staged rows are deleted
  inside the publish transaction — so a publish that rolls back keeps the resume
  its own failure still needs.

- **`wiki source clear-graph-cache <id>`** drops a source's staged batches when
  its graph looks wrong. Re-ingesting does not clear them: `wiki add --force`
  re-adopts the same unit rows, leaving the batch keys unchanged.

### Fixed
- **A graph batch is no longer sent every span id in the source.** The chunk
  budget bounded the units block but not the prompt, which also carried the
  source's whole span-id list on every batch. On the reference vault's largest
  source that was **124,669 characters of span ids against a 15,981-character
  units block — 87% of every prompt** — while the batch cites a median of 67 of
  those 8,905 ids.

  Per batch the prompt drops from **143,582 to a median 19,938 characters**;
  across the source's 24 batches, from 3.4 MB to 464 KB. **7.4x less.** This is
  why quota looked healthy while runs kept dying on capacity: it was being spent
  about seven times faster than the work required.

  Nothing citable is lost — a relation is grounded in the spans its own units
  carry — and validation narrows with the prompt, so the model is judged by the
  list it was given.

- **Knowledge units are now listed in a deterministic order.** `created_at` has
  one-second granularity and L2 inserts a whole batch inside one second — every
  one of the reference source's 5,358 units sits in a tie group. Tied rows were
  ordered by SQLite's sorter rather than by the query, so a reorder would move
  every graph batch boundary and silently invalidate the entire cache.

### Changed
- **Model catalogue refreshed, and the default model moves with it.** Added
  **Gemini 3.7 Flash** (Antigravity), **Claude Opus 5** and **Claude Sonnet 5**,
  and DeepSeek's **`deepseek-v4-flash-vision-exp`**. The catalogue's first entry
  per provider *is* that provider's default, so a new install now defaults to
  `gemini-3.7-flash` and `claude-opus-5`. **An existing configuration is
  untouched** — a pinned `llm.primary` keeps whatever it names.

  Also corrects a real error: DeepSeek's context window was recorded as **128K
  when all three models carry 1M**, so the Model row under-reported the window
  eightfold.

- `SCHEMA_VERSION` 13 → 14 (additive: one new machine-local table, absent from
  the cross-device export). **Devices that upgrade at different times stop
  syncing until both are on v14** — the export format itself is unchanged.

## [0.62.5] - 2026-08-22
### Fixed
- **Answers about GPUs and vision no longer fail with "quota or capacity is
  currently unavailable" while your quota is fine.** The provider was never
  refusing. The plugin classified a finished CLI run by keyword-matching
  `stderr + "\n" + stdout` — and stdout **is the model's answer**. The matcher
  looks for `"capacity"`, `"quota"`, `"429"`, and `"rate limit"`, which are
  ordinary vocabulary in CUDA and computer-vision writing ("register capacity",
  "cache capacity", "model capacity", "the rate limit of convergence"). Any
  answer containing one was discarded, already paid for, and reported to the
  user as a quota failure.

  Quota evidence now comes from `stderr`, and from stdout only when the run
  produced **no answer at all** — some CLIs print the refusal there instead of on
  stderr. An answer that came back is delivered, whatever words it contains.

- **The quota detector no longer guesses from bare words.** It now matches the
  phrases providers actually emit — `RESOURCE_EXHAUSTED`, `No capacity
  available`, `Individual quota reached`, `insufficient balance`, `rate limit`,
  and a word-bounded `429` — mirroring the backend's `_is_capacity_error`. This
  also fixes three sites the answer-scanning patch left open, because they all
  call the same matcher: the **mid-stream stderr check that kills the running
  CLI**, and two that match an exception message where a typed id such as
  `ATM-429abc12` contains "429".

  The asymmetry decides the design: a false positive destroys an answer you
  already paid for, while a false negative costs only the "switch provider" hint,
  since the raw CLI error is shown either way.

- **Codex quota refusals are still detected.** Codex prints a JSON event stream
  to stdout, and the "did we answer at all" check falls back to that stream when
  no answer text could be extracted. The quota decision no longer inherits that
  fallback — otherwise a refusal printed inside the event stream would stop
  stdout being scanned, and the raw JSON would be shown as if it were an answer.

  Verified against a live `agy` 1.1.18, which answered normally throughout,
  confirming the quota was never the problem.

## [0.62.4] - 2026-08-22
### Fixed
- **Your API key no longer disappears every time the plugin updates.** Reproduced
  deterministically: deploying the plugin and reloading Obsidian was enough, and
  it blocked the acceptance test twice in one day.

  Three things combined. The key is deliberately stripped from `data.json` so it
  cannot ride Obsidian Sync or a git-tracked vault — that stays. Its only other
  restore path was the `DEEPSEEK_API_KEY` environment variable, which a
  GUI-launched Obsidian does not have. And the encrypted store that would have
  fixed it had **no way to be reached from the plugin at all**.

  Keys entered in settings are now stored encrypted outside the vault and read
  back at load. **Obsidian's key and the backend's `wiki config` key stay
  separate by design** — they may be different accounts or tiers — so they are
  stored under different names and share only the encryption.
- **The popover no longer waits a minute and a half to answer.** Its vault lookup
  is capped at 4 s — measured, the lookup itself takes **59–99 s** — fetched once
  per popover instead of once per follow-up, and skipped entirely for an edit
  request. Evidence enriches the answer; it never gates it. A `try/catch` was not
  enough on its own, because it catches a failure but not slowness, so a stalled
  backend previously meant no answer at all.
- **"Can you expand on this?" is a question, not an edit.** The rule that skips
  vault search for edit requests matched bare keywords, so `expand`, `fix`,
  `correct` and `format` inside ordinary questions switched the search back off —
  the exact problem v0.62.3 set out to fix. An edit now has to look like a
  request: the verb leads the sentence, or the sentence is a Korean imperative,
  and anything ending in a question mark never counts.

### Fixed
- **Search no longer loses the word that matters when the provider is down.**
  When query derivation fails, the fallback builds search terms from the message
  itself — and it was stripping every non-ASCII character, so `Plücker` became
  `Pl` + `cker`. Measured on a real index: `"Plücker"` and `"plucker"` each match
  **172 documents across 22 sources** (the index normalises the diacritic) while
  `"Pl" AND "cker"` matches **none**. The single most discriminating term in the
  query was destroyed, and the fallback compensated by matching stray single
  letters from matrix notation (`L`, `T`, `Q`), returning more results with worse
  precision.

  The fallback now keeps letters and digits of any script and drops
  single-character noise. On the same query it returns **1,479 hits across 28
  sources** against the old **1,310 across 27** — and against **1,500 across 28**
  for the LLM-derived query it replaces, with the same top sources, in **none of
  its 12–50 s**.
### Fixed
- **The popover's vault search now looks for the passage you selected, not just
  the words you typed.** v0.62.3 wired the retrieval and then handed it the
  question alone — and a popover question is almost always deictic ("이 제약이
  무슨 뜻이야?", "what does this mean?"), so it carries no topic at all. The
  subject is in the selection.

  Measured live against the vault: the question alone returned **0 evidence items
  from 0 sources**, and the answer said as much — *"검색 결과 추가로 매칭된 노트는
  없었다"*. The selection prepended to it returns **35 items across 9 sources**.
  The selection is capped so a page-long drag does not become the query.

- **The assistant now surfaces your other notes, not just the one you are in.**
  Selecting a passage and asking *"what else have I written about this?"* used to
  answer only from the note the selection came from. Both surfaces failed, for
  two unrelated reasons.

  **The popover had no vault retrieval at all.** It assembled from the selection,
  the current file's outline, pinned sources and citation resolution — nothing
  else — and the vault-level query had **zero callers anywhere in the plugin**.
  It now resolves vault evidence *before* the turn through the same DB-native
  search the sidebar uses, adding **no tool rounds** and granting the popover no
  tools.

  **The sidebar had the retrieval wired and then switched it off**, in the two
  situations that need it most. Any selection suppressed it — which is the case
  that asks for it — so that now applies only when you ask for an *edit*
  ("rewrite this", "번역해 줘"), not when you ask a question. And a focused PDF
  suppressed it unless some open source had L3 complete; measured on a real
  vault, `l3_status='done'` for **0 of 44 sources**, so with any PDF tab open the
  vault query never ran at all. L3 decides how an answer may be *framed*, not
  whether evidence may be *retrieved* — and the retrieval does not need it: the
  same question returned 30 evidence items across 6 sources with zero L3 reports.

  Measured on the reported case: asking about a Plücker–Quadric constraint
  surfaced only sections of the current note, while the vault held **21 published
  sources** on the topic — including the reader's own `Silhouette Based
  Reconstruction`, `EWA splatting`, `Auto Calibration` and `MultipleViewGeometry`
  notes.

## [0.62.2] - 2026-08-22
### Fixed
- **A job could never be claimed on a state database nothing had initialised —
  and the failure repeated forever.** Opening a state DB stamps its
  `schema_version` row, which is DML, and Python's `sqlite3` opens an implicit
  transaction for that write. The commit came *after* the connection was handed
  to its caller, so the caller received a connection already inside a
  transaction and `claim_next_job`'s `BEGIN IMMEDIATE` raised `cannot start a
  transaction within a transaction`. The raise then skipped the commit, rolling
  the stamp back and restoring exactly the state that produced the error, so
  every later call failed identically. The same applied to an existing vault the
  first time a job was claimed after a `SCHEMA_VERSION` bump, which takes the
  `UPDATE` branch of the same stamp.

  Schema installation and the version stamp are now committed before the
  connection is handed over.

  To be precise about who this affected: `wiki jobs run` and the MCP background
  worker were **not** failing, because both call `recover_stale_jobs` first and
  that commits the stamp on their behalf. What was broken is
  `db.claim_next_job` on its own — protected only by an incidental line
  ordering that nothing tested or documented.

- **A tiny reported context window turned one document into thousands of model
  calls.** L2 extraction subdivided an oversized span at `chunk_size = budget -
  500` with nothing keeping that positive. A client reporting a budget at or
  below 500 produced a negative size, which the chunker's forward-progress guard
  absorbed into one chunk per character *position*, each holding nearly the
  whole remaining text: 3,000 chunks totalling 810,000 characters from a
  3,000-character span, then one LLM call per chunk. Measured on eight
  3,000-character sections: **3,920 batches, now 40**. No shipped provider
  reports a window that small, so nobody was billed for this — but a single bad
  configuration value armed it, and it failed by spending rather than by
  failing.

  Sizes derived from the reported budget now carry a positive floor, and the
  chunker rejects a non-positive size outright instead of absorbing it. The
  budget itself is still used exactly as the client reports it: a small-context
  local model is never handed a larger default, which would only move the
  overflow to the provider.

- **Entity extraction could be handed an empty statement labelled
  `[TRUNCATED]`.** The graph-extraction path carried the same unchecked
  `budget - 500`, there as a slice bound. Negative, it amputated the tail of
  every long statement instead of keeping its head, and erased any statement
  shorter than the shortfall completely — leaving the model nothing but the
  truncation marker to extract entities and relations from.

  All three were re-verified against v0.61.1 before this release: none of the
  forty commits between v0.58.0 and v0.61.1 touched any of them.
## [0.62.1] - 2026-08-22
### Fixed
- **One provider refusal no longer kills an 87-batch compile.** Graph extraction
  guarded validation failures but had no `try` around the prompt runner, which
  closes its trace and re-raises — so a single refusal unwound the caller's
  staging block and failed the whole source. That is fatal at scale because
  publishing needs **every** batch: measured on a 673-page book, ~87 batches at a
  43% refusal rate meant the run aborted after 2 (expected 1/0.43 = 2.3) and the
  chance of a clean pass was about 7×10⁻²². The refusal is not deterministic —
  live, the same batch went through on its 3rd and 7th tries — so a refused batch
  is now retried, and exhausting the attempts reports the reason instead of
  raising.
- **A rate limit is not retried in that loop.** Splitting the live failures by
  cause gave 5 of 11 as 429 and 6 as permission denials. Hammering a 429 spends
  the budget against the wall and undoes v0.61.1, whose point is that a refused
  job stays queued and the worker says how long to wait. Capacity now propagates,
  detected by asking the client's own capacity block rather than by matching the
  message — substring matching on error text is what misclassified a permanent
  failure as transient in v0.62.0.
- **A killed run no longer strands its extraction.** The handler that releases
  a failed generation's units lives in an `except` block, so it covers every
  failure the process survives and none that it does not. Measured after killing
  a compile mid-graph: the generation stayed `staged` holding all **5,358**
  extracted units with **zero** adoptable, so the next run would have re-paid 85
  minutes of extraction that was sitting right there. A pre-existing staged
  generation is now released before extraction starts.

## [0.62.0] - 2026-08-21
### Added
- **L2 extraction is resumable.** An interrupted run used to discard every batch
  it had finished. Measured on a 673-page book: it completed **all 277
  extraction batches twice** and lost both at the publish step — about **86
  minutes** of provider work per attempt, at a median batch latency of 18.6 s
  across 1,811 real extract calls.

  Two things had to change, and shipping only the first would have been a
  feature that misses its own headline case. Batches are now persisted as they
  validate, **and** a failed staged compile releases that work instead of
  deleting it — the failure handler used to run a copy-on-stage discard that
  removed every row the extraction had written, which is precisely what happened
  to the book above. Caught by running it, not by a test: the unit tests call the
  extractor directly and never reach that handler.

  Each batch's units are persisted as it validates, with `generation_id`
  left NULL. That marker already meant "extracted, not authoritative" on the
  writer side, and `compile.py` stamps the staged generation onto the returned
  ids before the publish gate runs, so **publication is unchanged**: a partial is
  stored, never served. Search materialization joins `compiler_generations` on
  `generation_id`, so no partial can reach the search corpus.

  Resume keys on `prompt_runs.input_hash` — the digest of the fully rendered
  system+user messages — so there is **no new table, no new column and no
  migration**. It covers the batch text, the span ids in it, and the prompt
  template, which means a template edit invalidates every batch by construction
  rather than by a configuration key someone has to remember to bump. Across the
  same book's three attempts the hash set was **277 distinct values every time,
  and identical across all three**.

  Two simpler keys were measured and rejected. A batch index cannot work because
  `optimal_chunk_chars` changes the batch count with the provider — 12 / 23 / 46
  / 93 for one source. Span coverage cannot work because **1,790 of that book's
  8,692 spans (20.6%) appear in more than one batch** within a single clean run,
  so a span-keyed resume would have skipped work that was never done.

  The skip check runs at every level of batch narrowing, not only at the top, so
  a batch that previously succeeded only as split halves is not re-paid; and it
  accepts `repaired` as well as `ok`, because a JSON-repair retry still produced
  validated output (57 such runs in the reference vault carry 687 units).

  **Verified on the real thing.** The same 673-page source was run cold — 277
  calls, 85 minutes — and then resumed: **0 extraction calls, 277/277 reached in
  about two minutes**, counted against a snapshot taken immediately before
  (`prompt_runs` 1941 before and 1941 after).

  Resume stops at the source text: an L1 re-parse mints new span ids and the
  whole source is re-extracted. That is deliberate, and sharp — measured at
  **99.7% span overlap the batch hashes still shared only 21.7%**, because one
  changed span shifts the packer and invalidates everything after it.

### Changed
- **The compiler audit and synthesis dependency collection read published units
  only.** Now that a generation-less row can survive a crash, three table-wide
  scans would have reported an abandoned extraction as if it were knowledge —
  for the 673-page book, roughly 25,000 INFO lines out of `wiki lint`. They now
  require `generation_id IS NOT NULL`. Verified inert on real data: the audit
  report over a 233 MB vault is **byte-identical before and after**.
- A structural test now fails any new table-wide read of `knowledge_units` that
  neither filters on `generation_id` nor records why a partial is harmless
  there. The habit was real — `synthesis_audit` read the whole table with no
  filter at all.

### Fixed
- **A random span id no longer classifies a permanent failure as transient.**
  Retry classification substring-matched the whole failure message, and an L2
  batch failure embeds up to five `<PREFIX>-<8 hex>` ids. Random hex reads "503"
  or "429" often enough to matter: **1 spurious retry in 15 runs** of a single
  test, whose failing run carried `SPAN-13850308`. A permanent provider failure
  was being requeued and re-run three times whenever an id happened to look like
  a status code.

## [0.61.1] - 2026-08-20
### Fixed
- **A rate-limited job no longer restarts from scratch into the same wall.**
  Measured twice on a 673-page book: it completed **all 277 extraction batches**,
  was refused at the staged compile with a 429, and was requeued — which
  restarted it at batch 1, re-spent the same provider budget, and arrived at the
  identical refusal. Both runs discarded roughly **90 minutes** of provider work
  and published nothing; both compiler generations are `discarded` with zero
  surviving units.

  The 429 is a **burst limit, not exhaustion** — a trivial call succeeded within
  a minute of each failure — so a retry that merely waited would have published.
  The backoff for exactly this already existed and was inert twice over: it was
  per-client state, and `run_next_job` builds a fresh client per job; and it was
  consulted only by `ping()`, which the ingest path never calls.

  The block is now per provider and process-wide, and the worker asks **the
  client that would run the job**, before claiming it, so the job stays queued and claimable instead of being consumed into a
  failure. A source large enough that extraction exhausts the window can now
  finish on a later attempt rather than never.

  Scoped per provider, deliberately: `antigravity-cli` defaults to a failover
  with an Ollama fallback that already absorbs this error, so a global block
  would have stopped work a healthy fallback could do — including in a vault
  using no Antigravity at all.

- **A deferral is no longer reported as a completed drain.** "Nothing to do" and
  "work is waiting and the provider is refusing" both stop the loop and mean
  opposite things. `wiki jobs run` now says the queue is untouched and roughly
  how long to wait, instead of `Processed 1 job(s).` over a full queue.

## [0.61.0] - 2026-08-20
### Fixed
- **A file you are not allowed to read is no longer reported as missing or
  damaged.** Ingesting a Zotero-referenced PDF failed with `parse failed: Cannot
  parse PDF …` for a 21 MB file that opens instantly in Finder. The file was
  fine; the process was refused. Three checks in a row each answered a question
  nobody asked:

  ```
  exists()        -> True     it is there
  os.access R_OK  -> True     the permission bits allow it
  open()          -> PermissionError errno=1
  ```

  `os.access` is the trap, and it is why this is a release rather than a
  one-line patch: it reads POSIX permission bits and macOS denies below them.
  The obvious fix — "add a readability check" — would have reported a readable
  file and let the caller fail citing something else, exactly as before.

- **The message now names a folder you can act on.** `Not permitted to read
  <path> — grant access to <folder>`. The folder is the shallowest ancestor that
  is itself refused, found by probing upward. Measured on the live case it
  resolves to `~/Library/Mobile Documents` — the folder a user actually enables.

### Added
- **`wiki status` lists unreadable sources once**, grouped by the folder to
  grant, instead of leaving you to discover them one failed ingest at a time. On
  the live vault it found **four**, not the one that prompted the work — and one
  of them had ingested successfully the day before, so the report is about the
  machine's current state, not a permanent property of the source.
- `attachment_file_denied` joins `db_missing`, `attachment_key_missing` and
  `attachment_file_missing` in the Zotero resolution taxonomy. **The taxonomy is
  where this bug lived**: the code implemented all three states faithfully and
  none of them meant "present but not readable", so a 21 MB file on disk had to
  come back as missing. The spec changed first.
- `curator.file_access` — `probe()` returning `ok` / `missing` / `denied`, and
  `grant_root()`. Deliberately three outcomes rather than a bool, because a bool
  is what left the old helper unable to say anything: it picked a file it could
  not read, reported success, and left the parser to explain the failure wrongly.

### Changed
- `parsers.parse` raises `ParserAccessDenied(ParserError)` for a refusal. A
  subclass, so all three existing `except parsers.ParserError` sites keep working
  and get a better sentence for free. The check sits at the dispatch rather than
  inside the PDF parser because a denial has two shapes: an unreadable parent
  makes `path.exists()` itself raise, while macOS TCC lets `stat` through and
  refuses only `open`.
- **A denied attachment no longer degrades to the note.**
  `_resolve_reference_source` is a best-effort resolver where every failure means
  "no external file here, use the stub". Introducing a denied state made that
  fire for a file that is present and merely refused — so the source would have
  ingested four lines of frontmatter and reported SUCCESS, a 673-page book
  silently becoming metadata. Only the denial escapes; every other failure still
  degrades as designed.

### Notes
- Found by running it, not by a test: both the degrade-to-stub regression above
  and a `wiki status` that stayed silent because the reporting helper caught its
  own signal under a blanket `except Exception`. Both now have tests.
- Not in scope: no folder picker and no permission request (macOS has no API,
  and a background process is denied silently rather than prompted); no change to
  what a spawned CLI may read; the plugin's own read path still surfaces a raw
  error.

## [0.60.0] - 2026-08-19
### Fixed
- **A long ingest no longer dies because the model decided to write a program.**
  Asked to return knowledge units as JSON, the Antigravity CLI — which is an
  *agent*, not a text completion — wrote a `python3` script to build the object,
  and on another job a second one to `jsonschema`-validate it. The permission
  layer denied `python3`, the CLI exited 1, and the job failed. It took the two
  largest sources in the vault: **Hartley at batch 37 of 277 after 29 minutes**,
  and **Nicholson at batch 9 of 15**. Non-deterministic — 34 of 36 jobs in the
  same run never took that route — so those books were un-ingestable by luck.

  The fix is not a wider sandbox. Granting `python3` would trade arbitrary code
  execution for a JSON serialiser. Instead the extraction now uses the CLI's
  native structured-output mode: the contract's schema is sent with the prompt
  and a validated object comes back. Measured, the model answers in **one turn**
  — no tool call, so there is nothing for the permission layer to deny.

### Added
- **`supports_structured_output`, declared per client.** False by default; True
  only where the native mode has been measured. `agy` has one. `claude` and
  `codex` are *not assumed to* — this seam has produced four separate failures
  (v0.48.4, v0.55.0, v0.56.1, and this), every time by assuming one CLI behaves
  like another.
- `prompting/json_schema.py` — flattens `$defs`/`$ref` out of a pydantic schema
  before it reaches the CLI. **This is load-bearing, not cosmetic.** Measured
  with the schema as the only variable:

  | schema | status | turns | units returned |
  |---|---|---|---|
  | as emitted (`$defs` + `$ref`) | SUCCESS | 2 | **0** |
  | flattened | SUCCESS | **1** | **2** |

  The referenced schema does not fail — it *succeeds and returns nothing*,
  leaving the real answer in the response text under field names the contract
  never declared. Shipping without flattening would have ingested every book to
  nothing while reporting success.

### Changed
- **An empty result is only treated as a defect when the model took a detour.**
  Review caught the first version second-guessing every legitimately empty
  batch: a references page or boilerplate correctly yields `{"units": []}`, and
  the CLI — an agent — says so in a sentence. Returning that sentence where JSON
  is expected fails the parse, burns the one-shot repair retry, and can fail the
  batch, arriving at the same job-killing failure this release removes from the
  other direction. `num_turns` separates the two: one turn is a direct answer
  and its empty structure is trusted; more than one turn is the measured defect
  shape and still degrades to the text path.
- **An empty structured result after a detour is treated as a
  defect, not an answer.** It degrades to parsing the text — what a client
  without this capability does — and logs the degradation, rather than telling
  the pipeline the model found nothing.
- **The error reason is read from the response envelope.** Under
  `--output-format json` the CLI still exits non-zero, but stderr goes empty and
  the cause moves into the body. The client built its message from stderr, so
  without this it would raise `exited 1:` with nothing after the colon — and the
  capacity/quota check, which reads stderr and the log file, would be left with
  one signal instead of two.

- **A retried job now records what it discarded.** Requeueing for a transient
  error throws away everything the attempt did, and `requeue_job_for_retry`
  overwrites the job row's error — so until now the reason survived nowhere and
  the only trace was the batch counter restarting at 1. Found the hard way
  during acceptance: a 673-page book reached **batch 263 of 277**, was requeued,
  and left ninety minutes of work and no explanation. The retry event carries
  the attempt, the reason, and how far it got.

### Notes
- The schema is passed as a **string**, not a temp file: at one call per
  extraction batch (277 for Hartley) a file per call would litter the temp
  directory the workspace-hygiene test polices.
- A contract whose schema cannot be flattened — a recursive model — falls back
  to the text path with a warning rather than sending a half-flattened schema,
  which would reproduce the silent-empty failure above.
- The release gate is a **live** test asserting `num_turns == 1` against the real
  CLI with the real contract schema. Offline tests prove what we build; only this
  proves what the CLI accepts — the exact gap that let v0.58.0 ship a feature
  that never ran once.

## [0.59.0] - 2026-08-18
### Fixed
- **A background job now actually records what it is doing.** v0.58.0 added
  `job_events`, a writer for it, and `wiki jobs events <id>`. Every test passed
  and the feature never ran: the writer was attached to `WorkerCallbacks`, but
  an L2 job is compiled by `compile_source_l2`, which never touches those
  callbacks. Measured on a real vault — two jobs completed at `5/5` and `11/11`
  with **zero** event rows, and a traced `append` was never called. The table
  had moved from "nothing inserts" to "the inserter is never called".

  The signal now comes from the loop that does the work. `compile_source_l2`
  takes an optional progress sink and the extraction loop emits one event per
  extraction batch — a loop that already computed `batch 2/3` for its retry label and
  threw it away. A real job reads:

  ```
  07:34:09   1  status     phase=l2 stage=spans_stored spans=156
  07:34:53   2  extracted  phase=l2 batch=1 batches=3 units=32
  07:35:53   3  extracted  phase=l2 batch=2 batches=3 units=65
  07:39:20   4  extracted  phase=l2 batch=3 batches=3 units=105
  07:39:21   5  status     phase=l2 stage=publishing units=105
  07:39:47   6  done       pages_created=30 events_dropped=0
  ```

  Batch 3 took 3m27s against 44s and 60s for the first two. That whole stretch
  used to be a single row reading `0/1`, indistinguishable from a dead job.

- **`wiki jobs list` percentage moves through L2** instead of sitting at 10%
  until the phase ends. It renders only the `progress` float, so the float had
  to move; the phase→float convention is now written down in SYSTEM_BEHAVIOR
  §12.1 rather than implied in two places.

- **Every path a job can take reports what its history lost.** Review found the
  first draft counted drops only inside the L2 sink, so a job that failed, or
  one whose terminal event was itself lost, said nothing — while the spec
  promised the count unconditionally. A per-job `JobHistory` now owns both the
  writing and the counting; the success event, the failure event, and the log
  all carry it.

- **A lost event is reported instead of hidden.** Recording an event still
  never fails the job — but a writer that silently drops rows is exactly the
  blindness this surface exists to remove. `job_events.append` now returns
  whether the row landed, the job counts what it lost, the count rides on the
  terminal `done` event as `events_dropped`, and `wiki jobs events` says the
  history is incomplete. Measured cause: going through `connect()` under a held
  write lock blocked **5.23 s** and then discarded the row; the writer now uses
  its own lightweight connection (1.17 ms vs 1.79 ms, and it skips re-running
  the entire schema just to insert one row) and fails visibly in 0.29 s.

### Changed
- **`progress_current`/`progress_total` mean batches for the whole L2 run**, and
  are no longer overwritten with the atom count when L2 ends. The atom count is
  `pages_created` on the job row. Verified safe: both consumers render the
  fraction only while a job is running.

  This field's meaning is a stored contract, which is why this release is a
  Minor rather than a `### Fixed`-only Patch — `wiki jobs events` itself is not
  new.

### Notes
- Emitting an event is **not** committing a checkpoint. L2 extraction stays
  all-or-nothing, and a test pins that an interrupted run publishes nothing.
  Resumable L2 remains a separate roadmap item; a checkpoint mechanism was
  removed from this same function in v0.52.0 and its hazards are unchanged.
- The release gate that would have caught v0.58.0 is now part of the plan: run a
  real job and read its history. Both new history tests were verified to fail
  against the previous code.

## [0.58.0] - 2026-08-17
### Added
- **Long ingests now say what they are doing.** A `wiki add` on a 673-page book
  sat at 0% CPU for 26 minutes and looked hung. It was working correctly —
  transcribing pages one at a time through a subprocess — and nothing on screen
  or in the database could tell the two apart.

  Two fixes, because the blindness had two separate causes:

  - **Per-page progress during vision transcription.** The serial CLI path now
    reports `vision: 12/300 transcribed (page 12 of 673)` as it goes. Agentic
    CLI providers cannot be called concurrently, so that loop is serial by
    design and each page is slow; silence there reads as death.
  - **`wiki jobs events <id>`** — a job's history, oldest first. `ingest_jobs`
    only ever holds the LATEST phase, so a stalled job and a working one show
    the same row indefinitely. `job_events` existed for this since the schema
    was written, is transported by `db_sync`, is deleted from by `sources.py` —
    and nothing had ever inserted a row.

- **Ingesting a long book is resumable, and now says so.** The
  `vision_max_pages_per_run` rail (300) caps one run and cached pages are
  skipped, so re-running the same command continues instead of starting over.
  The message now says it: *"Re-run the same command to continue: the N page(s)
  done in this run are cached and will be skipped."*

### Fixed
- **An interrupted vision run kept nothing.** The transcription cache was
  written in a single loop *after* every page had finished, so a run that ended
  early — Ctrl-C, a crash, a provider refusing partway — left
  `vision_page_cache` exactly as it found it and the next run started from
  scratch. Measured on the 673-page book above: 26 minutes of transcription,
  zero rows cached. Each page is now cached as it lands, which is what makes the
  resumability described above actually true. The write still happens on the
  main thread — `ThreadPoolExecutor.map` yields into the caller's loop — so the
  "no DB access from worker threads" rule is unchanged.

### Changed
- Job history lives in a new `db/job_events.py` rather than in `db/jobs.py`.
  `db/jobs.py` and `db/__init__.py` are pinned by content hash in
  `D2_HOLDOUT_RESULT.yml`, which freezes an evaluation against specific code;
  adding a function there — or even a re-export — invalidates that result for a
  reason unrelated to retrieval. The first draft did exactly that and D2 caught
  it, so a test now pins that those files stay untouched.

## [0.57.0] - 2026-08-17
### Added
- **The assistant reads your own project notes.** Ask the sidebar a question
  while working inside `01_Workspaces/<project>/` and it now also looks through
  the notes you wrote in that project, surfacing what you already concluded and
  attributing it to you.

  This was the last thing standing between the assistant and its second stated
  job — remind the reader what they have already written. Measured on the
  reporting vault: **137 markdown files on disk, 36 ingested, and 75 of the gap
  were research notes inside one workspace.** They were simply invisible.

  Deliberately a *retrieval* path, not an ingestion one:

  - **Nothing is ingested.** No knowledge-graph node, no database row, no
    `.curator/` file. A workspace is project-local working state, and promoting
    it into a vault-wide graph is the mixing the vault topology exists to
    prevent. The notes are read when you ask and nowhere else.
  - **Only the project you are in.** Outside a workspace nothing is consulted.
    It does not fall back to searching the whole vault, and it will not surface
    another project's notes.
  - **The agent's own files are skipped** — `.agents/`, `CLAUDE.md`,
    `AGENTS.md`, `GEMINI.md`. Those are instructions to a tool. Quoting the
    agent's own plans back as "notes you wrote" is worse than surfacing nothing;
    13 of the reporting workspace's 88 markdown files are that.
  - **Built once per change, not once per question.** The index is bulk-built
    and reused until a note's path or mtime changes. The rebuild-per-call shape
    this avoids measured 331x the bulk path elsewhere (26,881 ms against 81 ms).

  Your notes reach the model labelled as *your working notes*, not as
  established fact, so a correct answer says "you concluded X" rather than
  asserting X.

## [0.56.1] - 2026-08-15
### Fixed
- **"jetski: no output produced" — the actual cause, found by testing the
  permission instead of trusting it.** Every image the assistant tried to read
  through Antigravity came back empty with:

      jetski: no output produced — a tool required the "read_file" permission
      that headless mode cannot prompt for, so it was auto-denied

  v0.53.1 corrected the rule's *shape* (`$read_file$()` → `read_file()`) and
  verified it survived a CLI run. Surviving is not granting, and no test could
  tell the difference — `read_file()` persists in `settings.json` and authorizes
  nothing. So the bug outlived its own fix by three releases while the rule sat
  there looking correct.

  Re-measured against agy 1.1.13 by writing each rule and then asking the model
  to read a real PNG:

  | rule | result |
  |---|---|
  | `read_file(*)` | the model read the file |
  | `read_file(/tmp/exact-file.png)` | auto-denied — an **exact path** is refused |
  | `read_file(/tmp/*)` | auto-denied |
  | `read_file()` | auto-denied — what v0.53.1 shipped |

  Only the wildcard is honoured for reads: a path-scoped read rule is not a
  narrower grant, it is no grant at all. `command(wiki)` was measured the same
  way and **does** work scoped, so the v0.23.0 posture keeps its narrow command
  permission — only the read rule is forced wide by the CLI's own parser.

  Upgrading also removes the retired `read_file()` rule rather than leaving it
  beside its replacement, where a dead grant would keep reading as configured
  access. Rules the user or another tool added are preserved untouched.

  With this, `wiki plugin pdf transcribe --image-file` returns transcribed LaTeX
  instead of an empty result — the first end-to-end confirmation of the vision
  path added in v0.55.0, which until now had only ever been verified as far as
  the rendered image.

  **What this costs, stated rather than buried.** `read_file(*)` lets the
  Antigravity CLI read any file your account can — agy accepts no narrower form,
  and the OS sandbox Incurator wraps it in restricts writes, never reads. The
  grant is global and lasting, and it is honoured by the `wiki` ingest pipeline
  too, which processes PDFs and pages you did not write. Incurator grants
  exactly two rules and Antigravity auto-denies anything unapproved in headless
  mode, so there is still no write tool, no arbitrary shell, and no network
  tool: the realistic worst case is a secret read into your own vault, not
  something sent elsewhere. Pointing PDF extraction at an API vision model
  avoids the trade entirely — it takes image bytes directly and needs no
  filesystem permission. Written up in both plugin guides and PLUGIN_SCHEMA
  §13.5, and the unsandboxed backend spawn it interacts with is tracked as
  ROADMAP item 11.

  The measurement is now automated rather than repeated by hand.
  `agyPermissionLive.test.ts` writes each rule, asks a real `agy` to read a file
  containing a token that appears nowhere in the prompt, and checks whether the
  token comes back. It is skipped unless `INCURATOR_LIVE_AGY=1` and `agy` is on
  PATH, because it spends provider quota — but it exists, so the next agy
  release that changes what a rule authorizes has something to fail against.
  Asserting what we wrote to the file is what let this ship twice.

- **The page-image path asked the wrong question.** v0.55.0 renders a whole page
  and sent it to the prompt that says "transcribe ONLY the selected PDF region",
  which is right for a `Cmd+Shift+X` snip and wrong for a page: handed a full
  page the model has to guess what counts as "selected". Measured on the page
  holding equation 29, it returned the sentence the reader had highlighted —
  about 150 characters — and not the equation being asked about.

  `wiki plugin pdf transcribe` now takes `--scope page|region` and the
  page-image tool asks for `page`. Same page, same model: **6,468 characters
  covering the whole page, with equation 29 in it.**

## [0.56.0] - 2026-08-14
### Added
- **`[8]` now resolves to the paper it names.** Ask the popover about a citation
  and the assistant gets the bibliography entry it points to, resolved before
  the turn starts so no tool round is spent chasing it.

  The hard part is not finding `[8]` — it is knowing that a given `[8]` IS a
  citation. Bare brackets collide with footnote markers (`[^8]`), markdown
  reference links (`[text][8]`), and array indices (`arr[8]`). The bibliography
  itself is the disambiguator: a number that does not match a parsed References
  section is **dropped, not reported unresolved**, because on ordinary prose
  "not found" almost always means "not a citation".

  Verified on a real 26-page paper: **110 entries, numbers 1–110, no gaps.**

- **Provenance under the answer.** Each lookup is listed with where it came
  from — `Eq. (29) — p.11`, `[8] — Bartoli et al., 2005`. It is assembled from
  what the plugin actually resolved, never recovered by scanning the model's
  output, so it cannot disagree with what really happened. A pointer that could
  not be reached reads "not retrieved", never "absent from the paper" — the
  popover searches only loaded pages, so the first is what the code can support.

### Fixed
- **Two-column papers were being read across the gutter.** Page text was grouped
  by vertical position with no notion of a column, so every line of a
  two-column paper concatenated the left and right sides. On the References page
  of the motivating paper that produced:

      [1] Hichem Abdellali, Robert Frohlich, Viktor Vilagos, and [18] Daniel
      DeTone, Tomasz Malisi...

  — two unrelated references welded into one line. This was never a citation
  bug; it is how the plugin has read **every** two-column paper, silently
  corrupting anything downstream that relies on page text.

  Pages are now split at a detected gutter and read one column at a time. The
  detector is deliberately conservative: a band essentially no item crosses,
  substantial text on both sides, wider than both 4% of the page and 1.5x the
  median glyph height. Both floors matter — the page-fraction test alone passed
  on ordinary word spacing and sliced single-column pages into ribbons. A
  single-column page produces byte-identical output to before.

  Same page: 16 contaminated entries before, 28 clean ones after.

- **A bibliography spanning pages is now followed.** The heading prints once —
  the motivating paper carries it on p.24 with entries 1–28, then continues
  across p.25 and p.26 with no heading at all. Stopping at the heading page
  found 28 of 110, so a real citation like `[42]` was being dropped for "not
  being in the bibliography".

### Changed
- `PLUGIN_SCHEMA.md` §13.8 records the reading assistant's role as contract —
  the three duties, the ban on self-cancelling duty clauses, and the prompt
  budget gate — with the audit that motivated it: duty 3 had four "enabling"
  sentences, all of them MCP tool descriptions, and no instruction anywhere.
- `PLUGIN_SCHEMA.md` §13.9 records that provenance is assembled from resolution
  results and never regexed from output, with the measurement that killed the
  output-scanning design: `quickQueryContext.ts` contains zero `[[`, so the
  check would have fired "no citation" on every popover answer ever produced.

## [0.55.0] - 2026-08-14
### Added
- **The assistant can look at a PDF page, not just read its text.** Ask about
  an equation that the PDF draws as a picture and the answer no longer depends
  on you snipping it first. When the text it fetched does not contain what you
  asked about, the assistant renders that page off-screen and reads the pixels
  through the same extraction model the manual `Cmd+Shift+X` snip already uses.

  This reaches three things the text layer structurally cannot hold: displayed
  equations and figures emitted as raster images, scanned inserts, and **your
  own handwritten margin notes**.

  Three properties are deliberate, and each is a decision rather than a
  default:

  - **The model asks for it; no heuristic routes it.** The obvious design is to
    reuse the existing `isScannedLike` verdict, and it cannot work: that verdict
    is a whole-page aggregate. Measured on the paper that motivated this
    feature, the page carrying the rasterized equation reports 4,193 text
    characters and 14 image draw operations against a prose control page's 5 —
    text-dense by every page-level measure, and missing the equation entirely.
    Only the model answering the question knows the answer is not in the text
    it received.
  - **It renders off-screen, so any page is reachable.** The existing render
    path draws into an on-screen element that exists only for pages you have
    scrolled to. Reading a page you never opened is the point, not an edge
    case.
  - **It is rationed separately from text reads.** A render plus a vision
    round-trip is the escalation of last resort, not a browsing mode, so a
    turn gets a small number of page images and answers everything else from
    text. A failed read is charged too: an unreadable page fails identically
    every time, and a free failure would let one turn retry it indefinitely.

### Fixed
- **The new tool would have shipped unreachable.** Found reviewing v0.53.0
  through v0.55.0 before merge. Exposing a tool is not the same as making the
  model use it: three prompt sites steered away from the page image and none
  mentioned it. The decisive one was the unresolved-reference note, which fires
  on *exactly* the condition the tool exists for — "commonly a rasterized
  equation or figure" — and then told the model to describe the target from
  what it already had. Asking about equation 29 would have produced the same
  non-answer as before the feature existed. All three sites now name the image
  read, conditionally (a CLI-routed provider has no local tools at all), and
  `pageImageReachability.test.ts` fails 4 of 5 without them.

- **The prompt could have sent a CLI-routed model back into "no output
  produced".** The instruction said to use "a tool for reading a page as an
  image". CLI-routed providers receive no local tools at all, yet still get this
  text — and the agy path holds a persistent `read_file()` grant, so a model
  told to go fetch a rasterized equation could reach for that instead and hit
  the headless auto-deny that caused the original v0.48.4 failure. Every site
  now names `read_pdf_page_image` literally: a model that was not handed it has
  nothing to match. Prompt assembly is still not provider-aware; that is a
  follow-up, not something this release closes.

- **The last instruction the model read still argued against the tool.**
  `buildRecencyAnchor` is emitted last, at the recency position, and duplicates
  the pointer rule — it kept telling the model to work "from the blocks given"
  while the three sites above had been fixed. A reviewer caught the identical
  miss on a previous release; the reachability test now covers this site too.

- **A model-invoked failure popped a toast at the user.** `transcribePdfCrop`
  raises a Notice on every failure, which is right for the two callers it was
  written for — both user actions. The page-image tool is not one: the model
  calls it by itself, on a page the reader may never have opened, and the error
  already goes back to the model as a typed tool result. Anyone without a vision
  model configured would have gotten an unprompted popup naming a page they did
  not ask about, up to twice per turn. That path is now silent and logs instead.

- **Reading a page image ignored the document-identity pin.** `readPageImage`
  crosses two awaits — the render and the vision round-trip — and resolved the
  active view at call time with no identity check, while `fetchActivePdfPage`
  directly above it pins before its first await and refuses on mismatch.
  Switching tabs mid-request would have rasterized a page of the *new*
  document and returned it as a page of the one asked about. It now pins, and
  re-checks after the render.

### Changed
- `PLUGIN_SCHEMA.md` §13.7's closed tool set grows from two names to three;
  `read_pdf_page_image(page_number)` joins `fetch_pdf_page` and
  `search_pdf_anchor`. It remains a plugin-executed local tool — never
  registered with an MCP server, never reaching the filesystem, the vault, or a
  shell — and is emitted under the same fail-closed preconditions as the rest.
- The plugin guide's "when a reference cannot be found" section was describing
  a limitation this release removes ("no amount of searching will locate it")
  and has been rewritten in both the English and Korean guides.

## [0.54.1] - 2026-08-14
### Fixed
- **The IDE-context hijack was only half fixed.** v0.53.2 stopped the Obsidian
  plugin from handing the host IDE's `ANTIGRAVITY_*` variables to a spawned
  `agy`, which is what let the CLI reconnect to the IDE daemon and answer from
  whatever document was open in the IDE instead of the prompt Incurator sent.

  The backend's own CLI clients were never changed. `curator/llm.py`'s
  `_repo_temp_env` — which builds the environment for every backend `agy`,
  `claude`, and `codex` spawn — still copied `os.environ` wholesale, so on the
  backend path the hijack was live the entire time. It now drops `ANTIGRAVITY_*`
  before `extra` is applied, so a caller that deliberately sets
  `ANTIGRAVITY_TRUST_WORKSPACE` (as `AntigravityCliClient` does) still gets it.

  The fix had in fact been written; it was sitting uncommitted and shipped to
  nobody. `test_llm_env_scrub.py` now pins it, and fails without it.

  Removing the workaround is part of the same fix. v0.53.2 also appended a rule
  to *every* surface's boundary constraints telling the model to ignore injected
  IDE metadata — including surfaces that never spawn a CLI and therefore never
  saw it. With both spawn sites scrubbed the metadata does not reach the model
  at all, so the instruction had nothing to suppress and was purely diluting the
  instructions that do apply. It was also phrased as a prohibition naming the
  exact strings to ignore, which primes the behaviour it forbids. No capability
  is added or removed by this: the prompt stops describing a condition that can
  no longer occur.

  One clause of that rule is kept, because it was never about IDE metadata: the
  sidechat states the active file and page itself, on every turn, and the env
  scrub does nothing about those. The instruction that the open document does
  not override a settled conversation topic now lives on the sidechat profile
  alone — the one surface whose prompt actually carries the line — phrased as
  what to do rather than what to ignore.


## [0.54.0] - 2026-08-14
### Changed
- **The prompt now states what the assistant is for.** The system prompt opened
  by describing Obsidian and then spent its length on prohibitions. Nothing in
  it said what the sidechat and popover actually exist to do, so the model
  optimized for the only goal it was given — stay inside the provided context —
  and a question it could have answered came back as a report on what it had
  not received.

  The prompt now opens with three duties, in order: read alongside the user
  (papers, books, and PDFs, including pages and figures they have not opened);
  remind them what they have already written, surfacing their own notes when
  those bear on the question; and help them get somewhere new — an implication,
  a tension, a connection they had not stated. The third duty had **zero**
  instructions anywhere in the stack before this release. It is qualified
  rather than mandated: answer the question first, add the connection when
  there is a real one, because a manufactured insight is worse than none.

- **Prohibitions rewritten as descriptions of the wanted behaviour.** Negative
  instructions prime the behaviour they forbid — the "pink elephant" effect —
  so "do NOT open the file" was itself part of why the model reached for a file
  tool. Each prohibition now states what to do instead. The general-knowledge
  fallback survives as a capability ("where those do not cover the question,
  answer it from your general knowledge of the field rather than stopping")
  with the mandate to *announce* that fallback removed.

- **The role and its budget are now gated by tests.** `promptRoleBudget.test.ts`
  asserts all three duties are present, caps the assembled prompt at 17,000
  characters and 23 negative constructions, and fails if a narration mandate
  reappears. A prompt that grows without bound dilutes every instruction in it,
  including the ones that matter.

## [0.53.3] - 2026-08-14
### Fixed
- **The Assistant Narrated Its Own Context Instead Of Answering**
  User-reported, verbatim from the popover:

  > "Sec. C의 보충자료 전문(p.12–13)은 지금 제 현재 컨텍스트에 로드되지 않았어요.
  > 대신 본문 3.3절(p.5)과 문서 아웃라인을 기준으로…"

  That was not the model being chatty. **Three prompt sites instructed it**, in
  so many words, to announce the gap: `chatContextPriority.ts` ("say you could
  not locate the referenced target", "say you could not retrieve the referenced
  item"), `crossReferenceResolver.ts`'s `UNRESOLVED_NOTE` ("say plainly that you
  could not retrieve the referenced item"), and `promptRegistry.ts` ("say you
  could not retrieve it"). All three shipped in v0.48.4 to stop the model
  reaching for a tool headless mode denies — the narration was the cure's side
  effect.

  Two findings shaped the rewrite:

  1. Established RAG prompting guidance is that the assistant should **not
     mention the retrieved context at all** — it is a cheatsheet for answering,
     not a subject to discuss.
  2. Negative instructions prime the behaviour they forbid (the "pink elephant"
     effect); Anthropic's own persona prompts use descriptive statements rather
     than prohibitions. `"do NOT attempt to open, read, or search the source
     file"` sat directly beside a model that would not stop talking about what
     it could not open.

  So each site now states the behaviour wanted instead of the one forbidden:
  describe the referenced target from what the supplied material establishes,
  work from the blocks given, and **write for a reader who cannot see the
  context** — statements about what is loaded, which blocks arrived, or whether
  something is general knowledge are not part of an answer.

  The honesty floor is unchanged and still tested: the unresolved note scopes a
  gap to *this context*, never to the document, so the model still cannot claim
  a verified absence it never established.

  `noContextNarration.test.ts` pins both rules across all three sites, matching
  only string literals so the explanatory comments do not satisfy it. Verified
  red-before-green: restoring the old prompts fails 5 of its 8 assertions. Two
  pre-existing tests that pinned the old wording were updated to assert the
  invariant rather than the phrasing.

## [0.53.2] - 2026-08-10

### Fixed
- **Popover Chat**: Relaxed strict grounding constraints in the Quick Query popover to allow the LLM to use its parametric knowledge as a fallback when the provided context lacks the answer, instead of strictly refusing to answer.
- **Popover Chat**: Injected the sidechat's pinned sources (e.g. pinned PDF pages, markdown files) into the popover context so it can also search and answer from those sources, while still preserving the popover's `local-only` secure boundary.
- **Context Hijacking Fix**: Scrubbed `ANTIGRAVITY_*` environment variables when invoking `agy` (the Antigravity CLI) from the Incurator plugin, fundamentally preventing the CLI from connecting to the host IDE's local daemon and receiving irrelevant injected active-tab metadata.


## [0.53.1] - 2026-08-09
### Fixed
- **"jetski: no output produced" — The Permission Rule Was Never Valid**
  Reported repeatedly since v0.30 and declared fixed several times. The real
  cause is a malformed permission string that Antigravity silently discards.

  The plugin grants the Antigravity CLI a narrow headless read permission by
  writing `permissions.allow` into `~/.gemini/antigravity-cli/settings.json`.
  The rule it wrote was `$read_file$()`. **Antigravity validates that list,
  prunes entries it does not recognise, and then deletes an emptied
  `permissions` object entirely** — so the grant survived exactly zero CLI
  invocations. Every tool the model reached for in headless mode was
  auto-denied, producing empty output. Measured against the real CLI:

  ```
  $read_file$()        -> permissions key deleted
  read_file()          -> survives
  command(wiki)        -> survives
  $command$()          -> pruned
  run_shell_command()  -> pruned
  ```

  The rule is now `read_file()`. The re-assert was never the problem —
  `syncAgyMcpConfig()` already runs immediately before every `agy` spawn; it was
  re-writing an invalid rule each time.

  **Why previous fixes missed it.** They reshaped the *prompt* so the model
  would be less likely to reach for a denied tool — a mitigation of the symptom.
  And the unit tests asserted the exact broken string (`allow: ["$read_file$()"]`),
  so they passed on every release while the grant was being discarded. A test
  that proves we wrote a string is not a test that the string works; the suite
  now pins the rule *format* and rejects the `$`-wrapped form outright.

- **The MCP Server Could Not Be Spawned From Chat**
  Calling a curator tool requires Antigravity's `command` permission, because
  the MCP server is spawned as a command. This became reachable only in v0.53.0,
  when the Obsidian plugin first got an `incurator` MCP entry — before that the
  model had no curator tool to call, so the denial never fired on this path.
  Granted as **`command(wiki)`**, scoped to the one binary the plugin itself
  configures. A bare `command()` would be the blanket bypass the v0.23.0 posture
  explicitly forbids, and is asserted against.

## [0.53.0] - 2026-08-09
### Fixed
- **The MCP Server Could Not Be Started By Any Client Since v0.34.0**
  Every documented client config launches it as
  `{"command": "wiki", "args": ["mcp"]}`. A bare `wiki mcp` exited **2** with a
  usage screen instead of serving, so no client ever got a session. Two
  independent Typer settings caused it: `no_args_is_help=True` short-circuits to
  help before the callback runs, and a callback without
  `invoke_without_command=True` is rejected earlier still with "Missing
  command" — the `mcp_callback` written to start the server on a bare invocation
  was unreachable. Both fixed; the TTY guard inside the callback still prints
  usage for a human, so only piped clients get a server. Verified end to end: a
  piped `initialize` now returns a handshake and `tools/list` returns **50**
  tools.
- **`./setup.sh` Never Installed The `mcp` Extra**
  The runtime venv got `-e backend` without `[mcp]`, so a fresh setup failed
  every MCP command with "The `mcp` package is required". `[mcp]` is a runtime
  feature — it is how the plugin's chat and external agents reach the knowledge
  base — not a dev tool, so it belongs in `<repo>/.venv`. Dev-only check tools
  still go to `.venv-dev`.
- **Install Hints Told Users To Run An Unqualified `uv pip install`**
  **Eleven** sites printed `uv pip install -e './backend[...]'`, which names no
  target interpreter: it installs into whatever environment happens to be
  active. This project keeps every venv at the repository root. Seven were in
  Python source; review caught four more in the guides describing the same
  repair — including `MCP_USER_GUIDE.md`'s own Prerequisites block, three lines
  above the section this release added. All eleven now point at `./setup.sh`, or
  spell out `--python <repo>/.venv/bin/python`, with the extras quoted so a zsh
  copy-paste does not glob on `[rerank]`.

### Added
- **`wiki mcp install obsidian` — Registers The Server The Plugin Chat Requires**
  Unlike the `claude` / `antigravity` targets, which print a snippet to paste,
  this one **writes**: a plugin's `data.json` is owned by Obsidian and is not
  meaningfully hand-edited.

  It closes a gap that made every retrieval improvement invisible from the
  plugin. Measured on the reporting vault, `mcpServers` was `[]` — and both the
  MCP tool injection and the system-prompt section that describes
  `curator_query` / `curator_fetch_context` / `search_curator` /
  `curator_get_pdf_context` are gated on an enabled server whose name contains
  `incurator`. With no entry the sidechat cannot call the knowledge base at all,
  regardless of how well the backend answers `wiki query`.

  Safety properties, each covered by a test: idempotent (a stale or disabled
  `incurator` entry is repaired in place, never duplicated); every unrelated
  setting is preserved; a `data.json` that is unparseable or not an object is
  refused rather than overwritten, because that file holds provider keys and
  Zotero profiles; and the registered command is the repo-root venv's absolute
  `wiki` path, since a GUI app does not reliably inherit the shell `PATH`.

  Minor rather than Patch: this adds a new user-facing CLI capability that
  mutates client configuration.

## [0.52.3] - 2026-08-09
### Fixed
- **Convert-to-LaTeX Silently Deleted Every Greek Letter (regression from v0.52.1)**
  User-reported: the copy produced `$2R^2T A + bT$, s.t. $TQ + qT = 0$.` where it
  should have produced
  `$$\min_{\lambda \in \mathbb{R}^2} \lambda^T A \lambda + b^T \lambda \quad
  \text{s.t.} \quad \lambda^T Q \lambda + q^T \lambda = 0$$`. Every λ is gone,
  and the remaining text is exactly the input with each λ deleted.

  **A U+0000 in a PDF text layer is not noise — it is a glyph pdf.js could not
  map.** Measured on `3D Line Mapping Revisited` page 4: its `AAAAAH+CMMI10`
  subset (the maths italic font that carries λ) declares `MacRomanEncoding` and
  has **no `/ToUnicode`**, so pdf.js has nothing to resolve the glyph with and
  emits NUL. Running pdf.js 4.10 against the real file with the plugin's own
  options returns, for equation (3):

  ```
  "\0 = (\0 1, \0 2) with a single constraint: min \0 2 R 2 \0 T A \0 + b T \0, ..."
  control code points: U+0000 x10        real U+03BB: 0
  ```

  v0.52.1 stripped control characters so `spawn` would stop throwing
  `TypeError: … must be a string without null bytes`. That silenced the crash
  and produced something worse: the model received the equation with all ten
  lambdas deleted, transcribed the wreckage faithfully, and a **confidently
  wrong equation landed on the clipboard**. A loud failure had become silent
  corruption — the exact trade this project's rules exist to prevent.

  No text processing can recover the character, because the character is not in
  the text layer at all. It exists only in the rendered pixels. So:

  - **A selection carrying unmapped glyphs is now read as an image.** The
    selection's bounding box is cropped from the already-rendered page canvas
    and sent through the existing `transcribePdfCrop` path, where the vision
    model reads the equation as drawn. The notice names the count
    (`Reading 10 unencoded symbol(s) from the page image…`) so the different
    route is visible rather than mysterious.
  - **`sanitizePdfSelectionText` removes only U+0000**, the single code point
    `spawn` actually rejects. v0.52.1 also stripped the rest of C0, DEL, and
    C1 — none of which break the boundary, all of which may be real content.
    Removing a character a process boundary would have accepted is data loss
    with nothing to justify it.
  - **When the crop cannot be captured, it says so and stops** rather than
    falling back to text already known to be missing its symbols.

  Verified against the backend: given the text layer *with* λ present, the
  existing transcribe path already returns exactly the expected LaTeX, which is
  what isolated the loss to the plugin rather than the model.

  Closing the review of this change (all six findings):
  - **The selection's geometry is captured while the selection is live**, at the
    same moment as its text — menu-build time for the context menu, in-handler
    for the shortcut. Reading the rect when the menu item was clicked let the
    routing decision and the pixels describe two different moments, and since a
    menu interaction can collapse the DOM selection, the context-menu route
    would usually have failed to capture anything at all.
  - **Only the line rects on the anchored page are unioned.** A selection
    running onto the next page has a bounding box spanning both pages and the
    gap, so cropping it swallowed every unselected line down to the page edge
    while still dropping the overflow.
  - **`transcribePdfCrop` takes the caller's failure wording.** Its default ends
    with "Attached crop fallback", which is true for the chat snip and false for
    a clipboard copy that attaches nothing. The chat message is unchanged.
  - Dead exports removed (`hasUnmappedGlyphs`, `isUnreadableSelection`) — this
    change deleted their only call sites.
  - `SYSTEM_BEHAVIOR.md` §26.2a rewritten; it still described the v0.52.1
    strip-and-send behavior this release removes.
  - `externalPdfViewSource.test.ts` now covers the routing, the no-text-fallback
    rule, live-rect capture, the per-page rect union, and the caller-specific
    failure wording. Reverting the fix fails them.

## [0.52.2] - 2026-08-09
### Fixed
- **§26.2b Extraction-Loss Recording Had Never Run On The Existing Corpus**
  User-reported through its symptom: a question about equation 29 of "3D Line
  Mapping Revisited" returned *"수식 29의 텍스트를 가져올 수 없어…"* and then
  pivoted to a different equation, saying nothing about why.

  Measured, the hedge was true but useless. Equation 29 is `SPAN-5a4b5830`, and
  its stored text is, in full, `**==> picture [185 x 12] intentionally omitted
  <==**`. Its neighbours by document order are "Then inserting into (28) we get"
  and "which is a rational function in _µ_ … Backsubstituting into (29)…", both
  under `section_title = "B.2 . M1. Triangulation with Multiple Points"` — the
  Supplementary Section B the answer guessed at. Retrieval reached the right
  neighbourhood; the equation itself was never ingested.

  Two defects, both closed:

  1. *The record was never written for older spans.* `classify_span_loss` is
     called only from the span **builder** (`spans_from_sections`), so it runs
     at ingest time and never revisits an existing row. On the reporting vault
     that left **132 placeholder spans carrying 2 loss records between them**,
     both classified the day v0.49.0's check was exercised. The feature worked
     and had simply never run on the corpus it was built for. New
     `backfill_span_loss` closes this with no provider call, no re-parse, and no
     schema change — the verdict is a pure function of text already stored. It
     runs with the deterministic structural repairs in `wiki sync` (skipped by
     `--no-fix`/`--dry-run`), reports its count, and is idempotent: a span that
     already carries a `loss` key is never rewritten, so an ingest-time record
     always wins. A span whose `metadata` is unparseable JSON is skipped rather
     than replaced. Measured on a copy of the reporting vault: 2 → 132 records,
     with a second run writing 0.
  2. *Nothing in retrieval knew what the placeholder meant.* All 132 placeholder
     spans are in the search index and can be retrieved, and evidence assembly
     passed the raw parser string through to the model, where it conveys
     nothing. `_span_items` now substitutes a description that states the region
     is an image, its geometry when the parser stated one, that no transcription
     exists, that the model must not guess at its contents, and both remedies
     (snip it, or set §26.2a `llm.vision_model` and re-add). This withholds no
     evidence — there is no text in such a span to withhold. The wording has one
     definition (`describe_span_loss`) so CLI, projection, and retrieval cannot
     drift, and retrieval falls back to classifying from stored text so a vault
     that has not yet run `wiki sync` still gets a truthful answer.

  End-to-end on the real span, equation 29 now serves:
  `[unreadable region] The source stores this as a 185x12 image, so its text was
  never extracted … snip the region in the PDF viewer, or set
  `llm.vision_model` … and re-add the source.`

  **This still does not recover the equation.** Recovery is §26.2 / ROADMAP
  item 1 and remains blocked on its three prerequisites. What changes is that
  the system now names exactly what is missing and how to obtain it, instead of
  hedging around a gap it could not describe.


## [0.52.1] - 2026-08-09
### Fixed
- **The Job Indicator Spun Forever While `wiki jobs list` Showed Nothing**
  User-reported. `runtime/jobs.json` is the only thing the chat status bar
  polls, and no terminal job transition rewrote it. `run_next_job` wrote the
  snapshot at exactly two mid-run points — after L2 completes and before L3
  starts, both as `running: [<this job>]` — while `mark_job_done`,
  `mark_job_failed`, and `requeue_job_for_retry` were each followed by a plain
  `return`. `IngestWorker._write_dashboard`, called after every job, writes the
  **markdown** build-status page, not the JSON snapshot, despite a docstring
  claiming it runs "at job start, completion, and failure". So once the last job
  of a batch ended, the file froze with that job still running, permanently.
  The three surfaces then disagreed exactly as reported: the passive indicator
  read the stale file and spun, while `wiki jobs list` and the dashboard both
  refresh the snapshot before reading and correctly showed nothing.
  The snapshot is now re-derived from a `finally` block, so `done`, `failed`,
  `requeued`, and an unexpected exception are all covered by one write, and
  `IngestWorker.run` writes one after `recover_stale_jobs` clears jobs a crashed
  process left marked `running`. Writes stay best-effort and can never fail a
  job whose DB state is already committed. `build_jobs_snapshot` itself was
  never wrong — it derives `running`/`queued`/`idle` from a single DB read.

- **Convert-to-LaTeX Blamed The LLM Provider For Three Things That Were Not It**
  User-reported, recurring. Three independent defects produced one misleading
  message.
  1. *A null byte aborted the conversion before the backend ran.* pdf.js emits
     U+0000 for glyphs whose embedded font carries no usable ToUnicode mapping —
     exactly the rasterized regions a reader most wants transcribed. Node's
     `spawn` rejects an argv entry containing one with a synchronous
     `TypeError: … must be a string without null bytes`, so the selection never
     left the plugin. PDF selections are now stripped of control characters (C0
     except tab/LF/CR, DEL, C1) at the selection reader, and a selection that is
     entirely artifacts reports an unreadable image region instead of failing
     silently.
  2. *The normalizer deleted numeric content.* `_CLI_NOISE_RE` carries a
     digits-only alternative for an agentic CLI's trailing "tokens used /
     12,345" banner, and `normalize_interactive_latex_transcription` re-applied
     the whole filter to the text INSIDE the model's `<transcription>` block,
     where a banner cannot occur. An equation number, a table cell, or a page
     number on its own line was deleted from a faithful transcription; an
     all-numeric selection normalized to nothing. Measured:
     `wiki plugin pdf transcribe --text "1"` returned `ok: true` with
     `latex: ""`. The block is now extracted from the raw text first and its
     contents are trusted; untagged output stays subject to the filter.
  3. *Every failure claimed the provider was misconfigured.* One `try` wrapped
     the backend call and the clipboard write together, and its `catch` showed a
     single hardcoded "Check Incurator Dashboard → LLM Provider" while the real
     error went only to `logger.error`. A **successful** backend call that
     returned an empty transcription, and a refused `navigator.clipboard.write`,
     both read as a broken provider. The four outcomes now have four messages,
     and real failures include the underlying error text.

  The provider was verified working throughout: with `vision_model:
  antigravity-cli::gemini-3.6-flash` and an empty `latex_extract_model`,
  `_resolve_extract_client` correctly falls through to the vision slot and live
  runs returned faithful LaTeX.

- **`npm audit fix` Reported ENOLOCK**
  Not a lockfile-policy regression. There is no `package.json` at the repo root
  — the npm project is entirely under `plugin/`, which is where the command must
  run. `plugin/package-lock.json` is tracked on purpose: Step 10 requires its
  top-level `version` and `packages[""].version` to match the other manifests,
  the CI `version-consistency` job blocks the merge otherwise, and
  `test_spec_sync.py` reads that file directly as the source of truth for the
  active version. Landed separately: nanoid `3.3.16 → 3.3.18`
  (GHSA-2v37-7h3g-55p8), after which `npm audit` reports 0 vulnerabilities.

## [0.52.0] - 2026-08-08
### Changed
- **The `db` Facade Loses Five Helpers, And `l2_checkpoints` Leaves The Schema**
  Minor rather than Patch: this removes a schema table and shrinks the guarded
  `db` public surface, which CLAUDE.md classes as a schema/contract change
  regardless of consumer count. The five helpers
  (`insert_l2_checkpoint`, `get_l2_checkpoint_hashes`, `clear_l2_checkpoints`,
  `has_l2_checkpoints`, `list_staged_unit_ids_for_source`) all had zero callers
  once the unreachable mechanism below was deleted.

### Removed
- **The Unreachable L2 Checkpoint-Resume** (B3 P6 / CP-5)
  `l2_checkpoints`, its four `db` helpers, and the `resume` branch of
  `extract_knowledge_units` are gone. The mechanism could never run: the only
  `insert_l2_checkpoint` call sat inside `if resume:`, while `resume` was set
  from `has_l2_checkpoints` — checkpoints were written only when resuming, and
  resuming happened only when checkpoints existed. Confirmed by AST inspection
  and against the reporting vault: **0 rows across 36 sources and 2,799
  knowledge units**.

  Its four tests passed because they called `extract_knowledge_units(resume=True)`
  directly, bypassing the gate that production can never open.

  Removing it changes no behavior — an interrupted L2 build has always restarted
  from the first batch. That cost is real (a 40-batch source re-pays every
  provider round-trip on retry), so resumable L2 is recorded on the roadmap as
  wanted. It needs designing rather than re-enabling: the removed branch returned
  the staged-unit list, which is empty after a successful publish and would have
  retired the source's entire authoritative unit set.

  Existing vaults keep the now-orphan empty table for now. `SCHEMA_SQL` only
  issues `CREATE TABLE IF NOT EXISTS` and there is no migration path, so nothing
  drops it here — which matches the Arena's recorded decision for this item
  ("delete; drop the table in B7"), B7 being the batch that owns schema
  migration. An empty, unreferenced table is inert until then.

## [0.51.0] - 2026-08-08
### Changed
- **`synthesis_nodes.dependency_hash` Now Carries The Layer's Node Count**
  The stored value changes from a bare corpus digest to `<hash>#<count>`. This
  is a Minor rather than a Patch because the field is exposed: `wiki inspect
  synthesis SYN-…` and `wiki plugin synthesis show` return it in the audit
  payload that SCHEMA §11.11.1 describes as stable for CLI and plugin
  consumers. Anything parsing it as a bare digest should take the portion before
  `#`. The reason for the change is below.

### Fixed
- **A Truncated L4 Layer Was Frozen As Complete, Permanently** (B3 P5 / CP-2a)
  `generate_synthesis` regenerates wholesale: clear the layer, then write N nodes,
  each committed separately and stamped with the current corpus hash. A crash
  between the clear and the last write leaves a truncated layer whose every
  surviving node carries the current hash — so the idempotency guard reads it as
  complete. Reproduced: 3 nodes of an intended 6 short-circuit the guard, and
  every later `wiki build` returns them as a finished layer. The vault serves a
  half-complete synthesis until the corpus changes enough to move the hash, and
  no surface reports it.

  `synthesis_nodes.dependency_hash` now records the layer's intended cardinality
  alongside the corpus hash (`<hash>#<count>`), and a layer counts as current
  only when the hash matches AND the count equals the nodes actually present.

  A vault already frozen by the old behavior repairs itself: its rows carry a
  bare hash with no cardinality, which reads as unknown rather than current, so
  the next build regenerates once. That is why the cardinality is encoded in the
  existing column rather than added as a new one — this codebase has no
  `ALTER TABLE` path, so a new column could not reach an existing vault at all.

  This detects an interrupted write; it does not prevent one. Making the rebuild
  atomic is the other half of CP-2 and remains deferred.

## [0.50.2] - 2026-08-08
### Fixed
- **Device Sync State Was An Unlocked Read-Modify-Write** (B2 / sync_db-4)
  Four sites read the local sync-state file, mutated it, and wrote it back with
  no lock, so two concurrent passes could interleave. Both consequences were
  reproduced against the real code:

  - **Split device identity.** `get_device_id` mints an id when none exists.
    Racing callers each minted a different one — measured: two callers received
    two ids while only one was persisted. The loser then exports as
    `dev-<its-id>.jsonl`, and every other device imports a peer that exists only
    as that filename and never exports again. A permanently stale phantom.
  - **Lost update.** Two sections read the same base and the last writer wins.
    Losing `peers` forgets a checkpoint, so that peer's entire snapshot
    re-imports on the next pass; losing `last_export_ts` re-fires the export
    gate.

  All mutation now goes through `sync_state_transaction`, which holds
  `durable_io.locked_path` on the state file, re-reads inside the lock so a
  caller can never act on a copy captured before acquiring it, and writes once
  through `atomic_write_text` on a clean exit. A failed pass leaves the file
  untouched.

  This also removes a hazard that was previously handled by remembering to order
  two calls: `import_all_peers` had to call `get_device_id` before snapshotting
  state, or a first-run identity would be clobbered by the checkpoint write. The
  ordering requirement is now structural.

  On platforms without `fcntl` the lock degrades to a thread lock, so separate
  processes are not serialized there. Recorded rather than assumed away — it is
  strictly narrower than the unlocked behavior it replaces.

- **Nested State Locking Deadlocked, Then Lost Writes**
  Found while reviewing the change above; both were introduced by it.

  `durable_io.locked_path` was not re-entrant. `flock` is per file descriptor,
  so a nested acquisition opened a second descriptor and `LOCK_EX` blocked
  against the first — from the same process, forever. A hang, not an error, and
  reachable: `_peer_files` calls `get_device_id` (now a transaction) whenever no
  id is passed, and is itself called from inside `import_all_peers`' transaction.
  It survived only because that one call site happens to pass the id.

  Making the lock re-entrant then exposed a second fault: a nested
  `sync_state_transaction` read its own copy of the state, and the outer
  transaction overwrote it on exit with the snapshot taken before nesting —
  discarding a freshly minted `device_id` and failing validation. That is the
  lost update this whole change exists to prevent, reintroduced by nesting.

  The lock now tracks re-entrancy depth per thread and path, taking `flock` only
  at the outermost acquisition; and a nested transaction shares the outer
  state dict, with the outermost `with` committing once.

## [0.50.1] - 2026-08-08
### Fixed
- **`SCHEMA_SQL`'s `sources_set_sync_key` Was A No-Op** (B2 / sync_db-2)
  The trigger was written twice — once inline in `SCHEMA_SQL`, once in
  `_refresh_current_triggers` — and the two drifted. The `SCHEMA_SQL` copy spelled
  the path separator `'\'` inside a non-raw Python string, so the escape ate the
  backslash and the body became `replace(NEW.relpath, '', '/')`. Replacing an
  empty string is a no-op, so a Windows-style path was never normalized.

  `_triggers_need_refresh` could not catch it: it matched a substring
  (`NEW.sync_key IS NULL OR NEW.sync_key = ''`) that the BROKEN body also
  contains, so a database carrying the no-op reported "current" and kept it.
  Verified: a database built from raw `SCHEMA_SQL`, then reopened through
  `db.connect()`, still held the no-op.

  `sync_key` is the cross-device transport identity, so a source registered
  under that body gets `vault:04_Resources\win\a.md` instead of `.../win/a.md`
  and can never match its counterpart on another OS — and only the trigger
  self-heals on reopen, never the rows.

  The three managed triggers now have ONE definition (`TRIGGER_BODIES`) rendered
  into both install paths, with the separator built from `chr(92)` so no escape
  can eat it again, and `_triggers_need_refresh` compares the rendered body
  instead of a substring allowlist.

  No vault is affected in practice: `init_db` calls `_refresh_current_triggers`
  unconditionally, so every vault created the normal way already had the correct
  trigger. The reporting vault has it, with 0 of 36 sources carrying a backslash
  in `sync_key`.

  SCHEMA now states what happens to a key that was already derived wrongly: it
  is **never rewritten**. `sync_key` is the identity peers match on, so a
  retroactive repair on one device and not another would split the source
  instead of converging it. The trigger self-heals on open; the rows do not, and
  correcting them is a deliberate cross-replica action.

## [0.50.0] - 2026-08-08
### Fixed
- **An Import Reported Rows It Had Silently Dropped** (B2 / sync_db-1)
  This is B2's stated hard condition, and it was violated. `_do_insert` used
  `INSERT OR IGNORE`, so a row the database refused — a truncated or malformed
  peer export — was discarded while `_lw_upsert` still returned `inserted` and
  the caller incremented `stats.inserted`. Reproduced directly: importing one
  valid row and one constraint-violating row stored **1** row and reported
  **2 inserted**.

  `INSERT OR IGNORE` stays, but not for the reason it looks like: callers look
  the row up by transport key first, so an identical row never reaches the
  INSERT twice. What it absorbs is a UNIQUE constraint the key lookup cannot
  see. The insert now reports which of the three happened — stored, already
  present under another identity, or refused — and only the last is counted as
  `rejected`.

  That distinction matters more than the original bug. `graph_entities` is
  UNIQUE on `(canonical_name, entity_type)` and `source_spans` on
  `(source_id, content_hash)`, while both transport on a surrogate `id`, so two
  devices that independently extract the same entity mint different ids and
  collide on content. The row is already present; calling that a refusal would
  have fired on every sync forever, since the ids never reconcile.

  Classification asks the schema (`PRAGMA index_list`) which UNIQUE index
  collided, mirroring SQLite's semantics — NULLs are DISTINCT, and a partial
  index applies only to rows matching its predicate. Where it cannot decide, the
  row is reported as refused: over-reporting a loss is recoverable,
  under-reporting one is the silence this feature exists to remove.

  A refused `sources` row no longer raises. It used to, and nothing catches per
  row, so one malformed source rolled back every well-formed row in the file and
  never checkpointed the peer — re-failing on every retry. Its child rows are
  counted as refused too, since nothing can attach them to a parent that is not
  there.

### Added
- **`rejected` In Import Reporting**
  `ImportStats.rejected`, the `wiki db import` summary and its `--json` output,
  and the autosync totals. When it is non-zero the CLI says plainly that those
  rows are NOT in the vault and names the likely cause — a truncated or
  malformed peer export — because claiming a clean import over a silent loss
  removes the only signal that anything is wrong.

  A refused row still does not abort the pass: the rest of the file imports, so
  one bad row cannot wedge a device's sync. `wiki db autosync` reports refusals
  in its console output as well as its `--json`, and the Obsidian plugin raises
  a notice even when sync notifications are off — this is data that did not
  arrive, not routine progress.

## [0.49.3] - 2026-08-08
### Fixed
- **Rows Written During An Export Were Recorded As Already Exported** (B2 / sync_db-3)
  `export_for_device` stamped `last_export_ts` AFTER `export_knowledge` returned.
  `local_has_unexported_changes` treats anything older than that stamp as
  already shipped, so a row mutated while the export was running — not in the
  snapshot, but with a `created_at` earlier than the stamp — was silently
  considered exported. No peer would ever be offered it until an unrelated later
  mutation happened to move the clock past the stamp.

  The window is the export's own duration, so it widens with the vault: it is
  largest exactly when there is most to lose. The stamp is now taken before the
  snapshot is read and written only after a successful export, so a failure does
  not claim to have shipped anything.

## [0.49.2] - 2026-08-08
### Fixed
- **One Un-archivable Conflict File Wedged Sync Permanently** (B2 / CAND-03)
  After merging a sync conflict, `_archive_conflict` moved the file out of the
  synced vault (`<vault>/.curator/sync/`) into the repo-local cache
  (`<repo>/.cache/vaults/<hash>/runtime/sync_conflicts/`) with `Path.rename`.
  Those are different trees by design — the vault lives on synced storage
  (iCloud, Syncthing, a network mount), the cache is local — so they are
  routinely on different filesystems, where `rename` raises `OSError(EXDEV)`.

  `autosync` turns that into an `AutosyncError`, and the file stays in the sync
  directory: every later run re-imports the same conflict and fails again. One
  file wedged sync for that vault forever. It now uses `shutil.move`, which
  falls back to copy+unlink across filesystems.

  The archive name is also made unique instead of overwritten. A conflict file
  holds data not merged anywhere else, so silently replacing one with another of
  the same name destroyed it.

- **A Test That Went Red On A Calendar Boundary**
  `test_span_metadata_sync.py` (added in v0.49.1) hardcoded
  `2026-08-08T00:00:00Z` as a "newer than `created_at`" stamp. The derived
  revision is `max(created_at, metadata stamps)` and `created_at` is `now`, so
  that value was newer when written and older a day later — the suite went red
  with no code change. Timestamps there are now far-future sentinels, with the
  reasoning recorded so the trap is not reset.

## [0.49.1] - 2026-08-08
### Fixed
- **The v0.49.0 Sync Clock Was Applied At Two Sites And Missed Four**
  v0.49.0 derived a `source_spans` LWW revision from `created_at` plus the
  timestamps inside `metadata`, but only wired it into the `_lw_upsert`
  comparison and the `_local_max_ts` export gate. Four other places still ranked
  a span by the immutable column:

  - `_row_is_blocked_by_tombstone` and `_apply_tombstone` — on the **default**
    `wiki db import` path. Every metadata edit looked older than any tombstone,
    so an edit made *after* a delete was silently discarded instead of
    resurrecting the row, and an incoming delete destroyed a locally-newer edit.
  - `clear_row_tombstone_on_connection`.
  - `wiki db export --since`, which filtered on the raw column and so omitted
    exactly the metadata-only writes the derived clock exists to carry.

  Rather than patch a fifth site later, `row_revision()` is now the single entry
  point for "how new is this row", and `_UPDATED_AT_COL` carries a comment
  saying never to rank rows by it directly.

- **`_local_max_ts` Scanned Every Span On A Default-On Path**
  It materialized and JSON-decoded the whole `source_spans` table, and runs once
  per ingest job via `maybe_auto_export` — making a batch ingest
  O(jobs × total_spans). It now scans only rows carrying metadata and keeps the
  indexed `MAX(created_at)` for the rest.

- **The L1 Marker Could Be Cut In Half**
  `[image not extracted]` was three whitespace-delimited tokens, so
  `_section_preview`'s pre-existing word-boundary truncation could leave a
  dangling `[image not` — which reads as ordinary cut-off prose rather than a
  flagged loss, defeating the point of showing it. It is now the single token
  `[image-not-extracted]`, which `rsplit(" ", 1)` drops whole. Being one
  bracketed token also reads as an annotation rather than prose, which matters
  because this preview is quoted to the model as source text.

- **Spec Corrections**
  SCHEMA §20.4a described a "one-shot backfill … the only path for existing
  rows". No backfill was ever built — the shipped mechanism is a `text_preview`
  fallback at read time, exactly as the v0.49.0 CHANGELOG described. §20.4a now
  documents what exists, including that a *missing* `loss` key is not proof
  nothing was lost. Two dangling cross-references are fixed (§20.4a pointed at a
  nonexistent §20.6a; §26.2b cited the unrelated §20.6), and the v0.49.0 sync
  change — a runtime behavior change that had no spec entry at all — is now
  SYSTEM_BEHAVIOR §26.2c.

- **An Unenforced Vocabulary Claim**
  SCHEMA §20.4a states the loss verdict shares
  `formula_recovery.LOSS_VERDICTS`. Nothing checked it. `source_spans` cannot
  import that module without dragging `claim_support` onto the instant-L1 path,
  so a test now enforces the equivalence and a rename on either side fails.

## [0.49.0] - 2026-08-08
### Added
- **Unreadable PDF Regions Are Reported Instead of Silently Dropped**
  Many papers render displayed equations and figures as images. The parser
  cannot read them, so their content never reaches the knowledge base — and
  that happened silently. Measured on a real vault: one 27-page paper discarded
  **158** such regions, and **130** existed vault-wide across 4 sources, with no
  surface reporting any of it. A question about one of those equations could not
  be answered and nothing explained why.

  Three changes make the loss visible:

  - `source_spans.metadata.loss` records the verdict (`image_only`) and whatever
    geometry the parser stated (SCHEMA §20.4a, SYSTEM_BEHAVIOR §26.2b). It is
    additive: it gates nothing, changes no `formula_status`, and triggers no
    provider call.
  - `wiki lint` gains an `extraction_loss` check — one line per source with the
    count and sections, never one per span, and silent for sources that lost
    nothing. `wiki add` reports the same at ingest time.
  - The L1 projection keeps a `[image not extracted]` marker where the region
    was. `_section_preview` had been eliding it to whitespace, and for an
    `on_demand` source that preview **is** the CTX body that
    `_durable_l1_projection` serves as the plugin's chat context — so the one
    surface a reader actually sees had the gap closed, leaving prose that
    stopped mid-sentence.

  Existing vaults are covered with no migration and no re-ingest: the check also
  recognizes the placeholder still present in `text_preview`. That deliberately
  avoids `wiki add --force`, which sets `l2_status` back to `pending` and
  silently triggers a full L2/L3 rebuild across every source.

### Fixed
- **A `source_spans.metadata` Write Was Silently Dropped By Every Peer**
  `source_spans` has no `updated_at`, and `db_sync` used the immutable
  `created_at` as its last-write-wins clock. Any metadata mutation therefore tied
  on import and lost the strict `>` comparison, so the peer discarded it — and
  `_local_max_ts` never moved either, so the writing device did not even detect
  it had something to export. This was live but unexercised: `recover_formula()`
  has mutated `metadata` since v0.8.0.

  The LWW clock for `source_spans` is now derived from `created_at` plus the
  timestamps inside `metadata`, applied identically to both sides of the
  comparison and to the export gate. No new column — this codebase has no
  `ALTER TABLE` path, so an existing vault could not have received one.

### Notes
- This release makes formula loss **observable**; it does not recover a single
  equation. Recovery is blocked on three prerequisites documented in the Arena
  record: the `recover_formula` acceptance gate uses token-tuple equality where
  `validate_claim_support` uses subsequence (so faithful transcriptions are
  rejected), `validator_trace_id` has no producer anywhere in the backend (so
  the `reviewed` state is unreachable), and placeholder spans carry no bbox or
  physical page (so the region cannot be cropped for a vision model).

## [0.48.4] - 2026-08-07
### Fixed
- **`no output produced` Instead of an Answer About a Formula**
  Asking about a numbered equation in a PDF whose displayed math is rasterized
  returned no answer at all, only the provider's own failure text:

  > jetski: no output produced — a tool required the "command" permission that
  > headless mode cannot prompt for, so it was auto-denied

  `buildResolvedReferencesBlock` returned the empty string whenever no
  reference resolved. The user's question ("수식 26 설명좀") therefore reached
  the model with the equation absent *and* with nothing indicating an equation
  had been asked about — the prompt read as though the selection pointed at
  nothing. The model did the reasonable thing and tried to open the PDF with a
  file-reading tool. A headless CLI provider cannot prompt for that permission,
  the runtime auto-denied it, and the turn produced no output.

  Unfindable references are now named in an `<unresolved_cross_references>`
  block whose `note` states the text is genuinely absent from the extracted
  document, directs the model to answer from the context it already has and to
  say which item was unavailable, and forbids it from opening the file itself.
  The block carries labels only and never a snippet, so the existing
  fail-closed guarantee on content is unchanged — no context is still preferred
  to wrong context. `PLUGIN_SCHEMA.md` already required that "the prompt must
  tell the provider when the referenced target could not be located"; this is
  the concrete block that requirement was missing, and the spec now names it.

  Note that this restores a useful answer, not the equation: recovering math
  that was never extracted is a separate defect (`recover_formula()` is
  implemented and specified in SYSTEM_BEHAVIOR §26.2 with zero production call
  sites) and is tracked as its own roadmap item.

- **A Merged Page Reference Was Declared Missing While Being Quoted**
  Found in review of the fix above, before release. `resolveWithNearbyPageHints`
  relabels a successfully resolved page reference `method: "unresolved"` purely
  to suppress a duplicate render once its text has been folded into a nearby
  sibling. That flag never escaped while every unresolved entry was dropped;
  naming them sent it straight into the prompt. Selecting
  `(Section 11.1.2, p281)` produced page 281's text quoted verbatim under the
  section entry *and* `p.281` listed as absent from the document, in the same
  prompt — misleading content, which is worse than the silence it replaced.

  The two meanings are now distinct: `consumedBySibling` records that the text
  was delivered elsewhere, so such a reference appears in neither block, while
  `method` keeps its existing meaning for the fetch and identity-repair paths.

- **The Unresolved Note Claimed a Verified Absence It Never Established**
  The note asserted the text "is absent from the extracted document" and that
  the gap was final. The quick-query popover passes no whole-document locator
  at all, and where one is wired it returns nothing when the backend is
  offline, so "we did not look" was being reported to the model as "confirmed
  absent" — directing it to state a falsehood confidently. It now claims only
  that retrieval failed.

- **The Recency Anchor Did Not Carry the New Rule**
  `buildRecencyAnchor` is emitted last, at the position of strongest attention,
  specifically to survive long-session attention decay, and is appended on the
  same sidechat surface where the failure was reported. It still named only
  `<resolved_cross_references>`, so a long enough session could steer the model
  back into the auto-denied tool call even with the fix in place. It now
  carries the unresolved case and the no-file-read rule.

## [0.48.3] - 2026-08-07
### Fixed
- **"Add source" Stayed Clickable After A PDF Was Already Added**
  Adding a Zotero PDF from the purple pin registered it correctly, but the
  control kept reading "Add source" and remained clickable, so the same source
  could be submitted again with no sign it was already in the knowledge system.

  A Reference-Mode source stores the vault-side **stub** in `sources.relpath`
  (`04_Resources/References/<title>.md`), never the external PDF path. The
  plugin checked status by the PDF path, which matches nothing — verified
  against the reporting vault, where source 37 has all four layers `done` and
  yet `wiki plugin source status --file-path <pdf>` answers "Source not found".
  That `untracked` result renders the "Add source" label, and the
  already-added guard (`isAddedState`) never fires because the state never
  reaches an added value.

  `logical_source_id` (`zotero:<key>`) is the identity that survives, and the
  backend's `get_source_row` already matches on it — confirmed by looking the
  same source up that way and getting id 37 with `l1..l4 = done`. The plugin
  simply never sent it. It now does, on every status check rather than only
  when no local path is known, so a Zotero PDF whose path is unresolved on this
  device also resolves instead of being reported untracked without asking.

## [0.48.2] - 2026-08-07
### Fixed
- **The Sidechat Job Indicator Disappeared**
  The spinner and "N running / N queued" badge in the sidechat header stopped
  appearing entirely. `updateStatusBar` read
  `<vault>/.curator/runtime/jobs.json`. Runtime snapshots moved to the
  repo-local cache in 2026-07 and nothing migrated or rewrites the vault-side
  copies, so that file froze: on the reporting vault it sat at 2026-07-04 with
  `running: []` while the live snapshot showed a job actively running. With an
  empty `running` list the render block is skipped and nothing is drawn, which
  is indistinguishable from the feature having been removed.

  It now reads the snapshot at its real location through
  `plugin.readRuntimeJson("jobs")`, which resolves the hash-keyed cache
  directory (`vaultMachineCacheDir`, mirroring the backend's
  `get_vault_cache_dir`) and is already used in production by the main status
  bar. This stays a cheap file read: `b9a49a1` deliberately left the sidebar on
  the snapshot rather than the live CLI, because unlike the dashboard's
  once-per-render fetch this polls for the lifetime of the view. Polling stays
  at 2 s.

  A missing or unreadable snapshot is treated as "unknown", not "no jobs" —
  whatever is on screen is left alone. Blanking on a read failure would
  reproduce the exact symptom being fixed from a different cause.

  Two source-level tests guard the invariants that let this hide for a month:
  that the poll resolves the hash-keyed path rather than any `.curator` vault
  path, and that the not-readable early return sits before the element is
  emptied.

## [0.48.1] - 2026-08-07
### Fixed
- **Asking About A Formula On A Distant PDF Page Produced No Answer At All**
  Reading page 1 of a 30-page paper and asking about equation (24) on page 27
  returned only a provider error:

  > no output produced — a tool required the "command" permission that headless
  > mode cannot prompt for, so it was auto-denied

  The reference resolver probes for a numbered equation at `currentPage ±2`
  only (`ADJACENT_EQUATION_PAGE_OFFSETS = [1, -1, 2, -2]`). Page 27 was never
  fetched, so the reference failed closed, no `<resolved_references>` block was
  attached, and the provider was left to locate the page with its own tool call.
  A headless CLI provider cannot prompt for tool permission, so it produced
  nothing — the error was the symptom, not the cause.

  The resolver now falls back to a whole-document lookup when the adjacent probe
  comes up empty: the backend already indexes every page of a tracked PDF and
  returns a page number per hit, so the referenced equation is located and its
  page fetched deterministically before the provider is called.

  Deliberately bounded: the lookup runs **only** after the cheap adjacent probe
  fails (verified by test — no backend search for an equation one page away),
  fetches at most 3 located pages so a poor hit list cannot become dozens of
  fetches, and a locator that throws leaves the previous fail-closed behaviour
  intact rather than surfacing a resolved-looking reference with no content.

## [0.48.0] - 2026-08-07
### Changed
- **The Internal Language Boundary Is Enforced By The Backend, Not Requested By Callers**
  v0.47.0 fixed Korean questions failing to reach L3/L4 by adding
  Korean/CJK/Cyrillic alternatives to the route signals and making `seed_terms`
  script-aware. That worked, and it was architecturally backwards: it made the
  system's INTERNALS multilingual, when the contract is that internals are
  English and only input/output carry the user's language
  (USER_GUIDE: "using English only as the internal search/reasoning language").
  Every future internal component would have inherited the same obligation.

  The real defect was that `QueryRequest.english_query` — the slot built for
  exactly this — was never populated on the ContextService path, so
  `working_query` silently fell back to the raw question.

  - Route signals and `seed_terms` are back to English/Latin-only.
  - `fetch_context` derives the English query itself. It is **not** a CLI flag:
    an invariant with no exceptions cannot depend on a caller remembering to
    pass it, and a caller that forgets degrades silently — the original bug.
  - New prompt contract `curator.query_search_terms` extracts a short English
    **search query**, not a translation. Translating is wrong for real requests:
    "이 문장을 한글로 번역해줘: <body>" rendered into English becomes an English
    sentence asking for a Korean translation, which would then be routed and
    matched as a question about the vault; and a long paste would be translated
    in full at cost with none of it usable as a query.
  - The same step returns `is_knowledge_question=false` when a message needs no
    stored knowledge, and retrieval is skipped with a stated reason. This is
    decided by reading intent — never by matching trigger words, which is
    unmaintainable and fails on the first synonym.
  - When derivation is unavailable it falls back to the ASCII terms already in
    the message (a real query for mixed-script input like "ellipsoid 형태의
    quadric") and says so.

## [0.47.0] - 2026-08-07
### Fixed
- **Routing Was Language-Bound: Korean Questions Could Never Reach L3/L4**
  `retrieval/router.py` chose the route with ASCII-only keyword regexes, so a
  non-English question could not match `global` or `explore` and always fell
  through to `local`. Measured on the real vault: all four of a Korean user's
  questions returned 0 of 233 community reports and 0 of 4 synthesis nodes —
  including one that explicitly asked to synthesize across multiple papers. The
  identical questions in English routed `global`. The distilled layers were not
  badly ranked for a non-English speaker; they were unreachable.

  Signals now cover the five languages USER_GUIDE documents as supported. Note
  `\b` is deliberately not applied to CJK alternatives: Python word boundaries
  are defined on `\w` and never fire between Han/Hangul characters, so a
  boundary-anchored CJK pattern silently never matches.

- **Entity Seeding Was Latin-Only**
  `seed_terms` tokenized `[A-Za-z]` only, so a pure-Korean question produced
  zero seed terms and entity resolution returned nothing on every route,
  regardless of graph coverage. It is now script-aware. A lone Hangul/Han
  character is skipped — it is a grammatical particle far more often than a
  term, and seeding on it matches any entity containing that character.

- **The Chat Surface Never Passed A Workspace, So The Curation Lens Never Applied**
  `ChatSidebarView` sent the Obsidian vault ROOT as `workspace_path`.
  `curate.yml` lives only at `01_Workspaces/<project>/`, so the backend found
  none, silently fell back to the empty default policy, and every pack reported
  `workspace_id: "default"` with an empty `policy_hash` — the Artist-persona
  lens of `about.md` §4/§5.6 applied to nothing a user read. The workspace is now
  resolved from the note in focus, through one helper shared by every
  ContextService call so a pack cannot be fetched under one policy and expanded
  under another. It still falls back to the vault base when no project applies,
  because `workspace_path` also selects which vault the backend opens.

- **Entity Descriptions Were Frequently Circular** (`curator.entity_relation_extract`
  v1 → v2) — 12 of 34 entities in served packs (35%) merely restated their own
  name, with a ~10% floor across all 965 entities. The v1 prompt had seven hard
  rules about relations, confidence and span citation, nothing about
  descriptions, and a worked example showing `"description": "..."`. v2 adds a
  description contract with worked bad/good examples. The version bump is
  required rather than cosmetic: `prompt_run_id` and `prompt_contract_version`
  are recorded against generated records.

### Changed
- **Claim Support Now Ranks And Labels Knowledge Instead Of Hiding It**
  `retrieval/materializer.py` selected only `support_status = 'verified'` units
  when building the search index, making claim-support validation an **admission
  gate**. A unit that had not been validated was not ranked lower — it was
  invisible to every route, every ranker, and every reranker.

  Validating an `uncertain` claim requires a calibrated secondary validator, and
  when none is configured the unit stays `unchecked` permanently. So a missing
  provider configuration silently deleted most of a knowledge base, with no
  warning and no way for a user to discover it.

  **Measured on a real 36-source vault: 1,701 of 2,799 live units (61%) were
  unreachable.** 1,117 of those were merely `unchecked` — never validated
  because no validator was configured. The reporting user's own question — how
  an ellipsoid quadric is written as a matrix — had its exact answer
  (`$Q^* = Z \breve{Q}^* Z^T$`) sitting in the database at confidence 1.0 and
  could not be retrieved by any route. After this change the index carries 2,215
  units (+1,117) and that answer is reachable, labelled `unchecked`.

  **`failed` stays excluded, deliberately.** It is not a weaker tier: it means
  the support check ran and found the cited span does not support the claim.
  Such a unit already writes no atom page and never feeds graph extraction, so
  search was the one remaining place ungrounded content could leak back in.
  (498 of the 584 `failed` units carry `formula_status='preserved_in_text'` and
  are prose-gate false negatives — real, but fixable at the gate rather than by
  admitting flagged content to the index.)

  This is the same defect shape as the pre-v0.43.0 relation-corroboration gate,
  and it takes the same resolution:

  - **Ranking**: `verified` is unpenalised; `unchecked` / `uncertain` / `failed`
    are multiplied down so they sort below comparable verified evidence. The
    penalty is applied *before* ranking so it reorders rather than relabels, and
    is deliberately gentle — a strongly matching unverified claim may still beat
    a weakly matching verified one, because the alternative is serving nothing.
  - **Labelling**: every evidence item now carries `support_state`. Serving
    unverified knowledge without saying so would trade a silent omission for a
    silent overstatement.

  The gates that were correct are unchanged: retired units never serve, and
  staged or discarded generations never serve (§26.3).

### Fixed
- **L3/L4 Content Reached Through Search Arrived Anonymous**
  `EngineHit.record_type` was discarded when building the public `SearchHit`, so
  a community report or synthesis node found via search surfaced as a bare
  `search_hit` with an empty `community_report_id` / `synthesis_node_id` — served
  in the pack but invisible to the pack's own L3/L4 counters, which is why an
  audit measured "0 synthesis nodes" on a pack that contained one.

## [0.46.0] - 2026-08-06
### Added
- **Vault File Moves And Deletes Are Tracked**
  Moving a file inside the vault after importing it broke every stored reference
  to it. Reported through the sidechat: after moving a Zotero-imported note from
  `03_Notes/Vision/3DRec/` to `03_Notes/Papers/3DRec/`, an agent edit block came
  back `File not found` against the pre-move path.

  **The plugin subscribed to no vault file events at all** — two `registerEvent`
  calls existed repo-wide and both were workspace layout events. Obsidian
  supplies the old path on rename; nothing listened. It now subscribes to
  `vault.on("rename")` and `vault.on("delete")`.

  **A move preserves everything except the location.** `db.relocate_source`
  updates all three places the path is denormalized (`sources.relpath`, every
  `source_spans` row, `search_documents.projection_path`) in one transaction,
  keeping the content hash, every layer status, `context_id`,
  `logical_source_id`, and the whole derived L1–L4 closure. `sync_key` is
  deliberately NOT rewritten: it is the cross-device identity, minted once and
  matched only by equality, and changing it would make a peer replica see a
  delete plus an insert rather than one moved row.

  **Zotero stubs relocate freely.** `logical_source_id` identifies the document;
  `relpath` is only where the stub sits. This is why the existing
  `rebind_source` was the wrong tool — it keeps `relpath` unchanged, re-points
  the EXTERNAL file, and refuses `zotero:` sources, because Zotero owns the PDF
  path but not the stub's folder.

  **A delete marks the source and keeps its knowledge.** It records
  `error_reason='file_missing'` and retires nothing, so an accidental delete —
  or a file moved out of the vault and back — cannot silently destroy extracted
  knowledge. `wiki source rm` remains the only path that retires a dependency
  closure.

  **Historical chat paths still resolve.** A bounded rename journal follows
  recorded moves, collapsing chains (A→B then B→C means A resolves to C).
  `resolveVaultFile` consults it only after every exact-path candidate fails,
  and still refuses a basename fallback — a same-named file in another folder is
  a different note and retargeting an edit to it would corrupt the wrong file.
  The journal is exact provenance from Obsidian's own event, not a guess.

- **`wiki lint` reports registered sources whose file is gone.** This is how the
  delete mark becomes visible, and it also finally diagnoses the real defect
  behind a pile of `invalid_source_path` errors: on the reporting vault, 48 Atom
  errors all traced to ONE source row registered at a path that no longer
  exists. The finding is never auto-fixable — restore versus retire is the
  user's call.

- New hidden CLI surface: `wiki plugin source relocate --from --to` and
  `wiki plugin source missing --from [--restored]`.

### Known Gap
- Vaults that already carry a dead source row from a pre-v0.46.0 move are
  reported by the new lint check but not repaired automatically. Retro-repair
  needs a content-hash reconciliation sweep and is tracked separately.

## [0.45.0] - 2026-08-06
### Changed
- **A Failed Layer Is Now `error`, Never `skipped` (BREAKING for status readers)**
  `compile_global_l3` recorded `l4_status='skipped'` when synthesis threw.
  SYSTEM_BEHAVIOR §4.1 already required `error` there, so the code was the side
  that was wrong. `skipped` means "this source contributed nothing to the
  layer" — an ordinary non-failing outcome — so recording an
  attempted-and-thrown layer as `skipped` made a broken build indistinguishable
  from an empty one. Observed on a real vault: 10 of 36 sources sat at
  `skipped` across L2/L3/L4 with **both** `layer_error` and `error_reason`
  empty, two of them holding 11 knowledge units each.

- **L3 And L4 Failures Are No Longer Conflated**
  A single `errors` list collected failures from both community-report
  construction and synthesis, so a synthesis failure marked `l3_status='error'`
  even though clustering had succeeded completely. The two are tracked
  separately: L3's status now reflects only L3's own work.

### Fixed
- **Crash Recovery Erased The Post-Publish Projection Marker**
  `sources.layer_error` is overloaded three ways — human error text, the
  post-publish projection marker that `pipeline/compile.py` *reads* to take the
  recovery path instead of recompiling, and sync annotations. `recover_stale_jobs`
  cleared the column unconditionally, so the real crash sequence (worker dies
  after publishing a generation → supervisor restarts → recovery requeues the
  job → retry runs) lost the marker at the recovery step and re-ran the entire
  LLM extraction against an already-published generation. The existing test
  missed it by retrying in the same process with no recovery interposed.

  The `running` → `pending` reset §4.1 requires still happens; `layer_error` is
  preserved when it matches the marker and cleared otherwise, so stale human
  error text still goes away. The marker prefix moved to
  `constants.POST_PUBLISH_PROJECTION_PREFIX` so the SQL and the Python cannot
  drift apart.

- **The L4 Status Write Clobbered The Real L3 Error Message**
  `layer_error` is one column shared by all four layers, and the loop wrote it
  twice per source — first with the L3 cause, then with a fixed L4 string. The
  second write won, destroying the actual reason L3 failed on the same line
  that recorded it. A build that fails at more than one layer now composes one
  layer-tagged message (`"l3: … ; l4: …"`) and writes it once.

  That fixed L4 string was also a lie in the one case it mattered: it read "L3
  prerequisite failed; synthesis not attempted" even when the error had come
  from synthesis itself, which had demonstrably been attempted. It is now used
  only when L3 really did fail first and gate it.

- **`wiki sync` Promoted L3/L4 To `done` From A Filesystem Glob**
  `_mark_clean_sync_status` set `l3_status='done'` for **every** source with
  `l2_status='done'` whenever *any* `CON-*.md` file existed anywhere on disk,
  and the same for L4 against `SYN-*.md`. The promotion was not per-source and
  consulted no record of what a given source contributed, so a genuinely
  `skipped` source came out of sync indistinguishable from a completed one.
  `.curator/Collections/` is a disposable projection; the presence of a file
  there says nothing about provenance.

  The promotion is deleted. `_mark_clean_sync_status` now does what its name and
  docstring always claimed — clear stale `layer_error` — and nothing else.
  SYSTEM_BEHAVIOR §26.3 states the rule explicitly: layer status is computed by
  the compiler and by nothing else.

- **A Second Filesystem-Glob Status Promotion, Reachable From Two Read-Only
  Commands**
  `_mark_existing_l3_done_if_present` was the twin of the promotion deleted from
  `_mark_clean_sync_status` — same glob, same every-source promotion — and it
  ran unconditionally from `wiki sources ls` and `wiki status --refresh`, two
  surfaces that should not mutate the vault at all. Removed along with its
  callers; `--refresh` now only rewrites the runtime snapshot cache, and its
  help text says so.

- **`wiki sync` Erased The Gap Reason It Had Just Recorded**
  `_mark_layer_status_from_sync_gaps` wrote the `sync_logical_gap:` reason with
  the L3 status, then immediately wrote `l4_status='pending'` with no `error=`
  — defaulting to `None` and clearing the shared column. `l3_status` was left
  `error` with no explanation, permanently. The same clobber this batch fixes in
  `compile_global_l3`, one function away.

### Added
- `db.UNSET` sentinel for `set_source_layer_status` / `set_sources_layer_status`,
  leaving `layer_error` untouched, plus `set_source_layer_error` /
  `set_sources_layer_error` for writing the column without touching a status.
  The default stays `None` (clear) — see `.agents/plans/03_b3_roadmap_evidence.md`
  for why flipping it would have traded this bug for its mirror image across
  ~25 call sites. Bulk id predicates are chunked to the module's conservative
  999-variable convention, matching the eight existing `_chunks()` call sites.
## [0.44.1] - 2026-08-06
### Fixed
- **`wiki lint` Reported 70 Errors The User Could Not Act On**
  Audit of a real 37-source vault after the post-v0.43.0 build scored 70 errors
  / 0 warnings, every one of them `invalid_source_path`. Three separate defects
  in the same check produced them.

  **(a) Two Unicode normalizations compared byte-exact.** `lint.py` built its
  set of known source paths from a filesystem walk, which on macOS yields
  decomposed (NFD) names — `Plu` + U+0308 — while the path stored in
  `sources.relpath` and written into page frontmatter is precomposed (NFC)
  `Plü`. Python string equality has no opinion about Unicode equivalence, so
  the two never matched in a `set` lookup even though they name one file that
  `Path.exists()` opens either way. 22 of the 70 errors were this. Both sides
  of the comparison are now NFC-normalized.

  **(b) The repair resolved through a field the compiler no longer writes.**
  `check_atom_source_paths` recovered an Atom's true source by following its
  `parent_source` wikilink to a Context and looking the Context up in `sources`.
  Measured on the same vault: **0 of 1098 Atoms carry `parent_source`** — the
  compiler emits `source_span_ids` instead. So `fixable` was False for every
  modern Atom while the suggestion still said to run `wiki lint --fix`, which
  then did nothing. The repair now resolves through the Atom's own
  `source_span_ids` → `source_spans.source_id` → `sources.relpath`, which is
  the provenance the page actually carries; `parent_source` is still consulted
  second so pre-compiler pages keep working.

  **(c) An unrepairable error advertised a repair.** Even with a resolvable
  source, `--fix` copies `sources.relpath` into the Atom — which helps only if
  that row still names a file that exists. When a source is renamed on disk
  without being re-registered, the "repair" wrote the dead path straight back
  and the identical error returned on the next run: a loop the tool could not
  exit. An issue is now marked fixable only when the repair value resolves on
  disk, and the three cases (repairable / stale source row / no registered
  source) each carry a suggestion naming the actual remedy.

  On the audited vault this takes 70 errors to 48. The 48 that remain are one
  genuinely stale `sources` row whose file was renamed away, and they now say
  so and point at `wiki add` / `wiki source rm` instead of at a fix that cannot
  work.

## [0.44.0] - 2026-08-05
### Removed
- **`wiki query --update` And Its Insight-To-Atom Path**
  The flag created an L2 Atom out of the synthesized answer. It did so by
  writing an `ATM-*.md` file directly into `.curator/Collections/02_Atoms/`
  with **no `knowledge_units` row behind it** — an orphan in a directory the
  system treats as a derived, disposable projection of the database. The node
  was therefore invisible to search, to the graph, and to every integrity
  check, and any re-emission from the DB dropped it. It also contradicted
  SYSTEM_BEHAVIOR §22.2, which requires backpropagation to be
  correction-driven and independent of query artifacts.

  Querying is now read-only with respect to the DAG, which is what the user
  guide already claimed. To feed something learned from an answer back into the
  graph, promote it to `02_Wiki/` (it re-enters as an L1 input on the next
  cycle) or use the insight lifecycle (`wiki insight list` / `show` /
  `promote`). `wiki sync --backward` is unaffected — it still synthesizes atoms
  from *corrections*, which is the sanctioned path.

### Fixed
- **`context_expand` Double-Subtracted The Expansion Reserve, So Every Handle It
  Advertised Was Guaranteed To Be Refused**
  `context_fetch` withholds a reserve (`min(1000, limit // 4)`) so that
  expansion has headroom, and `context_expand` withheld it a *second* time
  against the same `limit_tokens`. Since both paths share a cost function and
  the running total only grows, an item that fetch omitted because
  `used + cost > limit - reserved` could never satisfy
  `already_used + cost <= limit - reserved` afterwards. Every handle offered in
  `next` was therefore mathematically certain to come back as
  `expansion_refused / budget_exhausted` at the budget that offered it, and the
  progressive-expansion surface was inert on its own default path
  (`limit_tokens=8000` for both operations). The admission ceiling on expand is
  now the full `limit_tokens` per SYSTEM_BEHAVIOR §31.1, and an expand response
  reports `budget.reserved_tokens = 0` because nothing is being withheld.

- **A Secret That Cannot Be Decrypted Was Reported As A Missing API Key**
  `secret_store.get_secret` swallowed `InvalidToken` and returned `""`, which
  is exactly what "no secret stored" returns. The Fernet key is machine-local
  and never syncs, so this is the ordinary result of the project's own
  cross-device config sync: the config names a secret whose ciphertext this
  machine cannot open, and DeepSeek then told the user to set
  `DEEPSEEK_API_KEY` — sending them to check an environment variable that was
  never the problem. Reading an undecryptable entry now raises
  `SecretDecryptionError` naming the secret and the fix. `wiki config secret
  list` still succeeds, rendering that row as `<undecryptable>`.

- **Silent Exception Boundaries (SYSTEM_BEHAVIOR §32)**
  `wiki lint --fix` swallowed a failing `search.update_index` with
  `except Exception: pass` — a false success, since the pages on disk and the
  search index had diverged and queries would serve stale text with no
  indication. It now warns with the cause and points at `wiki reindex`. The two
  account-identity fallbacks in `llm_identity.py` log the suppressed cause
  instead of silently degrading to "Authenticated", and the JWT claim decoder
  narrows its catch to the specific parse classes §32 requires. The
  atom-from-insight path (still reachable through `wiki sync --backward`) logs
  which of its three failure modes it hit instead of collapsing them all to a
  bare `return None`.

### Documentation
- SCHEMA §7 MCP payload examples were stale: `check_source_status` gained
  `relpath`, `l4_complete`, and the full `source` record, its three other
  response shapes are now documented, and `get_available_models` shows the `ok`
  wrapper, the `deepseek`/`ollama` providers, and the per-model entry fields.

## [0.43.0] - 2026-08-05
### Changed
- **Relation Corroboration Threshold Lowered To One Independent Source**
  A relation entered authoritative topology only with **≥2** distinct verified
  `source_lineage_hash` values. But the lineage hash already collapses
  copied/duplicated/forked sources to one lineage, so requiring two did not
  exclude fraud — it excluded every proposition that only one source states,
  which in a personal research vault of distinct papers is nearly every
  proposition.

  Measured on a real 37-source vault: **717 of 722 relations were quarantined**
  as `copied_source_only` (every one of them with exactly one lineage), leaving
  5 active relations, 6 community reports, and 3 synthesis nodes. Community
  construction consumes only `active` relations, so it had almost no input, and
  34 of 37 sources reported `l3_status='skipped'` and `l4_status='skipped'`. The
  knowledge graph the product exists to build was effectively empty, which is
  also why sidechat and MCP had no L3/L4 to reference.

  This contradicted the stated philosophy, where a Permanent Note is "a **single**
  idea as an independent Atom" and the value is *linking* such notes across
  distinct sources — Zettelkasten never requires two sources to agree before an
  idea may be linked. Corroboration is now treated as a ranking/confidence
  signal rather than an admission gate: `active` requires **≥1** verified
  lineage, and only **0** is `unsupported`.

  **Existing vaults recover without re-extraction.** Relation lifecycles are
  recompiled for every non-retired relation at the start of graph rebuild, so
  the next `wiki build` re-admits previously quarantined relations. Verified on
  a copy of the affected vault: active relations went from **5 to 651**, with
  the remaining 71 held only by the separate `bridge_risk` structural check.

  `copied_source_only` is retired as an outcome and kept in the frozen reason
  set so historical rows stay decodable and re-evaluable. SYSTEM_BEHAVIOR §27.2
  /§27.3, SCHEMA §21.5/§21.6, and the §27.6 graph-audit assertion are updated to
  match.

## [0.42.4] - 2026-08-05
### Fixed
- **A Cancelled CLI Request Is Actually Cancelled**
  The non-streaming CLI paths returned their promise from inside the request's
  guarded block, so the block settled at launch and the `finally` released the
  request — detaching the owner's abort listener — while the CLI child was still
  running. A Stop or dismiss then reached nothing. Both the primary CLI path and
  the HTTP-auth CLI fallback now await inside the guard.
- **Reposition Listeners No Longer Leak Onto Popout Windows**
  The Quick Query trigger attaches `scroll`/`resize` listeners to the window
  owning the selection, but detached against whichever window was active at
  teardown. Selecting text in a popout and then in the main window stranded a
  capture-phase `scroll` listener on the first one for the rest of the session.
  The attach-time window is now recorded and detached against, and the existing
  trigger is torn down before the active-document reference moves.
- **A Second Vault No Longer Deletes The First One's In-Flight Chat Image**
  The startup sweep for crash-leftover chat images removed the whole
  `chat_images` directory. That directory is scoped to the Incurator repository,
  not to a vault, so opening a second vault in another Obsidian window destroyed
  an image payload the first vault was mid-send with. The sweep is now per run
  directory and skips anything younger than the longest a single request can
  legitimately live; per-request cleanup in the request's own `finally` remains
  the primary mechanism.
- **Auto-Sync No Longer Runs After Unload**
  `SyncScheduler.dispose()` cancelled the debounce timer but left a queued
  follow-up armed, so a pass already in flight re-fired from its own completion
  handler and started a backend subprocess after the plugin had unloaded.
  Disposal now sets a terminal flag that every entry point checks and clears the
  queued flag.
## [0.42.3] - 2026-08-04
### Fixed
- **Quick Query No Longer Answers From The Wrong PDF After A Tab Switch**
  `fetchActivePdfPage` guards document identity only when the caller supplies an
  expected id. The local PDF tool runner opted in; Quick Query did not. Its
  cross-reference resolution issues several sequential backend round-trips
  (~0.2 s each), so switching tabs mid-flight let later fetches read pages out
  of the newly active PDF and splice them into the answer. Because the resolver
  also writes each fetched page back into the index under the document id it was
  given, foreign page text contaminated the original document's BM25 index and
  skewed later queries too. Quick Query now reads the document identity once,
  before the first await, and uses that same pinned id both for every page fetch
  and for the index it writes into — so a mid-flight tab switch fails closed
  instead of answering from the wrong document.

## [0.42.2] - 2026-08-04
### Fixed
- **Quick Query No Longer Crashes On PDF Text Containing Null Bytes**
  Selecting text from certain PDFs and asking a question in the popover threw
  `The argument 'args[11]' must be a string without null bytes`. PDF text
  extraction can embed `\0` characters which are valid in JavaScript strings but
  fatal when Node.js converts CLI arguments to C-strings for `execve`.
  `messagesToCliPrompt` — the single funnel for all CLI provider prompts — now
  strips null bytes before the string reaches `child_process.spawn()`.

## [0.42.1] - 2026-08-04
### Fixed
- **Zotero Import Profile Edits No Longer Vanish After The First Keystroke**
  Changing a profile's template path from `.../book_template.md` to
  `.../paper_template.md` saved `.../boo_template.md` — the value after exactly
  one backspace. `saveSettings()` → `saveZoteroProfiles()` ends by assigning
  `settings.zoteroProfiles = store.profiles`, replacing the array and its
  objects with ones re-read from the merged on-disk store, while the settings
  editor had captured `settings.zoteroProfiles[index]` once at render time. The
  first keystroke's save therefore detached that reference and every later
  keystroke mutated an orphan nothing persists, so the edit looked applied in
  the field and was silently lost. Each write now resolves the live profile
  instead of a captured one. Because the editor has no Save button, fields also
  commit on blur, so leaving a field is always a durable save rather than
  relying on the last keystroke's in-flight write.

## [0.42.0] - 2026-08-04
### Added
- **`setup.sh` Provisions The `wiki` Alias**
  Setup previously provisioned no backend entry point, so users hand-rolled
  one — and a hand-rolled alias carried between machines is how a macOS install
  ended up pointing at a `/home/<user>/…` path that cannot exist there, silently
  degrading `wiki` to an unrelated install found on PATH. Setup now writes an
  alias whose target is derived from its own repository root. Re-running
  REPLACES the previous Incurator block (including the legacy undelimited
  form), so a wrong alias self-heals; other tools' blocks are preserved and the
  rc file is replaced atomically with its mode intact. Both `~/.zshrc` and
  `~/.bashrc` are handled, and a different `wiki` earlier on PATH is reported
  with both paths rather than silently winning. Skip with
  `INCURATOR_SKIP_ALIAS=1`.

### Fixed
- **Quick Query Popover Shows Elapsed Time Instead Of A Frozen Label**
  Measurement first: a CLI-backed provider round-trip costs 8.2–12.2 s for a
  one-word answer regardless of model or effort, while the CLI binary starts in
  0.29 s and an Incurator backend round-trip is 0.20 s — the wait is the
  provider service handshake, not inference and not Incurator overhead. Because
  `agy --print` cannot stream, the popover's static "Thinking…" was
  indistinguishable from a hang for the whole wait (an ambiguity that already
  caused a real crash to be misread as slowness). The popover now ticks elapsed
  seconds like the sidebar, stops on success, error, and teardown, and no longer
  lets the streaming callback overwrite the live readout with static text. The
  PDF reference-fetch path was deliberately left alone: it accounts for at most
  ~0.6 s of a ~13 s action, and its existing tests prove the common case already
  issues a single fetch.
- **Backend Version Checks Read Build Identity, Not Package Metadata**
  The plugin compared the backend's top-level `version` — installed package
  metadata — against its own bundled build manifest. An editable install freezes
  that metadata at the version it was first installed at while continuing to run
  current repository code, so the two could never agree and the "Run Setup"
  banner could never be cleared by running setup. Version checks now gate on
  `build.backend_version`, falling back to the metadata version only when no
  build manifest is present. Package metadata is now not consulted at all — not
  as a gate and not as a fallback, since the backend seeds
  `build.backend_version` unconditionally, so an absent value means the backend
  is too old to state its identity and is reported as exactly that. A mismatch
  message now also names the backend launcher that answered, so "this install is
  out of date" is distinguishable from "you are talking to a different install
  entirely".

## [0.41.1] - 2026-08-04
### Fixed
- **Deferred PDF Tabs No Longer Disable Chat, Popover, And Context Pins**
  Obsidian 1.7.2+ restores workspace tabs as *deferred* views whose `leaf.view`
  reports the real view type while carrying none of the concrete view class's
  methods. The plugin narrowed external-PDF leaves on that type string alone and
  then called `getRuntimePath()`, throwing
  `TypeError: getRuntimePath is not a function` out of the shared leaf resolver.
  Because that resolver feeds both the active-context capture and the open-tab
  inventory, a single restored PDF tab simultaneously blanked the purple context
  pins, made sidechat Send do nothing, and left the Quick Query popover on
  "Thinking" — and restarting Obsidian reproduced it, because a restart is what
  creates deferred tabs. Every external-PDF narrowing now goes through a
  capability-checked guard that also rejects stale instances left by an in-place
  plugin update; a deferred tab degrades to its persisted state instead of
  throwing, and is never force-loaded as a side effect of building context.
- **PDF Pages No Longer Collide On Their Own Canvas**
  Page canvases are reused across zoom, scroll, and document swaps, but the
  PDF.js render task was fire-and-forget, so a re-render could start while the
  previous one still owned the canvas — PDF.js then threw "Cannot use the same
  canvas during multiple render() operations" and left the page blank. Renders
  are now tracked per page and cancelled (and awaited) before the next render
  claims the canvas, including on document swap, reload, and view close. The
  existing render-token guard is unchanged; it stops work scheduled after a
  bump but never a task already inside PDF.js.

## [0.41.0] - 2026-08-03
### Added
- **Ask AI And Sidechat Can Turn PDF Pages**
  The reading assistant already received the document outline with page
  numbers, so it could reason "that result is in Appendix 4, around p.617" —
  but it had no way to get there and could only tell you to navigate yourself.
  It now has a read-only page reader for the PDF you already have open, used
  as a fallback after automatic reference-following: it covers references
  discovered only after reading the target page, targets named in your
  question rather than the selected text, and prose references carrying no
  number. Documents with no embedded table of contents additionally allow
  searching the pages already read, since there is no map to navigate by.

### Changed
- **Popover Tool Boundary Stated Precisely**
  The Quick Query popover's tool policy moved from "no tools at all" to
  "no MCP tools, no filesystem, no scripts, plus the bounded PDF page reader".
  The zero-MCP guarantee is unchanged and is now locked by behavioral tests
  rather than by prompt wording. The reader refuses page numbers outside the
  open document, stops after a bounded number of fetches per question, is not
  offered at all when no PDF is open or the page count is unknown, and refuses
  to read across a document swapped mid-request. CLI providers (Antigravity
  `agy`, Claude, Codex) are excluded and keep the deterministic path, so the
  v0.23.0 sandbox contract is untouched.

---

## [0.40.3] - 2026-08-03
### Fixed
- **Correct Target Pages For PDF Cross-References**
  Ask AI / Sidechat pointer resolution no longer injects the wrong physical
  page for printed-page locators in books with front matter (e.g. selecting
  `From Result A4.1-(p581)` used to inject Appendix A1 tensor-notation text
  from physical page 581 instead of Result A4.1 on printed page 581). Printed
  pages now map through PDF page labels, a consensus front-matter offset
  inferred from printed header/footer numbers, and a printed-header scan; the
  literal identity guess survives only until the fetched page's own header
  disproves it, in which case resolution fails closed and a single bounded
  repair fetch retrieves the correct page. Theorem-family references accept
  appendix-lettered numbers (`Result A4.1`, `Corollary B2.3`), their
  definition lines join the caption index, and `Appendix 4`-style ToC titles
  answer to `A4`-style anchors for outline-range expansion.

---

## [0.40.2] - 2026-08-01
### Fixed
- **Explicit Retrieval Degradation**
  Runtime query-embedding failures now set lexical fallback and emit a stable
  `vector_failed` warning, including for vector-only queries without inventing
  lexical hits. Invalid reranker output preserves the complete RRF candidate
  order and reports `reranker_failed` instead of silently dropping candidates.
- **Exact Finite Provider Results**
  Corpus embedding batches and reranker responses must match request
  cardinality exactly and contain only non-empty finite numeric results.
  Invalid embedding batches persist nothing and count every requested chunk as
  failed.
- **Truthful Prompt Provenance And Versions**
  Prompt traces now finalize provider/model attribution from the provider that
  produced the final response after failover. Prompt versions are validated as
  numeric `vN[.N...]` identifiers, so latest lookup and listing place `v10`
  after `v9`.

---

## [0.40.1] - 2026-08-01
### Fixed
- **Independent Provider Cancellation And CLI Fidelity**
  Overlapping sidebar and Quick Query requests now own independent cancellation
  signals, so closing one popover cannot stop another request and foreground
  cancellation returns to an older still-active sidebar request. Caller-owned
  popovers never replace the sidebar Stop target; cancellation during context
  preparation launches no provider transport, and Ollama preserves normal
  `AbortError` semantics. Streaming and non-streaming CLI children bind to the
  correct request; non-streaming calls also preserve their per-call model and
  GUI-safe PATH/temp environment.
- **Collision-Safe MCP Lifetimes**
  Sanitized model-facing MCP tool names now dispatch through an explicit unique
  route map instead of lossy reverse parsing. Shutdown rejects pending JSON-RPC
  work, clears request timers, waits through bounded TERM/KILL escalation, and
  ignores late exit and stdout events from a replaced server generation. Each
  restarted generation begins with a fresh JSON framing buffer.
- **Bounded Plugin Backend Commands**
  The vault-local backend runner now applies separate normal and long-operation
  timeout/output policies. Hung or overproducing subprocesses fail visibly and
  settle once, while pipeline, import, model, and job commands retain larger
  limits suitable for legitimate long work.

---

## [0.40.0] - 2026-08-01
### Changed
- **Obsidian 1.1.0 Minimum**
  Existing synced session and Zotero-profile commits now use Obsidian's atomic
  adapter processing API. The plugin therefore requires Obsidian 1.1.0 or
  newer; `versions.json` keeps v0.39.2 available to Obsidian 1.0.x users.

### Fixed
- **Fail-Closed Plugin Persistence**
  Chat-session and Zotero-profile storage now distinguishes missing state from
  corrupt or unreadable canonical files. Invalid files remain untouched and
  block ordinary saves. Existing valid files parse and merge the canonical text
  supplied at the atomic commit boundary, preserving peer arrivals and deletion
  tombstones; interrupted commits and initial temp writes preserve canonical
  bytes and clean temporary siblings.
- **Durable Secret And Config Updates**
  Encrypted-secret and YAML-config mutations now hold per-target locks across
  fail-closed read/merge/write operations and commit through flushed temporary
  files. Project saves merge into the freshly locked mapping so peer-only
  nested keys survive. Existing ordinary config modes are preserved, new files
  follow normal umask semantics, and secret temps are private from creation;
  corrupt state and interrupted replacement leave prior bytes and modes intact.
- **Recursive Runtime Credential Redaction**
  Plugin-readable runtime snapshots now remove credential-bearing keys at every
  nested mapping and array depth while retaining non-secret provider, model,
  and feature selections.

---

## [0.39.2] - 2026-08-01
### Fixed
- **Latest-User PDF Equation References**
  Sidechat now recognizes explicit equation pointers in the latest question,
  including `수식 (10)`, and refreshes a bounded next-first adjacent page through
  the existing read-only PDF context API when the loaded window lacks the target
  body. Resolved evidence is supplied before generic PDF context, so external
  Zotero/iCloud PDFs remain outside provider filesystem roots and no native
  `read_file` or `command` permission is needed. Resolution now fails closed
  when the bounded scan finds no exact equation label, and latest-question
  pointers are scoped to the active or explicitly attached primary PDF instead
  of being claimed by background PDF tabs.

---

## [0.39.1] - 2026-07-30
### Fixed
- **Complete Source Lifecycle Closure**
  Local source removal and imported source tombstones now retire/discard the
  complete authoritative generation, claim, graph-support/report, synthesis,
  span, projection, and search dependency closure. Shared graph knowledge
  remains only while another live source supports it, and serving/search paths
  fail closed on missing source provenance.
- **Deterministic Projection Recovery**
  Compiler publication now persists stable Atom ids, DAG edges, and dependency
  rows before writing derived files. A post-publish filesystem/search failure
  or process interruption keeps the authoritative generation and retries
  through DB-backed re-emission without another LLM call or generation.
  Re-emission refreshes only generated ATM/CON/SYN page hashes and removed
  orphan CTX hashes, so preserved CTX edits remain detectable; normal compiles
  update only their source projection instead of rebuilding the whole corpus
  per source.
- **Replica And Autosync Monotonicity**
  Tombstones cannot be backdated, mutable local reinserts advance strictly past
  future-clock deletes, immutable tombstoned rows fail closed, and malformed
  current-schema peer headers stop autosync visibly without checkpointing.

---

## [0.39.0] - 2026-07-30
### Added
- **Authored-Note Graph Topology**
  Registered visible Markdown notes now compile exact internal wikilinks,
  embeds, tags, and frontmatter wikilinks into deterministic `authored` graph
  relations. Exact vault-root/source-relative paths, unique names, and unique
  frontmatter aliases resolve; ambiguous, external, hidden, unsafe, and
  unresolved targets fail closed.

### Changed
- **Active-Only Graph Serving**
  Explore memory paths, graph status, search materialization, and community
  construction consume only active canonical topology. Authored edges may shape
  membership and dependency identity, but only independently supported
  extracted relations enter factual report relation ids and citations.

### Fixed
- **Atomic Lifecycle And Replica Convergence**
  Authored topology publishes and reconciles inside the existing compiler
  generation transaction, including edit/rename/delete retirement and failed
  publish rollback. Unicode-NFC portable IDs converge across devices; import
  restores one authoritative generation per source and retires losing authored
  rows. Relation re-assertion now preserves existing lifecycle metadata unless
  explicitly replaced.
- **Adversarial Authored-Topology Correctness**
  Masked Markdown no longer joins unrelated text into invented links or tags;
  escapes, numeric-only pseudo-tags, fenced blocks, balanced destinations,
  vault-bounded parent paths, `.markdown` notes, and ambiguous resolution obey
  the fail-closed contract. Generation audits retain exact authored membership,
  clock-skewed replica merges preserve shared edges, DB-only/type-change
  republishes cannot leave discarded-generation ownership, topology additions
  invalidate stale reports, and rematerialization removes authored search
  ghosts. Follow-up review hardening also reconciles lone generations after
  source tombstones, enforces exact audit membership at lifecycle admission,
  advances repair/retirement LWW clocks strictly, preserves winner-dependent
  reports, accepts balanced nested Markdown labels, and decodes targets once.

---

## [0.38.0] - 2026-07-30
### Added
- **Grounded Sidechat Vault Wikilinks**
  Every selectable Sidechat provider now shares one exact-path wikilink
  contract. Prompt-included note paths and usable ContextService locators retain
  vault-relative Markdown, PDF, heading, and block targets so answers can open
  the referenced page directly in Obsidian.

### Fixed
- **Fail-Closed Link Grounding**
  Sidechat no longer needs to infer a target from a display label. External,
  stale, unavailable, duplicate-anchor, source-fallback, absolute, and traversal
  locators are withheld from provider link targets, while uncertain plain text
  is left unchanged instead of being post-processed into a guessed link.

---

## [0.37.1] - 2026-07-30
### Fixed
- **Provider Failure Normalization**
  Ollama, Claude, and Codex now reject blank output consistently. Codex rejects
  non-zero processes before reading any partial output file, every `LLMError`
  subtype participates in configured failover, and an exhausted chain retains
  bounded provider-labelled attempt diagnostics with its terminal cause.
- **Traceable Query Failures**
  Provider and structured-output repair failures now retain their query trace,
  failed prompt traces, evidence provenance, warnings, retry count, first-output
  hash, and failed synthesis action. Unexpected runtime and storage defects
  continue to propagate instead of being mislabeled as provider failures.
- **Consistent Query Failure Surfaces**
  `wiki query` prints non-streaming success answers and exits non-zero with a
  concise expected-failure message. MCP and plugin queries share one existing
  response serializer, the hidden plugin command emits one JSON failure object
  before exiting non-zero, and the plugin trace panel preserves and displays
  the failure reason, prompt trace ids, and warnings.

---

## [0.37.0] - 2026-07-30
### Changed
- **Schema-v13 Composite Tombstone Contract**
  Composite-primary-key deletes now use a closed, versioned canonical-JSON key
  registry. Source page keys carry `sources.sync_key` instead of replica-local
  numeric ids, malformed or legacy ambiguous tokens fail closed, and v12/v13
  snapshots never partially interoperate.

### Fixed
- **Cross-Device Delete Convergence**
  All six synchronized composite-key tables now delete by their complete key.
  Equal/newer tombstones block stale rows, strictly newer mutable rows clear an
  older tombstone, immutable rows cannot resurrect, and dry-run remains
  read-only. Local PDF provenance, claim-support, artifact-dependency, relation
  support, and entity-lineage writers clear or emit exact tombstones as rows
  become live or absent. First-import dry-runs now resolve source-scoped keys
  from the incoming source map, so their counts match the real pass without
  writing parent or child rows.
- **Transactional Source Tombstones**
  Imported and local source deletion now share one dependent-cleanup path for
  job events, jobs, ingest runs, page provenance, DAG edges, and PDF pages.
  Delete, tombstone recording, and import statistics remain atomic per file.

---

## [0.36.8] - 2026-07-30
### Fixed
- **PDF Convert-to-LaTeX Antigravity Prompt Transport**
  The backend now sends the complete PDF transcription request as the
  `agy --print` prompt instead of placing it on ignored stdin behind a generic
  placeholder. It also passes the exact selected `--model`; dedicated extraction
  slots use `low` when supported and omit effort for fixed/no-effort models.
  The plugin's Antigravity chat command now forwards its selected model as well,
  and the catalogue uses the live `claude-opus-4-6-thinking` slug. Convert to
  LaTeX therefore preserves the selected prose, rewrites equations with LaTeX
  delimiters, and no longer copies Antigravity scratch-workspace planning
  narration as a successful result.
- **MCP 2.0 Dependency Boundary**
  Fresh validation environments now retain the supported MCP Python SDK 1.x
  line. MCP 2.0 removed the `mcp.server.fastmcp` API used by the current server
  and previously caused fresh GitHub Actions mypy runs to fail before pytest.

---

## [0.36.7] - 2026-07-26
### Fixed
- **Antigravity Hotfix Activation**
  Provider startup now verifies the running Obsidian bundle against the active
  vault's installed `main.js` and manifest before authentication or CLI launch.
  A copied-but-not-reloaded hotfix is blocked with a reload instruction instead
  of silently continuing with stale permission code. The update action requires
  all three plugin artifacts and then performs an actual Obsidian renderer
  reload.
- **Complete Open-Tab Context Inventory**
  The purple context row now enumerates every open Markdown/PDF tab, including
  hidden members of tab groups. Visible tabs default to included; hidden tabs
  default to eye-off and cannot enter tab lists, bodies, outlines, edit targets,
  or continuity context until explicitly included and materialized. Exact
  source/page keys preserve distinct PDF pages and prevent stale cached PDFs
  from returning after tabs close.

---

## [0.36.6] - 2026-07-23
### Fixed
- **Purple Pin Zotero Source Registration**
  Purple Pin's **Add source** action now preserves the Zotero attachment key as
  the portable source identity when the plugin also supplies its already
  resolved local-filesystem PDF path, including linked attachments. Valid
  Zotero references on macOS and Linux no longer fail with `root_unregistered`
  when generic `external.path_roots` is empty, while unregistered non-Zotero
  external paths remain blocked.

---

## [0.36.5] - 2026-07-22
### Fixed
- **Zotero Import Case-Collision Refresh**
  `Import Zotero Item` now updates an existing note when Zotero metadata renders
  a filename that differs only by letter case and the filesystem reports
  `EEXIST`. The existing filename and persisted template regions are preserved,
  while the selected item's current metadata and Zotero parent/attachment links
  replace stale values. Unrelated create failures remain visible.

---

## [0.36.4] - 2026-07-22
### Fixed
- **Antigravity Headless PDF Reads**
  Antigravity CLI 1.1.3+ no longer auto-denies `read_file` when the Obsidian
  Agent summarizes an open PDF. The plugin atomically preserves and merges the
  narrow `$read_file$()` rule into the live
  `~/.gemini/antigravity-cli/settings.json`, refuses to overwrite malformed
  settings, and removes the ineffective v0.36.3 TOML artifact only when it still
  bears Incurator's generated-file marker. Existing `--add-dir` visibility and
  OS write containment remain unchanged.
- **Gemini 3.6 Flash Effort Forwarding**
  Antigravity CLI 1.1.5+ now receives the selected `--effort` value for base
  model slugs such as `gemini-3.6-flash`, which otherwise fail before inference.

---

## [0.36.3] - 2026-07-22
### Fixed
- **Headless `agy` CLI `read_file` Policy Auto-Sync**
  `syncAgyMcpConfig()` now automatically syncs a `read_file` policy to `~/.gemini/policies/incurator-read.toml` scoped to the plugin's allowed roots (vault + Zotero). This prevents headless `agy` (`-p --sandbox`) from auto-denying file reads following the v0.23.0 removal of `--dangerously-skip-permissions`.

### Added
- **Gemini 3.6 Flash Support in Antigravity Model Catalogue**
  Added `gemini-3.6-flash` ("Gemini 3.6 Flash") to the single-source model catalogue (`backend/src/curator/data/models.json`) under the `antigravity` provider options.

---

## [0.36.2] - 2026-07-20
### Fixed
- **Fail-Closed Knowledge Sync**
  Existing unreadable, malformed, or wrong-shaped device-local sync state now
  fails without replacing the device identity or peer high-water marks. Peer
  import and conflict archive failures are surfaced with file context, and a
  conflict is reported as merged only after import and archive both complete.
- **Transactional Tombstone Deletes**
  Imported tombstones no longer suppress target-row deletion errors. A failed
  delete rolls back the input-file transaction instead of recording and
  propagating a deletion that did not occur locally.
- **Workspace Policy Integrity**
  ContextService and QueryOrchestrator now use one validated `curate.yml` policy
  resolver. Existing malformed KRS files, invalid source-scope shapes, semantic
  validation errors, and policy hash/read failures stop before retrieval or
  synthesis rather than widening to the unrestricted default policy.
- **CLI Query Scope And Read-Only Behavior**
  `wiki query --workspace` now forwards the selected workspace into the shared
  policy boundary and reports invalid KRS configuration without starting the
  provider or printing a traceback. Query no longer runs pending ingestion as a
  hidden side effect; `wiki add` and `wiki build` remain explicit operations.
- **Validation Cache Isolation**
  The backend check helper now pins pytest to the backend configuration and the
  repository `.cache/pytest` directory even when callers pass only CLI options,
  preventing local validation from creating a forbidden root `.pytest_cache`.
- **Curation Plan Persistence Guard**
  MCP and hidden plugin planning surfaces validate the KRS before inserting a
  `curation_plans` row; invalid plans return failure and the plugin command exits
  non-zero without leaving a database side effect.

---

## [0.36.1] - 2026-07-19
### Fixed
- **Observable Runtime Degradation**
  Replaced silent broad-exception handlers in decomposed CLI, MCP, and plugin
  API internals with specific catches or logged best-effort fallbacks while
  preserving established command and tool boundaries.
- **MCP False Success And Missing Warnings**
  Synchronous source builds no longer report success when no per-source result
  is produced. Successful builds and knowledge promotions now return warnings
  when their follow-up search refresh cannot run.
- **Provider Model Catalogue Loading**
  Restored `curator_get_provider_config` model discovery after the MCP module
  move by loading `models.json` from packaged resources. This makes the current
  Claude Code and Codex model catalogue visible to Obsidian again.
- **MCP And Guide Contract Parity**
  Corrected the documented provider-setting parameters and recorded the actual
  build, knowledge-promotion, and provider-config result behavior.

---

## [0.36.0] - 2026-07-19
### Changed
- **Plugin Module Ownership**
  Moved the chat sidebar, LLM client, and external PDF view implementations into
  dedicated internal packages while preserving their established import paths,
  class names, view types, persistence formats, provider behavior, and UI flows
  through stable public facades.

### Fixed
- **External PDF Documentation Parity**
  Corrected the English/Korean plugin guides to describe portable Zotero and
  external-reference restoration instead of the removed persisted absolute-path
  behavior.
- **Review Lifecycle Hardening**
  Prevented concurrent abort/stream requests from clearing each other's request
  controllers, invalidated in-flight PDF renders on view close, and guarded MCP
  child stdin plus omitted server argument arrays.

---

## [0.35.0] - 2026-07-19
### Added
- **Current Claude Code and Codex CLI Models**
  Updated the shared backend/plugin catalogue for Claude Sonnet 4.6, Fable 5,
  Opus 4.8, and Haiku 4.5, plus Codex GPT-5.6 Sol, Terra, Luna, and GPT-5.5.
  Model-specific context capacities, effort choices, and defaults now drive all
  model pickers from the same contract.

### Fixed
- **Model-Specific Effort Handling**
  Settings, the chat sidebar, the dashboard, and stored-setting migration now
  normalize effort when a model changes. Models without an effort dimension
  clear stale values and omit the CLI flag; Claude vision calls now preserve a
  configured effort, while Codex supports the current `max` and `ultra` levels.

---

## [0.34.1] - 2026-07-19
### Fixed
- **Endless Obsidian Knowledge Sync**
  Made current-schema full-snapshot import content-idempotent for composite-key
  and immutable rows. Equivalent snapshots with fresh `export_id` values no
  longer report thousands of false updates and trigger cross-device re-export
  ping-pong. Dry-run now honors recorded peer high-water marks, and the plugin
  watcher ignores its known self snapshot instead of treating it as incoming
  peer data.
- **Plugin Lockfile Version Drift**
  Restored `plugin/package-lock.json` parity with the backend, plugin package,
  and Obsidian manifest versions.

---

## [0.34.0] - 2026-07-09
### Changed
- **Command Module Decomposition**
  Split the backend CLI, MCP server, and plugin API god files into modular
  package structures while preserving existing command names, MCP tool
  contracts, plugin API functions, and backward-compatible import facades.

### Fixed
- **PR #85 Review Hardening**
  Closed command-layer LLM clients in persona, workspace, and plugin PDF
  transcription flows; made `wiki models ensure` degrade gracefully when no
  vault exists; and replaced per-row source status resets with batch updates.
- **Extracted CLI Facade Compatibility**
  Restored `curator.cli.list_models_on_host` patch compatibility for extracted
  plugin model commands so CI and legacy tests observe mocked Ollama installs.

---

## [0.33.0] - 2026-07-07
### Changed
- **Strict Sync Schema Enforcement (Removal of Legacy Compatibility)**
  All backward-compatibility logic for parsing pre-v12 database schemas and legacy `last_imported_mtime` / `added_at` timestamps has been strictly removed. The system no longer attempts to automatically migrate or inject synthetic timestamps for malformed rows during P2P sync. Peer snapshots with incompatible schemas or missing `export_id` headers will now be skipped entirely rather than triggering partial imports. 
- **DB Initialization Speedup (Dead Code Removal)**
  The `init_db` and `connect` startup pathways have been significantly simplified by deleting over 700 lines of obsolete `v12` data-migration logic and fallback checks. Vault connections now start faster as they no longer perform redundant schema validation against legacy formats.

---

## [0.32.2] - 2026-07-06
### Fixed
- **`wiki db autosync` no longer crashes on pre-v12 peer export files.**
  After the v0.32.1 schema upgrade (v11 → v12), `_read_export_id` hard-crashed
  with `ValueError: Missing export_id in export header` when encountering legacy
  peer snapshots that lacked the `export_id` field introduced in v12. The plugin
  surfaced this as `"Empty response from backend"` and a persistent
  `"⚠ Sync Failed"` status bar / `"Auto-sync failed"` notice. `_read_export_id`
  now returns `None` for incompatible peer files (wrong schema version, missing
  `export_id`, malformed headers), and `import_all_peers` skips them with a log
  warning. Once peer devices upgrade and re-export v12 snapshots, their files
  are imported normally.

---

## [0.32.1] - 2026-07-06
### Changed
- DB schema upgraded to v12. Sources carry a `sync_key` column — a portable
  transport identity for cross-device JSONL sync. Local integer `id` values
  remain replica-local; imported child `source_id` foreign keys are remapped to
  the receiving device's ids on import.
- `compiler_generations` rows now have an `updated_at` column, making generation
  status transitions participate in monotonic LWW sync and preventing stale
  snapshots from regressing authoritative state.
- JSONL export headers include an `export_id` (UUID). Import rejects snapshots
  without one, preventing same-mtime snapshot confusion across replicas.
- JSONL import validates all table names and column names against an allowlist
  derived from the local schema, rejecting unknown tables and columns.
- Device-local state — `state.sqlite`, runtime, staging, sync reports, event
  log, PDF page/crop caches, and conflict archives — now lives under the
  Incurator repository `.cache/vaults/<vault-key>/` instead of the synchronized
  vault `.curator/`. The vault hash is derived from the resolved vault root. A
  one-time migration moves the existing `.curator/state.sqlite` (and sidecars)
  to the new location; if both old and new DB files exist, the backend aborts
  with explicit recovery instructions.
- Plugin session saves are serialized to prevent concurrent writes from
  corrupting the session store.
- Zotero profile store supports explicit deletion tombstones and serialized
  saves, preventing profile resurrection after cross-device sync.

### Fixed
- Cross-device source convergence no longer relies on integer primary keys.
  Two independently allocated `id=1` sources with different `sync_key` values
  converge to two distinct local sources with correct child provenance.
- Source deletion propagates via `sync_key` tombstones. Deleted sources stay
  deleted even when a stale pre-deletion snapshot is replayed from another
  device.
- Plugin temporary files (CLI output, PDF crops) are written to the repo cache,
  not the vault `.curator/` directory, preventing them from syncing across
  devices.

---

## [0.32.0] - 2026-07-04
### Changed
- External source configuration now accepts only the current
  `external.path_roots` / integration `root_keys` contract. Legacy root arrays
  are no longer converted or used for runtime source discovery.
- Absolute non-reference `sources.relpath` values are no longer treated as
  runtime filesystem paths.

### Removed
- Removed the `wiki paths` command group, the standalone portable-path migration
  service, and the pre-v0.29 `sources.external_path` / `sources.import_origin`
  table converter from DB initialization.

### Fixed
- Normalized the affected macOS device-local `second_brain` DB to schema 11
  before deployment, preserving its three Zotero attachment keys and removing
  the `wiki status` migration error.

---

## [0.31.0] - 2026-07-03
### Changed
- Dashboard L1-L4 density counts now come from authoritative serving DB records,
  not disposable Collection Markdown projections.
- Source rows have a schema-v11 `updated_at` revision, so status-only L1-L4
  changes participate in cross-device LWW sync.

### Fixed
- L3 is no longer reported complete when no live source-grounded community
  report exists; empty successful passes are terminal `skipped`.
- Emitted Zotero reference stubs resolve their `zotero_attachment_key` directly,
  and failed CTX projection repair no longer downgrades valid L1 DB state.
- JSONL snapshots and sync state use atomic replacement; MCP/worker mutations
  export automatically and compound `wiki update` runs export once.
- Zotero profile writes are serialized read-merge-write operations, preserving
  peer-only profiles and recent items.

---

## [0.30.0] - 2026-07-02
### Added
- **Zotero import profiles now sync across devices.** `zoteroProfiles` and the
  `recentZoteroItems` LRU moved from the plugin's device-local `data.json` to
  `.curator/zotero_profiles.json` inside the vault (the `sessions.json`
  pattern), so a profile created on one machine appears on the others after
  Syncthing sync. Existing profiles are migrated automatically and
  non-destructively on first load; `data.json` never carries profiles again.
- `wiki db autosync --dry-run` now reports whether an export is pending
  (`would_export`, text + `--json`), making a stale never-shipped snapshot
  visible without mutating anything.

### Changed
- **Cross-device knowledge auto-sync is now default-on (opt-out).**
  `auto_sync.enabled` defaults to `true`, and the snapshot export hook runs
  after every mutating CLI command — `wiki add`, `wiki build` (both `--wait`
  branches), `wiki sync`, `wiki update`, and `wiki jobs run` (covering the
  detached daemon spawned by background builds) — LWW-gated so unchanged state
  is never re-exported. Set `auto_sync.enabled: false` in
  `.curator/settings.yml` to opt out.

### Fixed
- **Dashboard on a second device showed a stale, smaller source count (e.g. 5
  instead of 31).** Root cause: every autosync export trigger was opt-in — the
  hook was wired only into `wiki update`, `auto_sync.enabled` defaulted to
  `false`, and disabling the plugin (`incuratorEnabled: false`) on a
  CLI-primary device silently killed all plugin-side triggers — so the device
  that ingested sources never re-exported its snapshot and peers kept
  converging on an old one. Mutating CLI commands now always publish the
  snapshot (see Changed above).
- **Zotero import profiles differed per device** because they lived in the
  unsynced `data.json` (see Added above).

---

## [0.29.1] - 2026-07-02
### Fixed
- **Side chat sidebar is blank after upgrading to v0.29.0.** The v0.29.0 portable
  path storage changes introduced four interacting regressions that collectively
  prevented the chat sidebar from rendering:
  - `isRetainablePersistedDoc` silently dropped all legacy path-only external PDF
    documents from `localStorage` on startup, causing `ExternalPdfView` to lose its
    file identity and fail to resolve the PDF path for any non-Zotero local PDF.
  - `loadPersistedDocs` omitted `path` from the in-memory registry even for docs
    that had one, so `resolveDoc()` could not find the PDF after restart.
  - `syncState()` in `ExternalPdfView` rebuilt `docState` via `buildSyncedExternalPdfState`
    which dropped the runtime `path` field, permanently losing the path from `docState`
    after any zoom/page-change interaction.
  - `ChatSidebarView.onOpen()` called `renderContextChips()` without error handling;
    any exception thrown while iterating partially-initialized `ExternalPdfView` leaves
    aborted the entire `onOpen()` flow, leaving the sidebar blank.
  - `main.ts:getLeafFile()` used `getState().path` to identify external PDF leaves,
    but v0.29.0's `getState()` strips `path` before returning — so external PDF
    leaves were invisible to the open-tab context builder.

  All five vectors are fixed: path-only docs are retained (the reopen prompt already
  handles gracefully missing files), `loadPersistedDocs` restores path into the
  in-memory map, `syncState()` preserves the runtime path in `docState`,
  `getLeafFile()` uses `getRuntimePath()` as the primary source, and `onOpen()`
  wraps the initial chip render in a guard so one bad leaf cannot blank the sidebar.

## [0.29.0] - 2026-07-02
### Changed
- Replaced persisted absolute Reference Mode paths with portable identity.
  Zotero sources and plugin PDF views now store only the effective attachment
  key and resolve through the current device's Zotero database. Generic
  external sources store `@<root_key>/<relative-path>` backed by machine-local
  roots in repo `.cache/config/config.yml`.
- Added transactional schema-v10 migration with dry-run, ignored cache backup,
  vault-relative stub repair, dependent PDF-page/span repair, and v10 sync
  export regeneration.
- Removed absolute PDF paths from plugin localStorage, Obsidian view state,
  sessions metadata, and persisted backend/repository/Zotero path overrides.

## [0.28.5] - 2026-07-01
### Fixed
- **Plugin runtime status/source snapshots no longer export absolute local paths.**
  Backend-written `.curator/runtime/status.json` and `sources.json` now keep
  source identity portable, clear `external_path`, hide vault/model/cache paths,
  and sanitize machine-local config blocks. Device-specific paths remain in the
  repository-local `.cache/config/config.yml` and are resolved through backend
  commands only when needed.
- **The Obsidian plugin no longer falls back to stale global `wiki` commands.**
  The default `wiki` setting now resolves to the repository-root
  `.venv/bin/wiki` only. The plugin refuses unresolved PATH launchers, may use a
  memory-only sibling `Incurator` repo hint without writing it to `data.json`,
  and records per-device launcher hints in repo-local `.cache/config/devices.json`.

## [0.28.4] - 2026-07-01
### Fixed
- **`curate.yml.vault_root` is now device-portable.** Workspace provisioning
  writes `vault_root` relative to the workspace directory (e.g. `../..` for an
  in-vault workspace; the matching `../…` hop for a workspace outside the vault)
  instead of baking in the generating device's absolute path, so a synced
  `curate.yml` stays valid across machines whose vault lives at a different mount
  point. The MCP fallback now resolves a relative `vault_root` against the
  workspace directory rather than the process CWD, and re-running `workspace init`
  heals only a genuinely stale `vault_root` while preserving any value (relative
  or absolute) that already resolves to the active vault. The per-device
  `VAULT_ROOT` env var remains authoritative when the MCP server is running.
- **Workspace initialization no longer leaks Incurator repository workflow
  rules into generated workspaces.** `wiki workspace init` and
  `curator_workspace_init` now render only Curator navigation hooks into the
  selected agent rule file, keep `curate.yml.vault_root` as the vault-root
  source of truth, and avoid injecting repo-local roadmap, inbox, draft-plan, or
  release-workflow instructions.
- **Codex workspace provisioning uses the workspace-agent slug consistently.**
  Codex client detection now resolves to `codex` rather than the LLM-provider
  slug `codex-cli`, and shared `AGENTS.md` managed blocks are rendered only for
  the selected/detected runtime instead of being overwritten by Antigravity.

---

## [0.28.3] - 2026-06-29
### Fixed
- **MCP source registration no longer hides skipped search-index refreshes.**
  `curator_register_source` now returns a success `warnings` array when L1
  registration succeeds but the non-fatal DB-native search-index refresh is
  skipped, and unexpected refresh errors are no longer swallowed.

---

## [0.28.2] - 2026-06-29
### Fixed
- **Plugin source registration no longer hides skipped search-index refreshes.**
  `wiki plugin source register` now returns a success `warnings` array when L1
  registration succeeds but the non-fatal DB-native search-index refresh is
  skipped, and unexpected refresh errors are no longer swallowed.

---

## [0.28.1] - 2026-06-29
### Fixed
- **CLI best-effort maintenance failures are no longer silent.** `wiki init`
  now warns when a known MCP client config target cannot be updated — including a
  wrong-shaped config (e.g. a non-object top-level document or a non-object
  `mcpServers` value, which previously raised an uncaught `TypeError`) — while
  still continuing with other targets and completing vault initialization. `wiki
  config provider` and project-scoped `wiki config set --local` now warn (never
  crash) when expected dashboard runtime snapshot refresh failures occur — not
  just write errors, but also a plugin-locked `state.sqlite` or, for `config
  set --local`, a malformed merged config — without rolling back the
  already-successful config write.
- **Root-level plugin validation command works again.** `plugin/vitest.config.ts`
  now pins the plugin directory as Vitest's root, so
  `npx vitest run -c ./plugin/vitest.config.ts` discovers plugin tests when run
  from the repository root.

---

## [0.28.0] - 2026-06-29
### Changed
- **PDF chat crop (Cmd+Shift+X) now passes the image DIRECTLY to a vision-capable
  main chat model instead of a redundant backend VLM round-trip.** The backend
  `plugin pdf transcribe` resolver, in the default config, resolves to the SAME
  provider CLI the chat already uses (`latex_extract_model → vision_model →
  main-if-vision`) — so a crop was transcribed by one CLI call and then re-sent in
  a second CLI call to the same model. Now, when the main chat model is
  vision-capable (antigravity / claude / codex — all live-verified), the crop image
  is read directly by that model through a scoped CLI image channel, with the
  pymupdf region text riding along as a caption. A non-vision main model (text-only
  Ollama) still falls back to backend transcription. (SYSTEM_BEHAVIOR §26.2a
  revised; PLUGIN_SCHEMA §2.1.3 added.)
- **Interactive chat image channel (claude/agy/codex CLI).** Chat images (crops,
  pastes, PDF-page captures) are written to `<repo>/.cache/cli/chat_images/<run>/`
  and referenced by path; image-bearing CLI turns enable scoped `Read` +
  `--add-dir <that dir>` (claude drops `Read` from its denylist only for those
  turns) so the same model can open them. For claude — the only provider whose
  `Read` is denied by default — the image-turn `--add-dir` is confined to JUST the
  image dir (NOT the broad allowed roots), so the re-enabled `Read` cannot reach
  arbitrary vault/Zotero files and the v0.23.0 no-vault-read hardening still holds.
  Text-only turns keep the hardened no-`Read` denylist; DB-scoped MCP curator tools
  stay available; every invocation stays inside the OS sandbox (v0.23.0). Temp PNGs
  are removed in the CLI/stream `finally` (success, error, abort) — including when
  pre-spawn setup throws — and stale dirs are swept on startup.

### Fixed
- **Send no longer freezes for ~1 minute on a PDF crop.** v0.27.9 only relocated
  the blocking VLM call to send-time, where it still ran BEFORE the "Thinking…"
  indicator rendered, so Send looked frozen until transcription finished. The
  deferred materialize now runs AFTER the assistant thinking message is rendered;
  on the vision-passthrough path there is no transcription round-trip at all, so
  Send is instant.
- **Quick Query popover now follows distant PDF references.** A selected pointer
  like `Section 11.1.2, p281` now treats the explicit page locator as a fetchable
  target, while bare object labels like `(3.5)` use the PDF outline to fetch a
  bounded candidate page range. Exact ToC section matches are tried before wider
  chapter fallbacks, fetched in small batches, and stopped as soon as the target
  is found, so the popover does not scan a large chapter before answering. The
  fetched target text is sent in `<resolved_cross_references>` instead of
  answering from only the current page window.
- **PDF page fetches now share the backend page cache across sidechat and
  popover.** Quick Query uses the same backend PDF context path as sidechat
  before falling back to the open PDF.js viewer. Backend `plugin pdf context`
  reads and writes `.cache/pdf_pages/<content_hash>/<page>.txt` when a registered
  source or file hash is available, so repeated page lookups avoid reparsing
  PDFs. `04_Resources` Reference Mode stubs keep portable identity only; absolute
  local paths remain per-device backend hints and are not written to synced
  stubs. Missing or invalid PDF content hashes no longer crash page lookup, and
  backend/network failures now fall through to the open PDF.js viewer.
- **Runtime temp/cache files stay inside Incurator-owned roots.** PDF crop
  transcription now writes temporary images under the vault's
  `.curator/runtime/pdf_crops/`; plugin CLI cache falls back to
  `.curator/runtime/cli/` instead of OS temp when the repo path is unknown; backend
  CLI logs/output and Zotero SQLite lock-bypass copies now live under repo
  `.cache/`; and provider CLI subprocess `TMPDIR`/`TEMP`/`TMP` values point at
  those allowed cache roots.

---

## [0.27.9] - 2026-06-29
### Fixed
- **PDF crop (Cmd+Shift+X) now shows the context chip instantly.** VLM
  transcription was blocking at capture-time, delaying the chip appearance and
  prematurely showing the "Add source" badge. The VLM call is now deferred to
  send-time (`materializeContextRefs`), so the crop image thumbnail and region
  text appear in the sidebar immediately after snipping.

---

## [0.27.8] - 2026-06-29
### Changed
- **DB-2 (slice 2): `jobs.py` + `sources.py` carved out of `db/_entities.py`.**
  Continuing the `db/` package decomposition, the ingest job queue moved to
  `db/jobs.py` and the sources / layer-status / DAG-edge / source-page functions
  to `db/sources.py` — byte-for-byte verbatim moves. Both are dependency-leaves
  (import only `db.schema`; no import cycles), and the public `db.*` surface is
  unchanged (guarded by `test_db_public_api.py`). Internal-only; no SQL, schema,
  contract, or behavior change. (The graph/community/knowledge cluster and the
  leaf entity modules remain in `db/_entities.py` for a later slice.)

### Fixed
- **Small pre-existing bugs in the carved `db/sources.py` functions** (surfaced in
  review of the moved code): `get_pending_count` (which queries the `sources`
  table) moved from `jobs.py` to `sources.py`; `vision_cache_put` /
  `update_page_hash` now write UTC timestamps via `_now_iso()` instead of
  timezone-naive `datetime.now().isoformat()`; and `get_source_row`'s
  `resolved_lookup` defaults to `None` (binds SQL `NULL`) instead of `""`, so a
  relative-path lookup can no longer accidentally match empty `external_path` /
  `import_origin` rows.

---

## [0.27.7] - 2026-06-28
### Changed
- **DB-2 (slice 1): `db.py` decomposed into a `db/` package.** The 4759-LOC
  `db.py` god-file was split — byte-for-byte behavior-preserving — into
  `db/schema.py` (DDL, migrations, `connect`, `init_db`, `get_stats`, enums) and
  `db/_entities.py` (entity repository queries), with a `db/__init__.py`
  re-export facade. The public `db.*` surface is unchanged (callers use
  `from . import db` → `db.<name>`), guarded by a new `test_db_public_api.py`
  snapshot. Internal-only; no SQL, schema, contract, or behavior change. (Job
  queue and per-entity module carving follow in slice 2.)

---

## [0.27.6] - 2026-06-28
### Fixed
- **XC-1 (slice 2): bug-masking broad-`except` narrowed in `model_setup.py`.**
  Ollama serve/pull/reachability/unload, llama-cpp install, and GGUF download now
  catch the specific expected exceptions (`OSError`/`subprocess.SubprocessError`/
  `httpx.HTTPError`) so unexpected errors propagate instead of being hidden, while
  genuinely best-effort steps (native `llama_cpp` import, embed/rerank smoke
  tests) keep a broad catch with a justifying comment + log.

### Changed
- **XC-4: plugin logs now go through a namespaced, level-gated logger**
  (`src/utils/logger.ts`). `warn`/`error` always print (prefixed `[Incurator]`);
  verbose `debug`/`info` are off by default and enabled per-device via
  `localStorage["incurator-debug"] = "1"` (+ reload). All 42 `console.*` calls
  across the plugin were routed through it, so a user's developer console stays
  quiet unless they opt in. No new plugin setting; nothing synced.

### Notes
- XC-4 plugin timer audit: all 39 `setTimeout`/`setInterval` were reviewed; every
  interval and stored timeout is already cleared on teardown and fire-once UI
  deferrals are benign — no timer changes were needed.

---

## [0.27.5] - 2026-06-28
### Fixed
- **XC-1 (slice 1): bug-masking broad-`except` narrowed across the backend data
  pipeline.** Previously several `except Exception: pass` handlers in
  `config.py`, `parsers/pdf.py`, `llm.py`, `ingest_raw.py`, `ingest_worker.py`,
  and `pipeline/compile.py` swallowed real failures silently. They are now either
  narrowed to the specific expected exceptions (so unexpected errors propagate
  instead of being hidden) or kept broad **with a justifying comment and a log
  line** for genuine best-effort steps. Notably, the Zotero/external source-path
  resolver (`_resolve_reference_source`) now logs and degrades to the original
  source on a transient DB lock / IO error instead of failing silently, and the
  windowed PDF parse logs at warning when a page batch fails. The pipeline's
  intentional fault-tolerance (instant-L1 guards, per-page fallback, provider
  failover, checkpoint-resume) is unchanged — no previously-tolerated degradation
  was turned into a hard abort.

### Maintenance
- Added module-level loggers to `config.py`, `parsers/pdf.py`, `llm.py`,
  `ingest_raw.py`, and `pipeline/compile.py` for the above; removed an orphaned
  import. No public CLI / MCP / plugin contract or schema change.

---

## [0.27.4] - 2026-06-27
### Fixed
- **G17-7: Zotero "Reload Source" no longer rewrites a note from empty
  metadata.** A note that has only a `citekey` and no `zotero_app_url` passed the
  citekey where a Zotero item key was expected; the backend queries `items.key`,
  so the lookup returned empty metadata and the note was re-rendered with blanks.
  Reload now aborts with a clear error and leaves the note unchanged when the
  item cannot be resolved. (Full citekey → item-key resolution requires new
  backend support and is deferred.)

### Maintenance
- **G17-12: the deprecated `imageFolder` profile field is retired from stored
  profiles.** A one-time load-time migration normalizes any profile still
  carrying `imageFolder` to `assetFolder`/`assetSubfolder` and deletes
  `imageFolder`, then persists settings. The runtime fallback in
  `resolveProfileAssetSpec` is retained (the migration reuses it).

---

## [0.27.3] - 2026-06-27
### Fixed
- **G17-1: Settings auth polling stops on close/re-render.** The plugin settings
  tab now owns the login auth-poll timer on the tab instance and clears it when
  the tab hides or re-renders, preventing detached-DOM auth badge updates and
  repeated CLI probes after the settings UI is closed.
- **G17-5: Check DeepSeek API Key now checks key configuration.** The command
  palette action now reports a saved plugin key or `DEEPSEEK_API_KEY` instead of
  calling the login helper and always showing setup help.
- **G17-6: Zotero note reload uses the originating import profile.** Imported
  Zotero notes now store `zotero_profile` in frontmatter, and reload uses that
  profile for the template and annotation asset folder instead of always using
  `zoteroProfiles[0]`. The frontmatter stamp now detects the closing `---` by
  line (so a `---` inside a value or body no longer truncates the note, and
  empty rendered frontmatter no longer produces a duplicate fence), handles both
  LF and CRLF line endings (Windows notes are no longer given a duplicate
  frontmatter block), and new profiles are saved under their trimmed name so the
  stamp round-trips.
- **G17-9: Zotero open-link fallbacks preserve later plugin patches.** The
  global `window.open` / Electron `openExternal` fallbacks now restore their
  originals on unload only if Incurator still owns the patched function.
- **G17-11: Plugin `data.json` writes now use a single serialized settings
  writer.** Scroll-position saves, usage accounting, migrations, explicit
  settings saves, and unload now share `persistSettings()` instead of racing
  direct whole-settings `saveData` calls.

### Documentation
- **G18/G19 docs-surface guards.** `PLUGIN_SCHEMA §2.1` now includes the live
  persisted `PluginSettings` fields (`agentEffort`, `ollamaHost`, and the
  `autoSync*` group), Failure Atlas files have a role index, and USER_GUIDE is
  the canonical reference for `curate.yml` and CLI command definitions. Added
  guard tests for MCP/tool docs, plugin settings docs, Failure Atlas indexing,
  `curate.yml` single-sourcing, and CLI-reference links.

### Maintenance
- Removed dead plugin auth helpers from the settings tab and the unused
  `CLIAuthResolver.normalizeExpiry` helper.
- Removed the stale hardcoded model-default denylist; model migration now resets
  unavailable models by checking the live bundled catalogue, while exempting
  non-empty custom Ollama model ids the bundled catalogue cannot enumerate.
- Consolidated duplicate device-registry writers into one async helper so
  backend-command caching and Syncthing registry refresh no longer repeat inline
  synchronous mkdir/write setup.

---

## [0.27.2] - 2026-06-26
### Fixed
- **Large PDF L2 extraction could still use unsafe 60k prompt batches with CLI
  providers.** L2 and graph extraction now accept `optimal_chunk_chars` whether
  a client exposes it as a property or a method, so CLI providers such as
  Antigravity use their conservative chunk budgets instead of silently falling
  back to 60k-character batches.
- **Provider exceptions left `prompt_runs` rows stuck in `pending`.** Prompt
  traces now close as `failed` with the provider exception recorded when the
  initial call or JSON-repair call raises, making capacity/timeouts diagnosable.
- **L2 continued running later batches after a fatal batch error.** The
  top-level L2 loop now fails fast after the first unrecoverable batch, avoiding
  wasted LLM calls and preserving the detailed batch/span/provider error in the
  source and job state.

---

## [0.27.1] - 2026-06-26
### Fixed
- **Large PDF/Markdown L2 extraction could run for hours and then fail with
  `knowledge unit extraction failed`.** L2 knowledge-unit extraction now retries
  a failed validation batch as smaller source-span-preserving batches before
  failing the source. Validated units are held in memory until every batch and
  retry slice succeeds, then written in one transaction with claim supports, so
  a hard failure no longer leaves orphan or unpublished partial L2 rows behind.
  A fresh retry also discards active generation-less units left by older failed
  runs for that source before prompting while preserving retired audit history.

---

## [0.27.0] - 2026-06-26
### Fixed
- **G08-6: LLM client leak in `curator_build_all` / `curator_sync` MCP tools.**
  Both tools now use `with build_client(...) as client:` so the underlying HTTP
  session / CLI process is always released, even when the build or sync raises.
- **G11-8: `wiki lint` cross-layer suggestion emitted `dataclasses.field` instead
  of the field name.** `check_cross_layer_links` used the loop variable `field`
  (the imported function) in `suggestion` and `context["field"]`; fixed to use
  `fm_field` (the string frontmatter key), so lint output and machine consumers
  receive the actual field name (e.g. `concept_ids`).
- **G11-9: `wiki lint --save` wrote reports as invalid L4 synthesis pages.**
  Reports used `type: synthesis` with missing required L4 fields (`id`,
  `community_report_ids`, `source_span_ids`), causing future lint runs to flag
  their own saved reports.  Reports now use `type: lint_report` with a minimal
  header and are written to `.curator/reports/` instead of
  `.curator/Collections/04_Synthesis/`, so the lint inventory never ingests them.
- **G11-10: `wiki lint --deep` mutated atom files without `--fix`.**
  `check_contradictions_deep` wrote `is_flagged_for_agent: true` to both atom
  files on every detected contradiction, even during a read-only audit pass.
  The write-back is now gated on an `apply_flags=False` parameter (default
  read-only); the flag will only be persisted when called from an explicit
  fix/apply command.
- **G14-5: Model change did not persist the spec-required reasoning-effort reset.**
  `syncReasoningControl()` computed the valid effort for the newly selected model
  but only assigned it to the UI control, leaving the persisted setting stale.
  When the normalized value differs from the stored one it is now written back to
  the provider-specific effort setting and `saveSettings()` is called.
- **G15-6: Dashboard Jobs tab stacked polling intervals on re-entry.**
  `renderJobs()` installed a new `setInterval` every time it was called (e.g.
  cancel then re-run, repeated tab switches) without clearing any prior timer.
  An explicit `clearInterval` guard at the start of `renderJobs()` ensures only
  one 2-second poller is ever active.

---

## [0.26.0] - 2026-06-26
### Added
- **Cross-page PDF equation lookup (P1 — plugin).** The quick-query popover now
  resolves equation, figure, section, and theorem references that point to pages
  the user has not yet scrolled to. When the synchronous resolver finds a target
  page whose text is absent from the in-memory window, `resolveSelectionReferencesBlockAsync`
  fetches that page directly from pdf.js via the new `ExternalPdfView.fetchPage()`
  API, upserts it into the BM25 index, and re-resolves — so the LLM receives the
  actual LaTeX/prose regardless of which page is currently displayed.
  `PdfReferenceSource` gains an optional `searchIndex` field so the full
  document BM25 index (all previously-viewed pages, not just the visible window)
  is used for cross-document search.
- **Per-PDF page cache (P2 — backend).** `fetch_document_section` now accepts
  `content_hash` for source lookup (G08-1) and serves PDF page requests from a
  persistent `.cache/pdf_pages/<hash>/<pagenum>.txt` cache.  Cache hits skip PDF
  parsing entirely; misses trigger a bounded `parse_page_window()` call and write
  the result to disk for future sessions.
### Fixed
- **G08-1: `fetch_document_section` hash dispatch.** `db.get_source_row` now
  accepts a `content_hash` parameter and queries `WHERE content_hash = ?` when
  no `source_id` or `relpath` is provided — enabling the plugin to look up a PDF
  by its SHA-256 content hash instead of its vault path.
- **G12-2: `parse_page_window` bounded parse.** `pymupdf4llm.to_markdown` is now
  called with `pages=[n-1 for n in page_nums]` so only the requested pages are
  decoded, avoiding a full-document load for single-page cross-reference lookups.
## [0.25.8] - 2026-06-26
### Fixed
- **G07-1: `wiki config models use` for Ollama.** The command now writes
  `llm.primary = "ollama::<tag>"` (the canonical format read by all code paths)
  instead of the nested `llm.ollama.model` key that is stripped by
  `_migrate_llm_config` on every load — meaning the selection previously had no
  effect.
- **G07-3: `wiki query` no-op flags now warn.** `--mode`, `--lex`, `--vec`,
  `--limit`, `--min-score`, `--no-rerank`, `--scope`, and `--no-intent-classify`
  are not yet wired to the QueryOrchestrator. Passing any of them now prints a
  yellow warning instead of silently accepting a flag that has no effect on
  retrieval.
- **G07-7: `wiki status` is now read-only by default.** The command no longer
  calls `_mark_existing_l3_done_if_present` or `write_runtime_snapshots` on a
  plain diagnostic invocation. Pass `--refresh` to run those side-effects
  (re-marks stale L3 jobs and refreshes the on-disk runtime snapshot cache).
- **G07-8: `wiki lint` is now read-only by default.** The command no longer
  rebuilds the index, overview, ledger, or appends a log entry unless `--fix`,
  `--save`, or the new `--refresh-manifests` flag is passed.
- **G17-6: `deepseekApiKey` no longer persisted in `data.json`.** The key was
  being saved wholesale with all plugin settings, leaking it to Obsidian Sync and
  any git-tracked vault (PLUGIN_SCHEMA §2.4). All `saveData` call sites now route
  through `_persistableSettings()`, which strips `deepseekApiKey` before
  persisting. On load, the key is restored from the `DEEPSEEK_API_KEY` environment
  variable if present.

## [0.25.7] - 2026-06-26
### Fixed
- **G01-1: `remove_source` cascade.** `wiki source rm` now deletes `job_events`,
  `ingest_jobs`, and `dag_edges` referencing the source before removing the source
  row, preventing `sqlite3.IntegrityError` on compiled sources with FK constraints
  active.
- **G03-1: Sources LWW coalesce.** `db_sync` now uses `COALESCE(last_ingested,
  added_at)` as the LWW timestamp for `sources` — both in the SQL `SELECT`/`WHERE`
  clause and in the Python row-dict comparison — so pending sources (where
  `last_ingested IS NULL`) are included in since-filtered exports and resolve LWW
  conflicts correctly.
- **G04-1: Incremental sync DB-hash fast path.** `_find_changed_nodes` now
  compares full-file SHA-256 hashes against the DB page-hash store (via
  `db.get_page_hashes` / `calculate_hash`) instead of reading a `content_hash`
  frontmatter field that was never written, making the incremental sync fast path
  actually functional.
- **G06-1: Dead code removal in `run_query`.** ~230 lines of unreachable legacy
  search/synthesize pipeline (after an unconditional `return`) and their orphaned
  constants, helper function, and test cases were removed from `query.py`.
- **G06-3: `insert_query_trace` preserves `created_at`.** `_append_context_action`
  now passes the original trace `created_at` through to `db.insert_query_trace`,
  preventing the timestamp from being clobbered to `_now_iso()` on every action
  append.

---

## [0.25.6] - 2026-06-26
### Fixed
- **G14-1: Streaming spinner cleared on context-build failure.** `buildLLMMessages`
  is now inside the try/catch block so any failure during context preparation
  correctly clears `assistantMsg.isStreaming`, preventing the spinner from getting
  stuck forever.
- **G14-2: Manual continuation targets correct bubble.** `renderMessage` now stamps
  `data-msg-id` on each message element; `renderAssistantMessage` uses a CSS
  attribute selector to target the correct bubble by ID rather than always selecting
  the last assistant element in the DOM.

---
## [0.25.6] - 2026-06-26
### Fixed
- **chatSidebar streaming never stuck on context-build failure (G14-1).** `buildLLMMessages`
  was called outside the try/catch that clears `isStreaming`; a context-build failure
  (e.g. vault read error) left the assistant bubble permanently spinning. Moved the
  call inside the try block so all failures — context or streaming — go through the
  same catch that resets `isStreaming = false`.
- **Manual continuation renders into correct assistant bubble (G14-2).** `renderAssistantMessage`
  previously selected `querySelectorAll(".ai-agent-chat-msg-assistant")[last]`, so
  clicking "Continue" on an old truncated answer updated the wrong (newest) bubble.
  Fixed by stamping each message element with `data-msg-id` in `renderMessage` and
  looking up by ID first, with last-element fallback for backward compatibility.

---
## [0.25.5] - 2026-06-26
### Security
- **OS sandbox write scope narrowed to active provider only** (`sandboxWrapper.ts`):
  The v0.23.0 sandbox allowed write access to ALL four provider state directories
  (`~/.gemini`, `~/.antigravity`, `~/.claude`, `~/.codex`) regardless of which
  CLI was actually running. Antigravity now only gets `~/.gemini` + `~/.antigravity`,
  Claude CLI gets `~/.claude`, and Codex gets `~/.codex`. A cross-provider agent
  could no longer overwrite another CLI's auth state. When `provider` is not
  specified, the safe fallback grants all four dirs for backward compatibility.
  5 regression tests added.
## [0.25.4] - 2026-06-26
### Fixed
- **`curate.yml` boolean strings no longer invert policy** (`curate_yml.py`):
  Python's `bool("false") == True` caused any quoted boolean in `curate.yml`
  (e.g. `allow_general_knowledge: "false"`) to be read as the opposite of the
  user's intent. A new `_bool_from` helper accepts both Python booleans and
  YAML-style string literals (`"true"/"yes"/"on"`, `"false"/"no"/"off"`).
  Affects: `allow_general_knowledge`, `require_source_spans`,
  `exploration_enabled`, `require_insight_candidates`, `allow_external`,
  `require_rebind_approval`, `backprop.enabled`.
- **Scalar `include` pattern no longer silently drops the filter** (`curate_yml.py`):
  Writing `include: "03_Notes/**"` (a bare string) returned an empty list,
  which the source-matching logic interprets as "include all". Now wrapped in a
  one-item list so the filter is honoured.

## [0.25.3] - 2026-06-26
### Fixed
- **`resolveCredential` exhaustiveness** (`cliAuth.ts`): Added a `default` case
  to the provider switch that throws an explicit error with a `never`-typed guard.
  Without it, an unrecognised provider silently returned `undefined` as the
  credential, causing opaque call-site crashes.
- **`updateSettings` drops its argument** (`main.ts`): `Object.assign` now merges
  `updates` into `this.settings` before the data is saved. Previously every caller
  was saving the unchanged current settings, so settings-panel mutations were
  discarded on navigation.
- **`claude-sonnet-4-6` wrongly in unavailable-model blocklist** (`main.ts`):
  Removed from `unavailableDefaults`; it is a live, valid model ID. Its presence
  caused the plugin to force-reset users whose active model was
  `claude-sonnet-4-6` to the provider's default (Gemini) on every load.

## [0.25.2] - 2026-06-26
### Fixed
- **Stale config path references removed from docs.** All references to the
  retired `~/.config/curator/config.yml` global path and the renamed
  `.curator/config.yml` vault file have been corrected to reflect the actual
  paths used since v0.25.0: vault-scoped settings are in `.curator/settings.yml`
  and machine-local settings are in `.cache/config/config.yml` at the repo root.
- **False auto-processing callout removed from USER_GUIDE.** The `[!IMPORTANT]`
  callout that incorrectly claimed `wiki query` / `search_curator` auto-ingest
  pending sources has been replaced with an accurate note describing the manual
  pipeline (`wiki add` → `wiki build` → `wiki sync` → `wiki query`).
- **CLAUDE.md spec paths made explicit.** The `SEARCH_ENGINE_SCHEMA.md` glob in
  the version-bump instructions now lists its actual subdirectory
  (`docs/specs/search_engine/`) instead of relying on an ambiguous wildcard that
  agents misread as `docs/specs/system_behavior/`.

## [0.25.1] - 2026-06-25
### Fixed
- **Safer source/job recovery.** `wiki source rm` now keeps source files unless
  `--delete-file` is explicit, `wiki source retry` sees layer-scoped failures,
  and `wiki jobs rerun` is idempotent for already queued jobs.
- **Portable PDF/VLM ingest and L2 generation.** VLM markdown strips transient
  `.cache/vision_render` temp links before persistence; generated L2 Atom/KNU
  fields now pass an English-output guard with retry/failure behavior; generated
  CTX projections no longer expose parser-made same-document heading wikilinks.
- **Plugin source/PDF/quick-query stability.** Registered source chips stay
  inert while queued/running, generated vault block links are clickable, quick
  query preserves LaTeX copy data and now supports multiple independent popovers,
  bare PDF equation references like `(19.11)` resolve through local PDF context,
  and Convert-to-LaTeX uses an output-only dedicated transcription path.
- **L4 and PDF viewer clarity.** Completed builds now mark L4 `done`, `skipped`,
  or `error` instead of leaving eligible sources indefinitely `pending`; the
  dashboard renders `Skipped`, and PDF scroll work is coalesced per animation
  frame to reduce long-document jank.

---

## [0.25.0] - 2026-06-23
### Changed
- **Backend ↔ plugin config isolation + rename.** The vault-scoped config file is
  renamed `.curator/config.yml` → `.curator/settings.yml` so it no longer collides
  by name with the per-device backend config `<repo>/.cache/config/config.yml`.
  Rule: per-device backend settings (`llm`, `search`, `external`) and
  `devices.json` live only in the repo's `.cache/config/` (never synced); only
  device-portable, syncable settings live in the vault's `.curator/settings.yml`.
  No backward-compat: existing vaults must re-init or rename their config file.
### Added
- **`wiki status --json`.** Prints the live consolidated `{status, sources, jobs}`
  payload to stdout. The Obsidian dashboard now reads this live output directly
  (one CLI call per render, cached across panels) instead of the on-disk
  `.curator/runtime/*.json` snapshot — so it can never show stale data when a
  backend change forgets to regenerate the snapshot. The snapshot file remains a
  best-effort cache for the lightweight chat status bar only.
### Fixed
- **Dashboard ↔ `wiki status` desync ("Apply reverts after visiting Jobs").**
  `wiki config set --global` wrote `settings.yml` while the loader read
  `config.yml`, so global LLM changes (fallback / PDF-vision / LaTeX-region
  models, set via `config set`) silently reverted while the primary (set via
  `config provider`) stuck. Both `config get/set --global` now use the backend
  global `config.yml`.
- **Dashboard LLM Apply did nothing on fresh vaults.** Apply was gated on a
  successful `.curator/settings.yml` read, but LLM is a machine-local key that
  never lives there — the gate is removed (model-selected is the only precondition).
- **Dashboard changes appeared to revert.** The LLM Apply and Persona Save
  handlers did not refresh the backend snapshot after writing, so re-rendering
  showed the stale pre-save values; both now regenerate + re-read like every other
  mutation handler.
- **Dashboard model-load timer leak.** Closing the dashboard before the model
  catalogue loaded left a 400 ms `setInterval` polling a detached DOM; it is now
  tracked and cleared in `onClose()`.
### Changed
- **Edit-review loop demoted from hard gate to a hint.** A valid `ai-agent-edit`
  proposal now always opens a reviewable diff, even when the model skips the
  `[[PHASE:…]]` review markers. The old gate suppressed the diff entirely on
  token-limited / low-instruction-following models, producing "I made an edit"
  with no diff. Non-conforming answers now show the edit pills plus a soft,
  non-blocking note with an optional **Re-run with review** button; the blocked
  banner and the "Override & review anyway" escape hatch are removed.
### Added
- **Output-token truncation recovery.** Cut-off answers (Gemini `MAX_TOKENS`,
  OpenAI/Ollama `length`, Claude `max_tokens`) are detected via a normalized
  `StreamChunk.finishReason`/`truncated` mapped in every provider adapter, and
  auto-continued up to 3 times. Continuations resume mid-edit-block, are stitched
  with overlap de-dup (no duplicated text, no mangled `ai-agent-edit` fence), and
  the message stays streaming until truncation fully resolves — so edit pills /
  auto-open never fire on an in-flight partial. A manual **↪ Continue** button
  appears if it's still cut off after the cap.
### Fixed
- **Diff Viewer keyboard hijack.** Accept/Reject/navigate shortcuts now fire only
  when the diff editor or its toolbar is focused — pressing Enter in the chat box
  no longer silently applies an open diff. Opening a diff focuses it so the keys
  work immediately.
- **Multi-edit "could not be matched" / "already opening" errors.** Proposals are
  matched against the original file (order-independent), so accepting one edit can
  no longer break another's SEARCH; skipped edits are reported as not-found vs
  overlapping. A same-file re-entrant Review request now coalesces silently
  instead of raising "a diff review is already opening".
- **No more silent open failures.** `DiffViewer.show` returns a typed result and
  callers surface the exact reason (nothing changed / editor not ready).

---

## [0.23.0] - 2026-06-22
### Security
- **CLI provider tool-scope sandbox.** The Quick Query popover and chat sidebar use
  CLI agents (Antigravity `agy`, Claude, Codex) that have their own built-in tools —
  which the v0.19.0 MCP isolation did not govern, so the agent could run scripts,
  create files, and search the whole filesystem (e.g. a hallucinated
  `find_mvg_text.py`). Now `toolPolicy` reaches the CLI command builder:
  - **Popover runs the CLI tool-free** (claude `--tools ""`; codex `--sandbox
    read-only`); the **sidechat scopes tools to the allowed roots** (vault +
    configured Zotero folder + Zotero library) — claude `--disallowedTools`
    (keeping only the DB-scoped Incurator MCP tools), codex `workspace-write` +
    `--add-dir`. The dangerous `agy --dangerously-skip-permissions` /
    trust-workspace bypass is removed.
  - Antigravity's own `--sandbox` is ineffective (it still created files in testing),
    so every CLI subprocess is wrapped in an **OS sandbox** generated from the allowed
    roots — macOS `sandbox-exec` (Seatbelt, deny writes outside the roots; validated
    to contain nested child processes) and Linux `bubblewrap` (`bwrap`). On Linux,
    install `bubblewrap` (`sudo apt install bubblewrap`); without it the agentic CLI
    is blocked with a reminder. Windows CLI sandboxing is not yet supported. Setup is
    automatic — no manual profile configuration. Reads remain allowed (the contained
    harm is file creation / script execution); external user-configured `mcpServers`
    remain the user's own trust boundary.

---

## [0.22.0] - 2026-06-21
### Added
- **Dedicated PDF-extraction vision models (`vision_model` / `latex_extract_model`).**
  PDF text-layer extraction (pymupdf4llm) cannot reliably reconstruct LaTeX for math.
  You can now elect a **vision model**, configured in the **Dashboard → LLM Provider**
  card and decoupled from the main chat model, to read rendered pages. When
  `llm.vision_model` is set, every `add source` PDF page is rendered (PyMuPDF
  `get_pixmap`, bounded DPI + longest-edge cap) and transcribed to Markdown + LaTeX,
  becoming L1 with `parser_used="vlm"`. The pymupdf4llm text is retained per page as
  `parser_text`; a transient per-page VLM failure falls back to it (never aborts).
  A `vision_max_pages_per_run` rail bounds a single run. Cloud vision runs on your
  existing **CLI subscription** (Ollama in-memory, or the `claude`/`agy`/`codex` CLIs
  reading a temp PNG under `.cache/vision_render/` that is always cleaned up) — **no
  provider API keys**. Per-page transcriptions are cached by
  `(rendered-image hash, model)` so a Dashboard model switch invalidates stale L1.
  A second light slot, `llm.latex_extract_model` (empty → falls back to
  `vision_model`), powers interactive region OCR for right-click **Convert to
  LaTeX** and **Cmd+Shift+X** crop transcription. (SYSTEM_BEHAVIOR §26.2a.)

### Fixed
- **Interactive PDF snippets now use the selected PDF extraction model.**
  Right-click **Convert to LaTeX** and **Cmd+Shift+X** route through the backend
  `plugin pdf transcribe` resolver instead of the plugin main chat model. When a
  crop is successfully transcribed, the chat context carries the transcription
  text without forwarding the crop image to the main chat model's vision path.
- **Chat context decay on `Cmd+Shift+L` localized questions.** In long, edit-heavy
  sessions, a freshly referenced line range asked about as a *question* could be
  ignored while the agent proposed a whole-file edit. The root cause was a payload
  self-contradiction: a `Cmd+Shift+L` line range is both a primary-focus selection
  (recency anchor: "answer only, do not modify the document") and an editable range
  (`<editable_selection>` + the `<edit_review_loop>` contract: "you may edit these
  lines"). The plugin now suppresses both edit affordances when the latest turn is a
  localized question (a primary-focus selection present and the turn is not an edit
  request), so the recency anchor is unopposed. The decision is unconditional with
  respect to prior turns — a fresh question after an earlier whole-document edit is
  still honored. Genuine edit requests keep the full edit/diff flow.

### Changed
- **Zotero import profiles are ordered most-recently-used first.** The import
  wizard now auto-loads the most-recently-used profile (not merely the first saved)
  and orders the Import Profile dropdown recent-first via a new optional
  `lastUsedAt` timestamp, stamped when a profile is used for an import or created.
  Profiles never used keep their insertion order; the persisted profile order is
  not mutated by rendering.

---

## [0.20.0] - 2026-06-20
### Fixed
- **`context_expand` token-budget inflation.** Expansion now budgets against the
  *cumulative* pack — the tokens already consumed by the pack's selected items seed
  the budget, so a newly expanded item is admitted only if it fits within
  `limit_tokens` alongside everything already selected. Previously each expansion
  was granted a fresh full budget, so a near-full pack plus an expansion could
  overflow the model context window. Items that no longer fit return as
  `expansion_refused` (increase `limit_tokens` or refetch).
- **Retrieval provenance erased on answer-synthesis failure.** A failed
  `query_local_answer`/`query_global_reduce` validation no longer clears the
  result/trace `source_span_ids` (and sibling provenance arrays); the retrieved
  evidence is preserved exactly as the `explore` route already preserves it, so a
  synthesis failure is no longer misclassified as a recall=0 retrieval failure. The
  answer-cited spans on the `synthesis_status=failed` action remain empty.
- **Token estimate charged literal `"None"`.** A payload whose `detail` is JSON
  `null` is now costed as an empty string (1 token) instead of the 4-char `"None"`.
- Dropped a redundant `curate.yml` re-parse in `QueryOrchestrator.run` — the policy
  hash is now reused from the snapshot `context_fetch` already resolved.

### Changed
- **Explore route unified through `ContextService` (SYSTEM_BEHAVIOR §31.8).** The
  `explore` route no longer runs a divergent associative retrieval pipeline. It now
  grounds on the same `context_fetch` pack path as every other route — producing a
  `PACK-*`/`SNAP-*` snapshot, obeying the shared token budget, and recording ordered
  `CTXA-*` actions under a single `QTR-*` root. The explore-specific behavior
  (follow-up questions + provisional insight candidates) became a synthesis-phase
  consumer of that normalized pack rather than a second retrieval path.
  `explore` is admitted to `_ADMITTED_ROUTES` (not a safe baseline — it can still be
  rolled back to `local` via `INCURATOR_DISABLED_ROUTES`). `curator_fetch_context`
  now returns explore-route grounding for discovery-signal questions instead of
  silently degrading them to `local`.
- Removed the orphaned legacy explore branch in `QueryOrchestrator.run` and its
  dead helpers (`_evidence_json`, `_build_retrieval_trace`, `_question_hash`).

### Notes
- This release closes the RAG-hardening milestone's one genuinely-unimplemented
  systemic gap (explore unification). A grounding audit of the remaining
  `batch_1_to_3_audit` findings confirmed they were already shipped by the Plan A–G
  stabilization (orphaned-support truth state, CJK-safe token estimation, rank-order
  preservation, expansion state machine + budget-exhausted signal, graph
  giant-component `bridge_risk` quarantine + entity-alias resolution, degraded-mode
  eval fixtures) and are pinned by regression tests.
- Verified end-to-end on two testbed scenarios (`complex_math_backprop`,
  `testbed_template`) against a live LLM backend: `add` → `build` → `sync` →
  query (`local`/`global`/`explore`) → Mode B backprop.

## [0.19.0] - 2026-06-20
### Added
- **Shared prompt registry** (`plugin/src/context/promptRegistry.ts`). The chat
  sidebar and the Quick Query popover now assemble their security-critical prompt
  rules from one set of composable blocks (`boundaryConstraints`,
  `buildRecencyAnchor`, `SurfaceProfile`/`SIDECHAT_PROFILE`/`POPOVER_PROFILE`), so
  filesystem/tool boundaries can no longer drift between the two surfaces. The
  popover's "no filesystem access" rule is now sourced from the registry instead
  of a hardcoded duplicate.
- **Recency anchor against long-session context decay.** A `<critical_invariants>`
  block is appended LAST in each request (the strongest-attention position),
  re-asserting "answer only about the current `<primary_focus_selection>`; do not
  edit the whole document unless explicitly asked" — deferring to the existing
  pointer / `<resolved_cross_references>` rule. Fixes the case where a localized
  `Cmd+Shift+L` selection added late in a long chat was ignored and the agent
  reverted to whole-file modification.
### Fixed
- **Quick Query popover is now hard-isolated from MCP tools.** `LLMClient.streamChat`
  gained an optional `{ toolPolicy: "auto" | "none" }`; the popover passes
  `"none"` so `mcpManager.getAllTools()` is never invoked on its path. The popover
  can no longer run scripts (e.g. a hallucinated `find_mvg_text.py`), create
  files, or traverse the filesystem — it answers only from the selected passage
  and current page. The single `shouldInjectMcpTools` helper funnels the
  toolPolicy-none, CLI-provider, and no-MCP-manager cases into one no-tools path
  so they cannot diverge. The chat sidebar's tool behavior is unchanged
  (default `"auto"`).

## [0.18.0] - 2026-06-20
### Added
- Synthesized chat/query answers now cite the **original source documents**
  outside `.curator/` (e.g. `[[04_Resources/Paper]]`), not only the hidden DAG
  node. Each retrieved hit's spans are resolved to their real, visible source
  files via the new forward provenance trace `db.sources_for_spans` (span →
  `source_spans.source_id` → `sources.relpath`), and the synthesis prompt
  instructs the model to cite them. Only the `.md` suffix is stripped, so `.pdf`
  and other source links still resolve.
- `02_Wiki/` promotions (`promote_answer` / `wiki query` "save to wiki" / the MCP
  `promote_answer` tool / CLI `plugin promote`) accept the answer's
  `source_span_ids` and append a deterministic `## Sources` section linking every
  distinct source document behind the answer. Because the promoted note is a
  visible vault file, those sources appear in Obsidian's native Graph view and
  Backlinks pane — the hidden DAG cannot contribute such edges (the c3 hybrid).
  Multi-source syntheses list all contributing papers, not just the first.
- A **💾 Save to 02_Wiki** button in the chat **Sources & Trace** panel promotes the
  current answer to a durable `02_Wiki/` page, passing the trace's
  `source_span_ids` so the page's `## Sources` section (and thus native Graph /
  Backlinks) is populated. Promotion stays an explicit, human-approved action.
### Fixed
- Verified a gap left by RAG stabilization: the search materializer aggregates
  source provenance up to abstraction records (entities, relations, community
  reports, synthesis nodes) via `source_span_ids`, but this was never asserted and
  `_first_source_id` kept only a single source. `db.sources_for_spans` now returns
  every distinct origin in span order, pinned by `test_abstraction_source_trace`
  (including a multi-source synthesis node tracing back to both papers).
- `db.sources_for_spans` now resolves all distinct source relpaths with one
  batched `IN` query instead of one query per source.
- Promoting a historical chat answer now uses that answer's own trace and the
  immediately preceding user question. Older trace panels keep source navigation
  and Save to 02_Wiki available, but hide mutating context-pack actions so they
  cannot affect the active query state.

## [0.17.0] - 2026-06-20
### Fixed
- Curator DAG wikilinks are now clickable. The L1–L4 knowledge DAG lives under
  the hidden `.curator/Collections/` folder, which Obsidian's metadataCache never
  indexes — so curator-layer links such as `[[02_Atoms/ATM-9f8e7d6c]]` previously
  rendered as dead, unresolved links (no click, hover, graph, or backlinks) in the
  chat sidebar, the quick-query popover, and opened DAG pages. The plugin now
  registers a single markdown post-processor that rewrites these rendered links
  into clickable links which open the hidden page via `openLinkText`. The rewrite
  accepts an optional `.curator/Collections/` prefix, an optional `.md` suffix, and
  a `#heading`/`#^block` subpath; marks a missing target with an `is-missing`
  style instead of opening a nonexistent page; and leaves non-curator internal
  links, external links, real-vault embeds, and `[[PHASE:…]]` markers untouched.
### Notes
- Because the DAG stays hidden, curator nodes still do not appear in Obsidian's
  native Graph view or core Backlinks pane; use the chat Sources & Trace panel for
  backlink-style provenance. The backend `[[LAYER/ID]]` link format is unchanged.

## [0.16.1] - 2026-06-20
### Fixed
- Narrowed wikilink target normalization so it strips only the retired curator
  URI schemes (`legacy://` and the pre-v0.3.2 search-binary scheme) instead of
  any `scheme://` prefix. Standard external links (`http://`, `https://`,
  `obsidian://`, `zotero://`) in source paths are now preserved instead of
  having their scheme and authority mangled.

## [0.16.0] - 2026-06-20
### Changed
- Removed legacy external-search-binary runtime/build/status surfaces. The
  backend and MCP status payloads now expose the DB-native `search_*` contract
  only.
- Updated plugin dashboard/status handling to read `search_ready`,
  `search_version`, and related DB-native search fields without legacy fallback
  keys.
- Removed the obsolete benchmark harness and archived parity writeups that still
  invoked the retired external search path.

### Fixed
- Added a guard test that prevents active source, tests, plugin, scripts, specs,
  guides, and agent rules from reintroducing retired search-binary references.

## [0.15.0] - 2026-06-19
### Changed
- **Quick Query popover is now persistent.** Outside clicks and background
  scrolling no longer close or drag the popover away from the user's chosen
  context; close it explicitly with **×** or `Esc`.
- **Quick Query popover can be moved and minimized.** Drag the header to place it
  anywhere in the current window, and collapse it to a header-only state without
  losing the answer, input, or follow-up state.
- **Quick Query title follows the latest question.** The header updates on each
  submit so minimized popovers remain identifiable.

### Fixed
- Fixed old quick-query teardown order so popout-window scroll/resize listeners
  are removed before switching the active document.
- Fixed text-node outside-click handling in the quick-query document listener.

## [0.14.1] - 2026-06-19
### Fixed
- **Diff Viewer — Accept All cursor.** Accepting all changes now leaves the
  cursor at the first changed line instead of teleporting to the bottom of the
  document.
- **Diff Viewer — toolbar anchoring.** When a diff opens off-screen, the editor
  scrolls the first change into view before measuring, so the Accept/Reject
  toolbar anchors next to the change instead of jumping to the top of the screen.
- **Diff Viewer — multi-file review race.** Opening a diff is serialized behind a
  single in-flight guard, so clicking a second proposal pill can no longer
  re-point the singleton Diff Viewer to the wrong file mid-open.
- **Edit-proposal pills show honest, live status.** Each review pill is derived
  from the current file via the shared matcher: **✓ Applied** when the edit
  already appears, or when an empty-replacement deletion has already removed the
  SEARCH text; **⚠ Not found** when neither side matches. Applied/not-found pills
  no longer re-run doomed matches on click, so no "could not find" appears after
  a status pill already reported the state. Self-healing across re-render and
  session reload (no schema change).
- **Path resolution fallback.** `resolveVaultFile` adds a case-insensitive,
  whitespace-trimmed full-path scan, fixing spurious "file not found" on existing
  notes whose path differs only by case without retargeting same-named notes in
  other folders.
- **Agent no longer claims edits are applied.** The edit-loop post-edit phase now
  states edits are *proposed and pending your Accept in the Diff Viewer*; nothing
  is written to disk until you accept.

### Notes
- Triaged against the v0.11.0 Diff Viewer overhaul: navigation scroll and
  premature-disk-write were confirmed already fixed and are now pinned by
  regression tests. Unified-view polish and cross-model output determinism remain
  deferred to the Agent UI/UX & Context Architecture milestone.

## [0.14.0] - 2026-06-19
### Added
- **Enforced & observable sidechat edit-loop state machine.** Edit proposals
  now must walk a visible four-phase loop — **Analysed → Reviewed → Updated →
  Reviewed** — before any change can be accepted. A new composable
  `getEditLoopContract()` system-prompt block (anchored last, at strongest LLM
  attention) instructs the agent to emit canonical `[[PHASE:...]]` markers, and
  is appended for any edit-likely turn: a Markdown edit request, an editable
  selection, an open Markdown edit target, or a multi-turn continuation of an
  edit loop a previous answer already opened.
- **Runtime hard gate (`context/editLoopContract.ts`).** A pure validator parses
  the response; an edit-bearing answer that skips or mis-orders the loop no
  longer auto-opens the Diff Viewer. Instead the chat shows a **"Agent skipped
  the review loop"** banner with **Re-run with loop** (re-prompt) and **Override
  & review anyway** (open the diff regardless) actions. Pure Q&A with no edits is
  never gated.
- **Observable phase UI.** Conforming answers render each phase as a labeled,
  collapsible section (`.ai-agent-edit-phase[data-phase]`), with the inline diff
  review pill anchored inside the **Updated** phase. Phase markers never leak as
  raw text in any render path.

## [0.13.0] - 2026-06-19
### Added
- **Unified Agent ContextService feedback (Plan F P7).** New append-only
  `context_feedback` operation records `FBK-*` events against the exact served
  pack/snapshot with the nine locked feedback types (relevant, irrelevant,
  incorrect, stale, insufficient, duplicate, new_insight, correction,
  promotion_request). Feedback is hard-quarantined: it never edits source files,
  generated records, ranking, or truth state. A `new_insight` event enqueues a
  provisional `pending` insight candidate for human review. Exposed through
  `plugin_api.feedback_context` and the hidden `wiki plugin context feedback`
  command.
- **Sources & Trace feedback UI (Plan F P7).** Each evidence item shows
  relevant/irrelevant controls and a "Report..." menu
  (incorrect/stale/insufficient/duplicate) that records feedback through the
  backend without mutating the pack.
- **ContextService route admission and rollback (Plan F P8).** The service serves
  only Plan-A pack-integrated routes (`local`, `source-section`, `global`).
  `explore` and unknown routes degrade to `local` before retrieval runs; the
  experimental `global` route is independently disableable via
  `INCURATOR_DISABLED_ROUTES` for rollback. The decision is recorded as
  `route_admission` on the response and root trace.

### Changed
- **Sources & Trace locator resolution extracted (Plan F P6).** The pure
  open-target decision moved to `incuratorQueryTraceLocator.ts` with behavioral
  unit tests; the vault PDF locator label no longer repeats the `#page=N` anchor.

## [0.12.0] - 2026-06-19
### Added
- **Unified PDF asset identity resolution (Plan G).** Backend Reference Mode,
  Zotero-backed PDFs, add-source registration, and PDF viewer context now route
  through shared AssetIdentity/AssetSource contracts instead of ad hoc path
  conversion.
- **Device-safe PDF session sync.** Synced chat sessions no longer persist
  macOS/Linux absolute PDF paths or volatile backend path status as durable
  identity; portable identifiers are kept so each device re-resolves local paths.

### Changed
- **External PDF viewer slimmed.** Persistence/registry behavior and capture/RAG
  composition were extracted from `externalPdfView.ts`, with the PDF module LOC
  total reduced below the Plan G baseline.
- **Zotero PDF handling hardened.** Status keys, durable attachment identity,
  cache epoch invalidation, and stale localStorage path replacement now use the
  same resolver model.

### Fixed
- **Reference PDFs open the real file, not the stub.** Locator consumers now
  honor `external_uri` for Reference Mode PDFs while keeping vault stubs as
  portable metadata. Non-PDF local external references now use the desktop system
  opener instead of relying on Chromium `window.open`.
- **Add-source badge state regressions.** Zotero identity no longer depends on
  currently open PDF tabs, and added/building states are covered by contract
  tests.
- **PR review hardening.** Fresh Zotero/current-device path resolution now
  overrides stale DB/layout path hints, Reference Mode stubs no longer mark
  unresolved assets as resolved, Sources & Trace verification updates the
  displayed item, and synthesis output cannot overwrite `source_span_ids` with
  `None`.

---

## [0.11.0] - 2026-06-16
### Fixed
- **Complete overhaul of Diff Viewer UI (resolving 34 known bugs)**:
  - Implemented Inverted Decoration Model (projects diffs virtually without pre-mutating the buffer).
  - Prevented OOM crashes by setting hard limits on the LCS diffing algorithm.
  - Stabilized UI layout (floating toolbar now maintains correct viewport coordinates during scroll).
  - Enforced strict state synchronization (buffer is only modified upon explicit 'Accept').
  - Prevented DOM and event memory leaks via strict singleton enforcement and layout-change listener cleanup.
  - Added robust support for multi-file edit proposals and target-isolated routing.

## [0.10.0] — 2026-06-15

RAG Retrieval Provenance release (Plan A, Program 3). Builds the trusted
retrieval and evidence-selection substrate consumed by the forthcoming Plan F
ContextService. Every retrieval call now carries one authoritative RTR-*
execution ID, bounded and query-relevant evidence, explicit omission counts,
CurationPolicy enforcement, and resolvable structured source locators.
Specs: SCHEMA.md §22, SYSTEM_BEHAVIOR.md §28–§30, SEARCH_ENGINE_SCHEMA.md §12.

### Added

- **Authoritative RTR-\* retrieval execution ID (§30.1).** Each `build_evidence`
  call generates a unique `RTR-<8hex>` ID stamped on the `EvidencePack`, stored
  inside `query_traces.retrieval_trace_json` with `contract_version: "1"` for
  Plan F consumption (§22.4).
- **CurationPolicy forwarded through evidence assembly (§28.1 / F3).** The
  orchestrator now passes the resolved `CurationPolicy` to `build_evidence` on
  both the `fetch_context` and `run` paths, enabling workspace-scoped retrieval
  filtering.
- **Bounded, query-relevant global route (§28.2 / F4).** Community reports are
  scored by query-term overlap and capped at 10 (`_MAX_GLOBAL_REPORTS`);
  synthesis nodes capped at 6. Omitted report counts are recorded in
  `pack.omitted_counts["global_reports"]`.
- **Explicit evidence-block omission marker (§28.3 / F5).** `evidence_block()`
  appends `[N items omitted — character budget reached]` when the character
  budget causes items to be dropped. Previously items were silently truncated.
- **StructuredLocator dataclass (§29.2).** A transport-neutral, in-memory
  locator providing `source_id`, `source_kind` (vault_markdown/vault_pdf/
  external_uri/promoted_wiki), `relpath`, `heading`, `block_id`, `page_number`,
  `toc_id`, `external_uri`, and `locator_status` (exact/fallback_file/
  fallback_source/duplicate_anchor/stale/unavailable).
- **Locator resolution on source-span evidence items (§29.4).** `_span_items()`
  batch-fetches source metadata and resolves a `StructuredLocator` for every
  span-backed `EvidenceItem`. The `source-section` route is refactored to use
  the same path, gaining locators for free.
- **Plan-F handoff contract in `fetch_context` (§30.2).** The response now
  includes `retrieval_execution_id` at the top level, and each evidence item
  carries a serialized `locator` dict for Plan F to consume without re-querying.
- **`EvidencePack` extended fields (§22.3).** Added `retrieval_execution_id`
  (str) and `omitted_counts` (dict) to `EvidencePack`. Added `locator`
  (StructuredLocator | None) to `EvidenceItem`.

### Fixed

- **F3 — CurationPolicy not enforced (§28.1).** `build_evidence` now applies the
  workspace source-scope globs (`source_include`/`source_exclude`) via
  `CurationPolicy.allows_source` with a **strict all-spans rule**: an item is kept
  only when *every* backing span is in scope. Multi-source artifacts (community
  reports, synthesis, entities) are excluded entirely if any backing span is out
  of scope — their text commingles all sources, so partial inclusion would leak
  excluded content and trimming `source_span_ids` would corrupt provenance;
  `source_span_ids` is never mutated. Items dropped by scope are counted in
  `omitted_counts["policy_excluded"]`. (PR #31 review: the policy kwarg had been
  plumbed but the filter was missing; a follow-up review then tightened the
  initial "any-in-scope" rule to strict exclusion to close a private-data leak.
  The F3 oracle is behavioral — it seeds a mixed public+private report and asserts
  it is excluded whole.)
- **F4 — Global evidence query-independent and unbounded (§28.2).** All
  community reports were loaded regardless of query relevance or count.
- **F5 — Evidence block silent truncation (§28.3).** Character-budget cutoffs
  dropped items without any indicator; now always emits an explicit marker, and
  the marker (plus `\n\n` separators) never pushes the block past `max_chars` —
  it replaces the last partial item to fit. (PR #31 review fix.)
- **Locator `promoted_wiki` kind (§29.2).** Sources under `02_Wiki/` now classify
  as `promoted_wiki` instead of `vault_markdown`. (PR #31 review fix.)
- **Retrieval-trace `candidate_count` (§30.2).** `candidate_count` now reports
  `selected_count + omitted total` instead of being hardwired equal to
  `selected_count`. (PR #31 review fix.)

---

## [0.9.0] — 2026-06-15

Graph Quality release (Plan C). The trusted v0.8.0 claim layer compiles into a
reversible, support-aware knowledge graph and deterministic, claim-grounded
community reports — with a read-only graph audit that gates the serving path.
Specs: SCHEMA.md §21, SYSTEM_BEHAVIOR.md §27.

### Added

- **Entity resolution and reversible merges (§27.1).** Similar names are only
  ever *candidates*: synonyms, abbreviations, and translations merge only after
  type/context/contradiction/`avoid_merges` guards pass; ambiguous homonyms stay
  unmerged until an explicit decision. Every accepted merge keeps the origin
  identity (`redirected`) and a complete `entity_resolution_lineage` rewrite
  record, so it reverses to byte-identical pre-merge endpoints. A homonym
  surrogate-key alias model (`ALI-` ids) lets one surface form resolve to many
  distinct entities without collision.
- **Independent claim-level relation support (§27.2).** A relation is a
  proposition; re-asserting it *aggregates* `graph_relation_supports` instead of
  overwriting. Independence is counted by source lineage, so copied/forked
  sources count once. A relation becomes `active` only with **≥2 independent
  source lineages** of verified support — so a single source per topic builds no
  community reports until a second independent source corroborates the same
  relations.
- **Relation lifecycle and quarantine (§27.3).** Every relation carries
  `lifecycle_status ∈ {active, provisional, quarantined, retired}`. Weak edges
  are quarantined with a frozen reason (`unsupported`, `self_loop`,
  `contradiction`, `copied_source_only`, `bridge_risk`, `endpoint_unresolved`)
  and a re-evaluation trigger — never silently dropped or admitted. Purely
  topological cut-edge (bridge) detection gates on structure, not on the
  non-discriminative production confidence (GQ07). Authored vs extracted edge
  classes stay distinct.
- **Deterministic community construction (§27.4).** Filtered connected components
  over `active` relations between canonical entities is the explicit degraded
  fallback; the same `(graph, config, seed)` yields an identical partition, pinned
  by `config_hash`. Seeded weighted Leiden stays a benchmark-gated candidate
  (blocked on labeled relation-quality data; modularity alone is insufficient).
- **Claim-grounded community reports + reconciliation (§27.5/§27.8).**
  `rebuild_graph_generation` compiles the authoritative graph into reports whose
  identity is content/config-derived (`community_key = f(level, member_hash,
  support_hash, config_hash)`); a changed membership/support restructures and
  retires the superseded community before synthesis consumes it. Reports cite
  exact eligible active claim support — the broad whole-community-span fallback is
  removed. An unchanged rebuild is idempotent (no count amplification); a one-source
  edit/delete reconciles only its measured downstream closure.
- **Graph audit + `wiki lint` Graph Quality section (§27.6).** A read-only
  `graph_audit` asserts the §21.8 invariants (no active relation below the
  ≥2-lineage floor, no endpoint that is not a canonical entity, no reference to a
  redirected entity, every quarantined relation carries a reason + re-eval
  trigger, every served report finding cites active support). `wiki lint` gains a
  Graph Quality section that exits non-zero on release-blocking findings.
- **Live claim-grounded cutover.** The L2 compile writes one
  `graph_relation_supports` row per asserting claim, keyed by the source's lineage;
  `wiki build`/`wiki update`'s L3 (`compile_global_l3`) now grounds community
  reports on `rebuild_graph_generation`'s corroborated `active` relations, replacing
  the prior broad-span community path on the serving path.

### Changed

- **Schema v9 (additive, forward-only).** New `entity_aliases`,
  `entity_merge_proposals`, `entity_resolution_lineage`, `graph_relation_supports`
  tables + resolution/lifecycle/identity columns on `graph_entities` /
  `graph_relations` / `community_reports`. The migration infers nothing (legacy
  entities `canonical`, legacy relations `provisional`, zero alias/support rows).
- **MCP/plugin contracts unchanged.** Plan C is CLI-side; agents/plugin clients
  observe it only as better evidence on already-returned records (canonical
  entities, active relations, claim-grounded reports).

## [0.8.1] — 2026-06-15

Hotfix for the PDF crop (`Cmd+Shift+X`) context regression.

### Fixed

- **PDF crop now captures region-scoped text as primary focus.** The previous
  hotfix made the crop image-only with empty text, which caused two regressions:
  the crop image had no `<primary_focus_selection>` anchor and got buried under
  the full-page background context, and the crop's text ("line") extraction was
  lost entirely. The crop now extracts **only the text lines inside the drawn
  rectangle** (via text-layer span ∩ crop-rect intersection, in reading order)
  and uses that region text as the crop's primary focus — never the whole page
  text (the original pollution bug stays fixed) and never empty. Scanned regions
  with no selectable text fall back to an image-only reference.
- **Image-only primary context is no longer buried.** A primary user reference
  that carries an image but no text (a scanned-PDF crop or a dragged image) now
  emits an explicit `<primary_focus_selection>` anchor naming the attached image
  as the core subject, instead of the weak, ignorable "(Image context attached
  below.)" line.

---

## [0.8.0] — 2026-06-14

Evidence Compiler Integrity release (Plan B + Plan B2). Markdown/PDF source
truth compiles into stable, minimal, claim-level grounded L2 knowledge
without formula loss, unsupported broad-span grounding, duplicate
accumulation, stale records, or partial authoritative publishes.

### Added

- **Claim-level minimal support lifecycle (§26.1).** Every extracted claim
  is validated by a deterministic structural gate (verified/failed/uncertain
  trichotomy) against hydrated full span text, with ordered LaTeX
  token-sequence formula matching (direction/binding-preserving, contiguous
  sub-formula aware). Wrong-real-span citations (F6) are release-blocking.
  Evidence freshness re-checks detect stale claim supports. No gold-fixture
  lookup at runtime (overfitting ban).
- **Formula lifecycle and selective recovery (§26.2).** Provider-free
  measured-loss classification (`fragmented|image_only|parser_omitted`),
  additive `source_spans.metadata.formula_recovery` candidates with 0.80
  acceptance threshold + validator-trace + exact-claim-formula gates, and
  page-hash invalidation. Formula-bearing graph input is never destructively
  truncated.
- **Staged compile generations and atomic publish (§26.3, Plan B2).** Every
  compile runs inside a `GEN-` generation. Visibility gated at
  write/materialization time: staged units are never emitted as ATM pages,
  upserted into the graph, or materialized into search. Atomic publish
  wraps reconcile + graph persist + generation flip in a single DB
  transaction. Graph extraction (LLM) runs during staging but persistence
  is deferred to the publish transaction. A failed gate/error discards the
  staged generation with the prior authoritative state byte-untouched.
- **Source edit/delete/split reconciliation (§26.4).** Unchanged claims
  (per `semantic_hash` + exact statement equality) keep their stable ids
  and verified supports. Changed claims are re-extracted. Claims whose
  source basis disappeared are retired. Stale spans are reconciled.
- **Compiler audit surface (§26.5).** `wiki lint` gains a Compiler
  Integrity section reporting unsupported/failed/stale claims, dangling
  supports, formula inconsistencies, staged leftovers, duplicate candidates,
  and broad-fallback findings (Plan-C-assigned). Exits non-zero on
  release-blocking findings.
- **Full-span hydration (F10, SEARCH_ENGINE_SCHEMA §10.2).** Evidence items
  carry `evidence_status='ok'` when hydrated, `'stale'` when falling back
  to the 200-char preview.
- **`list_serving_units` / `list_generation_units` APIs (§26.3).**
  Serving surfaces read only authoritative-generation ∧ verified ∧
  not-retired units. Compiler reads its own staged generation.
- **Legacy NULL-generation backfill.** `init_db` attributes pre-B2 verified
  units to a deterministic synthetic authoritative generation so
  generation-scoped visibility has no permanent NULL escape hatch.

### Changed

- `SCHEMA_VERSION` bumped from 7 → 8 (`claim_supports` table,
  `compiler_generations` table, `knowledge_units` additive columns).
- `db_sync` exports/imports both new canonical tables (`claim_supports` with
  LWW, `compiler_generations` with always-upsert).
- `compile_source_l2` now runs the full copy-on-stage pipeline: stage →
  validate → gate → reconcile + graph persist + publish (atomic txn) →
  re-emit ATM/search from the authoritative served set.
- `materializer` and `reemit_projections` read `list_serving_units`.

### Fixed

- F6 (wrong-real-span citations): release-blocking gate rejects zero-overlap
  span citations.
- F7 (stale span accumulation): reconciliation removes the edited source's
  prior spans instead of lingering beside replacements.
- F10 (truncated evidence): full-span hydration replaces the 200-char
  preview in evidence packs.
- Re-publish publish gate now audits the uncommitted re-validated state
  inside the same transaction (§26.3), so it checks exactly what is about to
  be committed and a re-validation can heal a transiently-dangling support
  instead of being permanently blocked.
- Stale `formula` support rows are cleared on re-validation when the claim
  lost its formula or no longer cites the support's span (§20.5), preventing
  lingering/dangling formula links; valid recovery links are preserved.

---

## [0.7.0] — 2026-06-12

Program 1 D2 quality-observatory release.

### Added

- Fine-grained provider-free retrieval evaluation with per-family Recall@k,
  MRR, citation correctness/completeness, authoritative provenance resolution,
  hard-negative outranks, indexed-character cost, and latency.
- Query-level minimal-support labels and an auditable D2 Q06 holdout result.
- Final Program 2/3 Failure Atlas handoff contracts.
- A tracked current-architecture testbed scenario gate covering CTX/ATM/CON/SYN,
  DB-native retrieval, query traceability, and unchanged-update correctness.

### Fixed

- Search-hit `source_span_ids` now survive the public search adapter and
  evidence assembly, including global search fallback.
- Orchestrated queries persist one authoritative `QTR-` containing the engine
  retrieval trace instead of a disconnected second trace.

---

## [0.6.1] — 2026-06-12

Hotfix release. No schema or API changes.

### Fixed

- **SQLite connection leak in `db.init_db`** (`backend/src/curator/db.py`).
  `init_db()` used `with sqlite3.connect(...)`, but Python's sqlite3 context
  manager only commits/rolls back the transaction — it never closes the
  connection. The leaked connection kept the `state.sqlite-wal` /
  `state.sqlite-shm` sidecar files alive until garbage collection, which is
  timing-dependent across platforms and caused environment-dependent
  `sqlite3.OperationalError: database is locked` failures on Ubuntu 24.04
  (observed in `wiki status` bootstrap paths and the corresponding test).
  `init_db()` now closes its connection explicitly in a `finally` block, so
  no WAL sidecars outlive the call.
- **Same leak class in `db.connect()` on the setup-failure path** (review
  follow-up). `connect()` ran `executescript(SCHEMA_SQL)` and
  `_apply_migrations()` *before* its `try`/`finally`, so an exception during
  schema setup or migration leaked the connection and its WAL sidecars
  exactly like the `init_db` bug. All post-instantiation work now runs inside
  the `try` block. Regression test holds a reference to the connection and
  asserts it is closed (GC-independent) with no surviving sidecars.
- **Unbound `conn` in Zotero readers' error paths.** One site in `zotero.py`
  and both sites in `zotero_integration.py` referenced `conn` in `finally`
  without initializing it before `try`; if `sqlite3.connect()` itself raised,
  the cleanup raised `UnboundLocalError` and masked the original error. All
  sites now initialize `conn = None` first, matching the existing pattern in
  the other `zotero.py` readers. With these, every production
  `sqlite3.connect` call site is leak-safe on both success and failure paths.

---

## [0.6.0] — 2026-06-12

Program 1 (RAG & Knowledge Quality Stabilization) — Plan D1 diagnostic
baseline release. **No runtime behavior, schema, or API changes**: this
release freezes the truth contract that Programs 2/3 will be measured
against.

### Added

- **Failure Atlas diagnostic contract** (`docs/specs/failure_atlas/`).
  Versioned machine-readable case records for all thirteen suspected
  end-to-end quality failures (F1–F13), each with exact code boundary,
  minimal deterministic fixture, capture-before-repair evidence, frozen
  oracle, status lifecycle (`suspected → reproduced → assigned/accepted |
  disproven`), and downstream owner (Plan D2, Program 2, or Program 3). All
  thirteen were reproduced deterministically and assigned.
- **Deterministic reproduction suite**
  (`backend/tests/test_failure_atlas_repro.py`). Baseline tests pin the
  current defective behavior; strict-xfail oracle tests encode the desired
  contract and intentionally fail CI (XPASS) when a failure is fixed without
  updating the atlas — the mechanical anti-silent-redefinition handoff.
- **Atlas contract tests** (`backend/tests/test_failure_atlas_contract.py`)
  rejecting missing snapshot identities, missing oracles, aggregate-only
  reporting, unsupported status transitions, and dangling fixture references.
- **Mutation/degradation/atomicity experiments**
  (`backend/tests/test_failure_atlas_experiments.py`): unchanged-rebuild
  idempotency at L1/search, rename-duplication, failed-batch partial graph
  state, and provider-free lexical degradation evidence.
- **Frozen evaluation baseline** (`fixture_corpus.yml`, `qrels.yml`,
  `EVALUATION_BASELINE.md`, `backend/tests/test_failure_atlas_eval.py`):
  synthetic corpus with dev/regression/holdout/adversarial partitions,
  deterministic lexical baseline metrics (binding regression floor:
  Recall@1 = 1.0, 0 hard-negative outranks), and a runner-enforced
  no-holdout-tuning rule. Proposed Program 1/2/3 thresholds recorded,
  pending user approval.
- **Docs**: `SYSTEM_BEHAVIOR.md` §25 (Failure Atlas diagnostic contract) and
  `AGENT_WORKFLOW_GUIDE(_KR).md` §5 (running the diagnostic suite; rules when
  a change touches an atlas case).

---

## [0.5.6] — 2026-06-12

### Added

- **PDF add-source asset routing (`--asset-dir`).** Images extracted from an
  added PDF during instant L1 no longer always land in the hardcoded
  `05_Assets/<slug>/`. `wiki plugin source register` accepts a vault-relative
  `--asset-dir`; the plugin resolves it per source — Zotero-backed PDFs reuse
  the Zotero import profile's asset folder (plus a per-item subfolder from the
  item's display name), other PDFs use a sanitized source-name subfolder under
  the new `incuratorPdfAssetFolder` base folder. Unsafe values (absolute paths,
  `..` escapes, or path-resolution errors) and an empty setting fall back to
  the legacy `05_Assets/<slug>/`, and the L1 page's `![[...]]` embeds always
  reference the folder actually written (PLUGIN_SCHEMA §1.1).
- **Inert "Added" badge for tracked sources.** A successfully built source
  (`l1_ready` … `l4_ready`) now shows a single non-clickable **Added** badge in
  the chat context chip instead of clickable layer labels, so an
  already-tracked PDF can no longer be re-imported by accident. The tooltip
  still exposes the underlying layer state, and a refresh that re-derives
  `stale`/`moved`/`changed`/`missing`/`error` makes the badge actionable again
  (PLUGIN_SCHEMA §4.1.1).

### Fixed

- **PDF viewer-to-L1 adaptive routing.** Passive PDF chat no longer registers an
  untracked source. Local PDF.js text/crops remain the fast path; after an
  explicit Add Source completes L1, durable CTX ToC/section projection becomes
  available without reparsing the original PDF. Missing or preview-only CTX
  projections visibly degrade to read-only parsing, and PDF-focused turns do
  not use concept-grounded `curator_query` until the relevant source reaches L3.

### Documentation

- Documented what add-source actually does (instant L1 immediately, L2/L3
  queued to the background worker) and where extracted PDF figures land, in
  `PLUGIN_GUIDE` (EN/KR). PDF math-extraction fidelity is explicitly out of
  scope here and tracked by the RAG & Knowledge Quality Stabilization program.
- Reconciled the documentation authority and workflow contracts with the
  implementation: `state.sqlite` is authoritative, Collections Markdown is a
  disposable projection, queries are sessionless, CLI `wiki add` stops at L1
  while plugin Add Source queues L2/L3, PDF.js remains the viewer fast path,
  and correction proposals classify without silently patching generated nodes.
  Also repaired internal documentation links and advanced the spec-sync guard
  to v0.5.6.

---

## [0.5.5] — 2026-06-11

### Fixed

- **LaTeX-copy review fixes (PR #22):** an escaped backtick (`\``) no longer makes
  the math-source parser mistake it for an inline-code opener (which could drop a
  later formula); the chat/quick-query copy handler reads the element's own
  document selection (`el.ownerDocument`) so it works in Obsidian pop-out windows;
  and the reading-view math post-processor extracts section source by line index
  instead of splitting the whole document on every render (large-note perf).
- **Zotero reload emitted absolute cache image paths.** "Reload Source"
  (`Cmd+Shift+R`, formerly "Refresh Zotero Item") read the deprecated `imageFolder`
  profile field, which was empty after the wizard migrated to
  `assetFolder`/`assetSubfolder`, so it skipped localization and wrote
  `![[/Users/.../Zotero/cache/...]]` instead of vault-relative `![[05_Assets/...]]`.
  Reload and import now share one localization path (`src/zotero/assetLocalization`).
- **Changed annotation regions did not refresh.** Localization skipped any asset
  that already existed; it now overwrites an asset whose source region bytes
  changed (and only then), so edited annotations update.
- **`zotero_app_url` PDF open failed with "attachment key not found".** That URL
  carries the **parent item** key; backend `resolve-pdf` now resolves it to the
  item's child PDF attachment and returns the effective `attachment_key`.
- **Zotero annotation links did not jump to the annotation.** The plugin now uses
  the resolved child attachment key for annotation lookups, so a parent/select link
  can open the PDF *and* navigate to + highlight the annotation.
- **`Cmd+Shift+R` reloads the active Zotero note OR external PDF view**, via the
  same code path as the PDF viewer's toolbar Reload button.
- **Dashboard showed a stale backend version / provider.** The dashboard read a
  cached `runtime/status.json` first; it now forces a fresh `wiki status` snapshot
  (deduped per render burst) and reports the backend as *unavailable* instead of
  trusting a stale snapshot when `wiki status` fails. A backend upgrade or
  `wiki config provider` change is reflected on the next dashboard open/refresh
  without restarting Obsidian.
- **External PDF view lost its document after restart** (`resolveDoc failed: no
  path in docState or cache for ID`). The persisted-doc cache no longer drops a
  path-bearing entry at load (startup `existsSync` race), `setState` keeps the doc
  identity even when a restored state lacks a name, and `getState` always persists
  the path — so a reopened/restored PDF resolves the same document; a genuinely
  missing file is reported distinctly at use time.

---

## [0.5.4] — 2026-06-11

### Added

- **LaTeX-preserving copy from the AI chat (copy as Markdown).** Selecting part of
  an assistant reply and pressing `Cmd/Ctrl+C` now copies it as Markdown with
  formatting *and* the formulas' LaTeX **source** (`$...$` / `$$...$$`) restored,
  instead of the browser's flattened plain text / empty MathJax SVG.
- **LaTeX-preserving copy/cut from a note's Reading View.** Drag-selecting note
  text that contains a formula and pressing `Cmd/Ctrl+C` (or `Cmd/Ctrl+X`) copies
  the selection as Markdown with the LaTeX source restored. Works in pop-out
  windows. The selection visually skipping a non-selectable formula is expected —
  the formula is still captured.
  - Implemented via a Markdown post-processor that re-parses each rendered
    section's source and stamps it onto every formula as `data-tex` (only when the
    parsed and rendered formula counts match exactly, so a wrong source is never
    attached), plus a capture-phase clipboard handler gated to
    `.markdown-reading-view` + rendered math.
  - Non-math selections are left to Obsidian's native clipboard (byte-identical).
    Live Preview / Source mode already preserve `$...$` natively (CodeMirror copies
    the document source), so they are unchanged.

### Docs

- `PLUGIN_GUIDE` (EN + KR) §3.6/§3.7 and `PLUGIN_SCHEMA` §14 document the chat and
  Reading-View LaTeX copy behavior, the render-time stamping mechanism, and the
  exact-count correctness guard.

---

## [0.5.3] — 2026-06-11

### Removed

- **GitHub CLI (`gh`) dependency** — Incurator no longer requires or installs
  `gh`. `setup.sh` no longer installs it; the plugin's GitHub Sign-in/out
  settings toggle, the `github_authenticated`/`github_account` status fields, and
  `auth/githubAuth.ts` are removed; the backend `git_manager` no longer shells
  out to `gh auth status`. None of the core Git features needed it — `status`,
  `log`, file `history`, `commit`, and `push` all use the local `git` binary.

### Changed

- **Sidechat Git integration is local-only.** Asking "how did I write this
  before?" / history & status / push continue to work via local `git` with no
  GitHub account. HTTPS-push authentication, if you use it, is handled by your
  normal git credential helper, outside the plugin (commit/push can also stay
  with whatever tool you already use).

---

## [0.5.2] — 2026-06-11

### Fixed

- **Plugin no longer falls back to a stale `backend/.venv`** — `resolveWikiBinary`
  used to probe `<repo>/backend/.venv/bin/wiki` as a fallback after the canonical
  `<repo>/.venv/bin/wiki`. Because `backend/.venv` is never created by the
  supported workflow, when present it is stale, and running it silently executed
  an out-of-date backend (wrong version, missing fixes) without the user
  noticing. The resolver now probes ONLY the repo-root `.venv` and returns
  nothing if it is absent, so the user is prompted to re-run `./setup.sh` instead
  of unknowingly running an old build.

## [0.5.1] — 2026-06-11

### Fixed

- **Ask AI dropped formulas when selecting over math** — the quick-query popover
  captured the selection via `selection.toString()`, which is empty for a
  MathJax formula rendered as SVG, so dragging across a formula lost it. Capture
  now reads the formula's LaTeX source from the DOM annotation (present in both
  the SVG and the Live-Preview swapped-text state), preserving `$...$` / `$$...$$`
  — independent of render timing. Non-math selections are unchanged.

### Added

- **Keyboard selections trigger Ask AI** — selecting text with the keyboard
  (Shift+Arrow, Shift+Home/End, or Ctrl/Cmd+A) now surfaces the floating
  **✨ Ask AI** button, not just a mouse drag. Collapsing the selection back to a
  caret hides it.

> Note: copying only a partial editor selection with LaTeX intact (Cmd+C in an
> open note) remains deferred — see the ROADMAP Icebox.

---

## [0.5.0] — 2026-06-11

### Changed

- **Resilient, ambiguity-safe agent-edit matching** — `ai-agent-edit` SEARCH
  blocks no longer need to match the file byte-for-byte. A single shared matcher
  (`utils/editMatch.findSearchBlock`, used by every apply and preview path) tries
  `exact → line-trim → anchored`, tolerating leading/trailing whitespace and
  indentation-level drift, and always splices the file's real text. It refuses
  (returns null → "could not find") when ≥2 spans are plausible or an anchored
  span balloons past 3× the search size, so it never applies a guessed edit. This
  fixes the frequent "Could not find the exact SEARCH block" failures where no
  diff rendered at all.
- **Immediate diff (safe-gated)** — when an answer's edits target the note you're
  already viewing (or no note is focused), the in-editor Diff Viewer now opens
  automatically instead of waiting for a "Review Diff" click. A different focused
  note keeps the clickable pill so the diff never steals your editor; auto-open
  fires once per message and never on history re-render.
- **Diff Viewer hunk counter is always visible** (e.g. `1/1`), with ↑/↓ · Tab
  navigation and Y/N/Enter/Esc shortcuts for multi-hunk diffs (unchanged).
- **Scoped edits** — the edit prompt now requires minimal, section-scoped REPLACE
  bodies (never pasting a whole chat answer), plus a non-blocking "large
  replacement" warning as a model-independent safety net.

### Fixed

- **Leaked edit markers** — orphan `<<<<` / `====` / `>>>>` markers from a
  malformed/partial edit block are stripped from the rendered message (fence-aware,
  evidence-gated). Stored message content is untouched, so "Copy as Markdown"
  stays faithful. The block parser also tolerates marker spacing/length variants
  and a missing closer.

### Removed

- **On-disk diff artifact** — the `00_System/Agent Diffs/` note feature and its
  **Write edits as diff artifact** setting were removed; the in-editor Diff Viewer
  is now the single source of truth. Existing artifact files in your vault are
  left untouched.

---

## [0.4.4] — 2026-06-11

### Fixed

- **Plugin resolved a stale `wiki` binary** — `resolveWikiBinary` probed
  `<repo>/backend/.venv/bin/wiki` *before* the canonical repo-root
  `<repo>/.venv/bin/wiki`. Because `setup.sh` installs the live backend into the
  root `.venv` (`VIRTUAL_ENV="$ROOT_DIR/.venv"` + `uv pip install -e ./backend`),
  the leftover `backend/.venv` copy was frequently stale, so the plugin reported
  an old backend version (e.g. `0.4.2`/`0.3.2`) and silently broke the self-update
  toast. The probe now prefers the root `.venv` and keeps `backend/.venv` only as
  a fallback for un-migrated checkouts. Completes the install-path hotfix started
  in the previous commit.
- **Backend dashboard misreported the active model** — the LLM selector fell back
  to the first catalogue entry (Antigravity Gemini) whenever the configured model
  was not in the bundled catalogue (e.g. a custom local Ollama model like
  `qwen2.5:3b`), so the dashboard always showed Antigravity Gemini even though the
  backend config (`wiki status`) was correct. The unmatched model is now surfaced
  as its own "(current)" option and selected, keeping the display faithful to the
  persisted config.
- **Docs path scrub** — removed an absolute `file:///Users/...` link from
  `SYSTEM_BEHAVIOR.md` (now relative) and genericized real vault-name examples
  (`second_brain`, `/Users/<you>/...`) to `/path/to/<vault>/...` in the dev/sync
  guides. Updated `DEV_SCRIPTS_GUIDE` to match `plugin/deploy.sh`'s new local-build
  fallback when `OBSIDIAN_PLUGIN_DIR` is unset.

---

## [0.4.3] — 2026-06-07

### Fixed

- **Chat sidebar LaTeX selection** — Shift+click could not extend a text selection
  across rendered MathJax formulas because SVG elements block mouse events by
  browser default. Added `pointer-events: none` and `user-select: text` on
  `.ai-agent-chat-msg-content mjx-container` and its SVG child so that the mouse
  event passes through to the surrounding text layer, letting selection span
  formulas. The existing `copy` event interceptor then extracts LaTeX source from
  `annotation[encoding="application/x-tex"]` as before.

---

## [0.4.2] — 2026-06-07

### Added

- **LaTeX copy preservation** — selecting rendered math in the agent chat sidebar
  or quick query popover and pressing Ctrl+C now copies `$...$` / `$$...$$` LaTeX
  source instead of empty SVG content. Implemented via a `copy` event interceptor
  that extracts the source from MathJax v3 `annotation[encoding="application/x-tex"]`.
- **PDF → LaTeX conversion** — right-click "Convert to LaTeX (Copy)" (or
  Cmd+Shift+C) in the PDF viewer sends selected text to the LLM, which returns
  clean Markdown with proper LaTeX delimiters. Result is copied to clipboard.
  Shortcut registered on `ownerDocument` via `registerDomEvent` for correct
  event bubbling and automatic cleanup.

### Fixed

- **CI TypeScript check** — `buildManifest.json` is gitignored so it was absent
  in CI after checkout. Plugin-tests job now generates a minimal stub before
  `tsc --noEmit` and `vitest run`.
- **CI pytest** — `test_plugin_version_returns_build_fields` was asserting stale
  `*_fingerprint` fields removed in v0.4.1. Updated to match current schema.
- **setup.sh plugin deploy** — after building, setup.sh now reads `last_root`
  from `.cache/config/last_root` and copies `main.js`, `manifest.json`,
  `styles.css` directly to the vault's plugin directory. Removes the need for
  `OBSIDIAN_PLUGIN_DIR` or a `.env` file.

---

## [0.4.1] — 2026-06-07

### Added

- **Vault schema migration** (`wiki migrate`) — explicit upgrade path for vaults
  after a backend update changes config or Collections structure. Tracks
  `VAULT_SCHEMA_VERSION`; `wiki status` warns when a vault is behind. `wiki migrate`
  applies pending steps, scans `Collections/*.md` for files missing required
  frontmatter fields, and `--requeue` re-queues their sources for regeneration.
  `--dry-run` previews without writing. `wiki init` stamps new vaults with the
  current schema version.
- **Plugin repo-path auto-discovery** — the backend now reports its own repo root
  via `wiki plugin version` (`repo_path`), so the Obsidian plugin no longer needs
  a manually configured "Repository path". The setting becomes an optional
  override. Non-editable (site-packages) installs report `repo_path: null` and the
  plugin hides the update banner instead of showing a dead button. The 1-click
  update copies built plugin files into the currently open vault only.

### Fixed

- **Machine-local config isolation** (`config.py`) — `llm`, `search`, and
  `external` blocks are no longer stored in the synced vault `.curator/config.yml`.
  `load_config()` automatically migrates any existing machine-local blocks into
  `.cache/config/config.yml` (global cache) and rewrites the vault config without
  them. `zotero_init()` saves Zotero roots to the global cache instead of the
  vault config, so ZotMoov/data-directory paths never leak into synced state.
- **Portable Zotero source identity** (`runtime_state.py`) — `build_sources_snapshot()`
  now returns `zotero://open-pdf/library/items/<attachmentKey>` as `source_path`
  for Zotero-backed references (where `logical_source_id` starts with `zotero:`).
  The absolute local PDF path is preserved as `external_path` (device-local hint)
  and is no longer surfaced as the portable display identifier.
- **Plugin dashboard always refreshes local snapshots** (`incuratorDashboardModal.ts`) —
  Added `readFreshRuntimeJson()` which always triggers a local backend refresh
  before reading. Sources tab now uses it so the dashboard never renders a peer
  device's stale snapshot. `wiki config set llm.fallback` no longer passes
  `--local` (vault scope); LLM fallback is now written to the machine-local
  global config, consistent with how all `llm` config is handled.

---

## [0.4.0] — 2026-06-06

### Added

- **Cross-device Knowledge Sync Bridge** (`wiki db export / wiki db import`)
  - Export the knowledge DB to a portable JSONL file (`wiki db export`)
  - Import a JSONL file into another device's DB with Last-Write-Wins merge (`wiki db import`)
  - `--dry-run` option to preview changes before writing
  - `--compress` option for gzip output (`.jsonl.gz`)
  - `--since <datetime>` for incremental (delta) exports
  - Post-import automatic `wiki reindex` (skippable with `--skip-reindex`)
  - Device-local tables (embeddings, job state, FTS5 indices) are automatically excluded from exports
- **Tombstone table** (`deleted_records`) — deleted records propagate to other devices on next import
- `db_sync.record_tombstone()` helper for future delete operations to call
- **Syncthing auto-sync (Zotero-grade, one-writer-per-file)** (`wiki db autosync`)
  - Each device writes only its own `.curator/sync/dev-<id>.jsonl` snapshot and imports
    every peer's — no Syncthing write-write conflicts by construction
  - Row-level Last-Write-Wins + tombstones: concurrent offline edits on two devices both
    survive (no whole-file overwrite)
  - Structural loop prevention with **no content-hash guard**: own file never imported,
    re-export only when the local DB actually changed
  - Syncthing `*.sync-conflict-*` files imported as LWW peers, then archived under
    `.curator/runtime/sync_conflicts/`
  - Reference-Mode `sources.external_path` preserved per device on merge
    (`_DEVICE_LOCAL_COLUMNS`)
  - Device-local `.curator/sync_state.json` (excluded via `.stignore`) tracks device id +
    per-peer high-water marks
  - Obsidian plugin: on-load sync, `.curator/sync` file watcher (desktop) + 60s poll
    fallback, manual "Sync Knowledge DB" ribbon, status-bar indicator, four default-on
    settings toggles
  - Optional `auto_sync.enabled` so CLI `wiki update` exports this device's snapshot

### Changed

- `SCHEMA_VERSION` bumped from 6 → 7 (non-destructive; adds `deleted_records` table only)
- Existing vaults self-heal on next `wiki` invocation

### Fixed

- `wiki db import` reported `0 changes` after any prior export — caused by a
  `sync_meta.json` content-hash loop guard, now removed in favor of structural
  loop prevention (dry-run and real import report/apply the identical delta)

### Documentation

- `docs/guides/USER_GUIDE.md` + `USER_GUIDE_KR.md`: "Cross-Device Knowledge Sync" +
  `wiki db autosync` section
- `docs/guides/PLUGIN_GUIDE.md` + `_KR.md`: plugin auto-sync settings/triggers
- `docs/guides/SYNC_IGNORE_GUIDE.md` + `_KR.md`: `sync_state.json` exclusion;
  keep `.curator/sync/` synced
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`: §13.1 one-writer-per-file auto-sync;
  §13.3 device-local sync state
- `docs/specs/curator_schema/SCHEMA.md`: §11.17 `deleted_records` contract +
  `_DEVICE_LOCAL_COLUMNS`

---

## [0.3.3] — 2026-06-06

Initial release on `master` branch. Baseline for the v0.4.x series.
