# Active Relay State

**STATUS: IDLE.**

No active goal. v0.27.5 (System Stability Overhaul Phase C — XC-1 error-handling
narrowing, slice 1: backend data-pipeline broad-`except`) shipped and merged via
PR #64.

## Next candidates (not started)

Remaining System Stability Overhaul work — start each on a fresh branch with its
own Arena plan (larger, plan approval before coding):

- **XC-1 slice 2**: error-handling in the god-files (`cli.py`, `mcp_server.py`,
  `plugin_api.py` — best done during CM-1) and `model_setup.py`.
- **XC-4**: plugin timer/`console.*` hardening.
- **S2 god-file decomposition**: CM-1 (cli.py + mcp_server.py), DB-2 (db.py),
  PL-1 (plugin chatSidebar.ts et al.).

Shipped so far in the overhaul chain: G17/G18/G19 (v0.27.3), G17 S3 (v0.27.4),
XC-1 slice 1 (v0.27.5).
