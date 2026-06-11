# Relay State — ACTIVE (2026-06-11)

## Goal
Sidechat Selection & LaTeX Robustness — **implemented, v0.5.1**, branch
`feature/sidechat-selection-latex`.

## Status — AWAITING REVIEW/MERGE
All phases done. Local CI green: vitest 303 pass, tsc clean, spec-sync 9 pass
(after `uv sync` — patch keeps the 0.5 line so no spec-title bump), versions
0.5.1 consistent across pyproject/package/manifest/lock. Plan + Arena + draft
deleted. ROADMAP/RELAY updated. PR pending push.

## What shipped
- `utils/textUtils.selectionToTextWithLatex` — reads MathJax annotation LaTeX
  from the selection DOM (SVG or swapped-text), math-gated (non-math = raw
  toString, byte-identical). Routed through both `quickQueryPopover` capture
  sites → dragging over a formula no longer drops it.
- `main.ts` gated `keyup` trigger (Shift+Arrow/Home/End, Ctrl/Cmd+A) per
  document + popout → keyboard selections surface the Ask AI button.
- Partial-editor LaTeX copy (Cmd+C) DEFERRED → ROADMAP Icebox.

## User decisions captured (2026-06-11)
Patch v0.5.1 (no spec-title bump) · symptom 3 deferred to Icebox.

## Recurring note
`uv run pytest` vs the editable install metadata drift keeps making spec-sync
look red locally until `uv sync`; CI is fine. Symptom of the lingering dual-venv
setup (the install-unification milestone improved but didn't fully kill it).

## Immediate Next Action
Push branch + open PR. After merge, next milestone candidate = To-Do #1
(Sidechat Local Git History — drop `gh`) — needs its own Arena plan + approval.
