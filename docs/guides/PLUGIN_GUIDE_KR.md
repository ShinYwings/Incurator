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
- **컨텍스트 참조**: 텍스트, PDF 페이지, 이미지 스니펫을 메시지에 첨부해 질문합니다.
- **Plan 모드**: `chatMode: plan`으로 전환 시 AI가 단계별 계획을 먼저 제시합니다.
- **Incurator 연동**: Curator 백엔드가 연결된 경우 추적 가능한 DAG 근거를 컨텍스트로 주입합니다.

---

## 3. 인라인 편집 (`Cmd+K`)

마크다운 편집기에서 텍스트를 선택한 뒤 `Cmd+K`를 누르면 인라인 프롬프트 위젯이 열립니다.

- **선택 없음**: 전체 문서 맥락으로 편집 명령을 입력합니다.
- **텍스트 선택 후**: 선택 영역만 대상으로 편집됩니다.
- **결과 표시**: 변경 전후를 인라인 Diff로 보여주며, 적용(Accept) 또는 거부(Reject) 선택 가능합니다.
- **채팅 편집 검토**: 사이드챗이 Markdown SEARCH/REPLACE 수정을 제안하면
  **Review in file**로 대상 노트를 source mode에서 열고, Markdown 편집기
  안에서 제안된 hunk를 확인한 뒤 Accept 또는 Reject합니다.
- **Diff 모드**: 설정에서 `inline` 또는 `side-by-side` 중 선택합니다.

```text
편집기에서 텍스트 선택
       │
       │ Cmd+K
       ▼
인라인 프롬프트 위젯 (명령 입력)
       │
       ▼
LLM이 제안 생성 → Diff 표시 → Accept / Reject
```

---

## 4. 라인 참조 (`Cmd+Shift+L`)

현재 보고 있는 내용을 채팅 컨텍스트로 추가합니다.

| 뷰 타입 | 동작 |
| --- | --- |
| **마크다운 파일** | 현재 커서 근처 텍스트를 컨텍스트 참조로 추가 |
| **PDF 뷰어** (선택 있음) | 선택한 텍스트를 컨텍스트에 추가 |
| **PDF 뷰어** (선택 없음) | 현재 페이지 전체를 컨텍스트로 추가 (`pdfCaptureMode`에 따라 텍스트·이미지·양쪽) |

Incurator PDF 뷰어의 텍스트 선택은 실제 텍스트 span 위에서만 시작됩니다. PDF의 빈 여백을 드래그해도 선택 영역이 생기지 않도록 처리합니다.

사이드챗에서 메시지를 보낼 때 선택 영역, 라인 참조, PDF 스니핑으로 명시적으로 추가한 컨텍스트가 현재 턴의 중심 맥락으로 취급됩니다. 보라색 pin 컨텍스트와 자동으로 보이는 탭은 질문에서 직접 요구하지 않는 한 배경 맥락으로만 사용됩니다. pin 또는 첨부 context chip은 invisible/excluded 상태로 전환할 수 있으며, 이 상태에서는 chip row에는 남아 있지만 다시 visible로 바꾸기 전까지 모델 prompt에는 포함되지 않습니다.

선택한 Markdown line range가 첨부된 상태에서 사용자가 해당 텍스트를 고치거나, 다시 쓰거나, 다듬거나, 번역하라고 요청하면 assistant는 `ai-agent-edit` SEARCH/REPLACE 제안을 반환해야 합니다. 선택 영역에 대한 단순 질문이면 파일 수정 제안 없이 답변만 합니다.

최신 요청이 선택한 PDF/text 영역을 예시로 삼아 Markdown 파일 안의 모든 비슷한 부분을 바꾸라고 요청하면, 선택 영역은 유일한 수정 대상이 아니라 pattern을 이해하기 위한 단서로 취급합니다. 플러그인은 열린 Markdown 탭의 전체 내용을 edit-target context로 보내므로 assistant가 파일 전체에서 같은 HTML/Markdown line 형태를 찾고, 기존 문법 형식을 보존한 SEARCH/REPLACE hunk를 Markdown 편집기 안에서 review할 수 있게 제안해야 합니다.

