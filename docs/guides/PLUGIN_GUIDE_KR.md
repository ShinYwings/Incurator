# Obsidian 플러그인 가이드 (incurator-agent)

> Incurator Obsidian 플러그인은 Obsidian Vault 안에서 AI 어시스턴트를 제공합니다.  
> 단독으로 사용하거나, Curator 백엔드(wiki CLI)와 연동해 지식 그래프 기반 답변을 생성할 수 있습니다.

[English Guide](PLUGIN_GUIDE.md)

---

## 1. 설치

플러그인 설치는 **Vault 생성 시 `wiki init` 마법사**를 통해 대화형으로 자동 진행됩니다.

```bash
# 1. 백엔드 설치
./setup.sh

# 2. Vault 생성 및 플러그인 자동 설치
wiki init /path/to/vault
```

`wiki init` 과정에서 플러그인 설치를 수락하면, 빌드 결과물(`main.js`, `manifest.json`, `styles.css`)이  
`<vault>/.obsidian/plugins/incurator-obsidian-agent/`로 자동 복사됩니다.

Obsidian → **설정 > 커뮤니티 플러그인 > 설치된 플러그인**에서 `AI Agent`를 활성화하세요.

Incurator v0.40.0 이상은 동기화된 session/profile commit에 Obsidian의
atomic adapter processing API를 사용하므로 Obsidian 1.1.0 이상이 필요합니다.
Obsidian 1.0.x에서는 `versions.json`을 통해 호환되는 Incurator v0.39.2를
계속 사용합니다.

> **참고:** 수동으로 플러그인만 별도 빌드해야 하는 경우, `plugin/` 폴더에서 `npm install` 및 `npm run build`를 실행하세요.

---

## 2. 채팅 사이드바

### 열기

| 방법 | 동작 |
| --- | --- |
| 왼쪽 사이드바 리본 아이콘(bot) 클릭 | 채팅 사이드바 열기/닫기 |
| `Cmd+Shift+;` | 채팅 사이드바 토글 |

### 기능

- **멀티턴 대화**: 세션 히스토리가 유지됩니다. 여러 세션을 생성·전환할 수 있습니다.
- **Codex 스타일 사이드바**: 상단 thread header에서 새 대화와 대화 목록을 열고, 대화 목록은 사이드바 안에서 검색·전환·삭제합니다.
- **스트리밍 응답**: 기본값으로 활성화되어 있으며, 설정에서 끌 수 있습니다.
- **스크롤 고정**: 답변이 스트리밍되는 동안에는 이미 맨 아래에 있을 때만 새 텍스트를 따라 내려갑니다. 위로 스크롤해 이전 내용을 읽고 있으면 현재 위치가 유지되며, 답변 생성이 끝나도 더 이상 화면이 맨 아래로 강제 이동하지 않습니다.
- **컨텍스트 참조**: 텍스트, PDF 페이지, 이미지 스니펫을 메시지에 첨부해 질문합니다.
- **Plan 모드**: `chatMode: plan`으로 전환 시 AI가 단계별 계획을 먼저 제시합니다.
- **Incurator 연동**: Curator 백엔드가 연결된 경우 추적 가능한 DAG 근거를 컨텍스트로 주입합니다.

---

## 3. 인라인 편집

마크다운 편집기에서 텍스트를 선택한 뒤 **Inline Edit** 명령을 실행하면 인라인
프롬프트 위젯이 열립니다. 이 명령은 **기본 단축키가 없습니다**(`Cmd+K`는
Obsidian/다른 바인딩이 이미 사용 중). 단축키가 필요하면 **설정 → 단축키(Hotkeys)**
에서 직접 할당하세요.

- **선택 없음**: 전체 문서 맥락으로 편집 명령을 입력합니다.
- **텍스트 선택 후**: 선택 영역만 대상으로 편집됩니다.
- **결과 표시**: 변경 전후를 인라인 Diff로 보여주며, 적용(Accept) 또는 거부(Reject) 선택 가능합니다.
- **채팅 편집 검토**: 사이드챗이 Markdown SEARCH/REPLACE 수정을 제안하면,
  지금 보고 있는 노트가 대상일 때(또는 포커스된 노트가 없을 때) 해당 노트의
  인편집기 Diff Viewer에 Diff가 **즉시** 열립니다. 다른 노트가 포커스되어 있으면
  편집기를 가로채지 않도록 대신 `✏️ <파일경로> · Review Diff` 형태의 간결한
  pill을 표시하며, 클릭하면 Diff가 열립니다.
- **편집 루프 검토 (v0.14.0, v0.24.0에서 완화)**: 에이전트가 파일 변경을 제안할 때
  **Analysed → Reviewed → Updated → Reviewed**의 네 단계 루프를 눈에 보이게 거치도록
  *권장*합니다. 그렇게 하면 각 단계가 채팅 답변에서 라벨이 붙은 접이식 섹션으로
  표시되며(제안된 Diff는 *Updated* 아래에 위치), 에이전트가 어떤 빈틈을 파악하고, 자기
  계획을 비판하고, 변경을 수행하고, 수락 전에 스스로 점검하는 과정을 볼 수 있습니다.
  **v0.24.0부터 이것은 하드 게이트가 아니라 품질 힌트입니다.** 모델(특히 작거나 출력
  토큰이 제한된 모델)이 단계를 건너뛰더라도 유효한 수정을 만들어 냈다면 Diff는 **여전히
  완전히 검토 가능**합니다 — 답변에는 편집 pill과 함께 *"모델이 자체 검토 단계를 건너뜀"*
  이라는 작은 안내와 선택적인 **Re-run with review** 버튼이 표시됩니다. 더 이상 "수정을
  했다"면서 Diff가 없는 상황에 갇히지 않습니다. 편집을 제안하지 않는 순수 질문은 단계도
  안내도 표시되지 않습니다.
- **잘린 답변 자동 이어쓰기 (v0.24.0)**: 출력 토큰 한도가 있는 모델(특히 Gemini)은 때때로
  답변 도중에 — 종종 편집 블록 한가운데서 — 멈춥니다. 이제 플러그인이 이를 감지하고 모델에게
  멈춘 지점부터 정확히 이어쓰도록 자동으로 요청하며(최대 3회), 텍스트를 중복하거나 편집 블록을
  깨뜨리지 않고 조각들을 이어 붙입니다. 그 후에도 여전히 잘려 있으면 **↪ Continue** 버튼이
  나타나 수동으로 이어쓸 수 있습니다.
- **견고한 SEARCH 매칭**: 더 이상 에이전트의 SEARCH 텍스트가 파일과 1바이트까지
  똑같을 필요가 없습니다. 앞뒤 공백과 들여쓰기 수준 차이는 허용되므로, 모델이
  다시 들여쓰기를 해도 올바른 수정이 적용됩니다. 매칭은 **모호성에 안전**합니다.
  두 군데 이상에 매칭될 수 있으면 잘못된 위치를 건드리는 대신 수정을 거부합니다
  ("could not find" 알림). 단일 교체가 매우 크면 "주의해서 검토" 알림이 뜹니다.
- **채팅에 코드 전체를 뱉지 않음**: 코드 수정 내용이 대화창을 길게 채우지
  않습니다. 답변이 스트리밍되는 동안 모든 `ai-agent-edit` 블록은
  *[Generating code edit…]* 자리표시자 하나로 가려지고, 답변이 끝나면 각 수정은
  간결한 pill로 접힙니다. 전체 before/after는 채팅 기록이 아니라 Diff Viewer
  안에서만 표시됩니다. 잘못 형성된 블록에서 남은 편집 마커(`<<<<`/`====`/`>>>>`)는
  렌더링된 메시지에서 제거됩니다.
- **Diff Viewer 내비게이션**: 떠 있는 툴바에 hunk 카운터(예: `1/1`, `2/8`)가
  표시되고, 변경이 둘 이상이면 ↑/↓(또는 Tab / Shift+Tab)로 hunk 사이를 이동하며
  Y/N으로 현재 hunk를 Accept/Reject합니다(Enter = 전체 수락, Esc = 전체 거부).
  **포커스 안전 단축키 (v0.24.0)**: 이 키들은 Diff 편집기나 그 툴바가 포커스된 동안에만
  동작합니다 — 채팅 입력창에서 Enter를 눌러도 열려 있는 Diff가 실수로 적용되지 않습니다.
  Diff를 열면 자동으로 포커스되므로 키가 바로 동작합니다.
- **순서 독립적 다중 편집 (v0.24.0)**: 한 답변이 같은 파일에 여러 편집을 제안할 때,
  하나를 수락해도 다른 편집의 매칭이 깨지지 않습니다 — 모든 편집을 원본 파일 기준으로
  찾기 때문입니다. 일부 편집을 배치할 수 없으면 모호한 경고 대신 "N개 건너뜀(찾지 못함 /
  겹침)"이라는 명확한 안내가 표시되고, 나머지는 그대로 검토용으로 열립니다.
- **전체 수락 시 위치 유지 (v0.14.1)**: 모든 변경을 수락해도 커서는 문서 맨
  아래가 아니라 첫 번째 변경 줄에 남습니다.
- **툴바가 변경 위치에 고정 (v0.14.1)**: Diff가 화면 밖에서 열리면 먼저 첫 변경을
  화면 안으로 스크롤하므로, Accept/Reject 툴바가 화면 상단으로 튀지 않고 변경
  옆에 나타납니다.
- **정직한 편집 제안 pill (v0.14.1)**: 각 `✏️ <파일>` 검토 pill은 실제 파일
  상태를 반영합니다 — 편집이 이미 파일에 적용되어 있으면 **✓ Applied**, SEARCH
  텍스트가 더 이상 일치하지 않으면 **⚠ Not found**로 표시되어, 클릭한 뒤에야
  혼란스러운 "could not find"를 보는 일이 없습니다. 검토는 한 번에 하나씩
  열리므로 두 번째 pill을 클릭해도 첫 파일의 Diff를 가로채지 않습니다. 경로
  매칭은 대소문자 무시 전체 경로 매칭으로 폴백하여 기존 노트에서 잘못 뜨던
  "파일을 찾을 수 없음"을 고치되, 다른 폴더의 같은 이름 노트로 대상을 바꾸지
  않습니다. **✓ Applied**는 교체 블록이 모호하지 않게 확인될 때, 또는 삭제
  제안의 SEARCH 텍스트가 이미 사라지고 교체 내용이 비어 있을 때 표시됩니다.
  Applied/not-found pill은 다시 review를 실행하지 않습니다. 에이전트는 편집을
  *제안되었고 수락 대기 중*으로 설명하며, 수락하기 전에는 디스크에 아무것도
  기록되지 않습니다.
- **Diff 모드**: 설정에서 `inline` 또는 `side-by-side` 중 선택합니다.

```text
편집기에서 텍스트 선택
       │
       │ Inline Edit 명령
       ▼
인라인 프롬프트 위젯 (명령 입력)
       │
       ▼
LLM이 제안 생성 → Diff 표시 → Accept / Reject
```

---

## 3.5 선택 영역 빠른 질의 (In-line Copilot)

마크다운 노트, 읽기 뷰, PDF 어디서든 텍스트를 선택하면 선택 영역 옆에
**✨ Ask AI** 버튼 하나가 나타납니다. 이 버튼을 누르거나(텍스트가 선택된 상태에서
`Cmd+Shift+K`를 눌러도 됨) 해당 구절에 대해 1회성 질문을 던질 수 있는 작은 팝업이
열립니다. 읽는 도중 "참조: [섹션 4.2]"나 "Eq. (3)에 의해…" 같은 구절을 빠르게
해석/요약받는, `wiki query`의 가벼운 버전처럼 동작합니다.

- **마우스·키보드 선택 모두 지원**: 마우스 드래그뿐 아니라 키보드 선택
  (Shift+화살표 / Shift+Home·End, 또는 Ctrl/Cmd+A)에서도 버튼이 뜹니다. 선택을
  다시 캐럿으로 좁히면 버튼은 사라집니다.
- **수식 보존**: 선택 영역이 렌더링된 MathJax 수식을 포함하면, 빈 SVG가 아니라
  LaTeX 원본(`$...$` / `$$...$$`)이 그대로 캡처됩니다. 따라서 Live Preview의 렌더
  타이밍과 무관하게, 수식을 가로질러 드래그해도 수식이 사라지지 않습니다.
- **버튼 1개**: 선택 시 툴바 없이 버튼 단 하나만 표시됩니다.
- **지속되는 팝업**: 팝업에는 질문 입력칸과 **Ask** 버튼만 있습니다. 프리셋·퀵버튼은
  없습니다. 한 번 열리면 다른 곳을 클릭하거나 스크롤해도 닫히지 않으며, **×** 또는
  `Esc`로 직접 닫습니다.
- **여러 팝업**: 다른 선택 영역에서 빠른 질의를 새로 열면 이전 팝업을 대체하지 않고
  별도 팝업이 만들어집니다. 각 팝업은 자기 답변, 위치, 최소화 상태, 짧은 후속 질문
  메모리를 독립적으로 유지합니다.
- **이동 및 최소화**: 팝업 헤더를 드래그해 현재 창 안에서 원하는 위치로 옮길 수
  있습니다. 최소화 컨트롤을 누르면 답변과 후속 질문 상태를 유지한 채 헤더만 남깁니다.
- **질문 제목**: 질문을 제출할 때마다 헤더 제목이 최신 질문으로 바뀌므로, 최소화한
  팝업도 어떤 질문의 답변인지 구분할 수 있습니다.
- **집중 답변 표시**: 질문을 제출하면 답변이 스트리밍되는 동안 입력칸은 숨겨지고,
  채팅 말풍선 구조 없이 답변 영역만 표시됩니다. 답변이 끝나면 같은 팝업 안에 작은
  후속 질문 입력칸이 다시 나타납니다.
- **꼬리 질문**: 같은 팝업 안에서 하는 후속 질문은 직전 quick-query 질의/응답을 짧은
  메모리로 유지합니다. 팝업을 닫으면 이 메모리는 사라지며 사이드바 대화 기록에는
  절대 저장되지 않습니다.
- **현재 페이지 + ToC 컨텍스트**: 선택한 구절은 항상 1차 초점입니다. 활성
  Markdown/PDF 페이지, 주변 PDF window 텍스트, 사용 가능한 Markdown/PDF outline을
  배경 컨텍스트로 함께 보내므로 "section 4.2", "Eq. (3)", "(19.11)" 같은 bare equation
  label, 현재 페이지 heading 같은 참조를 해석할 수 있으면서도 전체 문서가 선택 영역을
  압도하지 않습니다.
- **참조 따라가기**: 선택한 텍스트 자체가 "see Section A4.2 (p580)",
  "Figure 19.1", "Result A4.1", "(19.11)"처럼 다른 위치를 가리키는 pointer라면,
  플러그인은 먼저 PDF outline/window 텍스트와 search hit에서 해당 target을 찾아
  `<resolved_cross_references>`로 넣고, 그 뒤에 일반 페이지 배경을 보냅니다.
  pointer에 `Section 11.1.2, p281`처럼 명시적인 페이지 위치가 들어 있거나 `(3.5)`처럼
  번호만 있는 대상이면, 열린 Incurator PDF viewer는 먼저 PDF ToC에서 가장 작은 matching
  section range를 찾아 PDF.js로 읽고, ToC에 정확한 section이 없을 때만 제한된 chapter
  range로 fallback합니다. Theorem 계열 pointer는 부록식 문자-접두 번호
  (`Result A4.1`, `Corollary B2.3`)를 인식하고, `Appendix 4` 형태의 ToC 제목은
  `A4` 스타일 번호에도 응답하므로 부록 anchor도 해석됩니다.
