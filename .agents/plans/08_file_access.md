# v0.61.0 Master Implementation Plan — say "denied" instead of "missing"

Date: 2026-08-20
Status: AWAITING USER APPROVAL — Arena concluded, viability measured, no code written.

Arena: `.agents/plans/file_access_arena/`
(`00_problem.md`, `01_proposal_lead_architect.md`, `02_critique_redteam.md`,
`03_defense_measured.md`)

## 1. Objective

When the system cannot read a file it can see, make it say so — with the folder
the user has to grant.

Definition of done:

1. A Zotero attachment behind a denied folder produces a `denied` state, not
   `attachment_file_missing`, and not `Cannot parse PDF`.
2. The reported grant folder is the **shallowest denied ancestor**, derived by
   probing — for the live case, `~/Library/Mobile Documents`.
3. `wiki status` names sources whose file is unreadable, so this is learned once
   rather than on every ingest.
4. The live case: Hartley reports denied with a usable instruction. Whether the
   user then grants access is theirs; the system's job is to be legible.

## 2. Explicit Non-Goals

- **No folder picker, no grant request.** macOS has no API for it, and the
  picker-based design depends on an unanswered question (does a grant reach the
  spawned backend?). Tracked separately.
- **No sandbox change.** ROADMAP 8 covers what the spawned CLI may read; this
  covers whether we can explain a refusal. Fixing either alone leaves a wrong
  message or an unnecessary grant — they are deliberately separate releases.
- **Not the plugin.** `ExternalPdfView.ts:1385` goes `existsSync` →
  `readFileSync` and will still surface a raw Node error. Stated here rather
  than discovered later (red team F6).
- **Not the two Zotero root kinds.** `zotero_root_candidates` fusing data and
  attachment directories is real (briefing §5) but is a naming/typing change
  with its own blast radius. Separate.
- **Not `source_tools.py` / `asset_identity.py`** and the other existence checks.
  This release fixes the Zotero attachment path end to end; a helper the rest
  can adopt is the deliverable, not a sweep.

## 3. Strict Quality Conditions & Release Gates

- **G1.** `probe()` returns DENIED for a file whose `os.access(R_OK)` is True —
  the measured case that invalidates the obvious fix. Live-gated on a real
  denied path, skipped otherwise.
- **G2.** The grant root is found by probing ancestors, with **no hardcoded list
  of macOS folders**. Test: given a denied leaf and a readable ancestor, the
  shallowest denied one is reported.
- **G3.** `resolve_pdf` returns `attachment_file_denied` (not `..._missing`) for
  a present-but-unreadable attachment, and the existing three states are
  unchanged for their own cases.
- **G4.** `parsers.parse` raises `ParserAccessDenied(ParserError)`. Every
  existing `except ParserError` still catches it — enumerated, not assumed.
- **G5.** Selection order is pinned: two candidates, first denied and second
  readable with the same filename, must not silently repoint the source. The
  test asserts what is reported, so a change of intent has to change the test.
- **G6.** Probe cost stays within the measured envelope (OK 0.016 ms, DENIED
  0.722 ms, MISSING 0.001 ms) and the resolve path performs at most one probe
  per candidate per source.
- **G7.** `scripts/backend-check pytest | ruff | mypy` green; plugin vitest green.
- **G8.** Docs: SYSTEM_BEHAVIOR §12 taxonomy, both USER_GUIDE files. The macOS
  warning shipped in #161 gains a line pointing at the new message.

## 4. Locked Design Decisions (Arena Consensus)

**D1 — The probe opens the file.** `os.access(R_OK)` returns **True** for a
TCC-denied file (measured), so any predicate cheaper than an `open()` reports OK
and lets the caller fail later citing something else. `probe()` opens and reads
one byte — one, not zero, because an empty read can succeed where the first byte
does not.

**D2 — Three outcomes, not a bool.** `Reachability.OK | MISSING | DENIED`. A
bool is what made `_first_existing_pdf` unable to say anything useful.

