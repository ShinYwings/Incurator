# Obsidian 플러그인 가이드 (incurator-agent)

> Incurator Obsidian 플러그인은 Obsidian Vault 안에서 AI 어시스턴트를 제공합니다.  
> 단독으로 사용하거나, Curator 백엔드(wiki CLI)와 연동해 지식 그래프 기반 답변을 생성할 수 있습니다.

[English Guide](PLUGIN_GUIDE_EN.md)

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
- **Incurator 연동**: Curator 백엔드가 연결된 경우 Exhibition 기반 검색 결과를 컨텍스트로 주입합니다.

---

## 3. 인라인 편집 (`Cmd+K`)

마크다운 편집기에서 텍스트를 선택한 뒤 `Cmd+K`를 누르면 인라인 프롬프트 위젯이 열립니다.

- **선택 없음**: 전체 문서 맥락으로 편집 명령을 입력합니다.
- **텍스트 선택 후**: 선택 영역만 대상으로 편집됩니다.
- **결과 표시**: 변경 전후를 인라인 Diff로 보여주며, 적용(Accept) 또는 거부(Reject) 선택 가능합니다.
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

---

## 7. AI 제공자 설정

플러그인은 세 가지 AI 제공자를 지원합니다. 설정 탭에서는 제공자와 모델을 따로 조정할 수 있고, 채팅 사이드바 하단에서는 하나의 모델 선택 메뉴에서 `Provider · Model` 형식으로 함께 전환합니다. reasoning/effort 메뉴는 Codex와 Claude에서만 표시됩니다.

### 7.1 Antigravity (기본값)

Gemini CLI (`agy`)를 통해 Google Gemini 모델에 접근합니다.

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

---

## 8. MCP 서버 설정

플러그인이 외부 MCP 도구를 사용하도록 설정할 수 있습니다.

**설정 > AI Agent > MCP Servers**에서 서버를 추가합니다.

```json
{
  "name": "incurator",
  "command": "wiki",
  "args": ["mcp"],
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
IncuratorClient가 MCP를 통해 search_curator 호출
      │
      ▼
Exhibition 검색 결과를 시스템 컨텍스트로 주입
      │
      ▼
LLM이 Exhibition 내용을 근거로 답변 생성
```

### Incurator 연동 설정

| 설정 | 기본값 | 설명 |
| --- | --- | --- |
| `incuratorEnabled` | `true` | Curator 백엔드 연동 활성화 |
| `incuratorRepoPath` | `""` | 백엔드 자동 업데이트를 위한 Incurator 저장소 절대 경로 |
| `incuratorDefaultDestination` | `04_Resources` | PDF 임포트 기본 대상 폴더 |
| `incuratorDefaultImportMode` | `reference` | 파일 임포트 방식 (`copy` / `reference`) |
| `incuratorStatusPolling` | `true` | 소스 처리 상태 폴링 활성화 |

### 백엔드 자동 업데이트 (1-Click Auto-Update)

Incurator 백엔드와 Obsidian 플러그인은 각기 다른 주기로 업데이트될 수 있습니다. 플러그인은 시작 시 MCP를 통해 백엔드 버전을 확인(`curator_get_version`)하며, 버전 불일치(Mismatch)가 감지되면 채팅 창 상단에 **[Update Incurator Backend]** 배너를 표시합니다.
설정에서 `incuratorRepoPath`에 로컬 저장소 경로를 지정해 두었다면, 버튼 클릭 한 번으로 백그라운드에서 백엔드를 최신 버전으로 자동 업데이트하고 MCP 서버를 재시작합니다.

`Use Incurator backend`는 Incurator MCP 도구 사용 여부를 제어합니다. 켜면 플러그인이 현재 vault 경로를 `VAULT_ROOT`로 넣은 기본 `incurator` 서버(`wiki mcp`)를 자동 생성하고 즉시 연결을 시도합니다. 설정 화면의 이 항목 아래에는 현재 상태가 표시됩니다: disabled, connected, waiting, not configured. 범용 MCP Servers 섹션은 다른 MCP 서버를 관리하거나 자동 생성된 Incurator 서버를 고급 설정할 때 사용합니다.

### PDF → Curator 등록 흐름

Incurator 연동이 켜진 상태에서 PDF를 참조하면:

