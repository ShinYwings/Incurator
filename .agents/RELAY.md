# Relay State — IDLE (2026-06-07)

No active goal. Last shipped: `v0.4.3` — PR #14 open, awaiting merge.

## Last Completed Work
- **v0.4.3 hotfix (PR #14)**: `pointer-events: none` + `user-select: text` on `mjx-container` and its SVG child inside `.ai-agent-chat-msg-content`. Fixes Shift+click selection across MathJax formulas in chat sidebar.
- **v0.4.2**: LaTeX `copy` event interceptor, PDF LaTeX LLM conversion, CI stub manifest fix, `importlib.metadata` version fix.

## Pending (USER_REPORT)
- PDF LaTeX 변환용 "Fast/Light model" 설정 추가 — 사용자가 경량 로컬 모델(e.g. `qwen2.5:0.5b`) 별도 지정 가능하도록 settings에 옵션 추가 필요.
