# Incurator 전체 워크플로우

> 이 문서는 Incurator 시스템을 구성하는 세 가지 요소가 어떻게 맞물려 동작하는지 설명합니다.

[English Guide](WORKFLOW_GUIDE.md)

---

## 1. 시스템 구성 요소

Incurator는 세 개의 독립적인 구성 요소로 이루어집니다.

```text
┌─────────────────────────────────────────────────────┐
│                   Obsidian Vault                    │
│                                                     │
│  ┌──────────────────────┐   ┌─────────────────────┐ │
│  │  Obsidian Plugin     │   │  .curator/ (백엔드)  │ │
│  │  (incurator-agent)   │◄──►  Collections/       │ │
│  │  - 채팅 사이드바      │   │  L1 ~ L4 DAG        │ │
│  │  - 인라인 편집        │   │  state.sqlite       │ │
│  │  - PDF 컨텍스트       │   └──────────┬──────────┘ │
│  └──────────┬───────────┘              │            │
│             │ MCP                      │ wiki CLI   │
└─────────────┼──────────────────────────┼────────────┘
              │                          │
              ▼                          ▼
   ┌─────────────────────┐   ┌───────────────────────┐
   │  AI Agent (MCP)     │   │  wiki 명령어           │
   │  Claude Code        │   │  wiki add / query     │
   │  Antigravity        │   │  wiki sync / query    │
   │  Codex              │   │  wiki status / lint   │
   └─────────────────────┘   └───────────────────────┘
```

| 구성 요소 | 역할 | 진입점 |
|-----------|------|--------|
| **Curator 백엔드** | 소스 수집, 4-레이어 DAG 구축, 검색 | `wiki` CLI |
| **Obsidian 플러그인** | Obsidian 내 AI 채팅·편집·PDF 처리 | Obsidian 내 UI |
| **Agent MCP 서버** | AI 에이전트(Claude Code 등)에게 Curator 도구 노출 | `wiki mcp` |

---

## 2. Vault 위치 구조

Incurator에서 **세 가지 경로**를 구분하는 것이 중요합니다.

| 경로 | 역할 | 예시 |
|------|------|------|
| **Wiki system** | `wiki` CLI 코드가 위치한 곳 | `/path/to/incurator/` |
| **Vault** (`VAULT_ROOT`) | raw 파일과 `.curator/`가 상주하는 곳 | `/path/to/vault/` |
| **Workspace** | 프로젝트별 `curate.yml`이 있는 곳 | `<vault>/01_Workspaces/MyProject/` |

`VAULT_ROOT` 환경 변수 또는 MCP 설정의 `env.VAULT_ROOT`는 항상 **Vault 경로**를 가리켜야 합니다.

---

## 3. 4-레이어 DAG 구조

Incurator는 소스 문서를 4단계 추상화 레이어로 처리합니다.

```text
[소스 파일]  (03_Notes/, 04_Resources/, 02_Wiki/ 등)
     │
     │  wiki add
     ▼
[L1: Contexts]  (DB 레코드: source_spans)
  - 소스 1개당 1개의 컨텍스트 요약
  - 원본 내용, 메타데이터, 해시 연결
     │
     │  wiki build (L2 pass)
     ▼
[L2: Atoms]  (DB 레코드: knowledge_units)
  - L1에서 추출한 원자적 지식 단위
  - 하나의 사실·주장·결론
  - 검증 근거(인용) 포함
     │
     │  wiki build (L3 pass)
     ▼
[L3: Concepts]  (DB 레코드: graph_entities/relations + community_reports)
  - 여러 소스의 Atom을 묶은 주제 클러스터
  - 크로스-소스 비교·통합
     │
     │  wiki build (L4 종합 패스, L3 이후 자동 실행)
     ▼
[L4: Synthesis]  (DB 레코드: synthesis_nodes) → .curator/Collections/04_Synthesis/SYN-UUID.md
  - 공유되는, 워크스페이스 독립적인, 코퍼스 전체를 가로지르는 종합 인사이트
  - 모든 커뮤니티 리포트로부터 증류됨 ("synthesis"/영구 노트 계층)
  - 특정 워크스페이스에 맞춤되지 않은 지속적 지식
  - 전체를 한꺼번에 재생성; 리포트 코퍼스가 바뀌지 않으면 건너뜀
     │
     │  query (동적 Curation 렌즈 — 저장되지 않음)
     ▼
[Curation]  워크스페이스/쿼리별 L3/L4 노드의 동적 선택·재조합
  - 워크스페이스 curate.yml 지식 요구 사양(KRS)에 의해 편향됨
  - 매 쿼리마다 새로 생성; 고정된 파일이 아님
```

> **L4 Synthesis vs. Curation.** Synthesis 레이어는 다른 LLM 위키 레포지토리의
> synthesis 계층처럼 지식 그래프의 지속적·공유 최상위 계층입니다. **Curation**은
> 그 *위에 있는 동적 렌즈*로, 워크스페이스/쿼리별로 L3/L4 노드를 선택·재조합하며
> 절대 영속화되지 않습니다. v0.3.1에는 워크스페이스별 고정 Exhibition 파일이
> 없습니다.