```text
Cmd+Shift+L (또는 Cmd+Shift+X)으로 PDF 캡처
      │
      │ MCP: curator_import_source 호출
      ▼
Curator 백엔드에 소스 등록
      │
      │ L1 → L2 → L3 처리 (백그라운드)
      ▼
wiki curate 실행 → L4 Exhibition 갱신
      │
      ▼
이후 search_curator로 검색 가능
```

---

## 10. 동기화 주의사항

### 세션 히스토리 (sessions.json)

플러그인 데이터는 두 파일로 분리 저장됩니다.

| 파일 | 내용 | 기기 간 동기화 |
| --- | --- | --- |
| `data.json` | 설정(provider, model, MCP 서버 등) | 경로가 같을 때만 권장 |
| `sessions.json` | 채팅 대화 히스토리 | 가능 |

v0.2.1에서는 `sessions.json` 저장 시 디스크의 최신 파일을 다시 읽고 세션 id 단위로 병합합니다. 따라서 Linux와 macOS에서 서로 다른 채팅 세션을 만들면 두 세션이 함께 보존됩니다. 삭제된 세션은 `deletedSessionIds` tombstone에 남아 Syncthing 지연으로 오래된 파일이 도착해도 되살아나지 않습니다. 단, 같은 세션을 양쪽에서 동시에 편집한 경우에는 더 최신 `updatedAt`을 가진 세션이 이깁니다.

backend 실행 경로가 기기마다 다르거나 한쪽 기기에 Incurator가 설치되어 있지 않다면 `data.json`은 동기화하지 않는 편이 안전합니다. 이 경우 `.stignore`에는 `sessions.json` 대신 `data.json`을 추가합니다.

```text
.obsidian/plugins/incurator-obsidian-agent/data.json
```

macOS에 `wiki` 실행 파일이 PATH에 없다면 **Settings > AI Agent > PDF & Incurator**에서 `Incurator MCP command`와 `Incurator MCP args`를 해당 기기 기준으로 설정합니다. 예를 들어 repo는 있지만 backend가 전역 설치되어 있지 않은 경우:

| 설정 | 값 |
| --- | --- |
| `Incurator MCP command` | `/opt/homebrew/bin/uv` |
| `Incurator MCP args` | `["--directory", "/Users/<you>/Workspace/Incurator/backend", "run", "wiki", "mcp"]` |

Obsidian plugin은 시작 시 Syncthing이 공유 중인 device 목록과 현재 기기의 backend launcher hint를 `.curator/devices.json`에 자동 기록합니다. 이 registry는 `data.json`을 동기화하지 않아도 Linux/macOS 설정 차이를 서로 확인하는 용도로 사용할 수 있습니다. `wiki devices sync`는 자동 갱신이 실패했을 때 쓰는 수동 복구 명령입니다.

자세한 동기화 설정은 [SYNC_IGNORE_GUIDE.md](SYNC_IGNORE_GUIDE.md)를 참조하세요.

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

**설정 > AI Agent > Zotero 연동 > Zotero 데이터 디렉토리**에 Zotero 데이터 폴더 경로를 입력합니다.

| 운영체제 | 기본 경로 |
| --- | --- |
| macOS | `~/Zotero` |
| Linux | `~/Zotero` |
| Windows | `C:\Users\<username>\Zotero` |

이 디렉토리 안에 `storage/` 폴더가 있어야 합니다.

### Import Zotero Item

`Import Zotero Item` 검색창을 비워두면 최근 수정된 Zotero 항목을 `dateModified` 최신순으로 표시합니다. 설정값에는 여러 Zotero 데이터 디렉토리를 쉼표로 입력할 수 있으며, 플러그인은 각 경로의 `zotero.sqlite`를 순서대로 확인합니다.

### Zotero 링크 처리 흐름

```text
마크다운 노트에서 zotero:// 링크 클릭
      │
      │ (Zotero 데이터 디렉토리가 설정된 경우)
      ▼
플러그인이 클릭 이벤트 가로채기 (Zotero 앱 실행 방지)
      │
      │ storage/<ATTACHMENTKEY>/*.pdf 탐색
      ▼
PDF 파일 경로 확인 → Split 뷰로 내장 뷰어 오픈
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

## 관련 문서

- [전체 워크플로우](WORKFLOW.md) — 시스템 전체 동작 흐름
- [MCP 사용 가이드](MCP_USER_GUIDE.md) — AI 에이전트 MCP 연결 설정
- [사용자 가이드](USER_GUIDE.md) — wiki CLI 명령어 레퍼런스