- **참조를 찾지 못했을 때 (v0.48.4)**: 일부 PDF는 본문에 표시되는 수식과 그림을
  이미지로 렌더링하기 때문에, 그 라벨이 추출된 텍스트에 아예 나타나지 않아 아무리
  검색해도 찾을 수 없습니다. 이제 플러그인은 그 사실을 명시적으로 알립니다. 찾을 수
  없는 pointer는 `<unresolved_cross_references>` 블록에 나열되며, 이 블록은 모델에게
  해당 텍스트가 실제로 존재하지 않는다는 것, 이미 주어진 context만으로 답해야 한다는
  것, 그리고 파일을 직접 열어보려 하지 말라는 것을 알려줍니다. 이전에는 이 블록이
  그냥 생략되었고, 그 결과 프롬프트는 마치 아무것도 묻지 않은 것처럼 보였습니다.
  headless CLI로 실행되는 모델은 파일을 읽는 도구를 시도하게 되고, CLI는 프롬프트를
  띄울 수 없는 권한을 자동으로 거부하여 답변이
  `no output produced — a tool required the "command" permission that headless
  mode cannot prompt for, so it was auto-denied`로 돌아왔습니다. 이제는 어떤 수식이나
  그림을 가져오지 못했는지 밝히는 실제 답변을 받게 됩니다.

  표현은 의도적으로 "존재하지 않는다"가 아니라 "가져오지 못했다"입니다. 플러그인이
  얼마나 넓게 찾았는지는 어디서 질문했는지에 따라 다릅니다. 드래그 선택 popover는
  이미 로드된 페이지만 검색하고, 문서 전체 검색은 백엔드가 실행 중이어야 합니다.
  그래서 어시스턴트는 그 수식이 논문에 없다고 단정하는 대신 가져오기에 실패했다고
  보고합니다.

  이웃 참조를 통해 해석된 pointer는 누락으로 보고되지 않습니다.
  `(Section 11.1.2, p281)` 같은 것을 선택하면 페이지와 section은 하나의 참조이며,
  그 텍스트는 section 아래에 한 번만 나타납니다. 동시에 가져올 수 없는 항목으로
  나열되지 않습니다.
- **인쇄 페이지 번호 vs 물리 페이지 번호 (v0.40.3)**: 책 PDF에는 보통 앞부분
  front matter가 있어서 인쇄된 581쪽이 PDF의 581번째 페이지가 *아닙니다*.
  `p581` 같은 locator는 다음 순서로 매핑됩니다: PDF 자체의 page label; 독자가
  이미 본 페이지들의 인쇄 머리글/바닥글 번호에서 추론한 front-matter offset
  (두 페이지 이상이 명확한 다수결로 일치할 때만 채택); 인쇄 머리글이 일치하는
  이미 알려진 페이지 스캔; 마지막으로 문자 그대로의 페이지 번호 — 이 추측은
  가져온 페이지의 머리글이 그것을 반증하기 전까지만 유지됩니다. 머리글이 다른
  인쇄 번호를 가리키는 페이지는 절대 resolved target으로 주입되지 않습니다:
  Ask AI는 엉뚱한 페이지를 자신 있게 인용하는 것보다 target을 찾지 못했다고
  말하는 쪽을 선택합니다. 문자 그대로의 추측이 반증되면 그 머리글이 문서의
  실제 offset을 드러내므로, 제한된 repair fetch 한 번으로 올바른 물리 페이지를
  가져옵니다.
- **문서 내 위치이지 폴더가 아님**: "문서 위쪽", "앞부분", "top of the document",
  "end of the page" 같은 위치 표현은 파일 시스템이 아니라 **현재 문서의
  내용/outline 안에서의 위치**로 해석됩니다. 팝오버는 파일 시스템에 접근하지
  않으므로 폴더·파일 이름을 나열하거나 지어내지 않으며, "문서 위쪽"을 물으면 상위
  디렉터리를 뒤지는 대신 그 영역의 텍스트를 요약합니다.
- **도구 격리 (v0.19.0)**: 팝오버는 MCP 도구로부터 완전히 격리됩니다 — 채팅
  사이드바용으로 MCP 서버(Incurator 포함)를 켜 두었더라도 팝오버에는 MCP 도구가
  **하나도** 주입되지 않습니다. 스크립트를 실행하거나 파일을 만들거나 파일 시스템·
  vault·Zotero 라이브러리에 접근하는 일은 절대 없습니다. 지식 베이스 RAG, 파일 편집,
  MCP 도구 같은 완전한 에이전트 기능이 필요하면 팝오버 대신 채팅 사이드바를
  사용하세요.
- **사용자 대신 페이지 넘기기 (v0.41.0)**: 이제 팝오버가 이미 열려 있는 PDF의
  페이지를 직접 넘길 수 있습니다. 어시스턴트는 항상 문서의 목차를 페이지 번호와
  함께 전달받으므로 "그 결과는 Appendix 4, 617쪽쯤이겠군"까지 추론할 수 있었지만,
  v0.41.0 전에는 거기로 갈 방법이 없어서 "직접 가서 보세요"라고 말할 수밖에
  없었습니다. 이제 딱 하나의 읽기 전용 능력을 가집니다: 열린 PDF의 페이지를 번호로
  가져오기. 이는 자동 참조 따라가기가 구조적으로 처리할 수 없는 경우를 커버합니다 —
  대상 페이지를 읽은 *뒤에야* 발견되는 참조, 선택한 텍스트가 아니라 질문 쪽에
  들어 있는 대상, 그리고 "앞 장에서 보인 것처럼"처럼 번호가 없는 산문 참조입니다.
  목차가 내장되지 않은 논문의 경우, 탐색할 지도가 없으므로 이미 본 페이지들에 대한
  검색이 추가로 제공됩니다.

  이것이 위의 격리를 넓히지는 않습니다: 페이지 리더는 MCP 도구가 아니며 파일
  시스템·vault·Zotero에 접근할 수 없습니다. 눈앞에 열려 있는 PDF로만 범위가
  제한되고, 그 문서 밖의 페이지 번호는 거부하며, 질문당 정해진 횟수만큼만 페이지를
  가져온 뒤 멈춥니다. PDF가 열려 있지 않으면 이 능력은 아예 제공되지 않습니다.
  CLI 제공자(Antigravity `agy`, Claude, Codex)는 페이지 리더를 받지 않고 자동 참조
  따라가기만 유지합니다.
- **CLI 제공자 샌드박싱 (v0.23.0)**: 제공자가 CLI 에이전트(Antigravity `agy`,
  Claude, Codex)이면 그 에이전트는 v0.19.0의 MCP 격리가 통제하지 못하는 자체 내장
  도구를 가집니다. 이제 플러그인이 이를 가둡니다: 팝오버는 CLI를 **도구 없이**
  실행하고, 채팅 사이드바의 도구는 **당신의 데이터로 범위가 제한**됩니다 — 에이전트는
  vault와 설정된 Zotero 라이브러리를 **읽을** 수 있지만 **쓰기는 vault 안에서만**
  가능합니다. Zotero 라이브러리는 읽기 전용으로 취급되어 에이전트가 수정·삭제할 수
  없고, vault 밖 어디에서도 파일을 만들거나 스크립트를 실행할 수 없습니다.
  Antigravity의 자체 `--sandbox`는 효과가 없어서 플러그인이 OS 샌드박스로
  감쌉니다(macOS 내장; **Linux는 `bubblewrap`이 필요 —
  `sudo apt install bubblewrap` 또는 `sudo dnf install bubblewrap`으로 설치**).
  OS 샌드박스를 쓸 수 없으면 **Antigravity는 차단**되고(컨테인먼트가 전혀 없으므로),
  **Claude와 Codex는** 자체 내장 제한(더 약함) 하에서 계속 실행됩니다. Windows CLI
  샌드박싱은 아직 미지원입니다.

  Antigravity 1.1.3 이상은 플러그인이 `agy`를 headless(`-p`) 모드로 실행할 때
  대화형 승인이 필요한 도구도 거부합니다. 따라서 플러그인은 기존 Antigravity CLI
  설정을 보존하면서 `~/.gemini/antigravity-cli/settings.json`의
  `permissions.allow`에 좁은 규칙 두 개를 추가합니다: `read_file()`, 그리고
  Incurator MCP 서버를 띄우기 위한 `command(wiki)`.

> [!IMPORTANT]
> **`jetski: no output produced`가 반복해서 떴다면 원인이 이것입니다 (v0.53.1에서
> 수정).** 그전까지 기록하던 규칙은 `$read_file$()` 형식이었는데, Antigravity가
> 인식하지 못하는 형태입니다. Antigravity는 인식하지 못하는 규칙을 잘라내고 비어
> 버린 `permissions` 객체를 통째로 삭제하므로, 이 권한은 **단 한 번의 실행도**
> 살아남지 못했고 모델이 도구를 쓰려 할 때마다 자동 거부되었습니다. 사용자가 설정을
> 잘못한 것이 아닙니다. 업데이트하면 권한이 유지됩니다.

  `command(wiki)`는 플러그인이 직접 설정하는 `wiki` 실행 파일로만 범위가
  제한됩니다 — Incurator는 무엇이든 실행할 수 있게 하는 `command()`를 절대
  기록하지 않습니다. 이 규칙은 열린
  PDF나 첨부 이미지를 승인 프롬프트 없이 읽게 하지만 쓰기, 셸 명령, 네트워크 도구,
  임의 경로를 승인하지 않습니다. 표시되는 vault/Zotero 디렉터리는 계속
  `--add-dir`가 결정하고 쓰기는 계속 OS 샌드박스가 제한합니다. 잘못된 JSON 설정은
  자동으로 덮어쓰지 않습니다. Incurator v0.36.3이 만들었던
  `~/.gemini/policies/incurator-read.toml`은 Incurator 생성 파일 표식이 그대로 있을
  때만 제거하며, 사용자가 작성한 정책은 건드리지 않습니다.
- **Markdown 렌더링**: 스트림이 끝나면 답변은 Markdown(수식/LaTeX 포함)으로
  렌더링됩니다. 렌더링 전에 수식이 정규화되어, `` `$x^2$` `` 처럼 백틱으로 감싼
  수식은 `$x^2$` 로 풀려 모노스페이스 텍스트가 아니라 실제 수식으로 표시됩니다
  (채팅 사이드바와 동일한 동작).
- **복사 가능**: 답변 텍스트는 드래그로 복사할 수 있도록 선택 가능 상태를 유지합니다.
  렌더링된 수식은 복사 핸들러가 실행되기 전에 LaTeX 소스로 stamp되어 채팅
  사이드바와 동일하게 복사됩니다.
- **스크롤·최대 크기**: 팝업은 `max-height`/`max-width`로 크기가 제한되며, 내용이 길면
  팝업 내부에서 스크롤됩니다.
- **1회성(Temp)**: 임시 창이므로 `×` 버튼이나 `Esc`로 닫으면 해당 팝업의 데이터만
  소멸하며 사이드바 대화 기록을 오염시키지 않습니다. 열린 팝업 바깥을 클릭하면
  떠 있던 트리거 버튼만 사라지고 기존 팝업은 닫히지 않습니다. 열린 각 팝업이 자신의
  cancellation signal을 소유하므로 하나를 닫아도 다른 팝업이나 chat sidebar는
  중단되지 않으며, sidebar 자체의 Stop 대상도 바꾸지 않습니다. PDF context를 준비하는
  동안 팝업을 닫으면 이후 provider process나 HTTP request가 시작되지 않습니다.
  Ollama 연결 오류를 포함한 provider별 오류 메시지도 정상 cancellation을 대체하지
  않습니다. non-streaming CLI query도 선택한 per-call model과 streaming query와
  동일한 GUI-safe CLI search path를 유지합니다.

선택한 구절은 질문과 함께 1차 컨텍스트로 전달되고, 현재 페이지/outline은 배경으로
전달됩니다. 현재 설정된 AI 제공자/모델을 사용합니다. 버튼이 뜨지 않게 하려면
**설정 → AI Provider → Quick query on selection**에서 기능을 끌 수 있습니다.

```text
텍스트 드래그 선택
       │
       │ ✨ Ask AI 버튼 표시
       ▼
팝업: [ 질문 입력칸 ] [ Ask ]
       │  제출
       ▼
입력칸 숨김 → 답변만 스트리밍 (복사·스크롤 가능)
       │  후속 질문 입력칸 다시 표시
       ▼
같은 선택 영역에 대해 추가 질문 (선택 사항)
       │  닫기 (×, Esc, 바깥 클릭)
       ▼
소멸 — 대화 기록 유지
```

---

## 3.6 AI 챗과 popover에서 LaTeX 복사 (`Cmd/Ctrl+C`)

**챗 사이드바**나 빠른 질의 popover의 어시스턴트 답변에서 일부를 드래그로 선택하고
**Cmd/Ctrl+C**를 누르면, 선택 영역 안의 렌더링된 수식이 빈 MathJax SVG가 아니라
**LaTeX 소스**(인라인 `$...$`, 블록 `$$...$$`)로 클립보드에 담깁니다 — 그래서
유도 과정을 노트에 편집 가능한 LaTeX로 바로 붙여넣을 수 있습니다.

- **선택 영역만**: 선택한 영역만 복사됩니다 — 메시지 전체가 아닙니다.
- **수식 없는 복사는 그대로**: 수식이 없는 선택은 이전과 똑같이 복사됩니다.

---

## 3.7 읽기 모드에서 노트 수식 복사 (`Cmd/Ctrl+C`, `Cmd/Ctrl+X`)

**읽기 모드(Reading View)**에서 노트의 일부를 드래그로 선택하고 **Cmd/Ctrl+C**(또는
**Cmd/Ctrl+X**)를 누르면, 선택 영역에 렌더링된 수식이 있을 경우 빈 MathJax SVG가
아니라 **LaTeX 소스가 복원된 Markdown**(인라인 `$...$`, 블록 `$$...$$`)으로
복사됩니다. 드래그 중에 선택 하이라이트가 수식을 *건너뛰는* 것처럼 보여도 정상이며,
수식은 그대로 캡처됩니다. 팝아웃 창에서도 동작합니다.

- **선택 영역만**: 드래그한 영역만 복사됩니다. 선택이 수식과 일부만 겹쳐도 그 수식은
  **통째로** 캡처됩니다(반쪽 수식은 쓸모가 없으므로).
- **수식 없는 복사는 그대로**: 수식이 없는 선택은 옵시디언 기본 클립보드에 맡기며,
  플러그인이 가로채지 않습니다.
- **라이브 프리뷰 / 소스 모드**는 (CodeMirror가 문서 소스를 복사하므로) 이미 `$...$`를
  보존합니다. 따라서 별도 처리가 필요 없고, 플러그인은 소스를 잃어버리는 **읽기
  모드**만 보강합니다.
- **`Cmd/Ctrl+X`**: 읽기 전용인 읽기 모드에서는 LaTeX를 복사하되 (정상적으로) 아무것도
  삭제하지 않습니다. 라이브 프리뷰에서는 기본 잘라내기가 이미 소스를 제거합니다.

> **원리.** 옵시디언은 읽기 모드 수식을 CHTML로 렌더링하면서 페이지 DOM에 LaTeX
> 소스를 **전혀** 남기지 않습니다. 플러그인은 Markdown 후처리기를 등록해, 렌더된 각
> 섹션의 소스를 다시 파싱하여 모든 수식에 `data-tex`로 소스를 stamp 합니다(파싱된
> 수식 개수와 렌더된 개수가 정확히 일치할 때만 — 따라서 잘못된 소스가 붙는 일은
> 없습니다). 복사 핸들러가 그 stamp를 읽습니다 — 챗 사이드바(§3.6)와 동일한 방식입니다.

---

## 4. 라인 참조 (`Cmd+Shift+L`)

현재 보고 있는 내용을 채팅 컨텍스트로 추가합니다.

| 뷰 타입 | 동작 |
| --- | --- |
| **마크다운 파일** | 현재 커서 근처 텍스트를 컨텍스트 참조로 추가 |
| **PDF 뷰어** (선택 있음) | 선택한 텍스트를 컨텍스트에 추가 |
| **PDF 뷰어** (선택 없음) | 현재 페이지 전체를 컨텍스트로 추가 (`pdfCaptureMode`에 따라 텍스트·이미지·양쪽) |

Incurator PDF 뷰어의 텍스트 선택은 실제 텍스트 span 위에서만 시작됩니다. PDF의 빈 여백을 드래그해도 선택 영역이 생기지 않도록 처리합니다.

사이드챗에서 메시지를 보낼 때 선택 영역, 라인 참조, PDF 스니핑으로 명시적으로 추가한 컨텍스트가 현재 턴의 중심 맥락으로 취급됩니다. 명시적으로 선택한 snippet, 선택 텍스트, crop, line range는 pin 된 뒤에도 중심 맥락으로 유지됩니다. 반면 전체 파일이나 전체 PDF 페이지를 pin 한 context와 자동으로 보이는 탭은 질문에서 직접 요구하지 않는 한 배경 맥락으로만 사용됩니다. pin 또는 첨부 context chip은 invisible/excluded 상태로 전환할 수 있으며, 이 상태에서는 chip row에는 남아 있지만 다시 visible로 바꾸기 전까지 모델 prompt에는 포함되지 않습니다.