### Markdown 작업 위치 복원

플러그인은 Obsidian을 끌 때 활성 편집 모드 Markdown 파일의 커서와 스크롤 위치를 마지막 작업 위치로 저장합니다. Obsidian을 다시 켜면 workspace layout이 준비된 뒤 그 파일과 위치를 여러 번 재시도해 복원합니다.

마지막 작업 위치는 별도 snapshot으로 저장되며, 파일별 위치 캐시는 보조 기록으로 최대 100개까지 보관됩니다.

---

## 5. PDF 스니핑 (`Cmd+Shift+X`)

PDF 뷰어에서 특정 영역을 마우스로 드래그해 캡처합니다.

1. PDF 파일을 Incurator 뷰어에서 열기 (`.pdf` 파일을 우클릭 → Open with Incurator)
2. `Cmd+Shift+X` → 스니핑 모드 진입
3. 원하는 영역을 드래그 → 이미지로 캡처됨
4. 캡처된 이미지가 채팅 사이드바 컨텍스트에 자동 첨부

> **참고**: 스니핑은 Incurator 전용 PDF 뷰어(`EXTERNAL_PDF_VIEW_TYPE`)에서만 동작합니다.  
> Obsidian 기본 PDF 뷰어에서는 `Cmd+Shift+L`로 페이지 전체를 참조하세요.

PDF snip은 선택한 모델이 vision을 지원할 때 이미지 context로 전송됩니다.
활성 모델이 text-only이면 sidechat은 snip 첨부를 유지하되 이미지 세부 정보를
읽을 수 없다는 사실을 모델에 명시하고, crop을 조용히 무시하지 않습니다.
최신 메시지에 사용자가 선택한 crop/image가 이미 첨부되어 있으면, 플러그인은
그 로컬 이미지 context를 빠른 경로로 사용하고 해당 턴에서는 backend 전체 PDF
context/RAG 호출을 건너뜁니다.

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
| `pdfVisionFallback` | `true` | 텍스트 레이어 없을 시 자동 이미지 모드 전환 |
| `pdfFullDocumentIndex` | `true` | PDF 전체 색인 생성 (RAG 정확도 향상) |

PDF context는 다음 순서로 조립됩니다.

1. 로컬 PDF.js 페이지 텍스트와 첨부된 crop/image context.
2. 로컬 viewer text/window/image context가 없을 때만 backend PDF
   window/outline context.
3. backend PDF context를 사용하는 경우에만, `pdfRagEnabled=true`이고 source가
   tracked 상태일 때 backend 전체 PDF RAG.

채팅 사이드바는 backend PDF context, PDF RAG, Curator query 소요 시간을
developer console에 기록하므로, 느린 턴에서 어느 단계가 막히는지 확인할 수
있습니다.

PDF 채팅과 PDF 지식 정제는 별도 workflow로 취급합니다.

- 열린 PDF에 대한 일반 채팅은 viewer fast path를 사용합니다. durable
  Incurator ingest 없이 현재 페이지, 주변 페이지 텍스트, 선택 텍스트, crop
  image에서 바로 답하고, blocking backend PDF context 호출을 요구하지 않습니다.
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
**Model** 행의 설명에 함께 표시합니다.

플러그인은 Antigravity, Claude, OpenAI Codex, Ollama, DeepSeek를 지원합니다. 설정 탭에서는 제공자와 모델을 따로 조정할 수 있고, 채팅 사이드바 하단에서는 하나의 모델 선택 메뉴에서 `Provider · Model` 형식으로 함께 전환합니다. reasoning/effort 메뉴는 백엔드 카탈로그에서 effort 단계가 선언된 모델에만 표시됩니다.

> [!NOTE]
> **Incurator Dashboard → Overview → LLM Provider** 카드에서도 보관소(`.curator/config.yml`)의 Primary/Fallback 모델을 바꿀 수 있습니다. 각 모델 드롭다운 옆에는 **effort 드롭다운**이 함께 표시되며, 선택한 모델이 노출하는 강도만 보여줍니다 (강도가 없는 모델은 `—`). Apply 시 `llm.primary_effort` / `llm.fallback_effort` 로 저장됩니다. 모델 목록은 플러그인 빌드 시 백엔드의 `data/models.json` 카탈로그(단일 소스)에서 번들링되므로, 모델 이름 표시가 MCP 시작 여부에 의존하지 않습니다.

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
| `gemini-3.1-pro` | 고품질 추론 |
| `gemini-3-flash` | 이전 세대 Flash |

