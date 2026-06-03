## 수정 완료

### Bug 1: eye-off 상태 send 이후 유지 안 됨 (purple pin 해당)

**원인**: `handleSend()` 실행 시 `activeContextExcludedKey = null`로 리셋되어 auto-context chip의 eye-off 상태가 사라짐. Pinned ref(`ref.includeInPrompt = false`)는 별도로 잘 유지되고 있었으나, send 후 `renderContextChips()` 재렌더 시 auto-context 쪽 eye-off가 리셋되는 구조.

**수정**: `chatSidebar.ts` line 987 — send 후 `activeContextExcludedKey = null` 제거. 사용자가 명시적으로 eye-off한 상태는 send 이후에도 유지됨. (새 세션 생성 시, active-leaf 변경 시에는 기존대로 리셋됨.)

---

### Bug 2: side chat UI/UX 개선

→ 별도 작업으로 계획 중 (Antigravity IDE 분석 필요).

---

### Bug 3: 스트리밍 중 rendering 깨짐 + CPU 폭발

**원인**: 스트리밍 중 매 청크마다 `renderAssistantMessageContent()` → `contentEl.empty()` + `MarkdownRenderer.render()` 호출 → 매번 전체 DOM 파괴/재생성. 불완전한 markdown(스트리밍 중)을 처리해 렌더링 결과가 깨짐. 큰 답변일수록 CPU 폭발.

**수정**: 
- `chatSidebar.ts` — `renderAssistantMessageContent()`: 스트리밍 중(`msg.isStreaming = true`)에는 `MarkdownRenderer` 완전히 Skip → `<div class="ai-agent-streaming-text">` 에 `textContent`로 raw text 업데이트만 수행.
- 스트리밍 완료(`isStreaming = false`) 시점에 한 번만 `MarkdownRenderer`로 full render.
- `styles.css` — `.ai-agent-streaming-text` 스타일 추가 (`white-space: pre-wrap`으로 가독성 유지).

**파일 변경/생성을 채팅창에 넣는 문제**: 이미 이전 commit(`b73b2f8`)에서 auto-apply 방식으로 전환 완료. MD 파일은 직접 반영, 채팅창에는 `✓ Applied / ✓ Created` 요약 + `✗ Revert` 버튼만 표시.