context row는 **열린 탭**과 **prompt에 포함되는 탭**을 구분합니다. 같은 tab
group에서 선택되지 않아 뒤에 숨은 탭을 포함해, 열린 Markdown/PDF 탭은 모두 chip으로
표시됩니다. 각 split에서 현재 보이는 탭은 기본 eye-on이며 배경 context에 포함됩니다.
숨은 tab-group 탭은 기본 eye-off이며, 사용자가 eye를 켜거나 pin 하기 전까지 tab
목록, 파일 본문, outline, continuity summary, edit target 어디에도 전달되지 않습니다.
같은 source/page를 가리키는 완전히 동일한 view는 chip 하나를 공유할 수 있지만, 같은
PDF의 서로 다른 page는 별도 context로 유지됩니다.

선택 영역 중심 질문에서는 현재 페이지 구조도 배경 grounding으로 함께 전달됩니다. Markdown heading은 compact outline으로, PDF는 가능한 경우 outline/window context로 전달됩니다. 이 outline/page 블록은 보조 자료일 뿐이며, 선택한 텍스트, line range, crop이 여전히 답변의 대상입니다.

**긴 세션에서의 국소적 초점 (v0.19.0):** 긴 대화에서 — 특히 앞서 문서 전체를 편집한 뒤 — 새로 추가한 `Cmd+Shift+L` 선택이 무시되고 에이전트가 다시 파일 전체를 수정하려는 문제가 있었습니다. 이제 플러그인은 각 요청의 맨 끝(모델 attention이 가장 강한 위치)에 고우선순위 invariant 블록을 덧붙여 "현재 선택 영역에 대해서만 답하고, 명시적으로 요청하지 않는 한 문서 전체를 편집하지 말 것"을 재확인합니다. 따라서 긴 세션 후반의 국소적 질문도 앞선 턴과 무관하게 존중됩니다.

**국소적 질문에 대한 편집 권한 억제 (v0.21.0):** v0.19.0 앵커는 여전히 편집 메커니즘과 충돌하고 있었습니다. `Cmd+Shift+L` 라인 범위는 *편집 가능한* 범위이기도 하므로, 같은 요청에 "선택 영역에 대해서만 답하라"(앵커)와 "이 라인들을 편집해도 된다 / 편집 검토 루프에 있다"가 동시에 실렸습니다. 길고 편집이 잦은 세션에서는 편집 신호가 이겨, 단순 질문에도 에이전트가 파일 전체 편집을 제안하기도 했습니다. 이제 최신 턴이 선택 영역에 대한 **질문**일 때(중심 초점 선택이 존재하고 메시지가 편집 요청이 아닐 때) 플러그인은 편집 가능 선택 권한 블록과 편집 검토 루프 계약을 아예 생략하므로, 답변 전용 앵커가 방해받지 않습니다. 편집을 요청하면("이 줄을 다시 써줘…", "여기 문법 고쳐줘") 이전처럼 전체 편집/Diff 흐름이 그대로 제공됩니다.

assistant 답변에 `#page=604`, `p.604`, `#section=A4.2`, `§19.3` 같은 page 또는
section 링크가 포함되면, 사이드바에서 클릭했을 때 열린 Incurator PDF 뷰어가
해당 page로 이동합니다. section 링크는 활성 PDF outline으로 해석합니다. `p.580`
같은 printed page 링크는 Incurator PDF 뷰어가 PDF의 native PageLabels map을
제공하는 경우 이를 사용하므로, front-matter offset 때문에 `p.580`이 물리적 580쪽으로
잘못 이동하지 않습니다. 일반 웹 링크와 vault 링크는 기존 동작을 유지합니다.
`Auto Calibration#^8f735d`처럼 명확한 block anchor가 있는 생성 vault locator나
`Auto Calibration > ^8f735d`처럼 렌더링된 label은 Obsidian의 일반 vault-link
navigation으로 열립니다.

### Assistant Vault 페이지 위키링크

Sidechat provider가 사용자가 포함한 context, 사용 가능한 Incurator evidence
locator, 또는 tool 결과에서 정확한 vault-relative path를 확보한 경우
`[[02_Wiki/Optimization/Auto Calibration|Auto Calibration]]` 같은 Obsidian
위키링크로 해당 페이지를 인용할 수 있습니다. 알려진 heading이나 block도
`[[02_Wiki/Optimization/Auto Calibration#Method]]` 또는
`[[02_Wiki/Optimization/Auto Calibration#^8f735d]]`처럼 유지합니다. Markdown
대상에서는 `.md` suffix를 생략하지만 `.pdf` 같은 비 Markdown suffix는 그대로
보존합니다.

이 계약은 선택 가능한 모든 Sidechat provider와 model에 공통으로 적용됩니다.
모델에 vault 전체 파일명 목록을 보내거나, 페이지처럼 보이는 단어만 보고 링크를
추측하거나, 생성된 일반 답변 텍스트를 나중에 다시 쓰지 않습니다. 정확한 대상이
grounding되지 않았다면 assistant는 이름을 plain text로 남겨야 합니다. 유효한 일반
노트 링크는 Obsidian 자체가 렌더링하고 열기 때문에 native click, modifier-click,
hover 동작이 유지됩니다. 포함된 Markdown/PDF context에는 plugin이 검증된 완성형
`vault_link_target` literal을 제공하므로 작은 local model도 display label에서 경로를
다시 조립하지 않고 정확한 링크를 복사할 수 있습니다. 외부 또는 지원하지 않는 file
path에는 이 target을 제공하지 않습니다.

### Curator DAG 위키링크

Curator 지식 DAG(L1–L4 노드: `CTX-`, `ATM-`, `CON-`, `SYN-`)는 숨김 폴더인
`.curator/Collections/` 아래에 저장됩니다. Obsidian은 숨김(점으로 시작하는) 폴더의
파일을 인덱싱하지 않으므로, `[[02_Atoms/ATM-9f8e7d6c]]` 같은 curator 위키링크는
원래 클릭·hover·그래프·백링크가 전혀 동작하지 않는 죽은(unresolved) 링크로
렌더링됩니다.

플러그인은 이 간극을 메웁니다. 렌더링된 curator 레이어 위키링크
(`[[01_Contexts/CTX-…]]`, `[[02_Atoms/ATM-…]]`, `[[03_Concepts/CON-…]]`,
`[[04_Synthesis/SYN-…]]`. `.curator/Collections/` 접두사나 끝의 `.md` 유무와
무관)는 **숨겨진 DAG 페이지를 여는 클릭 가능한 링크**로 변환됩니다. 이 동작은 채팅
사이드바 답변, 빠른 질의 popover 답변, 그리고 열린 DAG 페이지의 읽기 모드에서
모두 적용됩니다. 대상 파일이 존재하면 정상적인 resolved 링크로 렌더링되고, 없으면
`is-missing` 스타일로 표시되어 끊어진 인용이 조용히 묻히지 않고 드러납니다.

DAG가 숨김 폴더에 있으므로 이 노드들은 여전히 Obsidian의 기본 그래프 뷰나 코어
백링크 패널에는 나타나지 않습니다. 백링크 성격의 출처 추적은 채팅의 **Sources &
Trace** 패널을 사용하세요. 일반 웹 링크와 vault 링크는 기존 동작을 유지하며,
curator 레이어 링크 대상만 재작성됩니다.

합성된 답변은 각 주장의 근거가 된 **원본 소스 문서**도 curator 노드와 함께
인용합니다 — 예: `[[04_Resources/Some Paper]]`. 이 소스 파일들은 숨김이 아닌
일반 vault 파일이므로 링크가 네이티브로 resolve되어 클릭 이동이 되고, 그래프
뷰·백링크에도 나타납니다. 답변이 여러 논문에 걸친 상위 수준 synthesis에
기반한 경우, 첫 번째 소스뿐 아니라 기여한 모든 소스 문서를 인용합니다.

선택한 Markdown line range가 첨부된 상태에서 사용자가 해당 텍스트를 고치거나, 다시 쓰거나, 다듬거나, 번역하라고 요청하면 assistant는 `ai-agent-edit` SEARCH/REPLACE 제안을 반환해야 합니다. 선택 영역에 대한 단순 질문이면 파일 수정 제안 없이 답변만 합니다.

최신 요청이 선택한 PDF/text 영역을 예시로 삼아 Markdown 파일 안의 모든 비슷한 부분을 바꾸라고 요청하면, 선택 영역은 유일한 수정 대상이 아니라 pattern을 이해하기 위한 단서로 취급합니다. 플러그인은 prompt에 포함된 Markdown 탭의 전체 내용만 edit-target context로 보내므로 assistant가 파일 전체에서 같은 HTML/Markdown line 형태를 찾고, 기존 문법 형식을 보존한 SEARCH/REPLACE hunk를 Markdown 편집기 안에서 review할 수 있게 제안해야 합니다. 열려 있어도 eye-off인 숨은 탭은 edit target이 아닙니다.

### Markdown 작업 위치 복원

플러그인은 Obsidian을 끌 때 활성 편집 모드 Markdown 파일의 커서와 스크롤 위치를 마지막 작업 위치로 저장합니다. Obsidian을 다시 켜면 workspace layout이 준비된 뒤 그 파일과 위치를 여러 번 재시도해 복원합니다.

마지막 작업 위치는 별도 snapshot으로 저장되며, 파일별 위치 캐시는 보조 기록으로 최대 100개까지 보관됩니다.

---

## 5. PDF 스니핑 (`Cmd+Shift+X`)

PDF 뷰어에서 특정 영역을 마우스로 드래그해 이미지와 그 안의 텍스트를 함께 캡처합니다.

1. PDF 파일을 Incurator 뷰어에서 열기 (`.pdf` 파일을 우클릭 → Open with Incurator)
2. `Cmd+Shift+X` → 스니핑 모드 진입
3. 원하는 영역을 드래그 → 이미지로 캡처됨
4. 캡처된 crop이 채팅 사이드바 컨텍스트에 자동 첨부

> **참고**: 스니핑은 Incurator 전용 PDF 뷰어(`EXTERNAL_PDF_VIEW_TYPE`)에서만 동작합니다.  
> Obsidian 기본 PDF 뷰어에서는 `Cmd+Shift+L`로 페이지 전체를 참조하세요.

Incurator PDF 뷰어는 주변 페이지만 lazy-render하고 scroll 작업을 animation frame당
한 번으로 합칩니다. 따라서 page number 판정과 lazy rendering이 원시 scroll 이벤트마다
반복 실행되지 않습니다.

crop은 페이지 전체가 아니라 **드래그한 사각형 안의 텍스트 라인만**(영역 한정)
캡처합니다. 그 영역 텍스트는 crop의 **primary focus**(질문의 핵심 주제)가 되어,
모델이 전체 페이지 배경 맥락에 묻히지 않고 사용자가 박스로 친 영역에 대해
답하도록 만듭니다. crop은 전체 페이지 텍스트(및 그 RAG hit)를 primary focus에
다시 주입하지 않으며, 전체 페이지는 여전히 배경 맥락으로 별도 제공됩니다.

**크롭이 모델에 전달되는 방식 (v0.28.0).** 메인 채팅 모델이 vision을 지원하면
(Antigravity, Claude, Codex, 또는 vision Ollama 모델) 크롭 이미지가 그 모델에
**직접** 전달됩니다 — 채팅이 스코프드·샌드박스 이미지 채널로 이미지를 읽습니다.
**별도 전사 단계가 없으므로**, Send를 누르면 백엔드 모델이 도는 동안 멈추지 않고
즉시 "Thinking…"이 표시됩니다. 활성 모델이 text-only이면 백엔드 전사로 폴백하여
(LaTeX/영역 텍스트가 답변의 근거가 됨), sidechat은 이미지 세부 정보를 읽을 수 없을
때 그 사실을 모델에 명시하며 crop을 조용히 무시하지 않습니다. 스닙한 영역 텍스트는
항상 캡션으로 함께 전달되므로, 선택 가능한 텍스트가 없는 스캔 크롭도 primary focus로
유지되어 묻히지 않습니다. 최신 메시지에 사용자가 선택한 crop/image가 이미 첨부되어
있으면, 플러그인은 그 로컬 context를 빠른 경로로 사용하고 해당 턴에서는 backend 전체
PDF context/RAG 호출을 건너뜁니다.

---

## 6. PDF 처리 설정

플러그인은 PDF 파일을 컨텍스트로 사용할 때 세 가지 캡처 모드를 제공합니다.

| `pdfCaptureMode` | 설명 |
| --- | --- |
| `text` | PDF 텍스트 레이어만 추출 (빠름, 토큰 효율적) |
| `image` | 페이지를 이미지로 캡처 (비전 모델 필요) |
| `both` | 텍스트 + 이미지 동시 전송 (기본값, 가장 정확함) |

### 추가 PDF 옵션

| 설정 | 기본값 | 설명 |
| --- | --- | --- |
| `pdfWindowRadius` | `1` | 현재 페이지 앞뒤로 포함할 페이지 수 |
| `pdfOutlineEnabled` | `true` | PDF 목차(아웃라인) 컨텍스트 포함 여부 |
| `pdfRagEnabled` | `true` | 전체 PDF 내 RAG 검색 활성화 |
| `pdfRagTopK` | `5` | RAG 검색 상위 결과 수 |
| `pdfVisionFallback` | `true` | text mode 캡처가 scanned-like이거나 쓸 수 있는 텍스트가 없을 때만 이미지 첨부 |
| `pdfFullDocumentIndex` | `true` | PDF 전체 색인 생성 (RAG 정확도 향상) |

PDF context는 다음 순서로 조립됩니다.

1. 로컬 PDF.js 페이지 텍스트와 첨부된 crop/image context. PDF viewer가 충분한
   selectable DOM text를 제공하면 그 텍스트를 빠른 경로로 유지하고 image
   fallback을 트리거하지 않습니다.
2. local viewer text/window/image context가 없을 때 등록되고 L1 완료된
   durable CTX projection context.
3. local context와 사용 가능한 durable projection이 모두 없을 때 read-only
   backend PDF parsing. 이 fallback은 PDF를 등록하지 않습니다.
4. backend PDF context를 사용하는 경우에만, `pdfRagEnabled=true`이고 source가
   tracked 상태일 때 backend 전체 PDF RAG.

PDF 중심 turn에서 Sidechat은 선택하거나 crop한 텍스트 안의 참조뿐 아니라 최신
질문에 명시된 참조도 따라갑니다. 예를 들어 현재 보이는 페이지가 수식 (9)에서
끝나는데 사용자가 `Eq. (10)` 또는 `수식 (10)`을 물으면, 먼저 이미 확보한 page
window를 확인합니다. 정확한 label이 없으면 read-only PDF context service를 통해
인접 페이지를 한 페이지씩 작은 범위로 요청하고(다음 페이지 우선, `radius=0`),
처음 정확히 일치하는 label에서 중단합니다. 제한된 탐색이 끝날 때까지 정확한 label을
찾지 못하면 Sidechat은 fail-closed로 동작하며, 번호만 비슷한 느슨한 search hit를
해결된 대상으로 바꾸지 않습니다. 최신 질문의 자동 lookup은 활성 PDF 또는 동일한
canonical document identity를 가진 primary context로 사용자가 명시적으로 첨부한
PDF에 대해서만 실행됩니다. 단순히 보이거나 pinned background이거나 prompt에 포함된
PDF tab은 Markdown 중심 질문의 참조를 가져갈 수 없습니다. 일치한 페이지는 일반 PDF
window보다 앞선 `<resolved_cross_references>`로 전달됩니다. 외부 Zotero/iCloud PDF는
provider의 native filesystem root 밖에 그대로 두며, provider에는 직접 file access가
아니라 해결된 텍스트만 제공합니다. Sidechat은 Ask AI 팝오버와 동일한
cross-reference resolver를 사용하므로, v0.40.3의 인쇄-물리 페이지 매핑
(label map → 추론된 front-matter offset → 인쇄 머리글 스캔 → 검증된 문자 그대로의
추측, 반증된 페이지에서는 항상 fail-closed)이 Sidechat pointer 해석에도 동일하게
적용됩니다.

content hash나 등록된 source identity가 있으면 sidechat과 quick-query popover는
같은 backend PDF page cache를 공유합니다:
`.cache/pdf_pages/<content_hash>/<page>.txt`. `04_Resources/` 아래의 Reference Mode
stub에는 portable identity만 두고, 절대 로컬 경로와 page text cache는 backend
state/cache에 남겨 macOS와 Linux 기기가 각자의 로컬 PDF 위치를 독립적으로 해석하게
합니다.

채팅 사이드바는 backend PDF context, PDF RAG, Curator query 소요 시간을
developer console에 기록하므로, 느린 턴에서 어느 단계가 막히는지 확인할 수
있습니다.

PDF 채팅과 PDF 지식 정제는 별도 workflow로 취급합니다.