---

## 4. 핵심 워크플로우

정확한 command flag와 명령별 정의는 canonical
[CLI Reference](USER_GUIDE_KR.md#cli-reference)를 기준으로 합니다. 이 가이드는
workflow 순서와 운영 맥락만 유지합니다.

### 4-1. 소스 수집 및 DAG 구축

```bash
# 1. Vault 초기화 (최초 1회)
wiki init /path/to/vault

# 2. 소스 추가 (wiki add) — 등록 + 즉시 L1만 (LLM 없음)
#    특정 파일 또는 디렉토리 전체
wiki add 03_Notes/paper.pdf
wiki add 04_Resources/

# 내부 동작 (Math-Aware v0.2.2):
#   - SHA-256 해시로 중복 감지
#   - 하이브리드 파이프라인: 기본은 pymupdf4llm(Markdown)으로 변환, 필요 시 VLM 파서 연동
#   - AST 기반 청킹: 수학 수식 블록($$...$$)을 보호하여 텍스트 분할
#   - L1 Context 파일을 구조로부터 즉시 생성 → 즉시 반환
#   - LLM 호출 없음; L1이 만들어지면 곧바로 검색(BM25) 가능

# 3. L2/L3 빌드 (wiki build) — 깊은 LLM 추출 단계
wiki build            # L2/L3를 백그라운드 워커에 큐잉 (논블로킹)
wiki build --wait     # L2(Atoms) → L3(Concepts)를 지금 동기 실행
#   - 진행 상황: plugin Dashboard가 backend-local runtime 상태를 읽음

# 단축: 2~4단계(add → build → 임베딩 → sync)를 한 번에 동기 실행
wiki update
```

> **2단계 수집**: `wiki add`는 소스를 등록하고 즉시 L1을 생성한다(구조 기반, LLM 없음) —
> 빠르고 오프라인에서도 동작한다. `wiki build`는 깊은 L2/L3 추출을 수행하며, 기본은 MCP 서버의
> 백그라운드 IngestWorker에 큐잉하고 `--wait`로 즉시 실행할 수 있다. L2 추출은 활성 LLM
> 클라이언트의 prompt budget에 맞춰 section batch 크기를 정하므로, CLI 기반 provider에는
> local high-context 모델보다 작은 prompt가 전달된다. 큰 PDF나 Markdown 배치가 검증에
> 실패하면, L2는 source-span provenance를 보존하는 더 작은 배치로 다시 시도한 뒤에
> 소스를 실패 처리하며, 실패한 실행은 부분 L2 unit을 발행하지 않는다. 진행률은 `wiki status`나
> plugin Dashboard에서 확인한다. L4 Synthesis는 `wiki build`가 생성하며,
> workspace curation은 별도의 staging 패스가 아니라 동적 query 렌즈입니다. eligible
> community report가 없으면 L4 pass는 source를 pending으로 남기지 않고 `skipped`로
> 끝납니다.

### 4-2. 고급 Workspace 큐레이션

```bash
# Workspace 폴더에 curate.yml 생성 (직접 또는 wiki workspace init)
# 전체 필드 레퍼런스:
#   USER_GUIDE_KR.md#curateyml--워크스페이스-설정-레퍼런스

# 워크스페이스 KRS가 반영된 동적 답변 질의
wiki query "질문" --workspace 01_Workspaces/MyProject
```

### 4-3. 검색 및 질의

```bash
# 자연어 질의 (BM25 + vector + LLM rerank + 동적 2-Step RAG)
wiki query "Gaussian Splatting에서 COLMAP 없이 카메라 포즈를 추정하는 방법은?"

# 명시적 Workspace를 지정한 질의 (curate.yml 기반 동적 curation)
wiki query --workspace 01_Workspaces/MyProject "우리의 목표를 요약해줘."

# 검색 인덱스 재구축
wiki reindex

# 전체 상태 확인 (백그라운드 잡 진행률 포함)
wiki status

# DAG 무결성 검사 (v0.2.1 — 기본값: hash 기반 증분 검사)
wiki sync              # 기본: 변경 노드만 재검증 (~1초, 변경 없을 시)
wiki sync --full       # 전체 재검증 (v0.2.0 이전 동작)
wiki lint

# MCP 서버가 꺼져 있거나 즉시 처리하고 싶을 때
wiki jobs list
wiki jobs run          # queued L2/L3 background jobs를 foreground로 처리
wiki jobs cancel <id>  # worker가 claim하기 전 queued job 취소
wiki jobs rerun <id>   # 완료/실패/취소된 job 재queue; queued는 no-op
wiki jobs events <id>  # job의 이력을 오래된 순으로: 지금 상태에 이르기까지의 과정
```

기본 `wiki --help` 화면은 일상적인 사용자 워크플로우 중심으로 제한됩니다.
통합/개발용 명령은 직접 호출할 수 있지만 일반 help 목록에서는 숨깁니다:
Obsidian plugin JSON 호출용 `wiki plugin ...`, 외부 에이전트용 `wiki mcp ...`,
개발 fixture용 `wiki testbed ...`, backend launcher 진단용 `wiki devices ...`.

> **wiki sync 기본 동작 변경 (v0.2.1)**: 변경되지 않은 DAG에서 `wiki sync`는 content_hash 검사만 수행합니다(~0.6초).
> 변경된 노드와 그 하위 노드만 LLM으로 재검증됩니다. 전체 재검증을 원하면 `--full`을 사용하세요.

> **wiki sync가 읽지 못한 영역을 기록합니다 (v0.52.2)**: 수식을 그림으로 저장하는
> PDF는 ingest 단계에서 해당 영역을 통째로 잃습니다 — 그 텍스트는 지식 베이스에
> 아예 들어오지 않습니다. `wiki lint`는 v0.49.0부터 이를 보고해 왔지만, 기록 자체는
> v0.49.0 이후에 ingest된 소스에만 남아 있었습니다. 이제 `wiki sync`가 이전 소스에
> 대해 이를 backfill하고 개수를 보고합니다
> (`Recorded 130 unreadable region(s) that predate the extraction-loss check.`).
> 결정적이며, 제공자 호출이 없고, 디스크를 다시 읽지 않으며, 멱등하므로 몇 번이든
> 실행해도 됩니다. `--no-fix`와 `--dry-run`은 다른 복구와 마찬가지로 이 단계를
> 건너뜁니다.
>
> 사용자에게 달라지는 점: 질문이 그런 영역에 걸리면, 이제 답변이 해당 영역이
> 이미지라는 사실과 크기를 알려주고, 그것을 읽는 두 가지 방법 — PDF 뷰어에서 스닙,
> 또는 `.curator/settings.yml`에 `llm.vision_model`을 설정하고 소스를 다시 add —
> 을 함께 제시합니다. 이전에는 이유를 말하지 않고 얼버무렸습니다. **이것으로 수식이
> 복구되지는 않습니다**; 무엇이 없는지와 어떻게 얻는지를 정확히 알려줄 뿐입니다.

> **Curation-native 질의**:
> - **Workspace Agent**: 워크스페이스가 지정되면 `curate.yml`의 페르소나와
>   Knowledge Requirement Spec을 사용합니다.
> - **Vault Agent**: 일반 Vault 질의는 글로벌 폴백 페르소나를 사용합니다.
> - **L3/L4 근거**: 질의는 필요에 따라 L3 Concepts, L4 Synthesis nodes,
>   memory paths, source sections, insight candidates에서 근거를 선택합니다.
> - **고정 질의 산출물 없음**: 질의 답변은 sessionless이고 `QTR-` trace를 남기며,
>   명시적 승격만 검토된 결과를 `02_Wiki/`에 씁니다.

> **백그라운드 워커 폴백**: MCP 서버가 실행 중일 때 IngestWorker가 대기 중인 작업을 자동으로 처리합니다.
> 테스트나 오프라인 CLI 사용 시에는 `wiki jobs run` 명령으로 큐를 전경(foreground)에서 처리할 수 있습니다.
> 실행하지 않을 queued job은 `wiki jobs cancel <id>`로 취소하고, 완료/실패/취소된 job은
> `wiki jobs rerun <id>`로 다시 queue에 넣을 수 있습니다. 이미 queued 상태인 job에 같은 명령을 실행하면
> 중복을 만들지 않고 성공 no-op으로 처리됩니다. `wiki jobs list`가 job의 현재 위치를 보여준다면,
> `wiki jobs events <id>`는 거기까지 온 과정을 오래된 순으로 보여줍니다 — 느리게 진행 중인 job과
> 멈춰버린 job의 차이이며, `ingest_jobs`의 최신 phase 한 행으로는 표현할 수 없는 정보입니다.

> **즉각적인 L1 / L2·L3 분리**: `wiki add`는 LLM 호출 없이 파서 구조로부터 즉시 CTX, ToC, 섹션 마커 및
> 대략적인 Atom 후보를 생성합니다(구조적 L1). v0.2.2부터 이 단계는 **AST 기반 청킹**을 사용해
> `$$...$$` 같은 수학 수식 블록을 텍스트 분할 중에도 보존합니다. 소스에서 유래한 parser-generated heading
> wikilink는 CTX projection에서 평문으로 렌더링하여 generated 파일이 broken link를 만들지 않게 합니다.
> 이후 L2 추출, community-report synthesis, query answer도 claim이나 답변에 필요한 핵심
> equation, formula, code expression을 정확히 보존해야 합니다. 깊은 L2/L3 추출은 `wiki add`와
> 분리되어 별도의 `wiki build` 명령으로 수행됩니다. 기본 동작은 백그라운드 작업 큐에 넣는 것이고,
> `--wait`는 동기 실행을 요청합니다. MCP에서는 `curator_register_source`가 L1 등록을 담당하고
> `curator_build_source`가 L2/L3 빌드에 대응합니다.

> **v0.2.1 성능 경로**: LLM 클라이언트를 안전하게 복제할 수 있는 경우 L2는 다중 섹션 인식 배치를 병렬로 실행합니다.
> L3는 임베딩 기반 클러스터링을 먼저 시도하고, 임베딩 경로가 없을 때만 기존 LLM 클러스터링 계획으로 폴백합니다.
---

## 5. Obsidian 플러그인 워크플로우

플러그인은 Obsidian 내에서 AI 어시스턴트로 동작하며, 선택적으로 Curator 백엔드와 연동합니다.

```text
Obsidian 플러그인 단독 사용:
  사용자 채팅 → LLM 직접 호출 (Antigravity/Claude/OpenAI/DeepSeek/Ollama)

Curator 백엔드 연동 사용:
  사용자 채팅 → 플러그인이 backend 도구 호출 → Curator가 파생 코퍼스 검색
              → LLM이 추적 가능한 근거로 답변 생성
```

### PDF 처리 흐름 (v0.2.1 — Adaptive Routing)

```text
Obsidian에서 PDF 열기
     │
     │ local PDF.js context 우선; backend fallback 필요 시에만 status 조회
     ▼
┌─── 미등록 ────────────────────────────────────────────────────┐
│ ephemeral L1 모드: PDF.js in-memory 파싱                       │
│ 플러그인 UI: "+ Add to Incurator" 버튼                         │
│ local context 우선; read-only backend parse fallback            │
│ passive chat은 PDF를 import/register하지 않음                   │
└───────────────────────────────────────────────────────────────┘
     │ (사용자가 "+ Add" 클릭 또는 import_source 호출)
     ▼
┌─── 처리 중 ──────────────────────────────────────────────────┐
│ 외부 PDF: 04_Resources markdown reference stub 생성             │
│ 플러그인 UI: "⟳ Processing" 상태 표시                          │
│ 5초 간격 재폴링 → l3_complete=True 되면 자동 업그레이드         │
│ l1_complete 이후 fallback/section 요청은 CTX projection 사용    │
└───────────────────────────────────────────────────────────────┘
     │ (L3 처리 완료)
     ▼
┌─── Added / L3 완료 ──────────────────────────────────────────┐
│ 플러그인 UI: 비활성 "Added" 배지                              │
│ 에이전트: curator_query("질문", workspace_path="...") 사용 가능 │
└───────────────────────────────────────────────────────────────┘
     │
     │ 동적 curation 질의
     ▼
Sources & Trace가 포함된 답변
```

handoff는 우선순위 기반입니다. 등록 후에도 화면에 보이는 PDF.js 텍스트, 선택
영역, crop은 가장 빠른 context로 유지됩니다. local context가 없으면 L1 완료된
등록 source의 durable CTX projection과 `toc_id` locator를 사용합니다. projection이
없거나 preview-only이면 backend가 degradation을 표시하고 원본 PDF를 read-only로
다시 파싱할 수 있습니다. source 등록은 명시적인 Add 동작만 수행하며,
L3-complete source부터 concept-grounded `curator_query`를 사용할 수 있습니다.

---

## 6. Agent 워크플로우

Agent 접근 경로는 두 가지로 분리합니다:

- **같은 기기 안의 Obsidian plugin agent**는 shared runtime snapshot과 숨겨진
  `wiki plugin ...` JSON command를 사용합니다. 로컬 backend 접근을 위해
  `wiki mcp`를 시작하지 않습니다.
- **외부 workspace agent**(Claude Code, Claude Desktop, Antigravity 등 MCP
  client)는 `wiki mcp`를 사용합니다.

두 경로를 섞지 않습니다. 같은 기기 안의 Obsidian plugin 기능은
`wiki plugin ...` 아래에 추가하고, 외부 agent 기능은 MCP server에 추가합니다.

### 외부 Agent(MCP) 워크플로우

Claude Code, Antigravity 같은 AI 에이전트는 MCP 서버를 통해 Curator에 접근합니다.

#### MCP 서버 시작

```bash
# Vault를 지정해서 MCP 서버 실행
VAULT_ROOT=/path/to/vault wiki mcp

# 또는 MCP 클라이언트 설정에서 env로 지정:
# {
#   "mcpServers": {
#     "incurator": {
#       "command": "wiki",
#       "args": ["mcp"],
#       "env": { "VAULT_ROOT": "/path/to/vault" }
#     }
#   }
# }
```

### 에이전트 세션 흐름

```text
에이전트 세션 시작
     │
     │ 1. curator_check_workspace(workspace_path)
     │    → curate.yml 유효성 확인 및 에이전트 룰 설치
     ▼
도메인 질의 발생
     │
     │ 2. curator_fetch_context(query, workspace_path)
     │    → 에이전트 grounding용 bounded ContextService pack 반환
     │    → curator_query는 동일 pack 위에서만 합성 가능
     ▼
답변 생성 (검색 결과 인용)
     │
     │ (선택) 검토된 인사이트 승격
     │ 3. curator_add_knowledge(insight, context)
     │    → human-reviewed note를 02_Wiki/에 기록
     ▼
세션 종료
```

### 주요 MCP 도구

| 도구 | 용도 |
|------|------|
| `curator_check_workspace` | 세션 시작 시 Workspace 상태 점검 및 룰 설치 |
| `curator_fetch_context` | 에이전트 grounding용 bounded normalized context pack 반환 |
| `curator_query` | Sources & Trace가 포함된 자연어 답변 |
| `curator_workspace_init` | 새 Workspace 생성 (인터뷰 방식) |
| `curator_add_knowledge` | 검토된 대화 지식을 `02_Wiki/`로 승격 |
| `curator_propose_correction` | 생성 노드에 대한 검토된 correction 제안 |
| `curator_get_node` | 특정 노드(CTX/ATM/CON/SYN) 내용 조회 |

Plan F는 외부 MCP 에이전트와 Obsidian 에이전트를 같은 ContextService pack
계약으로 라우팅합니다. 요청, scope, budget, snapshot 입력이 같으면 최종 provider
prompt 형식은 달라도 normalized backend pack은 동등해야 합니다.

---

## 6-1. 백그라운드 처리 모니터링

플러그인 Add Source 또는 `wiki build`가 queue에 넣은 L2/L3 작업은 MCP 서버의
IngestWorker 스레드, `wiki jobs run`, 또는 Dashboard의 **Run queued**가 처리합니다.
진행 상황을 확인하는 방법은 세 가지다.

### 방법 1: Incurator Dashboard (Obsidian)

IngestWorker가 자동으로 갱신하는 파일로, Obsidian live preview에서 실시간 확인 가능하다.

```text
# Incurator Build Status
*2026-05-29T14:32:07Z*

## Active
| Source         | Phase       | Progress |
|----------------|-------------|----------|
| paper_xyz.pdf  | l3_concepts | 3/5      |

## Queue
| Source         | Phase    |
|----------------|----------|
| new_paper.pdf  | l2_atoms |

## Completed Today
2 jobs · 47 atoms · 8 concepts
Cost: $0.043
```

### 방법 2: wiki status (CLI)

```bash
wiki status
# Background jobs 섹션에서 진행 중인 잡 목록 확인
```

### 방법 3: 플러그인 상태 바

Obsidian 하단 상태 바에 `⚡ 2 running / 1 queued` 형태로 표시.
클릭 시 `dashboard.md`를 Obsidian에서 오픈.

---

## 7. 설치 흐름

```bash
# 1. 저장소 클론
git clone https://github.com/your/incurator.git
cd Incurator

# 2. 전체 설치 (백엔드 + 플러그인)
./setup.sh

# 3. Vault 초기화
wiki init /path/to/your/vault

# 4. MCP 설정 자동 갱신 (setup.sh이 처리하거나 수동으로)
#    wiki init 실행 시 아래 파일들을 자동 갱신:
#    - ~/.antigravity/settings.json
#    - ~/.antigravity/mcp_config.json
#    - <vault>/.claude/settings.json

# 5. 소스 추가
wiki add 03_Notes/

# 6. 검색 확인
wiki query "첫 번째 질문"
```

---

## 8. 데이터 흐름 요약

```text
[Human Layer]
  03_Notes/ ──┐
  04_Resources/ ──┤── wiki add ──► L1 CTX ──► wiki build ──► L2 ATM ──► L3 CON
  02_Wiki/ ───┘                                                           │
                                                                          │ wiki query
[Machine Layer (state.sqlite DB)]                            ▼
  .curator/Collections/04_Synthesis/ ◄─────── L4 SYN (shared)
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
    wiki query  MCP Agent  Obsidian Plugin
   (CLI 검색)  (AI 에이전트) (채팅 사이드바)
```

---

## 9. v0.3.2 큐레이션-네이티브 컴파일 모델

v0.3.2는 Curator를 **컴파일러**로 만듭니다. 중간 표현(IR)은 DB이고, 마크다운
컬렉션은 Obsidian 표시용 파생 산출물이며 검색 코퍼스가 아닙니다.

- **`state.sqlite`가 큐레이션 지식의 유일한 진실원**입니다: `source_spans`,
  `knowledge_units`, `graph_entities`/`graph_relations`, `community_reports`,
  `memory_paths`, 의존성, 프롬프트 실행, 인사이트 후보.
- **`.curator/Collections/`의 L1–L4 마크다운(CTX/ATM/CON/SYN)은 DB에서 emit**되어
  Obsidian에서 확인할 수 있는 projection으로 쓰입니다. 권위가 없고 언제든 재생성 가능 →
  DB↔파일 드리프트 없음. no-op reemit은 L4 synthesis revision을 올리지 않습니다.
- **검색은 DB-native**입니다: authoritative record에 대한 FTS5, chunk-level
  vector, typed query expansion, RRF, configured reranking을 사용합니다. 현재 chunk
  embedding은 설정된 embedding identity가 사용 가능할 때만 재사용됩니다.
- **L4 Synthesis는 생성된 검색 projection**이며 사람이 직접 편집하는 산출물이
  아닙니다. 지속적인 human-reviewed 결과는 명시적 승격으로만 `02_Wiki/`에 기록됩니다.

전방 컴파일 흐름:

```text
wiki add   → 파싱(LLM 없음) → DB source_spans              → CTX projection emit
wiki build → LLM            → DB knowledge_units            → ATM projection emit
           → LLM+임베딩      → DB entities/relations/reports → CON projection emit
           → DB-native search rows/chunks/embeddings
wiki query → 라우트 → typed expansion + FTS5/vector/RRF/rerank + DB 그래프 탐색 → 답변 + QTR
```

### 9.1 쿼리 라우트

`wiki query "..." --route <route>` 는 v0.3.1 `QueryOrchestrator`로 답합니다:
`local`(엔티티/사실), `global`(커뮤니티 리포트), `explore`(메모리 경로 + 인사이트
후보), `source-section`(특정 원본), `auto`(orchestrator 선택)를 지원합니다.
`--route`가 없으면 `auto`가 실행됩니다. 동일 라우팅이 MCP `curator_query` /
`curator_explore`로 에이전트에도 제공됩니다. v0.20.0부터는 explore를 포함한 모든
라우트가 통합 `ContextService` 팩(`PACK-*`/`SNAP-*` 스냅샷 + 공유 토큰 예산) 위에서
grounding하며, explore의 후속 질문/인사이트 생성은 별도 검색 경로가 아니라 그 팩을
소비하는 synthesis 단계로 수행됩니다(SYSTEM_BEHAVIOR §31.8).

### 9.2 백프롭 & 인사이트 라이프사이클 (역방향 패스)

사람/에이전트 피드백은 **loss signal**입니다. 역방향 패스는 패치 전에 변경을
분류하고 원본 진실을 보호합니다:

- 에이전트는 MCP `curator_propose_correction`으로 피드백을 correction /
  contradiction / derived_insight / style_only / promotion_request / ambiguous로
  분류합니다. 이 도구는 자동 패치 없이 권장 동작과 영향받는 생성 노드 id를
  반환하며, 파생 인사이트는 잠정 **인사이트 후보**가 될 수 있습니다.
  `03_Notes/`/`04_Resources/`는 절대 수정하지 않습니다.
- `wiki insight list|show|promote`(또는 MCP `curator_list_insight_candidates` /
  `curator_promote_insight`)로 후보를 검토하며, 승격은 `02_Wiki/`에만 기록합니다.

### 9.3 프롬프트 추적성

모든 LLM 호출은 등록된 버전 있는 프롬프트 계약이며 `prompt_runs`(`PTR-`) 트레이스
(모델, 검증자 상태, 입출력 해시)를 남깁니다. Prompt version은
`v<정수>(.<정수>)*` 형식을 사용하며, 잘못된 version은 등록을 거부하고 최신
version과 목록은 숫자 순서로 정렬합니다(`v10`은 `v9` 다음입니다). Provider
failover가 성공하면 trace에는 row 생성 시 기록된 실패한 primary나 validation
완료 전에 복구된 primary가 아니라, 저장된 output을 만든 응답 단위의
provider/model이 기록됩니다. `wiki prompt list|show|trace|eval`
또는 MCP `curator_get_prompt_trace`로 검사합니다. provider 호출이 trace 생성 후
예외를 내면 해당 trace는 `pending`으로 남지 않고 예외 내용과 함께 `failed`로
닫힙니다. 모든 쿼리는 라우트·증거·프롬프트 실행을 잇는 `QTR-` 트레이스를
기록합니다.
쿼리 합성이 실패하면 QTR은 검색 근거를 유지하고 실패한 PTR을 연결하며 failed
synthesis child action을 기록합니다. CLI, MCP, hidden plugin surface는 동일한
기존 필드 실패 결과를 노출하고, CLI/hidden command만 종료 코드 1을 사용합니다.

---

## 10. v0.8.0 증거 컴파일러 무결성 (Evidence Compiler Integrity)

v0.8.0은 §9의 순방향 컴파일 흐름을 클레임 수준 grounding과 원자적 발행으로
강화합니다 (스펙: SCHEMA.md §20, SYSTEM_BEHAVIOR.md §26):

- **최소 클레임 지지**: `wiki build`는 L2 클레임마다 그 클레임을 entail하는
  최소 span 집합을 기록하고(`primary`/`contextual`/`formula` 역할의
  `claim_supports` 행) 이를 검증합니다. 실재하는 span id만으로는 더 이상
  지지의 증거로 취급되지 않습니다.
- **생성된 L2 필드는 영어**: 생성된 Atom 이름과 statement는 영어로 검증됩니다.
  비영어 생성 출력은 한 번 repair retry를 거치며, 그래도 실패하면 발행되지
  않습니다.
- **스테이징된 generation**: 모든 컴파일은 `GEN-` 컴파일러 generation 안에서
  실행됩니다. generation 소유 claim, support, graph 상태는 감사 게이트를
  통과한 뒤에만 함께 발행되며, 실패한 컴파일은 스테이징된 generation을
  폐기하고 이전 generation이 계속 서비스합니다. 안정적인 projection
  identity/의존성 행과 폐기 가능한 마크다운/검색 출력은 복구 가능한
  post-publish 단계에서 DB로부터 완성됩니다.
- **복구 가능한 projection 단계**: 권위 DB 트랜잭션 뒤에 안정적인 Atom id와
  의존성 행을 먼저 저장한 다음 파생 파일을 emit합니다. projection 또는 검색
  갱신이 실패하면 generation은 권위 상태로 유지되고 소스에는 post-publish
  projection 오류가 기록됩니다. 오류를 기록하기 전 중단되어도 같은 복구
  경로를 사용하도록 pending marker가 generation과 함께 커밋됩니다. 재시도는
  LLM을 다시 호출하거나 대체 generation을 만들지 않고 DB에서 모든 파생
  projection과 검색 행을 재생성한 다음, 다음 sync가 그 출력을 수동 편집으로
  오인하지 않도록 ATM/CON/SYN 페이지 hash 기준선도 갱신합니다. 보존된 live
  CTX hash는 다시 쓰지 않고, 복구가 제거한 orphan CTX hash만 삭제합니다.
- **멱등한 재빌드**: 변경 없는 소스에 `wiki build`를 다시 실행하면
  authoritative generation의 id, 해시, 카운트를 재사용합니다 — 중복 누적이
  없습니다.
- **편집/삭제/분할 reconciliation**: 소스 변경은 측정된 의존성 클로저만
  재생성합니다. 근거를 잃은 클레임은 retire 처리되고(감사용으로 보존, 서빙
  제외), 오래된 span은 방치되지 않고 정리됩니다.
- **완전한 소스 제거**: 로컬 제거와 가져온 source tombstone은 generation,
  claim, 그래프 지지/보고서, synthesis, span, 기기 로컬 파생물을 하나의 동일한
  트랜잭션 클로저로 닫습니다. 공유 그래프 상태는 다른 live 독립 지지가 있을
  때만 남고, rematerialization이 끝나기 전에도 serving query는 live source
  provenance를 요구합니다. 커밋 후 projection 갱신이 실패해도 제거는 유지되며
  결정적 복구 명령으로 `wiki sync --reemit`을 보고합니다.
- **수식 라이프사이클**: 핵심 수식은 증류를 거쳐도 본문에 온전히 유지되거나
  정확히 링크된 수식 증거로 남습니다. 선택적 시각 복구는 측정된 손실
  영역(`fragmented`/`image_only`/`parser_omitted`)에서만 실행되고, 원시
  증거와 분리 저장되며, 파서 출력을 절대 덮어쓰지 않습니다.
- **전체 span 증거**: evidence pack은 200자 미리보기를 증거로 제시하는 대신
  소스 파일에서 정확한 span 텍스트를(해시 검증과 함께) 하이드레이션합니다.
- **lint 감사**: `wiki lint`가 Compiler Integrity telemetry를 보고합니다.
  `failed`/`stale`/`unchecked` 클레임은 serving에서 제외되며 그 자체로 sync
  review blocker가 되지 않습니다. lint는 dangling support reference나
  formula evidence 불일치처럼 serving DAG를 깨는 구조 위반에서만 실패합니다.

---

## 11. v0.9.0 그래프 품질 (Graph Quality)

v0.9.0은 신뢰할 수 있는 v0.8.0 클레임을 가역적이고 지지(support) 인지형인
지식 그래프와 결정론적 커뮤니티 계층으로 컴파일합니다 (스펙: SCHEMA.md §21,
SYSTEM_BEHAVIOR.md §27). §10 위에 구축되며, 그래프 구성은 완전히 발행된 하나의
클레임 generation만 소비합니다:

- **안전한 엔티티 병합**: 이름이 비슷한 것은 언제나 *후보*일 뿐입니다. 동의어,
  약어, 번역어는 타입/맥락/모순 가드를 통과한 뒤에만 병합되고, 모호한
  동음이의어(예: 행성 "수성" vs. 원소 "수은")는 결정 전까지 분리된 채로
  남습니다. 수락된 병합은 모두 원본 정체성과 완전한 재작성 기록을 보존하므로
  정확히 되돌릴 수 있습니다.
- **추출 관계는 독립적 지지를 갖는 명제입니다**: 같은 관계를 다시 추출하면
  지지를 덮어쓰지 않고 클레임 수준 지지를 *추가*합니다. 독립성은 소스
  계보(lineage)로
  계산되므로, 복사/포크된 소스는 여러 번이 아니라 한 번으로 셉니다. 관계가
  `active`가 되려면 **독립 소스 계보 1개 이상**이면 됩니다(v0.43.0; 검증된
  지지가 0개일 때만 `unsupported`). 따라서 서로 다른 논문들로 이뤄진 Vault도
  개념과 보고서가 정상 생성됩니다. 이전의 2개 규칙은 계보 해시가 이미 복제본을
  접기 때문에 중복을 걸러낸 게 아니라, 논문 하나만 말하는 사실 전부를
  배제했습니다(실제 연결: L2 컴파일이 단언 클레임마다 소스 계보로 키가
  매겨진 `graph_relation_supports` 행을 하나씩 기록하고, `wiki build`/`wiki
  update`의 L3가 확증된 `active` 관계에만 보고서를 근거시킵니다).
- **작성 노트 토폴로지**: 등록된 visible `.md` 및 `.markdown` 노트의 정확한
  내부 wikilink, embed, tag, frontmatter wikilink는 결정론적 `authored`
  엣지로 컴파일됩니다. pipe label과 heading/block fragment는 여전히 같은
  노트/asset 페이지로 해석되고, 깊이가 제한된 균형 잡힌 중첩 label과 Markdown
  대상, vault 내부의 안전한 상위 상대 경로도 동작합니다. escape와 percent
  encoding은 한 번만 정규화됩니다. escape된 문법, 숫자로만 된 의사 태그,
  코드/주석, 모호한 대상, 외부·숨김 경로, vault 밖 traversal은 fail closed
  처리됩니다. portable 경로는 Unicode로 정규화됩니다. 편집, 이름 변경, 삭제,
  비-Markdown 형식 전환은 오래된 엣지를 원자적으로 retire 처리하며, replica
  import는 authored 토폴로지를 제공하기 전에 승자 generation의 정확한
  membership을 복원합니다. generation이 하나뿐이어도 reconciliation을
  실행하므로 소스 tombstone 뒤에 토폴로지가 active로 남지 않습니다.
- **관계 라이프사이클**: 추출 관계는 검증된 독립 지지와 해소된 엔드포인트가
  있어야만 `active`가 됩니다. 작성 관계는 정확한 구조가 현재 성공한 소스
  generation에 속할 때 `active`가 되며, 가짜 사실 지지를 만들지 않습니다.
  약한 추출 엣지는 사유(`unsupported`, `self_loop`, `contradiction`,
  `bridge_risk`, `endpoint_unresolved`; `copied_source_only`는 v0.43.0에서
  결과값으로 폐기되었고 과거 행의 해독을 위해서만 남아 있습니다)와 재평가
  트리거와 함께 `quarantined` 처리됩니다. 관계는 결코 "중복"이 아닙니다.
  같은 명제를 다시 단언하면 지지가 그 하나의 관계로 합산되므로, 엣지는
  `unsupported`이거나 합산된 지지를 갖는 유효한 관계일 뿐 격리할 중복이 없습니다.
  저작(authored) 링크와 추출(extracted) 관계는 별도 클래스로 유지됩니다.
  `active` 관계만 토폴로지와 explore path를 구성합니다.
- **결정론적 계층**: 커뮤니티 알고리즘은 벤치마크로 선택되며, 같은 그래프 +
  설정 + 시드는 매번 같은 계층을 만들고, 필터링된 연결 요소(connected
  components)를 명시적 성능저하 폴백으로 둡니다. 설명되지 않는 거대 컴포넌트는
  없습니다.
- **클레임 기반 보고서**: active 작성 엣지는 커뮤니티 membership을 구성할 수
  있지만, 커뮤니티 보고서는 정확한 적격 추출 클레임 지지만 인용합니다. 작성
  링크는 사실 근거가 되지 않으며, 작성 엣지만 있는 컴포넌트는 가짜 사실
  보고서를 만들지 않습니다. "커뮤니티 전체" 광역 폴백은 제거되었습니다.
  입력이 바뀐 보고서는 synthesis가 사용하기 전에 retire 후 재생성되며,
  replica reconciliation은 이미 승자 작성 관계를 의존성으로 기록한 import
  보고서를 보존합니다.
- **최신 그래프 검색**: retire된 작성 관계와 active 엣지가 없는 작성
  note/asset/tag 엔티티는 명시적 소스 삭제를 포함한 그래프 검색
  rematerialize 때 제거됩니다.
- **confidence는 노이즈 다이얼이 아닙니다**: 관계 `confidence`는 서빙 시점
  필터로 사용되지 않습니다(프로덕션 값이 모두 0.9–1.0이었음). 격리 결정은 raw
  confidence 컷오프가 아니라 지지 적격성과 구조 신호를 사용합니다.
- **lint 감사**: `wiki lint`에 Graph Quality 섹션이 추가되어 병합되어 사라진
  엔티티 참조, 유효하지 않은 active 관계, 해소되지 않은 엔드포인트, 근거 없는
  보고서, 동음이의어 오병합(0건이어야 함)을 검증하고, 릴리스를 막아야 하는
  위반에서 0이 아닌 종료 코드로 종료합니다.

---

## 관련 문서

- [플러그인 가이드](PLUGIN_GUIDE_KR.md) — Obsidian 플러그인 기능 상세
- [MCP 사용 가이드](MCP_USER_GUIDE_KR.md) — AI 에이전트 MCP 연결 설정
- [사용자 가이드](USER_GUIDE_KR.md) — CLI 명령어 레퍼런스
- [시스템 철학](../philosophy/ABOUT_KR.md) — Curator/Artist 메타포 배경
