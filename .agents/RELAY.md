# Relay State — ACTIVE (2026-06-11)

## Goal
ROADMAP To-Do #1: **Sidechat Selection & LaTeX Robustness**. Branch
`feature/sidechat-selection-latex` (from master @ afe8e60, post-PR#17).

## Plan Reference
- Master Plan: `.agents/plans/01_sidechat_selection_latex.md`
- Arena: `.agents/plans/sidechat_selection_arena/`
- Source draft: `.agents/drafts/sidechat_selection_latex.md`

## Analysis & Reasoning (key finding)
Symptom 1 ("Ask AI drops formulas") is a CAPTURE-METHOD bug, not a timing race:
`quickQueryPopover` reads `selection.toString()`, which is empty for SVG MathJax.
The `mjx-container` keeps its LaTeX in `annotation[...x-tex]` in BOTH SVG and
swapped-text states, and `textUtils.extractTextWithLatex` already extracts it
(used by chat copy). Fix = a new exported `selectionToTextWithLatex` (math-gated:
non-math → raw toString, byte-identical) routed through both capture sites →
timing-independent. Symptom 2 = missing event source; popover trigger is
mouseup-only (main.ts:138). Add a gated `keyup` listener (shift+Arrow/Home/End,
Ctrl/Cmd+A), NOT selectionchange. Symptom 3 (partial editor LaTeX copy) DEFERRED
to Icebox (needs heavy KaTeX/overlay route). No schema/RAG impact.

## Progress Status
- ✅ Investigation, Arena debate, Master Plan authored. ROADMAP/RELAY updated.
- ⏸️ **AWAITING USER APPROVAL + 2 questions (version: v0.5.1 patch vs v0.6.0
  minor; symptom-3 defer confirm) before any code (Workflow Step 4).**

## Critical Context / Blockers
- Do NOT start P1 until plan approved + version chosen.
- Minor (0.6.0) bump would also require all 4 spec titles + ACTIVE_VERSION; a
  patch (0.5.1) would not.
- Touched files (plugin-only TS): `utils/textUtils.ts`, `ui/quickQueryPopover.ts`,
  `main.ts`.

## Immediate Next Action
On approval: P1 — TDD `selectionToTextWithLatex` (math-gated) + tests; then P2
wire both popover capture sites; P3 keyboard trigger.
