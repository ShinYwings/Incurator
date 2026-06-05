1. Ollama/DeepSeek Native MCP 연동 및 Antigravity CLI 답변 미출력 버그
    - Native MCP 연동 에러: 파이썬 `codex` CLI 의존성을 제거하기 위해 플러그인 내부에 Native TypeScript MCP 루프를 구현했으나, 통신 루프가 비정상 동작하거나 400 에러가 발생함.
    - Antigravity 답변 미출력 (Thinking 증발): Antigravity(`agy`) 사용 시 답변 텍스트가 전혀 나오지 않고 'Thinking...'만 표시되다가 응답이 허무하게 끝나버림. (DeepSeek 연동 문제가 아니라 `agy` 파이프라인의 독립적인 결함)
    - 상태(Native MCP 400): **수정 완료** — 근본 원인은 MCP 툴 루프에서 assistant tool-call 턴의 `content`를 `null`로 보낸 것. DeepSeek/Ollama(OpenAI-호환)는 `content: null`을 거부("Invalid assistant message"). `llmClient.ts`에 `sanitizeOpenAIMessages`(빈 assistant 턴 제거) + `normalizeOpenAIContent`(assistant/tool 빈 content를 `""`로) 추가. 테스트 `llmClient.test.ts` 12/12 통과. (item 2와 동일 원인)
    - 상태(Antigravity Thinking 증발): **부분 진단 — 플러그인 경로 한정**. 라이브 확인: (a) `agy -p "간단"`는 정상("hello world"); (b) 백엔드 `wiki query`/`wiki plugin query`의 Antigravity 합성도 정상(일관 답변, latency~60s). 백엔드 경로엔 버그 없음. "Thinking 증발"은 **플러그인의 `agy` 스트리밍 경로(`llmClient.ts streamChatViaCli`)** 한정으로 좁혀짐. 유력 원인: agy가 답변을 stderr로 흘려 plugin이 status로 소비, 또는 stdout flush 타이밍. 플러그인에서 실제 `agy` 실행 시 raw stdout/stderr 캡처가 있으면 즉시 수정 가능.

3. github 연동해줘. git commit이나 원격 저장소 보면서 vault 문서 관리하게. 그걸 위해서 github 연동하는거 로그인 로그아웃 상태표시 이런거 다 해줘야하는거 알지? 워크플로우 다 고려하고 edge케이스도 고려하고

4. wiki cli에서 할수 있는거는 obsidian backend dashboard에서도 할수 있어야함.

5. inline copilot 꼬리 질문 할수 있어야함. 그리고 답변할때 ToC 및 현재 페이지 참고해야함. 그래야 엉뚱한소리 안하지.
6.cmd+shift+L 이나 cmd+shift+X 할때 그 부분에 대해 가중치 높게 대답안하고 md 파일이나 pdf viewer 에 대해서만 엉뚱한 답변함. 가끔 deepseek 같은 애들은 답변을 하는데 추출한 부분 외에는 pdf 나 md파일 열려있는 현제 페이지를 background로 보질 않음. (pdf viewer 를 이미지로 fallback함 dom 에서 텍스트 뽑아낼수 있음에도 불구하고 이거는 pdf를 못읽어와서 그런가? pdf viewer는 제대로 읽어오는데 backend에서 다르게 동작하나? 싶음, 그리고 md파일이랑 pdf 파일 ToC 참조도 안함. Ask Gemini 이런거 예전에 분석해놨었는데 그거 따라 해달라고 해도 안따라해지네...)

6. build 자동 임베딩 (jobs run이 빈 큐에서도 embed)	testbed 0→10 + second_brain 0→2119 검증 ->  wiki add, build, reindex 이런거 다 하나로 합치면 안됨? 어차피 다 순서대로 하는건데.  그리고 lint랑 sync도 둘이 세트인데, sync랑 reindex도 세트고 (wiki jobs run이 왜 있어야하는지 모르겠음 wiki jobs list도 status 비슷한 부류이고 source도 비슷한 부류이고)
wiki device는 init 할때 그리고 status 확인할때. 같이하고. syncthing device 체크 옵시디언 실행할때만 하면 되는건데.
그리고 prompt 역할이 애매함. 아 wiki 명령어도 대분류 이렇게 바꿨었는데 revert 됐네 gemini 시발련