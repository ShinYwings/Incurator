# Defense: F1 and F4 measured — one is dismissed, one rewrites the design

Date: 2026-08-20 | Agent Persona: lead_architect (responding), with schema_guardian

The red_teamer refused to accept "it does I/O, moving on" and demanded numbers.
Both demands were right, and they resolved in opposite directions.

## 1. F1 — probe cost, by outcome

200 iterations each, real paths on this machine:

| outcome | `probe()` | `os.path.exists()` | ratio |
|---|---|---|---|
| OK | 0.016 ms | 0.002 ms | 8× |
| **DENIED** | **0.722 ms** | 0.002 ms | **360×** |
| MISSING | 0.001 ms | 0.001 ms | 1× |

The red_teamer's instinct was correct: **the denial is the expensive one**, and
by two orders of magnitude. A TCC refusal is not a cheap `EACCES`.

## 2. …and the candidate list that multiplies it

Measured on the real vault:

```
zotero_root_candidates -> 2
    /Users/shin/Zotero
    /Users/shin/Library/Mobile Documents/…/Zotero
```

**Two.** Not a growing list. So the worst realistic case per source is one denied
probe: 0.7 ms. Across 44 sources that is **31 ms once**.

**F1 is upheld as an objection and dismissed as a blocker.** The cost is real and
the ratio is alarming in isolation, but the absolute number is a rounding error
beside an ingest that spends seconds per LLM call. The measurement is what
converts "this does I/O, be careful" into a decision.

**F2's memo is therefore NOT required.** It would save 30 ms and add
process-lifetime state that has to be reasoned about when a user grants access
and restarts. Dropped — with the number recorded, so a future reader can see it
was weighed rather than forgotten. If the candidate list ever grows (a user
configuring many roots), this is where to look.

## 3. F4 — the grant root, and this one changes the design

The proposal wanted `_grant_root` to match a hardcoded table of macOS locations.
The red_teamer said derive it by probing. Measured, walking up from the denied
file:

```
DENIED    …/CloudDocs/Zotero/[Project] COLMAPFreeReconstruction/Major
DENIED    …/CloudDocs/Zotero/[Project] COLMAPFreeReconstruction
DENIED    …/CloudDocs/Zotero
DENIED    …/com~apple~CloudDocs
DENIED    ~/Library/Mobile Documents
readable  ~/Library
```

The shallowest denied ancestor is `~/Library/Mobile Documents` — exactly the
folder a user grants — and it falls out of probing with no table at all.

**F4 is upheld and adopted.** The hardcoded list is deleted from the design. It
would have been wrong in both directions: it cannot know a location Apple adds,
and it would have named `~/Library/CloudStorage` as needing a grant when this
machine reads it fine, sending a Dropbox user into System Settings for nothing.

Note the cost: this walk is ~6 more probes, and by §1 each denied one is 0.7 ms.
It runs **only on the denial path**, once, when we are already reporting an
error — about 4 ms to turn "denied" into "grant this folder".

## 4. Conceded without argument

- **F3** — do not let `PermissionError` escape `parsers.parse`. The typed
  boundary is deliberate and every existing caller catches `ParserError`. A
  `ParserAccessDenied(ParserError)` subclass keeps them working and lets new code
  be specific. The proposal's bare `raise` was wrong.
- **F5** — the selection-order change gets a test. Two candidates, first denied
  and second readable: resolution must not silently repoint the source at a
  different file with the same name in another root. Quietly changing what a
  source *is* would be worse than either failure mode.
- **F6** — the plugin is out of scope for this release and the plan says so in
  its Non-Goals, rather than leaving a reader to discover that
  `ExternalPdfView.ts:1385` still throws a raw Node error.

## 5. Residual risk

Everything here is measured on **one machine, one macOS version, one denial
mechanism**. A network volume, a removable drive, or a different macOS may
report a denial as a different errno or take a different time. `probe()` treats
any non-`PermissionError` `OSError` as MISSING, which is the safe direction
(missing is the state we already handle) but will mislabel an exotic denial.
The live acceptance step exists to catch that on the one real case we have.