- 열린 PDF에 대한 일반 채팅은 viewer fast path를 사용합니다. durable
  Incurator ingest 없이 현재 페이지, 주변 페이지 텍스트, 선택 텍스트, crop
  image에서 바로 답하고, blocking backend PDF context 호출을 요구하지 않습니다.
- passive chat은 미등록 PDF를 import/register하지 않습니다. 등록은 보라색
  context chip의 명시적인 **Add to Incurator** 동작으로만 수행됩니다.
- 보라색 context chip과 **Add to Incurator**는 durable knowledge refinement를
  시작하는 컨트롤입니다. PDF를 source로 등록하고 instant L1 context를 만든 뒤
  L2/L3 build job을 queue에 넣습니다.
- Queued L2/L3 job은 **Incurator Dashboard > Jobs > Run queued** 또는 CLI
  `wiki jobs run`으로 실행합니다. 이렇게 하면 PDF viewer는 빠르게 유지하고,
  오래 걸리는 LLM-heavy refinement는 명시적인 background 작업으로 분리됩니다.
- Jobs 탭에서는 worker가 아직 claim하지 않은 queued job을 취소할 수 있고,
  완료/실패/취소된 job은 **Rerun**으로 다시 queue에 넣을 수 있습니다.

---

## 7. AI 제공자 설정

Settings 화면에서는 선택된 model의 context window를 별도 항목으로 만들지 않고
**Model** 행의 설명에 함께 표시합니다. 이 값은 provider/CLI의 token 용량이며,
개별 첨부 문서는 전체 model window를 정확히 token 단위로 배정받는 것이 아니라
보수적인 문자 수 guard로 잘립니다.

**비전 추출 모델 (v0.22.0):** PDF 수식 추출은 메인 채팅 모델과 별개의 전용 **비전**
모델을 쓰며, **Incurator Dashboard → LLM Provider** 카드에서 설정합니다. 두 개의 행:

- **PDF ingest 모델(전체 페이지)** — 설정하면 `wiki add`/Add Source가 각 PDF 페이지를
  이 비전 모델로 전사해 L1에 제대로 된 LaTeX가 들어갑니다(텍스트레이어의 근사 추출
  대신). 비우면 빠른 pymupdf4llm 경로 유지.
- **LaTeX/영역 추출 모델(경량)** — 우클릭 **Convert to LaTeX** 액션에서 쓰는 소형
  영역-OCR 모델(그리고 채팅 스닙의 text-only 폴백). 비우면 PDF ingest 모델로 폴백.
  Convert to LaTeX는 backend extractor를 호출하며, extractor는 엄격한
  `<transcription>...</transcription>` 블록을 요청하고 복사 전에 흔한 설명 문구를
  제거합니다. 선택한 본문은 그대로 보존하고 수식은 `$...$` / `$$...$$` LaTeX
  구분자로 변환합니다. Antigravity에서는 backend가 전체 변환 요청을
  `agy --print` 프롬프트로 전달하고 정확히 선택한 `--model`을 적용합니다. 명시적인
  LaTeX 모델 또는 PDF ingest 폴백 모델은 해당 모델이 지원할 때 `low`를 사용하며,
  고정/no-effort 모델에는 effort 플래그를 전달하지 않습니다. 두 전용 행 모두
  비어 있으면 메인 모델 폴백은 사용자가 선택한 effort를 유지합니다. 제공자의 작업
  로그는 변환 결과로 취급하지 않습니다.
  **참고 (v0.28.0):** 메인 채팅 모델이 vision을 지원하면 **Cmd+Shift+X** 채팅 스닙은
  더 이상 이 경로를 타지 않습니다 — 그 모델이 크롭 이미지를 직접 읽습니다(더
  빠르고 이중 왕복이 없음). 이 경량 모델은 채팅 모델이 text-only일 때만 적용됩니다.

**Convert to LaTeX — 메시지의 의미 (v0.52.1).** 이전 버전은 모든 실패에 대해
"Check Incurator Dashboard → LLM Provider"라는 하나의 메시지만 표시했고, 그 때문에
멀쩡한 제공자를 고치러 가게 만드는 경우가 많았습니다. 이제 각 결과가 실제로 무슨
일이 있었는지 말합니다:

| 메시지 | 의미 | 조치 |
|---|---|---|
| `LaTeX copied to clipboard.` | 성공. | — |
| `Reading N unencoded symbol(s) from the page image…` | 정상이며, 보통 성공으로 이어집니다. 선택 영역에 PDF가 텍스트로 인코딩하지 않은 기호가 있어(아래 설명) 해당 영역을 이미지로 읽습니다. | 기다리면 됩니다. |
| `This selection has N symbol(s) the PDF does not encode as text …` | 같은 상황이지만, 그것을 읽기 위한 페이지 이미지를 캡처하지 못했습니다. | 페이지를 화면에 완전히 보이게 스크롤한 뒤 다시 시도하거나, **Cmd+Shift+X**로 스닙하세요. |
| `The model returned an empty transcription for this selection.` | 백엔드는 정상 동작했고, 모델이 쓸 만한 결과를 주지 않았습니다. | 다시 시도하거나, 선택 범위를 넓혀 문맥을 더 포함시키세요. |
| `Converted, but the clipboard write was refused: …` | 변환은 성공했고 클립보드 쓰기만 실패했습니다(보통 포커스 문제). | 창을 클릭한 뒤 다시 시도하세요. |
| `LaTeX conversion failed: <detail> …` | 텍스트 경로에서 발생한 실제 백엔드/제공자 실패이며, 원인 오류가 함께 표시됩니다. | 상세 내용을 확인하고, 제공자를 지목하면 LLM Provider 카드를 점검하세요. |
| `LaTeX conversion failed while reading the page image: <detail>. Nothing was copied.` | 같은 실패이지만 이미지 경로에서 발생했습니다. 클립보드가 그대로라는 점을 분명히 하려고 따로 표시합니다. | 위와 동일합니다. |

**수식이 때때로 이미지 경로를 타는 이유 (v0.52.3).** LaTeX 논문은 기호를 Computer
Modern 폰트 서브셋에 담는데, 그 서브셋에는 `/ToUnicode` 맵이 없는 경우가 많습니다.
맵이 없으면 PDF는 그 글리프가 *어떤 문자인지*를 실제로 기록하지 않고 어떻게 그리는지만
담고 있으므로, pdf.js는 그 자리에 널 바이트를 돌려줍니다. `3D Line Mapping Revisited`
4쪽 수식 (3)의 람다 10개가 전부 그렇게 도착합니다.

이 기호들은 텍스트에서 복구할 수 없습니다 — 애초에 텍스트에 없고, 렌더링된 픽셀에만
존재하기 때문입니다. 그래서 선택 영역에 그런 기호가 하나라도 있으면, Convert to
LaTeX는 해당 영역을 페이지에서 잘라내어 **이미지**를 비전 모델에 보내고, 모델은
그려진 그대로의 수식을 읽습니다. `Reading N unencoded symbol(s) from the page
image…` 메시지가 뜬 뒤 평소와 같은 결과가 나옵니다.

> [!WARNING]
> v0.52.1과 v0.52.2는 이를 잘못 처리했습니다: 텍스트를 그대로 보내려고 그 글리프들을
> 삭제했습니다. 그 결과 모델은 λ가 전부 빠진 수식을 그대로 옮겨 적었고, **잘못된 결과가
> 그럴듯한 모습으로 클립보드에 복사되었습니다.** v0.52.1 또는 v0.52.2에서 수식을
> 복사했다면 다시 확인하세요.

별개로, 숫자만 있는 줄(수식 번호, 표 셀, 페이지 번호)이 더 이상 변환 결과에서
삭제되지 않으므로, 전부 숫자인 선택 영역도 빈 결과 대신 정상 변환됩니다.

ingest 비전은 기존 제공자의 **CLI 구독**(Ollama, 또는 `claude`/`agy`/`codex` CLI)으로
동작 — **추가 API 키 불필요**. 드롭다운에는 비전 가능 모델만 표시됩니다. v0.21.0의
`latexModel` 플러그인 설정을 대체합니다.

플러그인은 Antigravity, Claude, OpenAI Codex, Ollama, DeepSeek를 지원합니다. 설정 탭에서는 제공자와 모델을 따로 조정할 수 있고, 채팅 사이드바 하단에서는 하나의 모델 선택 메뉴에서 `Provider · Model` 형식으로 함께 전환합니다. reasoning/effort 메뉴는 백엔드 카탈로그에서 effort 단계가 선언된 모델에만 표시됩니다.
Antigravity CLI 1.1.5 이상에서 채팅은 선택한 모델을 `--model`로, 선택한
강도를 `--effort`로 전달합니다. 후자는 `gemini-3.6-flash` 같은 base slug를
사용할 때 필수입니다.

> [!NOTE]
> **Incurator Dashboard → Overview → LLM Provider** 카드는 현재 기기의 캐시 설정(`.cache/config/config.yml`)에 Primary/Fallback 모델을 저장합니다. 각 모델 드롭다운 옆에는 **effort 드롭다운**이 함께 표시되며, 선택한 모델이 노출하는 강도만 보여줍니다(강도가 없는 모델은 `—`). Apply 시 Primary/Fallback과 effort 값은 `wiki config`를 통해 저장되므로, 기기별 모델 선택이 동기화되는 vault의 `.curator/settings.yml`로 새지 않습니다. 모델 목록은 플러그인 빌드 시 백엔드의 `data/models.json` 카탈로그(단일 소스)에서 번들링되므로, 모델 이름 표시가 MCP 시작 여부에 의존하지 않습니다.
>
> 모델 드롭다운 아래의 **Ollama models** 섹션은 `data/models.json`의 추천 Ollama 모델을 이 머신 기준으로 보여줍니다. 이미 받은 모델에는 **installed** 배지, `vram_gb`가 감지된 RAM보다 큰 모델에는 **exceeds RAM** 배지가 붙고, 아직 설치되지 않은 모델에는 **Pull** 버튼(`wiki plugin models pull`)이 표시되어 `ollama pull`을 실행하고 새로고침합니다. 덕분에 "로컬 모델로 전환 → 빌드 재개"(Sources 탭의 **Retry errored sources** 버튼 참고) 흐름이 처음부터 끝까지 동작합니다.

### 7.1 Antigravity (기본값)

Antigravity CLI (`agy`)를 통해 Google Gemini 모델에 접근합니다.

```bash
# 로그인
agy login
# 또는 플러그인 내 명령: Login to Antigravity CLI
```

| 모델 | 설명 |
| --- | --- |
| `gemini-3.5-flash` | 기본값. 빠르고 효율적 |
| `gemini-3.6-flash` | 현재의 빠른 Gemini 비전 모델 |
| `gemini-3.1-pro` | 고품질 추론 |
| `claude-sonnet-4-6` | `agy`가 제공하는 고정-thinking Claude variant |
| `claude-opus-4-6-thinking` | `agy`가 제공하는 고정-thinking Opus variant |
| `gpt-oss-120b` | 텍스트 전용 medium-effort 모델 |

`antigravityPrintTimeoutSec`: CLI 응답 최대 대기 시간 (기본 300초)

### 7.2 Claude

Claude Code CLI (`claude`)를 통해 Anthropic 모델에 접근합니다.

```bash
# 로그인
claude login
# 또는 플러그인 내 명령: Login to Claude CLI
```

effort 지원 범위는 모델별로 다릅니다. Sonnet 4.6은 `low` / `medium` /
`high` / `max`, Fable 5와 Opus 4.8은 여기에 `xhigh`를 추가로 지원하며,
Haiku 4.5에는 effort 조절 기능이 없습니다.

| 모델 | 기본 effort |
| --- | --- |
| `claude-sonnet-4-6` | `high` (플러그인 기본값) |
| `claude-fable-5` | `high` |
| `claude-opus-4-8` | `high` |
| `claude-haiku-4-5` | 없음 |

### 7.3 OpenAI Codex

OpenAI Codex CLI (`codex`)를 통해 GPT 모델에 접근합니다.

```bash
# 로그인
codex login
# 또는 플러그인 내 명령: Login to OpenAI Codex CLI
```

`codexReasoningEffort` 지원 범위도 모델별로 다릅니다. Sol과 Terra는 `low` /
`medium` / `high` / `xhigh` / `max` / `ultra`, Luna는 `max`까지, GPT-5.5는
`xhigh`까지 지원합니다. Codex의 `ultra`에서는 작업이 자동 위임될 수 있습니다.

| 모델 | 설명 |
| --- | --- |
| `gpt-5.6-sol` | 기본값. frontier agentic coding (`low` 기본 effort) |
| `gpt-5.6-terra` | 균형 잡힌 일상 agentic coding (`medium` 기본값) |
| `gpt-5.6-luna` | 경량 agentic coding (`medium` 기본값) |
| `gpt-5.5` | 노출되는 호환 모델 (`medium` 기본값) |

### 7.4 Ollama (로컬)

로컬 Ollama 서버에 직접 HTTP로 연결합니다. 인증 없음, 완전 오프라인.

```bash
# Ollama 서버 시작
ollama serve

# 모델 설치
ollama pull qwen2.5:7b
```

설정:

- **Ollama host**: Ollama 서버 주소 (기본값: `http://localhost:11434`)
- **Model**: 설치된 모델 이름 직접 입력 또는 **Fetch models** 버튼으로 목록 조회
- Vision 지원 여부는 모델에 따라 다름 (예: `gemma3:12b` 지원, `qwen2.5:7b` 미지원)

### 7.5 DeepSeek API

DeepSeek의 OpenAI 호환 API에 API 키로 연결합니다. OAuth 또는 브라우저 CLI 로그인은 사용하지 않습니다.

설정:

- **API key**: 플러그인 설정에 기기 로컬 키를 저장하거나, 비워둔 뒤 Obsidian 프로세스 환경의 `DEEPSEEK_API_KEY`를 사용합니다.
- **Model**: 백엔드 카탈로그에서 선택합니다. 2026-06-01 기준 현재 DeepSeek API 모델 ID는 `deepseek-v4-flash`, `deepseek-v4-pro`입니다.
- `deepseek-chat`, `deepseek-reasoner`는 DeepSeek가 2026-07-24 폐기 예정으로 안내한 legacy alias이므로 기본 선택지로 권장하지 않습니다.

어떤 provider에서든 quota 또는 capacity 오류가 발생하면 sidechat에 명확히 표시되어 사용자가 provider/model을 바꾸거나 fallback을 설정할 수 있습니다. CLI provider(예: Antigravity `agy`)가 **답변 없이** 끝나는 경우 — 예를 들어 `Thinking…` 이후 토큰/quota 소진이나 타임아웃 — 이제 무한 스피너나 빈 말풍선 대신 **명확한 에러**를 표시합니다.

Antigravity `agy` print mode는 일반적으로 최종 답변을 stdout에 쓰고
진행/상태 줄은 stderr에 씁니다. CLI가 성공적으로 종료되었지만 stdout이
비어 있고 stderr에 상태가 아닌 답변 텍스트가 있으면, 플러그인은 그
텍스트를 assistant 답변으로 복구합니다. `Thinking…`, 모델 시작, MCP 상태
같은 순수 진행 stderr는 thinking/status 블록 안에만 숨기며 답변으로
취급하지 않습니다.

### 인증 상태와 로그아웃(Sign out)

각 provider의 **Authentication** 행은 현재 상태를 보여줍니다.

- **DeepSeek**은 플러그인에 저장된 키(`✓ API key configured (saved in plugin)`)와 환경 변수로 제공된 키(`✓ Using DEEPSEEK_API_KEY from environment`)를 구분합니다. 저장된 키는 플러그인 `data.json`에 있고 `.curator`에 있지 **않으므로**, `.curator` 삭제나 `wiki reset`으로는 지워지지 않습니다 — **Sign out**으로 제거하세요. 명령 팔레트의 **Check DeepSeek API Key**는 저장된 플러그인 키 또는 `DEEPSEEK_API_KEY`가 보이는지 확인하며, 브라우저 로그인 흐름을 실행하지 않습니다.
- **CLI provider**(Antigravity, Claude, Codex)는 각자의 CLI로 인증합니다. 플러그인은 CLI 파일에서 읽을 수 있을 때만(Codex) 계정 이메일을 표시합니다. Antigravity `agy` 1.0.5는 세션을 OS 키체인에 보관하고 계정 조회 명령이 없어, 플러그인은 계정을 추측하지 않고 중립적인 `agy CLI session`으로 표시합니다.
- **Sign out**은 플러그인이 제어할 수 있는 것(캐시된 자격증명, 저장된 DeepSeek 키, 플러그인이 읽을 수 있는 자격증명 파일)을 정리합니다. CLI provider는 실제 세션을 자체 키체인/설정에 보관하므로, 완전한 로그아웃은 provider CLI(`agy`, `claude`, `codex`) 실행이 추가로 필요할 수 있습니다 — 해당되는 경우 Sign out 알림이 안내합니다.