`antigravityPrintTimeoutSec`: CLI 응답 최대 대기 시간 (기본 300초)

### 7.2 Claude

Claude Code CLI (`claude`)를 통해 Anthropic 모델에 접근합니다.

```bash
# 로그인
claude login
# 또는 플러그인 내 명령: Login to Claude CLI
```

`claudeEffort`: `low` / `medium` / `high` / `xhigh` / `max` 중 선택

### 7.3 OpenAI Codex

OpenAI Codex CLI (`codex`)를 통해 GPT 모델에 접근합니다.

```bash
# 로그인
codex login
# 또는 플러그인 내 명령: Login to OpenAI Codex CLI
```

`codexReasoningEffort`: `low` / `medium` / `high` / `xhigh` 중 선택

| 모델 | 설명 |
| --- | --- |
| `gpt-5.5` | 기본값. 강력한 추론 |
| `gpt-5.4` | 일상 코딩 작업 |
| `gpt-5.4-mini` | 빠른 경량 작업 |
| `gpt-5.3-codex` | 코딩 특화 모델 |

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

어떤 provider에서든 quota 또는 capacity 오류가 발생하면 sidechat에 명확히 표시되어 사용자가 provider/model을 바꾸거나 fallback을 설정할 수 있습니다.

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
(`wiki plugin source ...`, `wiki plugin pdf ...`, `wiki plugin query`)
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
| `incuratorRepoPath` | `""` | 백엔드 자동 업데이트를 위한 Incurator 저장소 절대 경로 |
| `incuratorDefaultDestination` | `04_Resources` | PDF reference stub 또는 명시적 copy import의 기본 폴더 |
| `incuratorDefaultImportMode` | `reference` | 파일 추가 방식 (`reference`는 link stub 생성, `copy`는 vault 안으로 복사) |
| `incuratorStatusPolling` | `true` | 소스 처리 상태 폴링 활성화 |

Zotero나 다른 외부 위치에서 열린 PDF의 **Add to Incurator** 기본 동작은
Reference Mode입니다. backend는 PDF를 원래 위치에 두고 `04_Resources/` 아래에
작은 markdown reference stub만 만들며, 실제 PDF 경로는 기기별 backend source
metadata로 저장합니다. 자동 생성 stub에는 기본적으로 PDF 절대 경로를 넣지 않으므로,
Zotero나 외부 PDF의 로컬 위치가 다른 기기에도 안전하게 동기화할 수 있습니다. PDF를
vault 안으로 복사하는 동작은 기본값이 아니라 명시적 예외입니다.

Source badge는 layer 상태를 구분합니다. `L1 ready`는 즉시 section context를
사용할 수 있다는 뜻이고, `L2 ready`는 Atom이 생성됐다는 뜻이며, `Indexed`는
L3 Concept 기반 답변이 가능하다는 뜻입니다. `Synthesized`는 공유 L4 Synthesis가
사용 가능하다는 뜻입니다. 어떤 layer라도 error이면 정상 badge 대신 error를 표시합니다.

### 백엔드 자동 업데이트 (1-Click Auto-Update)

Incurator 백엔드와 Obsidian 플러그인은 각기 다른 주기로 업데이트될 수 있습니다. 플러그인이 백엔드 버전을 확인해 버전 불일치(Mismatch)를 감지하면 채팅 창 상단에 **[Update Incurator Backend]** 배너를 표시합니다.
설정에서 `incuratorRepoPath`에 로컬 저장소 경로를 지정해 두었다면, 버튼 클릭 한 번으로 백그라운드에서 백엔드를 최신 버전으로 자동 업데이트합니다. 업데이트 후에는 plugin reload 또는 Obsidian 재시작이 필요합니다.

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
있습니다.