**D3 — A fourth state, and the spec moves first.** `attachment_file_denied`
joins the existing three in SYSTEM_BEHAVIOR. Additive, so readers switching on
the old values keep working. **The contract is the root cause** — the code
implements its three states faithfully and none of them means "present but not
readable", so a code-only fix would put the implementation ahead of its spec.

**D4 — The grant root is probed, never matched against a list.** Measured: from
the denied file, ancestors are denied up to `~/Library/Mobile Documents` and
readable at `~/Library`. A hardcoded table would be wrong in both directions —
blind to a location Apple adds, and naming `~/Library/CloudStorage` (readable
here) as needing a grant, sending a Dropbox user to System Settings for nothing.

**D5 — No denial cache.** Measured: the candidate list on the real vault is
**2**, so the worst case is one denied probe per source, 0.7 ms, ~31 ms across
44 sources. A process-lifetime memo would save that and add state to reason
about when a user grants access mid-session. Recorded so the next reader sees it
was weighed; revisit if the candidate list grows.

**D6 — The parser keeps its typed boundary.** `ParserAccessDenied(ParserError)`
rather than letting `PermissionError` escape. Existing `except ParserError`
callers keep working.

## 5. Scope Exclusions & Stop Conditions

**Exclusions.** The folder picker, the sandbox (ROADMAP 8), the plugin read
path, the Zotero root-kind split, the non-Zotero existence checks.

**Stop conditions — halt and ask:**

- `probe()` cannot distinguish denied from missing on the live case — the whole
  premise fails and the design needs rethinking, not patching.
- Any existing `except ParserError` caller turns out to need different handling
  for a denial; that is a contract question, not an implementation detail.
- The grant-root walk reports a folder the user cannot act on (e.g. every
  ancestor denied up to `/`).
- Fixing this requires touching a file hash-pinned in `D2_HOLDOUT_RESULT.yml`.

## 6. Evidence Ledger

`.agents/plans/08_file_access_evidence.md`, before coding. Pre-recorded:

- **Rollback anchor**: `master` after v0.60.0 (`8779b93`).
- **The measurement that shaped the plan**: `os.access(R_OK)` True, `open()`
  `PermissionError errno=1` on the same path. The audit's original proposal —
  "add a readability check" — does not work.
- **Probe cost**: OK 0.016 ms · DENIED 0.722 ms · MISSING 0.001 ms (200 iters).
- **Candidate list**: 2 on the real vault.
- **Ancestor walk**: denied through `~/Library/Mobile Documents`, readable at
  `~/Library`.
- **Protected folders here**: `~/Documents`, `~/Desktop`, `~/Downloads`,
  `~/Library/Mobile Documents` denied; `~/Zotero`, `~/Library/CloudStorage`,
  `/Volumes` readable.

## 7. Execution Phases

- **P1 — Contract first.** SYSTEM_BEHAVIOR §12: the fourth state, the probe
  rule (why `access()` is not enough), the grant-root rule. **STOP for approval**
  if the taxonomy change turns out to affect the plugin contract.
- **P2 — Failing tests.** G1–G5 written and run against `master`; record which
  fail and why.
- **P3 — `file_access.py`.** `Reachability`, `probe`, `grant_root`.
- **P4 — Zotero resolution.** `_first_readable_pdf`, `resolve_pdf` returning the
  new state with `path` and `grant_folder`.
- **P5 — The parser boundary.** `ParserAccessDenied`, with its callers
  enumerated in the commit message.
- **P6 — `wiki status`.** Unreadable sources named once, with the grant folder.
- **P7 — Live acceptance.** Hartley reports denied and names
  `~/Library/Mobile Documents`. Output pasted into the ledger. This is the gate;
  a fixture cannot prove a TCC interaction.
- **P8 — Docs, version (Minor → v0.61.0: the failure taxonomy is a stored
  contract), all four spec titles, CHANGELOG, PR.**

## 8. What this plan is really fixing

Not a missing check. The system was **asking the wrong question** — `exists()`
where it needed `readable-by-me` — and then reporting the answer to a third
question entirely (`Cannot parse PDF`). The measurement that `os.access` also
answers the wrong question is what makes this an Arena rather than a one-line
patch.