---

## 8. MCP 서버 설정

플러그인이 외부 MCP 도구를 사용하도록 설정할 수 있습니다. 이 섹션은
Incurator 자체가 아니라 외부 도구 서버와 외부 agent 연동을 위한 것입니다.
같은 기기 안의 Incurator backend 연동은 `wiki mcp`를 띄우지 않고 backend
command를 사용합니다.

**설정 > AI Agent > MCP Servers**에서 서버를 추가합니다.

```json
{
  "name": "my-external-tools",
  "command": "example-mcp-server",
  "args": [],
  "env": {
    "VAULT_ROOT": "/path/to/your/vault"
  },
  "enabled": true
}
```

> **주의**: `VAULT_ROOT`는 반드시 Vault 경로(`.curator/`가 있는 곳)를 가리켜야 합니다.  
> Wiki 시스템(Incurator 코드) 경로나 testbed 경로를 설정하지 마세요.

### 툴 호출 와이어 포맷 (DeepSeek / Ollama)

MCP **서버 전송 계층**은 플러그인 내부에 native(JSON-RPC over stdio)로 구현돼 있으며
provider 중립적입니다. 플러그인이 HTTP provider(DeepSeek·Ollama)를 상대로 자체 에이전트
루프를 돌리며 MCP 툴을 모델에 넘길 때는 해당 provider의 `/v1/chat/completions`
엔드포인트로 통신합니다.

모델에 보이는 function name은 정리된 transport 식별자입니다. 구두점이나 이름 안의
separator 때문에 서로 다른 도구가 같은 정리된 이름이 되더라도, 플러그인은 각 server의
원래 tool name으로 돌아가는 명시적 map을 유지합니다. server를 재시작하거나 중지하면
진행 중 요청은 reject되며, 이전 process의 늦은 exit가 재시작된 server를 offline으로
표시할 수 없습니다. 또한 이전 process에서 늦게 도착한 stdout byte는 재시작된 server의
새 JSON framing buffer에 들어갈 수 없습니다.

**2026-06-05 기준**, 이 툴 호출 교환은 **OpenAI-호환 chat-completions 규약**(`tools`,
`tool_calls`, `role: "tool"`, 그리고 tool-call 턴의 빈 `content`는 빈 문자열)을
따릅니다. 이는 OpenAI사에 대한 종속이 **아니라**, DeepSeek와 Ollama가 스스로 노출하는
와이어 프로토콜입니다 — 현재 그 서버들이 받아들이는 유일한 요청 형태입니다. 자체 native
툴 스키마를 가진 provider(Anthropic Claude, Google Gemini/Antigravity)는 별도 어댑터를
쓰므로 영향받지 않습니다. 향후 DeepSeek/Ollama가 받는 스키마를 바꾸면 OpenAI-호환
어댑터만 갱신하면 됩니다.

---

## 9. Incurator 연동

`incuratorEnabled: true`로 설정하면 플러그인이 Curator 백엔드와 연동됩니다.

### 동작 방식

```text
채팅 메시지 입력
      │
      │ (Incurator 연동 활성화 시)
      ▼
IncuratorClient가 숨겨진 backend JSON command 호출
(`wiki plugin source ...`, `wiki plugin pdf ...`, `wiki plugin context fetch`,
`wiki plugin context expand`, `wiki plugin context verify`,
`wiki plugin context feedback`, `wiki plugin query`)
      │
      ▼
추적 가능한 DAG 근거를 시스템 컨텍스트로 주입
      │
      ▼
LLM이 검색된 근거를 바탕으로 답변 생성
```

### Incurator 연동 설정

| 설정 | 기본값 | 설명 |
| --- | --- | --- |
| `incuratorEnabled` | `true` | Curator 백엔드 연동 활성화 |
| `incuratorRepoPath` | `""` | **선택적 override.** Incurator 저장소 절대 경로. 보통 비워둡니다 — 백엔드가 `wiki plugin version`으로 자기 저장소 경로를 보고합니다. 자동 감지된 경로를 덮어쓰고 싶을 때만 설정하세요. |
| `incuratorDefaultDestination` | `04_Resources` | PDF reference stub 또는 명시적 copy import의 기본 폴더 |
| `incuratorDefaultImportMode` | `reference` | 파일 추가 방식 (`reference`는 link stub 생성, `copy`는 vault 안으로 복사) |
| `incuratorPdfAssetFolder` | `""` (비어 있음) | Zotero가 아닌 add-source PDF에서 추출된 이미지를 저장할 vault 기본 폴더. 각 PDF는 정리된 source-name 하위 폴더를 사용합니다. 비어 있으면 백엔드 기본값 `05_Assets/<source-name>/`을 사용합니다. Zotero PDF는 이 설정을 무시하고 import profile의 asset 폴더를 사용합니다. |
| `incuratorStatusPolling` | `true` | 소스 처리 상태 폴링 활성화 |

Zotero나 다른 외부 위치에서 열린 PDF의 **Add to Incurator** 기본 동작은
Reference Mode입니다. backend는 PDF를 원래 위치에 두고 `04_Resources/` 아래에
작은 markdown reference stub만 만들며, 실제 PDF 경로는 기기별 backend source
metadata로 저장합니다. 자동 생성 stub에는 기본적으로 PDF 절대 경로를 넣지 않으므로,
Zotero나 외부 PDF의 로컬 위치가 다른 기기에도 안전하게 동기화할 수 있습니다. PDF를
vault 안으로 복사하는 동작은 기본값이 아니라 명시적 예외입니다.

성공적으로 등록된 소스 — `Queued`, `Building...`, L1 ready부터 전체 L4 Synthesis까지의
모든 상태 — 는 import가 아닌 badge로 표시됩니다. ready 상태는 단일 **Added** badge로
접힙니다(v0.5.6). `Queued`와 `Building...`은 백그라운드 build가 도는 동안 기존
라벨을 유지합니다. 이 등록된 상태들의 badge는 모두 비활성입니다: 클릭해도 아무 동작이
없으므로 이미 등록된 소스를 실수로 다시 import할 수 없습니다. badge에 마우스를
올리면 tooltip에서 정확한 layer 상태를 확인할 수 있습니다. 이후 상태 갱신에서 소스가
`stale`, `moved`, `changed`, `missing`, `error`로 재판정되면 badge는 해당 actionable
라벨로 돌아가 다시 클릭 가능해집니다. 어떤 layer라도 error이면 정상 badge 대신 error를
표시합니다.

### Setup/Rebuild 배너

Incurator 백엔드와 Obsidian 플러그인은 기기마다 다른 시점에 rebuild될 수 있습니다.
`./setup.sh`는 backend/plugin 공통 build fingerprint를 기록합니다. 플러그인은
`wiki plugin version`을 확인할 때 backend fingerprint와 설치된 plugin bundle에
포함된 fingerprint를 비교합니다.
생성된 backend manifest가 없더라도 `wiki plugin version`은 backend/plugin version,
git commit key, schema metadata를 담은 안정적인 `build` 객체를 반환하므로 update
check가 빈 객체 때문에 실패하지 않습니다.

fingerprint가 없거나 서로 다르면 채팅 창 상단에 setup/rebuild 배너를 표시합니다.
단, 업데이트할 저장소 경로가 있을 때만 표시됩니다. 플러그인은 저장소 경로를 다음
순서로 결정합니다: 선택적 `incuratorRepoPath` override → 백엔드가
`wiki plugin version`으로 보고한 경로(`repo_path`) → 없음. 백엔드가 저장소가 없는
일반(non-editable) 설치이면 `repo_path`가 `null`이 되어 배너를 숨기므로, 동작하지
않는 업데이트 버튼이 뜨지 않습니다.

업데이트 버튼을 누르면 `<repo>/plugin/`에서 새로 빌드된 `main.js`,
`manifest.json`, `styles.css`를 **현재 열린 vault**의 플러그인 디렉토리로
복사합니다. `git pull`이나 `./setup.sh`를 실행하지 않습니다 — 백엔드와 플러그인
빌드는 업데이트를 pull한 뒤 직접 실행하는 `./setup.sh`의 역할입니다. 다른 vault는
다음에 열릴 때 각자 업데이트됩니다. 필요한 plugin artifact가 모두 성공적으로
복사되면 버튼은 **Reload Obsidian**으로 바뀌며, 새 bundle을 활성화하는 renderer
reload를 실제로 수행합니다.

Obsidian이 열린 상태에서 `./setup.sh`, Syncthing, 또는 다른 외부 배포가 plugin 파일을
교체해도 메모리에서는 이전 bundle이 계속 실행됩니다. AI provider를 시작하기 전에
plugin은 현재 실행 중인 bundle build identity와 디스크에 설치된 bundle을 비교합니다.
둘이 다르면 stale code로 질문을 실행하지 않고 reload를 요구합니다. 따라서 보안 또는
provider hotfix가 디스크에는 설치됐지만 구 runtime이 계속 답변하는 상태를 허용하지
않습니다.

`Use Incurator backend`는 local Incurator backend command 사용 여부를 제어합니다.
켜면 plugin이 `wiki` 실행 파일을 찾고, backend runtime snapshot을 읽으며, source,
PDF, query, promotion, Zotero 작업에 숨겨진 `wiki plugin ...` JSON command를
호출합니다. 범용 MCP Servers 섹션은 다른 MCP 서버를 관리할 때만 사용합니다.
같은 기기 안의 backend 접근을 위해 Incurator MCP를 자동 시작하지 않습니다.

### PDF → Curator 등록 흐름

Incurator 연동이 켜진 상태에서 PDF를 참조하면:

```text
Cmd+Shift+L (또는 Cmd+Shift+X)으로 PDF 캡처
      │
      │ backend source registration command 실행
      ▼
Curator 백엔드에 소스 등록
      │
      │ L1 → L2 → L3 처리 (백그라운드)
      ▼
agent가 필요로 할 때 workspace curation이 L4를 생성/갱신할 수 있음
      │
      ▼
이후 search_curator로 검색 가능
```

보라색 PDF chip은 refinement 컨트롤입니다. **Add source**를 눌러도 전체 DAG가
끝날 때까지 기다리지 않습니다. source 등록, L1 생성, L2/L3 queue까지만 수행합니다.
queue에 들어간 build 작업을 실제로 처리하려면 **Dashboard > Jobs > Run queued**를
누르거나 `wiki jobs run`을 실행합니다. queued job은 worker가 claim하기 전에
취소할 수 있고, 완료/실패/취소된 job은 **Rerun**으로 다시 queue에 넣을 수
있습니다. 소스가 추적되기 시작하면 chip에는 위에서 설명한 비활성 **Added**
badge가 표시됩니다.
backend 등록은 성공했지만 search-index refresh 같은 non-fatal maintenance 단계가
건너뛰어진 경우, backend는 등록을 실패시키지 않고 `warnings` 배열에 경고를 담아
반환합니다.

추가된 PDF에 포함된 이미지(figure, diagram)는 즉시 L1 단계에서 추출되어 vault에
저장되고, 생성된 L1 context 페이지가 `![[...]]` 링크로 임베드합니다. 저장 위치는
다음과 같습니다(v0.5.6):

- **Zotero 기반 PDF**는 매칭되는 Zotero import profile의 asset 폴더(annotation
  이미지가 쓰는 것과 같은 base 폴더 + item별 subfolder)를 재사용하므로, 논문의
  추출 figure가 annotation asset 옆에 놓입니다.
- **그 외 PDF**는 `incuratorPdfAssetFolder` 기본 폴더 아래의 정리된
  source-name 하위 폴더로 갑니다.
- **Fallback** (설정이 비어 있거나, 결정된 폴더가 안전하지 않거나 경로를
  해석할 수 없거나 vault를 벗어나는 경우): 백엔드 기본값
  `05_Assets/<source-name>/`.

L1 페이지는 항상 이미지가 실제로 기록된 폴더를 링크하므로 어느 경우든 임베드가
해석됩니다. PDF의 수학 표기 텍스트 추출은 근사적이라는 점에 유의하세요. 수학
충실도 개선(VLM 보조 추출)은 이 asset-routing 기능이 아니라 RAG & Knowledge
Quality Stabilization 프로그램에서 별도로 추적합니다.

최신 사용자 턴에 primary selected text, line range, PDF page, crop image가
첨부되어 있지 않은 일반 workspace/domain 질문에서는 sidechat이 기본적으로
`wiki plugin context fetch`를 호출합니다. 반환된 ContextService pack은 provider
context에 evidence item으로 들어가며, Sources & Trace는 `pack_id`, snapshot,
budget, omission, locator, expansion handle, verification handle을 표시할 수
있습니다. sidechat은 backend synthesized answer를 기본적으로 주입하지 않습니다.
`wiki plugin query`는 명시적 backend synthesis 경로로 남아 있으며 compatibility를
위해 trace/provenance 필드를 계속 반환합니다. 최신 턴이 선택 crop이나 editable
Markdown 영역에 집중된 경우에는 workspace pack을 건너뛰고 해당 선택 context에서
답합니다.

Zotero PDF는 기본적으로 Reference Mode로 등록됩니다. 생성되는
`04_Resources` reference stub은 로컬 PDF 절대경로를 쓰지 않고 Zotero
attachment key와 `zotero://open-pdf/library/items/<key>` 링크 같은 portable
identity를 기록합니다. 실제 로컬 PDF 경로는 backend source metadata에만
저장됩니다.

대시보드의 **Reset** 작업은 로컬 DB와 생성된 L1-L4 콘텐츠를 지우기 전에 두 번 확인합니다.

Dashboard 상태는 plugin 자체 상태가 아니라 repo-cache `runtime/` 아래의
backend-owned local snapshot에서 옵니다. 해당 JSON 파일은 backend만 쓰고, plugin은
source count, job 상태, index health, backend version을 표시하기 전에 local backend에
refresh를 요청합니다. snapshot이 없거나 오래된 경우에는 backend가 비었다고 해석하지
않고 waiting/unknown 상태로 표시합니다. Runtime `status.json`과 `sources.json`은
절대 local path를 export하지 않습니다. model GGUF 파일, Zotero root, external
reference 위치 같은 기기별 path는 repo-local `.cache/config/config.yml`에 남기고,
plugin이 실제 local resolution이 필요할 때 backend command를 통해 참조합니다.

