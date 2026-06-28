# Active Relay State

**STATUS: IDLE.**

No active goal. v0.27.6 (System Stability Overhaul Phase C — Robustness Slice 2:
model_setup error-handling XC-1 + plugin timer audit & gated logger XC-4) shipped
and merged via PR #65.

## Next candidates (not started)

Remaining overhaul work — the big structural S2 refactors. Start each on a fresh
branch with its own Arena plan (plan approval before coding):

- **CM-1**: decompose `cli.py` (7389 LOC) + `mcp_server.py` (3362 LOC) into
  sub-apps / tool modules. Also folds in the god-file XC-1 broad-except cleanup
  for those files.
- **DB-2**: decompose `db.py` (4679 LOC) into schema/migrations + per-entity
  repositories (very wide blast radius; characterization tests first).
- **PL-1**: decompose plugin god-files (`chatSidebar.ts` 4828 LOC, etc.);
  replace `any`/`@ts-ignore` with real types.

Shipped in the overhaul chain: G17/G18/G19 (v0.27.3), G17 S3 (v0.27.4),
XC-1 slice 1 (v0.27.5), Robustness Slice 2 / XC-1 model_setup + XC-4 (v0.27.6).
