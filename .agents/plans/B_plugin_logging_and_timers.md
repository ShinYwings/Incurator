# Domain Analysis: Plugin Logging & Timer Lifecycle (XC-4) + model_setup errors (XC-1)

Date: 2026-06-28

## Constraints from the codebase
- Plugin has **no logger util** (grep confirms) → create `src/utils/logger.ts`.
- Obsidian provides `Component.registerInterval(id)` (auto-cleared on unload) and
  `registerDomEvent`; 25 cleanup calls already exist — the audit fills gaps only.
- `model_setup.py` steps return `ModelStep(ok, msg)` — failures already surface
  through the structured result, so most excepts are KEEP+log or NARROW-then-
  return-ModelStep.

## docs/specs invariants
- No schema/contract change. `localStorage["incurator-debug"]` is a dev-only
  affordance, not a documented setting — but PLUGIN_GUIDE should gain a short
  "Debug logging" note (docs mandate), and PLUGIN_SCHEMA a one-line mention that
  verbose logs are gated (no `PluginSettings` field added).

## Logger contract (locked)
- `logger.debug/info` → gated by `localStorage["incurator-debug"]==="1"` (captured
  at module load; toggling needs reload — documented in a code comment).
- `logger.warn/error` → always emit, prefixed `[Incurator]`.
- Conversion map: `console.log/debug`→`logger.debug`; `console.info`→`logger.info`;
  `console.warn`→`logger.warn`; `console.error`→`logger.error`. `*.test.ts`
  excluded.

## Timer disposition (locked) — applied to all 39
| disposition | when | action |
|---|---|---|
| managed — no change | already `registerInterval` / cleared in teardown | record only |
| convert | unmanaged `setInterval` | wrap in `registerInterval` or clear in `onunload`/`onClose` |
| guard | `setTimeout` callback touches DOM/state post-teardown | store handle, `clearTimeout` on teardown + disposed-state guard |
| race-fix | callback assumes a prior async step done | fix ordering; capture as a finding if non-trivial |

## model_setup.py inventory (filled at fix-time → evidence ledger)
11 sites (87, 107, 130, 156, 199, 222, 264, 302, 319, 377, 391). Expected:
NARROW `(OSError, subprocess.SubprocessError)` for subprocess launches;
NARROW `httpx.HTTPError` for reachability; KEEP+log where the surface is
heterogeneous. Complete the raisable set per body (slice-1 lesson:
AttributeError/IndexError on parsed data; RuntimeError on closed clients).

## Alternatives rejected
- *New "Debug logging" plugin setting*: rejected — would make this a Minor +
  contract change; the localStorage flag is sufficient for a dev affordance.
- *Blanket gate all console including errors*: rejected (R1) — error/warn must
  stay visible for field triage.