최신 사용자 턴에 primary selected text, line range, PDF page, crop image가
첨부되어 있지 않은 일반 workspace/domain 질문에서는 sidechat이 `wiki plugin
query`를 직접 호출합니다. backend에 L3 grounding이 있으면 응답에 compact trace가
포함되어 Sources & Trace 패널이 지원 근거를 링크할 수 있습니다. 최신 턴이 선택 crop이나 editable
Markdown 영역에 집중된 경우에는 `wiki plugin query`를 건너뛰고 해당 선택
context에서 답합니다.

Zotero PDF는 기본적으로 Reference Mode로 등록됩니다. 생성되는
`04_Resources` reference stub은 로컬 PDF 절대경로를 쓰지 않고 Zotero
attachment key와 `zotero://open-pdf/library/items/<key>` 링크 같은 portable
identity를 기록합니다. 실제 로컬 PDF 경로는 backend source metadata에만
저장됩니다.

대시보드의 **Reset** 작업은 로컬 DB와 생성된 L1-L4 콘텐츠를 지우기 전에 두 번 확인합니다.

Dashboard 상태는 plugin 자체 상태가 아니라 `.curator/runtime/` 아래의
backend-owned shared snapshot에서 읽는 구조가 권장됩니다. 해당 JSON 파일은
backend만 쓰고 plugin은 source count, job 상태, index health, backend version
표시를 위해 읽기만 합니다. snapshot이 없거나 오래된 경우에는 backend가 비었다고
해석하지 않고 waiting/unknown 상태로 표시합니다.

Add, Build, Sync, Lint, Reindex, Reset, LLM Apply, Persona Save 같은 dashboard
버튼은 상태 변경이 필요할 때 backend command를 실행합니다. plugin은 이 작업을 위해
backend-owned `.curator` 상태를 직접 수정하지 않습니다.

Zotero 검색, metadata refresh, PDF path resolution, annotation loading, source
status/import/rebind, PDF context/search, query, promotion은 숨겨진
plugin-local backend API(`wiki plugin ...`)를 사용합니다. 따라서 durable backend
상태 변경과 로컬 filesystem/database 해석은 backend 코드가 담당하고, plugin은
Incurator MCP tool discovery 없이 JSON 결과만 받습니다. 이 plugin plumbing은 일반
사용자가 쓰는 `wiki` 명령 표면에는 노출하지 않습니다.

---

## 10. 동기화 주의사항

### 세션 히스토리 (sessions.json)

플러그인 데이터는 두 파일로 분리 저장됩니다.

| 파일 | 내용 | 기기 간 동기화 |
| --- | --- | --- |
| `data.json` | 설정(provider, model, MCP 서버 등) | 경로가 같을 때만 권장 |
| `sessions.json` | 채팅 대화 히스토리 | 가능 |
| `.curator/runtime/*.json` | backend가 쓰는 dashboard/status snapshot | 생성 상태로 동기화 가능 |

v0.2.1에서는 `sessions.json` 저장 시 디스크의 최신 파일을 다시 읽고 세션 id 단위로 병합합니다. 따라서 Linux와 macOS에서 서로 다른 채팅 세션을 만들면 두 세션이 함께 보존됩니다. 삭제된 세션은 `deletedSessionIds` tombstone에 남아 Syncthing 지연으로 오래된 파일이 도착해도 되살아나지 않습니다. 단, 같은 세션을 양쪽에서 동시에 편집한 경우에는 더 최신 `updatedAt`을 가진 세션이 이깁니다.

사이드바 대화 목록의 채팅 제목은 첫 사용자 질문 뒤에 나온 첫 assistant 답변에서
생성합니다. 아직 답변이 끝나지 않은 동안에는 첫 사용자 질문을 임시 제목으로
사용합니다. 각 행에는 `updatedAt` 기준의 마지막 활동 시간이 `12m ago`,
`3h ago`처럼 현재 시각 기준 상대 시간으로 표시됩니다.