dashboard 버튼은 상태 변경이 필요할 때 backend command를 실행하며, plugin은 이
작업을 위해 backend-owned `.curator` 상태를 직접 수정하지 않습니다. Overview의 주
액션은 **Update**(한 번에 처리하는 `wiki update`: add → build → embed → sync)이고,
세부 단계인 **Add / Build / Sync / Lint / Reindex / Reset**은 **Advanced** 접이식
영역으로 옮겼습니다. 정확한 CLI 동작과 flag는 canonical
[CLI Reference](USER_GUIDE_KR.md#cli-reference)를 기준으로 합니다. LLM Apply와
Persona Save는 설정을 저장합니다.

중단된 subprocess가 무한히 대기하거나 메모리를 제한 없이 늘리지 않도록 backend
command에는 경계가 적용됩니다. 일반 metadata/search/config 작업은 최대 2분과 결합
output 16 MiB를, pipeline/import/model download/job 작업은 최대 60분과 64 MiB를
허용합니다. 경계에 도달하면 process를 중지하고 눈에 보이는 실패를 보고합니다. 긴
작업은 일반 command 한도에 의해 잘리지 않고 더 큰 전용 policy를 사용합니다.

### 대시보드 탭 (v0.3.3)

- **Overview → System** 카드는 DB-native 검색 엔진과 함께 현재 **Embed model**,
  **Reranker** 행(정체성 + health, backend `search_models` 상태 기반)을 보여줍니다.
  두 행 중 하나를 클릭하면 로컬 검색 모델을 재준비합니다
  (`wiki plugin models refresh` → 필요 시 Qwen3 GGUF 다운로드 / `llama-cpp-python`
  설치 / Ollama 기동). `· not downloaded` / `· runtime missing` 접미사는 비정상
  모델을 표시합니다.
- **Traces** 탭은 현재 Obsidian vault의 durable `QTR-` query trace 목록을
  vault-local backend command runner로 보여줍니다 (`wiki plugin trace list`).
  항목을 선택하면 별도의 backend detail view를 로드해 route, latency, intent/mode,
  degradation/`fallbackMode`, warnings, evidence, 사용 가능한 RRF/rerank
  contribution 데이터를 표시합니다 (`wiki plugin trace show`).
- **Synthesis** 탭은 현재 vault의 최근 L4 `SYN-` node 목록을 보여줍니다
  (`wiki plugin synthesis list`). 항목을 선택하면 community report, graph
  entity/relation, source span, prompt trace, grounding/staleness warning이
  포함된 read-only L4→L1 audit chain을 로드합니다
  (`wiki plugin synthesis show`).
- **Sources** 탭은 최근 소스를 L1–L4 단계별 상태 badge와 함께 보여줍니다. 빌드가
  에러로 멈춘 경우(예: *"Antigravity capacity exhausted (429)"*) 탭 상단에
  **Retry errored sources** 버튼이 나타납니다. 동작하는 모델로 전환한 뒤(설정 →
  LLM Provider, 또는 Overview의 LLM Provider 카드) 이 버튼을 누르면 재개됩니다.
  내부적으로 `wiki build`를 실행하여 L2/L3가 아직 `pending`이거나 `error`인 모든
  소스를 현재 provider로 다시 시도하므로, 지식 정제 그래프가 멈춘 지점부터 이어집니다.
  L4 **Skipped** badge는 실패가 아닌 terminal 상태입니다. global L3/L4가 끝났지만
  현재 community-report corpus에 eligible shared synthesis가 없다는 뜻입니다. 진행
  상황은 **Jobs** 탭에서 확인합니다.
- **Insights** 탭은 현재 Obsidian vault의 대기 중인 파생 insight 후보 목록을
  보여줍니다 (`wiki plugin insight list`). 항목을 선택하면 먼저 backend detail
  payload를 로드한 뒤(`wiki plugin insight show`) **Promote**(`insight promote`,
  `02_Wiki/`에 기록), **Reject**(`insight reject`) 액션을 제공합니다. 승급/거부는
  항상 명시적인 사용자 액션이며 backend가 자동 승급하지 않습니다.

Zotero 검색, metadata refresh, PDF path resolution, annotation loading, source
status/import/rebind, PDF context/search, query, promotion은 숨겨진
plugin-local backend API(`wiki plugin ...`)를 사용합니다. 따라서 durable backend
상태 변경과 로컬 filesystem/database 해석은 backend 코드가 담당하고, plugin은
Incurator MCP tool discovery 없이 JSON 결과만 받습니다. 이 plugin plumbing은 일반
사용자가 쓰는 `wiki` 명령 표면에는 노출하지 않습니다.

---

## 10. 동기화 주의사항

### 기기 간 지식 자동 동기화 (Syncthing)

**지식 DB 자동 동기화** 설정이 켜져 있으면(기본값), 플러그인이 Syncthing으로 vault를 공유하는 모든 기기에서 지식 베이스를 자동으로 맞춰 줍니다 — 수동 내보내기/가져오기가 필요 없습니다.

- **트리거**: Obsidian이 열릴 때 1회(열 때 자동 동기화), Syncthing이 피어 파일을 전달했을 때 실시간 감지(수신 동기화 데이터 감시 — 데스크톱 전용), 60초 안전 폴링, 수동 **Sync Knowledge DB** 리본 버튼. 백엔드가 이 기기의 내보낸 스냅샷 파일명을 알려 준 뒤에는 watcher가 해당 자기 파일을 수신 피어 데이터로 취급하지 않고 무시합니다. 감시 디렉터리가 삭제·이름 변경되거나 접근할 수 없게 되면 플러그인은 처리되지 않은 Electron 예외를 발생시키는 대신 watcher 오류를 로그에 남기며, 60초 폴링이 계속 안전망 역할을 합니다.
- **한 번의 동기화가 하는 일**: 백엔드에서 `wiki db autosync`를 실행 — 다른 모든 기기의 스냅샷(`.curator/sync/dev-<id>.jsonl`)을 가져오고, Syncthing `*.sync-conflict-*` 파일을 병합한 뒤, 변경이 있으면 자기 스냅샷을 씁니다. 무거운 작업은 모두 백엔드 서브프로세스에서 실행되어 Obsidian UI가 멈추지 않습니다.
- **거부된 row는 항상 보고됩니다 (v0.50.0)**: peer의 snapshot이 잘렸거나 손상되면
  데이터베이스가 해당 row를 거부합니다. 이런 row는 별도로 집계되며 절대 "new"로
  세지 않고, 플러그인이 그 개수를 알리는 notice를 띄웁니다. **sync 알림을 꺼둔
  경우에도** 표시되는데, 이는 일상적인 진행 상황이 아니라 도착하지 못한
  데이터이기 때문입니다. 파일의 나머지 row는 그대로 가져오므로 잘못된 row 하나가
  그 기기의 동기화를 막지 못합니다. 해결하려면 다른 기기에서 다시 export하세요.
- **병합 안전성**: portable source key로 기기별 숫자 id를 remap하고, 행 단위
  monotonic Last-Write-Wins + tombstone을 사용하므로 동시 읽기와 서로
  다른 source 편집은 안전하고, 동일 record 편집은 더 최신 행으로
  해소됩니다. 복합 tombstone은 검증된 canonical JSON에 모든 키 필드를
  저장하고, source 범위 tombstone은 로컬 id 대신 portable source key를
  사용합니다. 같거나 더 최신 tombstone은 오래된 행을 막고, 더 최신인
  mutable 행만 이전 tombstone을 제거한 뒤 병합됩니다. 복합 기본 키는 모든
  키 열을 함께 비교하고, 피어가 새
  `export_id`의 전체 스냅샷을 보내더라도 동일한 행은 건너뛰므로 변경 없는
  스냅샷이 재내보내기 ping-pong을 만들 수 없습니다. 삭제도 전파되며 파일
  통째 덮어쓰기는 없습니다.
- **피드백**: 실행 중 상태 표시줄 `⟳ Sync`, 그리고 실제로 변경이 적용됐을 때만 토스트 알림(동기화 변경 알림).

백엔드가 손상된 동기화 상태, 피어 가져오기, tombstone 삭제 또는 충돌 파일
처리 오류를 보고하면 플러그인은 **Sync Failed**로 표시합니다. 해당 실행은
병합 완료 토스트를 보여 주거나 실패한 충돌 파일을 처리 완료로 세지 않으며,
원본 파일과 상태를 보존해 다음 실행에서 안전하게 재시도할 수 있게 합니다.

모든 기기는 같은 JSONL schema version을 사용해야 합니다. v13으로
업그레이드한 뒤 각 기기가 새 snapshot을 내보내며, v12 snapshot은 일부만
적용하지 않고 건너뜁니다. 지원하지 않는 raw 복합 tombstone은 동기화를
명확히 실패시키고 운영자 검토를 위해 그대로 보존됩니다.

Source layer 상태는 source row 전용 `updated_at` revision을 사용하므로 L1-L4
상태만 바뀐 경우도 LWW 동기화에 포함됩니다. Dashboard Knowledge Graph 수치는
stale Collection projection 파일이 아니라 serving DB record에서 계산합니다.
기기 로컬 backend 설정(`llm`, `search`, `external` root/model path)은 현재
기기의 repo-local `.cache/config/config.yml`에서만 읽습니다. synced
`.curator/settings.yml`에 해당 block이 남아 있으면 backend가 무시하므로
Linux/macOS 경로가 서로를 덮어쓰지 않습니다.
Zotero profile 저장은 직렬화되며 atomic commit 경계에서 제공된 canonical
text를 병합하므로 stale 기기의 무관한 설정 저장이 peer-only profile을
지우지 않습니다.
부분적으로 손상된 decoded payload에 `profiles` 또는 `recentItems`가 없으면,
merge는 crash하지 않고 해당 property를 빈 배열로 취급합니다.

| 설정 | 기본값 | 효과 |
| --- | --- | --- |
| 지식 DB 자동 동기화 | 켜짐 | 모든 자동 동기화 동작의 마스터 스위치 |
| Obsidian 열 때 자동 동기화 | 켜짐 | vault 로드 시 1회 동기화 |
| 수신 동기화 데이터 감시 | 켜짐 | `.curator/sync/`의 피어 스냅샷을 `fs.watch`로 감시하고 확인된 자기 스냅샷은 무시(데스크톱) |
| 동기화 변경 알림 | 켜짐 | 변경이 적용됐을 때만 토스트 |

> [!WARNING]
> 플러그인의 **Enable Incurator** 마스터 스위치를 끄면 그 기기의 플러그인 측
> 자동 동기화 트리거도 전부 꺼집니다. CLI 위주 기기라면 문제없습니다 —
> v0.30.0부터 백엔드가 변경을 일으키는 모든 CLI 명령
> (`wiki add`/`build`/`sync`/`update`, `auto_sync.enabled` 기본 켜짐) 후에 이
> 기기의 스냅샷을 내보내기 때문입니다 — 하지만 플러그인도 안 돌리고 CLI로
> 변경도 하지 않는 기기는 새 지식을 피어에게 영영 발행하지 않게 됩니다.

> [!NOTE]
> 로컬 DB/runtime/staging/temp는 repo `.cache/vaults/<vault-key>/`에
> 저장됩니다. device id와 peer
> high-water mark는 vault 밖의
> `.cache/config/sync_state/<vault-root-hash>.json`에 저장되고,
> `.curator/sync/`의 JSONL 스냅샷만 기기 간 이동합니다. 사용자 가이드
> "기기 간 지식 동기화"와 동기화 무시 가이드를 참고하세요.

### 세션 히스토리 (sessions.json)

플러그인 데이터는 다음 파일들로 분리 저장됩니다.

| 파일 | 내용 | 기기 간 동기화 |
| --- | --- | --- |
| `data.json` | 설정(provider, model, MCP 서버 등) | 경로가 같을 때만 권장 |
| `.curator/sessions.json` | 채팅 대화 히스토리 | 가능 |
| `.curator/zotero_profiles.json` | Zotero import profile + 최근 항목 LRU (v0.30.0) | 가능 |
| `<repo>/.cache/vaults/<vault-key>/runtime/*.json` | backend dashboard/status snapshot | 로컬 전용 |

v0.2.1에서는 `sessions.json` 저장 시 디스크의 최신 파일을 다시 읽고 세션 id 단위로 병합합니다. 따라서 Linux와 macOS에서 서로 다른 채팅 세션을 만들면 두 세션이 함께 보존됩니다. 삭제된 세션은 `deletedSessionIds` tombstone에 남아 Syncthing 지연으로 오래된 파일이 도착해도 되살아나지 않습니다. 단, 같은 세션을 양쪽에서 동시에 편집한 경우에는 더 최신 `updatedAt`을 가진 세션이 이깁니다.

v0.40.0부터 session load는 canonical file이 실제로 없는 경우와 corrupt 또는
unreadable 상태를 구분합니다. Legacy/default migration은
`.curator/sessions.json`이 missing일 때만 허용됩니다. 파일이 존재하지만 parse하거나
읽을 수 없으면 원본 byte를 그대로 보존하고, 현재 plugin 실행 동안 session store를
read-only로 유지하며, 파일을 repair/restore한 뒤 Obsidian을 reload하라는 notice를
표시합니다. Load 이후 save 전에 파일이 corrupt해진 경우에도 덮어쓰지 않고 save를
중단합니다. 기존의 정상 session과 Zotero profile file은 직렬화된 save에서
Obsidian의 atomic process callback이 제공한 canonical text를 parse·merge하므로,
commit 직전에 도착한 peer update나 삭제 tombstone도 보존됩니다. Commit이
성공한 뒤에만 in-memory state를 갱신합니다. 일시적인 process 실패는 해당
save만 실패시키며 정상 data를 corrupt로 잘못 표시하지 않습니다. 첫 생성은
sibling temp file과 rename을 사용할 수 있고, temp write/rename 실패 시 sibling을
정리하여 일부 JSON을 게시하지 않습니다. Obsidian portable adapter에는
동시 첫 생성을 위한 create-if-absent 보장이 없으므로 해당 경우까지 conflict-free로
보장하지는 않습니다.

세션 동기화가 PDF/Zotero의 절대경로까지 portable하게 만드는 것은 아닙니다. 채팅
메시지에 붙은 context는 Zotero attachment key, file hash, vault-relative path,
page number 같은 portable identity를 보존할 수 있지만, macOS나 Linux에서 캡처된
기기별 절대경로는 사용 전에 현재 기기 기준으로 검증하거나 다시 해석합니다. 플러그인은
첫 저장이나 legacy migration 경로를 포함해 `sessions.json`을 쓸 때마다 저장 직전에
session data를 sanitize하므로, 캡처된 absolute source path가 동기화되는 채팅
히스토리로 남지 않습니다. Runtime backend `status.json`과 `sources.json` snapshot도
쓰기 전에 path-sanitize됩니다. 동기화된 세션이 Zotero PDF를 가리키는 경우에는 현재
기기의 로컬 Zotero database와 linked attachment root를 사용해 실제 PDF 경로를
복구합니다.

사이드바 대화 목록의 채팅 제목은 첫 사용자 질문 뒤에 나온 첫 assistant 답변에서
생성합니다. 이때 추론 모델의 `<think>…</think>` 블록을 먼저 제거해, 제목이
`<think>`/`<thinking>` 같은 글자가 아니라 실제 답변을 요약하도록 합니다(닫히지
않은 추론 블록은 통째로 버립니다). 아직 답변이 끝나지 않은 동안에는 첫 사용자
질문을 임시 제목으로 사용합니다. 각 행에는 `updatedAt` 기준의 마지막 활동 시간이
`12m ago`, `3h ago`처럼 현재 시각 기준 상대 시간으로 표시됩니다.

사이드바의 휴지통 버튼으로 채팅 세션을 삭제하면 별도 확인 없이 즉시 삭제됩니다. 삭제 기록은 `deletedSessionIds` tombstone으로 남아 동기화된 다른 기기에서 해당 세션이 되살아나지 않게 합니다.

backend 실행 경로나 repo 경로가 기기마다 다르거나 한쪽 기기에 Incurator가 설치되어
있지 않다면, `.cache/config/devices.json`이 현재 기기의 local override 역할을 합니다.
동기화된 `data.json`에 `incuratorRepoPath`가 들어 있더라도, 시작 시 플러그인은
현재 기기의 `.cache/config/devices.json` 안 `backend.repo_path`가 비어 있지 않으면 그
값으로 메모리상의 repo path를 교체합니다. plugin-local 설정 전체를 동기화하지
않고 싶다면 `.stignore`에는 `sessions.json` 대신 `data.json`을 추가합니다.

```text
.obsidian/plugins/incurator-obsidian-agent/data.json
```

`Backend command`를 `wiki`로 두면 plugin은 repository path에서
`<repo>/.venv/bin/wiki`를 해석합니다. 전역 PATH의 `wiki`는 실행하지 않습니다.
repository가 vault workspace의 sibling이면, 예를 들어 `Workspace/second_brain`
옆의 `Workspace/Incurator`이면 desktop plugin은 이 경로를 plugin `data.json`에
쓰지 않는 memory-only local hint로 사용할 수 있습니다. 그 외의 경우 각 기기에서
**Settings > AI Agent > PDF & Incurator**를 다음처럼 설정합니다:

| 설정 | 값 |
| --- | --- |
| `Repository path (override)` | `/Users/<you>/Workspace/Incurator` |
| `Backend command` | `wiki` |
| `Backend arguments` | `[]` |

Obsidian plugin은 시작 시와 설정 저장 후에 Syncthing이 공유 중인 device 목록과 현재 기기의 backend launcher/repository hint를 `.cache/config/devices.json`에 자동 기록합니다. 이 registry는 동기화된 `data.json`의 절대 경로가 현재 기기의 runtime path를 덮어쓰지 않게 하면서 Linux/macOS 설정 차이를 서로 확인하는 용도로 사용할 수 있습니다. Dashboard는 현재 Syncthing 공유 폴더 registry에 있는 모든 device를 표시하며, 현재 기기에 backend launcher가 없는 원격 device도 숨기지 않습니다. 각 device에는 동기화 중인 Vault/Zotero 폴더 이름을 표시하고, 현재 기기는 가능하면 Syncthing local REST `myID`로 식별하고, 그게 없으면 기기별 repository path/backend launcher hint로 식별해 **This device**로 표시합니다. platform 정보가 없으면 추측하지 않고 unknown으로 표시합니다. `wiki devices sync`는 자동 갱신이 실패했을 때 쓰는 수동 복구 명령이고, `wiki devices`는 현재 registry를 확인하는 명령입니다.

자세한 동기화 설정은 [SYNC_IGNORE_GUIDE_KR.md](SYNC_IGNORE_GUIDE_KR.md)를 참조하세요.

### 외부 PDF 재시작 동작

열린 외부 PDF의 해석된 절대 경로는 메모리에만 유지됩니다. 플러그인, view,
session의 영속 상태는 기기별 절대 경로를 durable identity로 사용하지 않습니다.
Zotero 기반 탭은 `zoteroAttachmentKey`를 저장하고 재시작 후 현재 기기의
backend/Zotero 설정으로 다시 해석합니다. 일반 외부 탭은 기기별 named root 아래의
portable `externalRef`를 저장합니다. 현재 기기에 해당 named root가 설정되지 않았거나
참조 파일이 root 밖으로 이동했다면 root 또는 reference를 복구할 때까지 탭에서 파일을
다시 열 수 없습니다. 플러그인은 동기화된 절대 `doc.path`로 fallback하지 않습니다.

---

## 11. Zotero 연동

Zotero 데이터 디렉토리를 설정하면, 마크다운 노트에서 Zotero 링크(`zotero://open-pdf/library/items/<KEY>?page=X`)를 클릭할 때 Zotero를 실행하지 않고도 해당 PDF를 플러그인 내장 뷰어로 직접 열 수 있습니다.
- 링크에 `?page=X` 파라미터가 포함되어 있으면 해당 페이지로 자동 스크롤됩니다.
- 링크에 `annotation=<KEY>&viewer=obsidian` 파라미터가 포함되어 있으면 같은 PDF 뷰를 재사용해 해당 페이지와 주석 위치로 이동하며, 주석 영역은 내용을 가리지 않는 빈 테두리 박스로 표시됩니다.
- 링크에 `viewer=zotero` 파라미터가 포함되어 있으면 플러그인이 가로채지 않고 Zotero 앱으로 넘깁니다.
- 동일한 PDF에 대한 링크를 여러 번 클릭하더라도 새 창을 열지 않고 기존 스플릿 뷰를 재사용하여 페이지를 이동합니다.

### 설정

**설정 > AI Agent > Zotero 연동 > Backend Zotero status > Open setup**을 열어 backend가 실제로 읽을 수 있는 Zotero 상태를 확인합니다. setup dialog가 Zotero data directory의 단일 입력 지점이며 기본값은 `~/Zotero`입니다. 홈 디렉토리 아래 경로는 절대 `/Users/...` prefix 대신 `~`로 축약해 표시합니다. 여기서 data directory와 optional linked attachment root를 backend 설정에 저장할 수 있고, 이 backend 설정은 이후 Zotero 검색, metadata, annotation, PDF 경로 해석, Add-to-Incurator 등록에 사용됩니다.
> **참고**: Zotero의 기본 프로필 위치(`~/Zotero`)를 사용하는 경우, 백엔드가 `prefs.js`를 자동으로 파싱하여 Linked attachment root(연결된 파일 기본 경로)와 ZotMoov 대상 폴더를 스스로 알아냅니다. 따라서 대부분의 경우 사용자가 설정 창에서 linked attachment root를 직접 적을 필요가 없습니다. 자동 탐색이 실패하는 특수한 커스텀 환경에서만 오버라이드(override) 용도로 사용하세요.
backend가 checked roots 또는 checked PDF paths를 반환하면 setup dialog가 이를 candidate root로 표시하고 **Use** 액션으로 data directory 또는 linked root 입력칸에 채울 수 있게 합니다. 긴 path를 직접 복사해 넣지 않아도 됩니다.

| 운영체제 | 기본 경로 |
| --- | --- |
| macOS | `~/Zotero` |
| Linux | `~/Zotero` |
| Windows | `C:\Users\<username>\Zotero` |

이 디렉토리에는 `zotero.sqlite`가 있어야 합니다. PDF 첨부 파일은 Zotero `storage/` 또는 linked/base attachment directory에 있을 수 있습니다. linked attachment root는 Zotero DB의 `attachments:` 경로를 풀기 위한 base path일 뿐이며, 일반 `storage/<KEY>/...` 첨부에는 필요하지 않습니다. 디렉토리가 이동했거나 DB가 없으면 Zotero 검색이 빈 결과처럼 보이지 않고 backend status가 구조화된 상태를 반환합니다.
Zotero 링크나 Add-to-Incurator 작업에서 PDF를 해석하지 못하면 backend는 `db_missing`, `attachment_key_missing`, `attachment_file_missing` 같은 구조화된 상태를 반환합니다. 그래서 "Zotero DB를 찾을 수 없음", "현재 DB에 해당 attachment key가 없음", "configured root 안에 linked PDF 파일이 없음"을 plugin UI에서 구분할 수 있습니다. Settings, Dashboard, Zotero link 실패, sidechat Add-to-Incurator 실패는 같은 Zotero setup dialog를 열어 복구 로직이 한 UI 경로에 모이도록 합니다.

### Import Zotero Item

`Import Zotero Item` 검색창을 비워두면 최근 수정된 Zotero 항목을 `dateModified` 최신순으로 표시합니다. 설정값에는 여러 Zotero 데이터 디렉토리를 쉼표로 입력할 수 있으며, 플러그인은 각 경로의 `zotero.sqlite`를 순서대로 확인합니다.

**설정 → Zotero Import Profiles**에서 저장된 profile을 편집할 때는 Save 버튼이 없습니다.
입력하는 동안 저장되고 필드를 벗어날 때 한 번 더 저장되므로, 값을 고친 뒤 다른 곳을 클릭하면
반영됩니다. (v0.42.1 이전에는 **처음 입력한 한 글자만 저장**되었습니다. 템플릿 경로를
`book_template.md`에서 `paper_template.md`로 고쳐도 `boo_template.md`로 저장될 수 있었습니다.
이전 버전에서 profile을 편집하셨다면 값을 다시 확인하십시오.)

저장된 import profile이 있으면 wizard가 열릴 때 **가장 최근에 사용한 profile이 자동으로 로드되며**, Import Profile 드롭다운도 최근 사용 순으로 정렬됩니다(v0.21.0). 따라서 지금 작업 중인 profile이 오래된 것들에 묻히지 않고 맨 위에 옵니다. profile의 최근 사용 시각은 해당 profile로 항목을 가져올 때(또는 새로 만들 때) 갱신됩니다. 성공적으로 가져온 Zotero 항목은 `recentItems` LRU 목록에 기록되어 이후 Zotero 검색 결과에서 다른 항목보다 먼저 표시됩니다. 생성 또는 업데이트된 Zotero 노트는 사용한 profile 이름을 frontmatter의 `zotero_profile`에 저장하므로, 여러 profile이 있어도 리로드가 같은 템플릿과 자산 폴더를 사용할 수 있습니다.

**Profile이 기기 간 동기화됩니다 (v0.30.0).** Import profile과 최근 항목 LRU는
vault 안의 `.curator/zotero_profiles.json`에 저장됩니다 — `sessions.json`과
같은 동기화 위치입니다 — 따라서 한 기기에서 만든 profile이 Syncthing 동기화
후 다른 기기에도 나타납니다. (v0.30.0 이전에는 플러그인의 `data.json`에
저장되었는데, 이 파일은 보통 동기화에서 제외되므로 기기마다 다른 profile
목록이 보였습니다.) 업그레이드 후 첫 로드 시 플러그인이 기존 profile을
`data.json`에서 자동으로, 비파괴적으로 마이그레이션합니다. profile에는 vault
상대 경로만 들어 있으므로 Linux와 macOS 간에 안전하게 공유됩니다. 직렬화된
save는 canonical commit-time value의 peer-only profile, 최근 항목 key, 삭제 tombstone을
병합합니다. 같은 이름의 동시 편집은 저장된 profile timestamp에 따라
last-write-wins로 해소됩니다.

`.curator/zotero_profiles.json`이 손상된 경우(잘못된 JSON 또는 알아볼 수 없는
구조 — 예: 동기화 중단이나 잘못된 수동 편집), 플러그인은 파일을 **덮어쓰지
않습니다**: 해당 세션 동안 profile은 읽기 전용이 되고, 파일을 복구하거나
삭제하라는 알림이 표시됩니다. 이후 다시 로드하면 정상 동작으로 돌아옵니다.
profile 데이터는 디스크에 복구 가능한 상태로 유지됩니다. 파일 자체는 정상인데
개별 항목만 손상된 경우에는 나머지를 건드리지 않고 그 자리에서 복구합니다
(사용 불가능한 항목은 제거되고, 누락된 텍스트 필드는 빈 값이 됩니다).

출력 subfolder, filename, asset subfolder는 Zotero note template과 같은 Nunjucks 템플릿 엔진을 사용합니다. 예:

```text
{{ date | format("YYYY") }}/{{ creators | firstAuthorLast | pathSafe }}
{{ creators | firstAuthorLast }}_{{ title | pathSafe }}
{{ tags | joinTags("; ") }}
```

렌더링된 경로 segment는 Vault에 파일을 만들기 전에 안전한 파일명 형태로 정리됩니다.

Import는 Zotero 항목이 다시 생성되었거나 ZotMoov 같은 첨부파일 관리 도구로 이동된
뒤 사용하는 명시적 복구 경로이기도 합니다. 선택한 항목의 렌더링 파일명이 기존
노트와 대소문자만 다르면 wizard는 `File already exists`로 실패하지 않고 그 기존
노트를 업데이트합니다. 기존 파일명과 template의 persist 영역은 유지하면서, 현재
parent item 및 PDF attachment 링크를 포함한 선택 항목의 최신 metadata로 노트를
새로 렌더링합니다. 그 밖의 파일 생성 오류는 기존처럼 그대로 보고됩니다.

### Zotero 항목 / PDF 리로드 (`Cmd+Shift+R`)

Zotero 노트(frontmatter에 `citekey` 또는 `zotero_app_url`이 있는 노트)나 외부 PDF
뷰가 활성화된 상태에서 **`Cmd+Shift+R`**을 누르면 리로드됩니다 — PDF 뷰어 툴바의
리로드 버튼과 동일한 동작입니다:

- **Zotero 노트**: 항목 메타데이터를 다시 가져와, 가능한 경우 노트에 찍힌
  `zotero_profile`의 템플릿으로 다시 렌더링합니다. 이 stamp가 없는 오래된 노트만 첫
  번째 저장 profile로 fallback합니다. 주석(annotation) 영역 이미지는 선택된 import
  profile과 **동일한** 경로 해석(`assetFolder` / `assetSubfolder`, 예:
  `05_Assets/.../{{citekey}}`)으로 Vault 자산 폴더에 로컬라이즈되어, 리로드 시
  **Vault 상대경로** 임베드(`![[05_Assets/...]]`)를
  씁니다 — 절대경로 `![[/Users/.../Zotero/cache/...]]`가 아닙니다. Zotero에서 주석
  영역이 바뀌었다면 해당 자산 파일을 **덮어써서** 최신 이미지를 반영합니다.
  항목을 해석할 수 없는 경우 — 예를 들어 `zotero_app_url` 없이 `citekey`만 있는
  노트(citekey는 Zotero item key가 아닙니다) — 리로드는 빈 메타데이터로 노트를
  덮어쓰지 않고 **명확한 오류와 함께 중단하며 노트를 그대로 둡니다**. 이런 노트는
  Zotero wizard로 다시 가져와 `zotero_app_url`이 기록되도록 하세요.
- **외부 PDF 뷰**: 캐시된 문서를 버리고 디스크에서 PDF를 다시 읽습니다.

### 주석 링크와 부모 항목 해석

`zotero://select/library/items/<KEY>` 링크(`zotero_app_url`에 저장됨)는 **부모 항목**
키를 담고 있습니다. 이제 backend PDF 해석이 그 부모 키를 **자식 PDF 첨부**로
해석하므로, 링크가 PDF를 정상적으로 열고, 주석 링크(`...?annotation=<KEY>`)는 해당
주석 위치로 점프·하이라이트합니다 — 주석 조회가 해석된 자식 첨부 키를 사용합니다.

Zotero PDF를 plugin viewer에서 연 뒤 sidechat/purple-pin 흐름으로 등록하면 Incurator는 파일을 vault로 복사하지 않고 원본 파일을 Reference Mode로 등록합니다. 등록에 성공하면 완료 알림을 표시하고, backend가 파일 path를 해석하거나 등록하지 못하면 오류 알림을 표시합니다.
Zotero PDF tab은 effective attachment key와 view 위치만 저장합니다. 복원할
때 plugin은 backend에 key 해석을 요청하고, backend는 현재 기기의 Zotero
database에서 실제 PDF를 찾습니다. 반환된 절대경로는 memory-only이며 plugin
localStorage, Obsidian view state, `data.json`, sessions 또는 backend DB에
저장하지 않습니다. 일반 external tab은 portable `externalRef`를 저장합니다.
Zotero path 설정은 Zotero 데이터 디렉토리나 `zotero.sqlite` 파일 자체를 가리킬 수 있습니다. backend PDF 해석은 `zotero.sqlite`가 들어온 경우 부모 디렉토리로 정규화한 뒤 `storage/<attachmentKey>/`를 확인합니다.
linked Zotero attachment의 경우 backend는 configured linked attachment root에서 `attachments:` path도 확인합니다.
plugin이 Zotero attachment key를 알고 있으면 Add-to-Incurator는 그 key를 backend source import에 직접 넘길 수 있습니다. backend가 PDF를 해석하고 local reference row에 `zotero:<attachmentKey>` 형태의 stable logical source id를 기록합니다. viewer가 PDF를 이미 해석했다면 plugin은 local path와 attachment key를 함께 넘길 수 있습니다. 이때도 backend는 key를 portable identity로 사용하고 path는 현재 기기의 read hint로만 취급하며, Zotero 등록에 일반 `external.path_roots` 등록을 요구하지 않습니다. 같은 Zotero attachment를 반복 등록하면 이 logical source id를 재사용하며 `-02` reference stub를 새로 만들지 않습니다. PDF crop/snipping 이미지는 임시 채팅 컨텍스트로만 사용하며, 가능한 경우 선택된 모델에 전달된 뒤 `05_Assets` 아래에 영구 생성물을 남기지 않아야 합니다. backend transcription용 crop과 CLI image/cache 부산물은 repo `.cache/` 아래에 만들고 요청 뒤 삭제합니다. repo를 찾지 못하면 vault에 fallback하지 않고 명시적으로 실패합니다.
Zotero 설정과 복구의 관리 주체는 backend입니다. 플러그인은 plugin 설정값을 canonical state로 보지 않고, `wiki plugin zotero status`, `wiki plugin zotero init`, `wiki plugin zotero search`, `wiki plugin zotero resolve-pdf` 같은 숨김 JSON 명령을 호출해 상태 진단, 초기화, 검색, PDF 경로 해석을 요청해야 합니다. PDF context 요청은 가능한 한 `source_id`, file hash, vault-relative path, absolute path, Zotero attachment key 같은 식별자를 함께 넘기고, backend가 reference-mode 파일이나 이동된 Zotero 파일을 일관되게 해석합니다. 절대경로는 현재 기기의 backend 호출에 쓰는 hint일 뿐이며, 동기화되는 `04_Resources` reference stub에는 쓰지 않아야 합니다.

채팅 최종 답변은 plugin에서 선택한 provider/model이 작성합니다. backend/Incurator 호출은 plugin이 명시적으로 호출했을 때 검색 컨텍스트, PDF window, source status 또는 backend synthesis를 제공하는 역할입니다. 채팅 답변에서는 매 최신 요청마다 language bridge를 사용합니다: 입력 언어 감지 → 영어로 내부 검색/추론/tool 인자 처리 → 최신 입력 언어로 최종 답변 작성 순서입니다. 이전 턴, 한글 Markdown 문맥, 저장된 metadata가 다음 영어 질문의 답변 언어를 한국어로 고정해서는 안 됩니다. `curator_query`가 실행되면 Sources & Trace 패널이 지원 근거를 표시할 수 있도록 trace 필드는 유지하지만, stale `final_output_language`를 sidechat 언어 상태로 재사용하지 않습니다.

입력 언어 감지는 결정론적이며 매 채팅 턴마다 새로 실행됩니다. plugin은 최신 요청을 유니코드 스크립트로 분류하며 — 예: 한국어(한글), 중국어(汉字), 일본어(かな), 러시아어(Кириллица), 아랍어 등, 라틴 문자는 영어로 폴백 — 백엔드 curator query를 트리거하든 일반 provider 채팅이든 동일한 단일 감지기를 공유합니다. 따라서 채팅 세션은 영어 질문이 들어오면 영어로, 한국어 질문이면 한국어로, 중국어 질문이면 중국어로 답하며, 이전 턴이 어떤 언어였든 메시지마다 독립적으로 결정됩니다. 감지된 언어가 곧 답변 언어이며, 모델이 먼저 영어로 만든 뒤 별도 단계에서 번역하지 않습니다. 세 가지 언어 필드(`input_language`, `english_query`, `final_output_language`)는 query JSON/trace에만 존재하고 생성 노드 frontmatter에는 절대 기록되지 않습니다. 활성 노트가 워크스페이스 폴더 안에 있지 않은 일반 채팅은 워크스페이스 밖으로 취급되어 `default`로 해석되며, 사용자가 열지 않은 무관한 프로젝트 워크스페이스에 묶이지 않습니다.

### Zotero 링크 처리 흐름

```text
마크다운 노트에서 zotero:// 링크 클릭
      │
      │ (Zotero 데이터 디렉토리가 설정된 경우)
      ▼
플러그인이 클릭 이벤트를 가로채고 내장 뷰어를 먼저 시도
      │
      │ storage/<ATTACHMENTKEY>/*.pdf 탐색
      ▼
PDF 파일 경로 확인 → Split 뷰로 내장 뷰어 오픈
      │
      │ 로컬 PDF 경로를 확인할 수 없는 경우
      ▼
Zotero 앱으로 넘김
      │
      ▼
Cmd+Shift+L로 채팅 컨텍스트 참조, Incurator 인제스트 가능
```

전역 `window.open` / Electron `openExternal` fallback은 플러그인 unload 시점에
Incurator가 아직 해당 patch를 소유하고 있을 때만 복원합니다. 따라서 더 늦게 같은
opener를 patch한 다른 플러그인의 변경은 보존됩니다.

### Zotero 링크 생성 방법

Zotero에서 논문 항목을 우클릭 → **항목 링크 복사**하거나, [Zotero Integration](https://github.com/mgmeyers/obsidian-zotero-integration) 플러그인을 사용해 `zotero://` 링크가 포함된 노트를 자동 생성합니다.

> **참고**: Zotero 데이터 디렉토리가 설정되지 않은 경우 링크 클릭은 기본 동작(브라우저/Zotero 앱 열기)을 유지합니다.

---

## 12. 단축키 요약

| 단축키 | 기능 |
| --- | --- |
| `Cmd+Shift+K` | 선택한 텍스트에 빠른 질의 (In-line Copilot) |
| `Cmd+Shift+L` | 현재 내용을 채팅 컨텍스트로 추가 (마크다운·PDF) |
| `Cmd+Shift+X` | PDF 영역 스니핑 → 채팅 첨부 (Incurator PDF 뷰어 전용) |
| `Cmd+Shift+;` | 채팅 사이드바 열기/닫기 |

> macOS에서 `Cmd`는 `⌘`, Linux/Windows에서는 `Ctrl`에 해당합니다.

---

## 13. v0.3.2 큐레이션-네이티브 인터페이스

플러그인은 백엔드의 v0.3.2 큐레이션-네이티브 기능을 숨김 로컬 JSON 명령으로
호출합니다(동일 기기 흐름에서는 MCP를 거치지 않음). 클라이언트
(`IncuratorClient`)가 노출하는 메서드:

| 클라이언트 메서드 | 백엔드 명령 | 반환 |
|---|---|---|
| `getCuratePlan(workspacePath)` | `wiki plugin curate plan` | `IncuratorCuratePlan` (route, 선택/제외 소스, 허용 모드, 검증 오류) |
| `getPromptTrace(traceId)` | `wiki plugin prompt trace` | `IncuratorPromptTrace` (프롬프트 id/버전, 검증자 상태, 모델) |
| `listInsightCandidates(workspacePath)` | `wiki plugin insight list` | `IncuratorInsightCandidate[]` |
| `getInsightCandidate(insightId, workspacePath)` | `wiki plugin insight show` | evidence/source event 세부 정보가 포함된 `IncuratorInsightCandidate` |
| `promoteInsight(insightId, workspacePath)` | `wiki plugin insight promote` | `{ promotedTo }` (`02_Wiki/`에만 기록) |
| `rejectInsight(insightId, workspacePath, reason)` | `wiki plugin insight reject` | `{ ok, status }` |
| `listQueryTraces(workspacePath, limit)` | `wiki plugin trace list` | 최근 `QTR-` trace summary |
| `getQueryTrace(traceId, workspacePath)` | `wiki plugin trace show` | query route, evidence id, retrieval trace, warning |
| `listSynthesisNodes(workspacePath, limit)` | `wiki plugin synthesis list` | 최근 L4 `SYN-` summary |
| `getSynthesisAudit(synthesisId, workspacePath)` | `wiki plugin synthesis show` | read-only L4→L1 synthesis audit report |
| `proposeCorrection(nodeId, correction, previous, workspacePath)` | `wiki plugin correction propose` | classification/recommended action/review flag |

## 14. Git Sidechat 연동

플러그인은 수동 Commit/Push dashboard 버튼을 추가하지 않고, sidechat을 통해
로컬 Git 저장소 워크플로우를 노출합니다. 기존 로컬 `git`만 사용하며 **GitHub
CLI(`gh`) 의존성이 없고** 플러그인이 GitHub token을 저장하지도 않습니다. (HTTPS
push 인증이 필요하면 플러그인 밖, 평소 쓰는 git credential helper가 처리합니다.)

저장소 작업은 숨은 backend JSON 명령을 사용합니다.

| 클라이언트 메서드 | 백엔드 명령 | 목적 |
|---|---|---|
| `getGitStatus()` | `wiki plugin git status` | branch, upstream, ahead/behind, dirty count, `.curator/` ignore 경고 |
| `getGitLog(limit)` | `wiki plugin git log` | 최근 vault commit |
| `getGitDiffStat()` | `wiki plugin git diff --stat` | 제한된 working-tree diff 요약 |
| `getGitHistory(filePath, queryText, limit)` | `wiki plugin git history` | 현재 Markdown 파일 또는 선택 텍스트 history |
| `pushGitChanges()` | `wiki plugin git push` | upstream이 안전할 때 현재 branch push |
| `commitGitChanges(message)` | `wiki plugin git commit` | 명시적 commit 요청용 guarded fallback |

기본 워크플로우는 vault에 scheduled commit이 이미 있을 수 있다고 가정합니다.
`push해줘` 같은 요청에서는 sidechat이 새 commit을 먼저 만들지 않고 기존 commit을
push해야 합니다. "이 내용 예전에 어떻게 바뀌었는지 히스토리 찾아줘" 같은 선택한
Markdown history 질문에서는 선택 텍스트 또는 정규화된 excerpt와 현재 Markdown 파일
경로를 `getGitHistory`에 전달해야 합니다.

Git 명령은 provider-native shell/tool 추측이 아니라 `IncuratorClient`를 통한 결정적
backend 호출이어야 합니다. backend가 git repository 없음, upstream 없음,
behind/diverged branch 같은 구조화된 blocker를 반환하면, sidechat은
merge/rebase/unsafe push를 시도하지 않고 그 blocker를 보고합니다.

쿼리 결과(`CuratorQueryResult`)와 Sources & Trace 패널은 v0.3.1 필드를 추가로
담습니다: `route`, `trace_id`(`QTR-`), `prompt_trace_ids`(`PTR-`),
`source_span_ids`(`SPAN-`), `community_report_ids`(`REP-`),
`memory_path_ids`(`MPATH-`), `insight_candidate_ids`(`INS-`), `pack_id`,
`snapshot`, `budget`. L3-complete ContextService-backed 답변에서는 hidden
`wiki plugin query` 명령이 이 필드를 additive result level과 `trace` 내부에 모두
반환합니다. 구버전/부분 응답은 이 필드를 생략하므로 패널은 우아하게 축소
렌더링됩니다.

명시적 backend synthesis가 provider 경계에서 실패해도 hidden
`wiki plugin query` 명령은 `ok=false`, `error`, 사용 가능한 모든
QTR/PTR/provenance/warning 필드를 담은 파싱 가능한 결과 하나를 출력한 뒤 종료
코드 1로 끝납니다. 플러그인은 이 non-zero 종료에서도 JSON을 사용합니다.
Sources & Trace는 유지된 trace와 함께 실패 이유를 표시하며, 진단용 process
텍스트를 답변에 섞거나 실패를 빈 성공으로 취급하지 않습니다.

Plan F는 이 흐름에 normalized context pack을 추가합니다. 플러그인은 local
selected/pinned/open-note/PDF/image context 이후 provider에 남은 context budget을
계산하고, 그 budget 안에서 backend pack을 요청한 뒤 pack의 evidence item으로
provider를 grounding합니다. Sources & Trace는 해당 turn에 실제 사용된
`pack_id`, snapshot, budget, coverage/degraded state, evidence item summary,
locator, expansion handle, verification handle, omitted expansion handle을
렌더링합니다. 가져온 pack은 trace payload의 `context_pack`에 유지됩니다.
locator는 클릭 가능하며 source kind에 따라 열기 대상이 결정됩니다. 외부 Reference
Mode 소스(`external_uri` 존재)는 vault에 없으며 `relpath`는 vault 내부 stub일
뿐이므로, stub이 아니라 실제 외부 파일(`external_uri`)을 엽니다. 레퍼런스 **PDF**는
플러그인 내장 외부 PDF 뷰어에서 인용된 페이지로 열고, 그 외 외부 레퍼런스는 시스템
핸들러로 엽니다(데스크톱의 로컬 파일은 desktop shell opener를 사용). vault 소스는 relpath를 열며, 등록된/vault PDF는 `#page=N` 앵커로
Obsidian 기본 뷰어에서 해당 페이지로 점프하고 그 외 노트는 heading/block anchor가
있으면 그 위치로 엽니다. Expansion/verification 버튼은 표시된 pack id와 snapshot id로
`wiki plugin context expand`, `wiki plugin context verify`를 호출합니다. Verification이 성공하면 표시 중인 evidence item을 제자리에서 갱신합니다. backend가
`snapshot_conflict`를 반환하면 패널은 표시 중인 pack을 stale 상태로 표시하고
expected/current snapshot id를 보여주며 **Refetch**를 제공합니다. Refetch는 원래
질문으로 `wiki plugin context fetch`를 다시 실행해 표시 pack을 교체하며, 서로 다른
snapshot의 evidence를 병합하지 않습니다. backend synthesized answer는 기본적으로
주입하지 않습니다.

Sources & Trace의 각 evidence item에는 피드백 컨트롤이 있습니다: 👍(relevant) /
👎(irrelevant) 버튼과 incorrect/stale/insufficient/duplicate를 위한 **Report…**
메뉴입니다. 하나를 선택하면 표시된 trace id와 pack id에 대해
`wiki plugin context feedback`로 이벤트를 추가합니다. backend는 root `QTR-*`를
직접 조회하고 해당 `PACK-*`가 그 trace에 속하는지 검증한 뒤, pack/snapshot에
연결된 append-only `FBK-*` 이벤트를 기록하고 `ranking_or_truth_mutated: false`를
반환합니다. 피드백은 소스 파일, 생성 레코드, ranking, truth 상태를 절대 수정하지
않으며, 별도로 검토된 정책이 적용하기 전까지 격리(quarantine) 상태로 유지됩니다.
`new_insight` 이벤트는 즉시 무언가를 변경하지 않고, 나중의 사람 검토를 위한
provisional insight candidate를 큐에 넣습니다.

Sources & Trace 패널에는 **💾 Save to 02_Wiki** 버튼도 있습니다. 이 버튼을 누르면
해당 답변을 명시적으로 `02_Wiki/` 페이지로 승격하며, trace의 `source_span_ids`를
함께 전달해 페이지에 원본 소스 문서를 링크하는 `## Sources` 섹션이 추가됩니다 —
이 소스들은 Obsidian의 그래프 뷰·백링크에 나타납니다. 플러그인은 자동으로
승격하지 않으며, 이 버튼(또는 동등한 backend 명령)만 페이지를 기록합니다. 버튼은
해당 답변 자체의 trace에 바인딩됩니다. 과거 답변을 승격할 때 trace에 명시적인
질문이 없으면, 플러그인은 채팅에서 가장 최신 사용자 메시지가 아니라 그 답변 바로
앞의 사용자 메시지를 질문으로 사용합니다. 과거 trace 패널에서도 navigation과
승격은 가능하지만, context-pack을 변경하는 expand, verify, refetch, feedback
액션은 최신 활성 답변에만 표시되어 오래된 패널이 live query 상태를 변경하지
못합니다.

규칙:
- 인사이트 후보 승격은 명시적 사용자 동작입니다. 플러그인은 `promoteInsight`
  호출 전 확인을 받아야 하며, 이는 `02_Wiki/`에만 기록합니다.
- 이 로컬 명령들은 JSON을 반환하며 Incurator MCP 도구로 라우팅하면 안 됩니다(MCP는
  외부 에이전트용). [플러그인 스키마 스펙](../specs/plugin_schema/PLUGIN_SCHEMA.md)
  §9–12 참고.
- Dashboard의 Trace/Insights 탭은 이 명령들 위에 놓인 click-to-use surface입니다.
  trace와 insight candidate를 list/show하고, 후보를 promote/reject하거나 correction을
  propose할 수 있지만 repo-cache `state.sqlite`, `.curator/Collections/`,
  `03_Notes/`, `04_Resources/`, `06_Archives`를 직접 쓰면 안 됩니다.

---

## 디버그 로깅

기본적으로 플러그인은 개발자 콘솔을 조용하게 유지합니다 — 경고와 오류
(`[Incurator]` 접두사)만 출력됩니다. 자세한 진단 로그를 보려면(예: 버그 리포트
작성 시) 개발자 콘솔(**Ctrl/Cmd+Shift+I**)을 열고 다음을 실행하세요:

```js
localStorage.setItem("incurator-debug", "1")
```

그런 다음 Obsidian을 다시 로드합니다(이 플래그는 플러그인 로드 시 한 번만 읽힙니다).
자세한 로그를 다시 끄려면 값을 `"0"`으로 설정(또는 제거)하고 다시 로드하세요. 이는
플러그인 설정이 아니라 개발자용 기능으로, 기기별로 적용되며 동기화되지 않습니다.

## 문제 해결

### 채팅·팝오버·컨텍스트 핀이 한꺼번에 동작하지 않을 때

퍼플 컨텍스트 핀이 사라지고, **전송**이 아무 반응이 없으며, Quick Query 팝오버가
"Thinking" 상태에서 멈춰 있다면, 개발자 콘솔(**Ctrl/Cmd+Shift+I**)을 열어 하나의
근본 오류를 찾으십시오. 이 세 표면은 컨텍스트를 만드는 경로를 공유하므로, 예외 하나가
셋을 동시에 무너뜨립니다.

`TypeError: getRuntimePath is not a function`이 v0.41.0에서 나타난 형태이며
v0.41.1에서 수정되었습니다. 복원된(지연 로딩된) PDF 탭에서 발생하므로, Obsidian을
재시작하면 오히려 재현 가능성이 **높아집니다**. 아직 v0.41.0을 쓰고 있다면
업데이트하십시오. 임시 회피책은 재시작 전에 PDF 탭을 닫아 두는 것입니다.

### 플러그인이 실제로 실행하는 `wiki` 확인

플러그인은 설정에 지정된 백엔드 명령을 실행합니다. 그 값이 `wiki`라는 이름뿐이면
Obsidian 애플리케이션 프로세스의 PATH에서 해석되는데, 이는 셸의 PATH와 **다릅니다**.
셸 alias나 `.zshrc`의 export는 적용되지 않습니다. 그 PATH에 다른 Incurator 설치본이
있으면(예: Anaconda 환경에 남은 예전 `pip install -e`), 플러그인이 조용히 그것을 쓸 수
있습니다.

백엔드 명령을 이 저장소 런타임 환경 런처의 절대 경로로 지정하십시오. 예:
`/path/to/Incurator/.venv/bin/wiki`. 어느 설치본이 응답하는지는 다음으로 비교합니다:

```bash
wiki version
/path/to/Incurator/.venv/bin/wiki version
```

editable 설치는 최초 설치 시점에 기록된 버전을 보고하면서도 현재 저장소 코드를 그대로
실행합니다. 따라서 버전 문자열이 낡았다고 해서 동작이 낡은 것은 **아닙니다**. 다만
경로를 바로잡기 전까지는 플러그인의 버전 검사를 신뢰할 수 없습니다.

## 관련 문서

- [전체 워크플로우](WORKFLOW_GUIDE_KR.md) — 시스템 전체 동작 흐름
- [MCP 사용 가이드](MCP_USER_GUIDE_KR.md) — AI 에이전트 MCP 연결 설정
- [사용자 가이드](USER_GUIDE_KR.md) — wiki CLI 명령어 레퍼런스
