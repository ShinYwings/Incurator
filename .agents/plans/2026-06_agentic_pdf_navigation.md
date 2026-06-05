# Incurator System Analysis & Implementation Plan

This document addresses your 4 requests, providing fact-checks, architectural deep dives, and an actionable plan to fix the MCP issue for DeepSeek and Ollama.

## 1. MD 파일과 PDF 컨텍스트 분리 (Ask Gemini 동작 원리)

**분석 결과: 완벽하게 분리되어 동작합니다.**
`chatSidebar.ts`의 `buildLlmMessages`와 `buildActiveContextParts` 로직을 분석한 결과, 백그라운드 탭(MD, PDF 등)은 하나의 텍스트로 합쳐지지 않습니다.
각 열린 탭은 `[파일명 p.페이지번호]` 형태의 명확한 출처 라벨이 붙은 독립적인 `LLMContentPart` 객체(배열의 한 요소)로 분리되어 API로 전송됩니다. LLM은 이를 뭉쳐진 텍스트가 아닌 "서로 다른 출처에서 온 별개의 문서 블록들"로 정확히 인식합니다.

## 2. UI 핀(Purple Pin) 아이콘 변경 현상 팩트체크

**분석 결과: 정상적인 UI 상태 변화입니다 (내부 동작과 일치).**
첨부해주신 스크린샷에서 두 번째 보라색 핀이 일반 문서 아이콘에서 '점선 네모(영역 선택)' 아이콘으로 바뀐 것은 새로운 영역 핀이 추가된 것이 아니라, **해당 PDF 탭 자체가 "선택된 영역을 포함한 상태"로 업데이트되었음을 시각적으로 알려주는 것**입니다.
내부적으로는 해당 파일의 전체/페이지 컨텍스트가 날아가는 것이 아니라, `hasTextSelection` 속성이 활성화되면서 해당 탭이 "이 문서의 특정 영역에 포커스가 맞춰짐" 상태로 전환된 것입니다. 
즉, 핀이 3개가 되는 것이 아니라, 2번 핀의 역할이 강화(문서 전체 + 크롭/텍스트 포커스)된 것이므로 지금의 동작이 의도된 정상 스펙입니다.

## 3. DeepSeek / Ollama MCP 미동작 원인 및 해결 방안

**원인 분석:**
현재 `llmClient.ts`의 `shouldUseCli()` 함수는 Claude, OpenAI, Antigravity에 대해서만 `true`를 반환합니다. 이들은 각각 `claude`, `codex`, `agy`라는 외부 CLI 도구를 통해 실행되며, 이 CLI 도구들 내부에 MCP(Tool calling) 엔진이 내장되어 있습니다.
반면 Ollama와 DeepSeek는 `false`를 반환하여, CLI를 타지 않고 플러그인 내부의 `OllamaAdapter` / `DeepSeekAdapter`를 통해 **순수 HTTP POST 요청(텍스트만 주고받음)**으로 동작하고 있었습니다. 즉, 플러그인 자체에는 MCP 툴을 파싱하고 실행하는 루프 엔진이 없기 때문에 MCP 서버를 탈 수 없었던 것입니다.

> [!TIP]
> **해결 방안 (제안): Codex CLI 브릿지 아키텍처**
> Ollama와 DeepSeek는 모두 **OpenAI API 호환 규격**을 지원합니다. 따라서 플러그인에서 HTTP 직접 통신을 하는 대신, OpenAI를 구동하는 `codex` CLI를 호출하되, **환경 변수(`OPENAI_API_BASE` 등)를 덮어씌워 트래픽이 OpenAI가 아닌 DeepSeek이나 Ollama 서버로 향하게** 만들 수 있습니다.
> 이렇게 하면 `codex` CLI에 내장된 강력한 MCP 도구 실행 엔진을 DeepSeek와 Ollama에서도 그대로 사용할 수 있게 됩니다.

## 4. Obsidian Agent vs External Agent (Cursor) 아키텍처 심층 분석

**분석 결과: 사용자님의 이해가 정확히 맞습니다! 아키텍처가 매우 훌륭하게 짜여 있습니다.**

- **Obsidian Agent (Native Client):** `incuratorClient.ts`를 통해 로컬의 `wiki` 백엔드 명령어(`wiki status`, `wiki query`, `wiki reindex` 등)를 `child_process.execFile`로 직접 호출합니다. 가장 빠르고 오버헤드가 없는 1급 클라이언트입니다.
- **External Agents (Cursor IDE, Claude Code 등):** 이 외부 툴들은 우리 백엔드 명령어 구조를 모르기 때문에 직접 실행할 수 없습니다. 따라서 `wiki mcp`라는 서버가 실행되어 표준화된 MCP 규격으로 우리 백엔드의 기능들을 "도구(Tools)" 형태로 노출합니다. 외부 에이전트들은 이 MCP 서버를 거쳐(연동하여) 백엔드 기능을 호출하게 됩니다.

이 투트랙(Two-track) 구조는 옵시디언 내에서는 극강의 속도를 내고, 외부 IDE에서는 뛰어난 확장성을 가지는 이상적인 아키텍처입니다.

---

## 🛠️ 변경 제안 (Proposed Changes)

DeepSeek와 Ollama에서 MCP를 지원하기 위해 다음과 같이 코드를 수정할 것을 제안합니다.

### 1. `plugin/src/agent/llmClient.ts` 수정
- `shouldUseCli()`에서 DeepSeek와 Ollama도 `true`를 반환하도록 변경하여 CLI를 타게 만듭니다.
- `buildCliCommand()`에서 `provider === "deepseek"`와 `"ollama"`일 때, 내부적으로는 `codex` CLI 명령어를 생성하도록 분기합니다.
- 이때 DeepSeek의 경우 `OPENAI_API_BASE="https://api.deepseek.com/v1"`과 `OPENAI_API_KEY` 환경 변수를 주입합니다.
- Ollama의 경우 `OPENAI_API_BASE="http://localhost:11434/v1"`과 텅 빈 키를 주입합니다.

## User Review Required

> [!IMPORTANT]
> 1, 2, 4번에 대한 심층 분석이 사용자님의 궁금증을 완벽히 해소해 드렸나요?
> 3번(Ollama/DeepSeek MCP 지원)을 위해 제안한 **Codex CLI 브릿지 방식**으로 코드를 즉시 수정하여 반영할까요? 승인해주시면 바로 작업을 시작하겠습니다.