사이드바의 휴지통 버튼으로 채팅 세션을 삭제하면 별도 확인 없이 즉시 삭제됩니다. 삭제 기록은 `deletedSessionIds` tombstone으로 남아 동기화된 다른 기기에서 해당 세션이 되살아나지 않게 합니다.

backend 실행 경로가 기기마다 다르거나 한쪽 기기에 Incurator가 설치되어 있지 않다면 `data.json`은 동기화하지 않는 편이 안전합니다. 이 경우 `.stignore`에는 `sessions.json` 대신 `data.json`을 추가합니다.

```text
.obsidian/plugins/incurator-obsidian-agent/data.json
```

macOS에 `wiki` 실행 파일이 PATH에 없다면 **Settings > AI Agent > PDF & Incurator**에서 `Backend command`와 `Backend arguments`를 해당 기기 기준으로 설정합니다. 예를 들어 repo는 있지만 backend가 전역 설치되어 있지 않은 경우:

| 설정 | 값 |
| --- | --- |
| `Backend command` | `/opt/homebrew/bin/uv` |
| `Backend arguments` | `["--directory", "/Users/<you>/Workspace/Incurator/backend", "run", "wiki"]` |

Obsidian plugin은 시작 시 Syncthing이 공유 중인 device 목록과 현재 기기의 backend launcher hint를 `.curator/devices.json`에 자동 기록합니다. 이 registry는 `data.json`을 동기화하지 않아도 Linux/macOS 설정 차이를 서로 확인하는 용도로 사용할 수 있습니다. Dashboard는 현재 Syncthing 공유 폴더 registry에 있는 모든 device를 표시하며, 현재 기기에 backend launcher가 없는 원격 device도 숨기지 않습니다. 각 device에는 동기화 중인 Vault/Zotero 폴더 이름을 표시하고, 현재 기기는 Syncthing remote 목록이 아니라 local fallback entry로만 잡히는 경우에도 **This device**로 표시합니다. platform 정보가 없으면 추측하지 않고 unknown으로 표시합니다. `wiki devices sync`는 자동 갱신이 실패했을 때 쓰는 수동 복구 명령이고, `wiki devices`는 현재 registry를 확인하는 명령입니다.

자세한 동기화 설정은 [SYNC_IGNORE_GUIDE_KR.md](SYNC_IGNORE_GUIDE_KR.md)를 참조하세요.

### 외부 PDF 재시작 제한

ExternalPdfView에 드래그한 PDF는 Obsidian이 실행 중인 동안만 파일 객체(File)가 메모리에 유지됩니다. Obsidian 재시작 후에는 캡처된 절대 경로(`doc.path`)로만 접근하므로, 파일이 이동·삭제된 경우 PDF를 다시 드래그해야 합니다.

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

저장된 import profile이 있으면 wizard가 열릴 때 첫 번째 profile이 자동으로 로드됩니다. 성공적으로 가져온 Zotero 항목은 로컬 `recentZoteroItems` LRU 목록에 기록되어 이후 Zotero 검색 결과에서 다른 항목보다 먼저 표시됩니다.

출력 subfolder, filename, asset subfolder는 Zotero note template과 같은 Nunjucks 템플릿 엔진을 사용합니다. 예:

```text
{{ date | format("YYYY") }}/{{ creators | firstAuthorLast | pathSafe }}
{{ creators | firstAuthorLast }}_{{ title | pathSafe }}
{{ tags | joinTags("; ") }}
```

렌더링된 경로 segment는 Vault에 파일을 만들기 전에 안전한 파일명 형태로 정리됩니다.

