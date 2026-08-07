# Status: INCOMPLETE — 2 of 4 inspectors, 0 of 2 critiques

Two inspectors (`router_and_layers`, `content_quality`) were terminated by a
session limit before writing their proposals. No red-team pass has run. Do not
treat this arena as finished.

## Established independently (my own measurement, not an agent's report)

These stand regardless of the missing agents:

1. **All four test questions route `local` and receive 0 L3 reports and 0 L4
   synthesis nodes**, against a vault holding 233 live L3 reports and 4 L4
   nodes. Two of the four are questions the user genuinely asked, recovered
   from `sessions.json`. Raw packs: `q1.json`–`q4.json`.

2. **The route signals are English-only regexes** (`retrieval/router.py:20-29`).
   Verified by running them directly:

   | question | `global` | `explore` |
   |---|---|---|
   | `ellipsoid 형태의 quadric 은 어떻게 매트릭스로 표현되나?` | False | False |
   | `2D GS가 3D보다 …여러 논문을 종합해서 설명해줘` | False | False |
   | `Summarize across all papers how kernel fusion…` | **True** | False |
   | `What are the overall themes in my vault?` | **True** | False |

   The same question in English routes `global`; in Korean it cannot. For a
   Korean-speaking user the distilled layers are **structurally unreachable** —
   not badly ranked, unreachable.

3. **The curation lens never binds.** All four packs report
   `workspace_id: "default"` and `policy_hash: ""`, while the live vault does
   have `01_Workspaces/COLMAP free GS/curate.yml`.

## Still owed

- `router_and_layers`: is the fix routing, `local`'s contract, or both?
- `content_quality`: are the entity descriptions and spans actually good?
  (Spot-checked examples like "A method using 2D Gaussian Splatting" and "The
  title of the scientific paper proposing 2D Gaussian Splatting" suggest a real
  problem, but it has not been counted or traced to the extraction prompt.)
- Red-team pass on all four domains. Nothing here has been adversarially
  checked yet, and the last two arenas both had findings downgraded or refuted
  at that stage.
