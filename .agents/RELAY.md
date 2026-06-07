# Relay State — IDLE (2026-06-07)

No active goal. Last shipped: `v0.4.2` (fully closed — hotfix + version bump + CI gate all merged to master).

## Last Completed Work
- **LaTeX copy preservation**: intercept `copy` events in chat sidebar and quick query popover so rendered MathJax math pastes as `$...$` / `$$...$$` source (`attachLatexCopyHandler` extracted to `textUtils.ts`).
- **PDF LaTeX convert**: right-click "Convert to LaTeX (Copy)" + Cmd+Shift+C shortcut in PDF viewer — sends selected PDF text to LLM, result copied to clipboard. Keydown registered on `ownerDocument` via `registerDomEvent` (auto-cleanup, non-focusable div fix).
- **CI fix**: stub `buildManifest.json` generated before `tsc --noEmit` in plugin-tests job so gitignored file no longer breaks TypeScript check.
- **Test fix**: `test_plugin_version_returns_build_fields` updated to match current manifest schema (removed stale `*_fingerprint` field assertions from `cdccda2`).

## Pending (USER_REPORT)
- PDF LaTeX 변환용 "Fast/Light model" 설정 추가 — 사용자가 경량 로컬 모델(e.g. `qwen2.5:0.5b`) 별도 지정 가능하도록 settings에 옵션 추가 필요.