Zotero PDF를 plugin viewer에서 연 뒤 sidechat/purple-pin 흐름으로 등록하면 Incurator는 파일을 vault로 복사하지 않고 원본 파일을 Reference Mode로 등록합니다. 등록에 성공하면 완료 알림을 표시하고, backend가 파일 path를 해석하거나 등록하지 못하면 오류 알림을 표시합니다.
Zotero path 설정은 Zotero 데이터 디렉토리나 `zotero.sqlite` 파일 자체를 가리킬 수 있습니다. backend PDF 해석은 `zotero.sqlite`가 들어온 경우 부모 디렉토리로 정규화한 뒤 `storage/<attachmentKey>/`를 확인합니다.
linked Zotero attachment의 경우 backend는 configured linked attachment root에서 `attachments:` path도 확인합니다.
plugin이 Zotero attachment key를 알고 있으면 Add-to-Incurator는 그 key를 backend source import에 직접 넘길 수 있습니다. backend가 PDF를 해석하고 local reference row에 `zotero:<attachmentKey>` 형태의 stable logical source id를 기록합니다. 같은 Zotero attachment를 반복 등록하면 이 logical source id를 재사용하며 `-02` reference stub를 새로 만들지 않습니다. PDF crop/snipping 이미지는 임시 채팅 컨텍스트로만 사용하며, 가능한 경우 선택된 모델에 전달된 뒤 `05_Assets` 아래에 영구 생성물을 남기지 않아야 합니다.
Zotero 설정과 복구의 관리 주체는 backend입니다. 플러그인은 plugin 설정값을 canonical state로 보지 않고, `wiki plugin zotero status`, `wiki plugin zotero init`, `wiki plugin zotero search`, `wiki plugin zotero resolve-pdf` 같은 숨김 JSON 명령을 호출해 상태 진단, 초기화, 검색, PDF 경로 해석을 요청해야 합니다. PDF context 요청은 가능한 한 `source_id`, file hash, vault-relative path, absolute path, Zotero attachment key 같은 식별자를 함께 넘기고, backend가 reference-mode 파일이나 이동된 Zotero 파일을 일관되게 해석합니다.

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

### Zotero 링크 생성 방법

Zotero에서 논문 항목을 우클릭 → **항목 링크 복사**하거나, [Zotero Integration](https://github.com/mgmeyers/obsidian-zotero-integration) 플러그인을 사용해 `zotero://` 링크가 포함된 노트를 자동 생성합니다.

> **참고**: Zotero 데이터 디렉토리가 설정되지 않은 경우 링크 클릭은 기본 동작(브라우저/Zotero 앱 열기)을 유지합니다.

---

## 12. 단축키 요약

| 단축키 | 기능 |
| --- | --- |
| `Cmd+K` | 인라인 편집 (마크다운 에디터에서) |
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
| `proposeCorrection(nodeId, correction, previous, workspacePath)` | `wiki plugin correction propose` | classification/recommended action/review flag |

쿼리 결과(`CuratorQueryResult`)와 Sources & Trace 패널은 v0.3.1 필드를 추가로
담습니다: `route`, `trace_id`(`QTR-`), `prompt_trace_ids`(`PTR-`),
`source_span_ids`(`SPAN-`), `community_report_ids`(`REP-`),
`memory_path_ids`(`MPATH-`), `insight_candidate_ids`(`INS-`). 구버전/부분 응답은
이 필드를 생략하므로 패널은 우아하게 축소 렌더링됩니다.

규칙:
- 인사이트 후보 승격은 명시적 사용자 동작입니다. 플러그인은 `promoteInsight`
  호출 전 확인을 받아야 하며, 이는 `02_Wiki/`에만 기록합니다.
- 이 로컬 명령들은 JSON을 반환하며 Incurator MCP 도구로 라우팅하면 안 됩니다(MCP는
  외부 에이전트용). [플러그인 스키마 스펙](../specs/plugin_schema/PLUGIN_SCHEMA_v0.3.2.md)
  §9–12 참고.
- Dashboard의 Trace/Insights 탭은 이 명령들 위에 놓인 click-to-use surface입니다.
  trace와 insight candidate를 list/show하고, 후보를 promote/reject하거나 correction을
  propose할 수 있지만 `.curator/state.sqlite`, `.curator/Collections/`,
  `03_Notes/`, `04_Resources/`, `06_Archives`를 직접 쓰면 안 됩니다.

---

## 관련 문서

- [전체 워크플로우](WORKFLOW_GUIDE_KR.md) — 시스템 전체 동작 흐름
- [MCP 사용 가이드](MCP_USER_GUIDE_KR.md) — AI 에이전트 MCP 연결 설정
- [사용자 가이드](USER_GUIDE_KR.md) — wiki CLI 명령어 레퍼런스
