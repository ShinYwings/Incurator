# Incurator Master Roadmap & Todo List

아키텍처 대공사 및 향후 업데이트를 위한 마스터 로드맵입니다.
이 문서는 에이전트들이 향후 마일스톤을 어떻게 계획하고 실행해야 하는지에 대한 핵심 지침을 제공합니다.

## 🚨 Update Classification & Planning Rule

모든 에이전트는 작업 시작 전 반드시 `.agents/USER_REPORT.md`를 단일 진실 공급원(Single Source of Truth)으로 삼아 미해결 항목(To-Do)을 파악해야 합니다. 
항목의 업데이트 규모에 따라 다음의 기획 규칙을 **반드시** 따라야 합니다:

- **메이저(Major) 및 마이너(Minor) 업데이트** (버전 `v.X.Y.Z`에서 X, Y가 증가하는 아키텍처/기능 변경):
  - **절대 코드를 바로 작성하지 마세요.**
  - `USER_REPORT.md`의 항목을 바탕으로, 구현 시작 전에 반드시 `.agents/PLAN_TEMPLATE.md` 템플릿을 엄격하게 준수하여 마일스톤 명세서와 세부 플랜을 작성해야 합니다.
  - 작성된 플랜은 파편화를 막기 위해 본 문서(`ROADMAP.md`)의 해당 마일스톤 항목 하단에 병합하여 관리해야 합니다.
- **핫픽스(Hotfix) 및 단순 버그 수정(Fix)** (버전 `v.X.Y.Z`에서 Z가 증가하는 규모의 버그 수정):
  - 무거운 템플릿 작성 절차에서 예외로 인정되며, 즉시 원인 분석 및 수정(Fix)이 가능합니다.

---


## 📥 Triage & Queuing (할 일 대기열)

`.agents/USER_REPORT.md`에서 접수된 유저의 요청들이 실제 마일스톤으로 기획/편입되기 전 대기하는 공간입니다.

### 🚀 향후 해결할 미해결 항목 (To-Do)

### 1. Knowledge Sync Bridge ← 최우선
기기 간 지식(`state.sqlite`) 파편화 문제 해결. JSONL 기반 Export/Import 파이프라인과 Tombstone 충돌 해결 로직 구현. PDF Annotation 마일스톤의 전제 조건.

- `backend/src/curator/db_sync.py` 신규 구현
- `wiki db export / wiki db import` CLI 추가
- 기기 종속 데이터(임베딩 등) Export 블랙리스트 정책
- 연관 USER_REPORT 항목: 없음 (독립 인프라 마일스톤)

### 2. Minor Quick Wins
독립적인 소규모 개선 항목들. 백엔드 대공사와 무관하게 플러그인 단독 작업 가능. Knowledge Sync Bridge와 병행 또는 그 사이에 처리.

**[마이너 업데이트] 웹 검색 기능 구현 검토**
- 현상: 로컬 모델(Ollama, Deepseek 등) 사용 시 웹 검색 기능 연동을 지원할지 설계 및 구현 필요.

**[검증 필요] L1~L4 생성 문서 내 Obsidian `[[wikilink]]` 명시적 링킹 도입 여부 검토**
- 현상: 백엔드 파이프라인에서 생성되는 L1~L4 문서들에 핵심 엔티티나 개념이 옵시디언 고유의 `[[wikilink]]` 문법으로 명시화되어 있지 않음.
- 불확실성(Pending): 사용자 기억상 과거 DB 구조에서 백링크(Backlink) 추적 시 정규식 편의를 위해 `()` 또는 일반 마크다운 링크를 쓰느라 `[[wikilink]]`를 의도적으로 제거했을 가능성이 있음.
- 요구사항: 무작정 프롬프트를 고치기 전에, 기존 백엔드 DB의 파싱 로직(`()` 백링크 처리 등)과 `[[wikilink]]` 문법이 충돌하지 않는지 아키텍처 레벨에서 검증 후 도입 여부 결정.

**[마이너 업데이트] Diff Viewer UI/UX 개선**
- 현황: `plugin/src/ui/diffViewer.ts` (530줄)에 기능 구현은 되어 있으나 현재 UI/UX가 불편함.
- 요구사항: 사용자가 직관적으로 변경사항을 수락/거절할 수 있도록 UI/UX 전반 개선. 예: 버튼/헝크 레이아웃 정리, 다크/라이트 테마 대응, 키보드 단축키 힌트 표시, 헝크 간 이동 UX 등.

### 3. RAG & Knowledge Quality Stabilization
검색 품질과 지식 추출 정확도를 높입니다. FTS5 + Qwen3 Reranker 파이프라인 안정화, 수식 누락 문제 해결, 엔티티 중복 병합, GraphRAG급 군집화 도입. 가장 복잡한 Major 작업.

**[매이저 업데이트] qmd/검색 엔진 심층 분석 및 보완**
- 현상: qmd가 어떻게 동작하는지 repository를 심층 분석해서 search engine에서 부족한 부분 보완.

**[매이저 업데이트] PDF 및 정제된 지식(Atom, Concept) 내 수학 수식 누락 문제 해결**
- 현상: 현재 pymupdf4llm을 기본 파서로 사용 중이나, 표나 텍스트 흐름 보존과 달리 복잡한 공학/수학 논문의 블록 수식은 완벽한 LaTeX 코드로 역변환(OCR)되지 않고 깨지거나 누락되어 L1에 온전히 반영되지 않음. 또한, Markdown 원본에는 수식이 유지됨에도 불구하고, 이를 바탕으로 L2(Atom), L3(Concept)로 지식을 정제하는 과정에서 LLM이 수식을 보존하지 않고 증발시키는 문제가 있음.
- 팩트체크 필요: 아키텍처 개편에 앞서, 실제로 pymupdf4llm이 수식 영역을 마크다운으로 변환할 때 어떤 형태의 텍스트(Garbage text)로 파편화하여 뱉어내는지, 혹은 완전히 생략해버리는지에 대해 L1 생성 결과물에 대한 구체적인 팩트체크 및 디버깅이 선행되어야 함.
- 개선 방향 (하이브리드 파이프라인): 팩트체크 결과에 따라, 페이지 전체를 VLM에 넘기는 대신 pymupdf4llm으로 텍스트와 뼈대를 빠르게 잡고 수식(Formula)으로 판별된 영역만 이미지 캡처 후 백엔드 VLM(Claude, Gemini 등)에게 넘겨 LaTeX 코드로 번역하는 하이브리드 추출 방식 도입 검토. 아울러 LLM 지식 추출 프롬프트 자체도 수식을 보존하도록 강화 필수.

**[매이저 업데이트] 지식 정제용 LLM과 쿼리 확장(HyDE)용 LLM 설정 분리 및 UI/CLI 노출**
- 현상: 사용자의 VRAM 환경과 용도(지식 정제용 무거운 모델 vs 쿼리 확장용 가볍고 빠른 로컬 모델)에 맞게 각각 독립적으로 모델을 선택할 수 있도록 설정 옵션을 명확히 제공해야 함.
- 팩트체크 필요: 현재 백엔드 설정(config.py) 내부에 query_expander 관련 구조가 어느 정도 준비되어 있는지, 그리고 CLI(wiki config provider)와 플러그인 대시보드 UI에서 사용자가 이 두 모델을 직관적으로 따로 선택할 수 있도록 노출되어 있는지 팩트체크 및 검증 후 미비점 보완 필요.

**[매이저 업데이트] GraphRAG급 엔티티 통합(Entity Resolution), 노이즈 필터링 및 보관소 용량 관리(Vault Quota) 아키텍처 설계**
- 현상: 현재 자체 DB(graph_entities, graph_relations) 구조상 동의어나 유사 개념이 파편화되어 중복 저장되거나 노이즈 엣지가 무한 증식할 위험이 있음. .curator DB와 마크다운 파일들이 방치되면 컴퓨터 디스크 용량이 터질 수 있음.
- 요구사항 1 (노이즈 필터링): 추출된 지식을 DB에 꽂아넣기 전/후로 임베딩 유사도 및 LLM을 활용해 동일한 엔티티를 병합하고 연결선 가중치를 정밀하게 최적화하는 파이프라인 아키텍처 설계 요망.
- 요구사항 2 (용량 관리/Context Compat): 무한 증식을 막기 위해 보관소 최대 용량(Default: 200GB) 제한(Quota) 개념 도입.
- 요구사항 3 (UI/UX 가시성): 사용자가 용량 압박을 직관적으로 인지할 수 있도록, Claude Code 스타일의 원형 프로그레스 바(Circle Bar) 형태의 UI를 도입.
  - 옵시디언 에이전트: 채팅창 상단에 상시 표시.
  - CLI: wiki status 출력 결과에 텍스트/이모지 기반 진행률 바 표시.
  - wiki init 시에도 명시적으로 용량 정책 안내 및 설정.

**[매이저 업데이트] 전역적 사고(Global Sensemaking)를 위한 계층적 군집화 알고리즘 설계 플랜 작성**
- 현상: 수백 편의 논문 전체를 아우르는 거시적 통찰력(Global Summary)이나 커뮤니티 단위의 요약 기능이 부족함.
- 요구사항: MS GraphRAG의 Leiden 알고리즘 등을 벤치마킹하여, 파편화된 L2(Atom) 지식들을 수학적으로 묶어 L3(Concept/Community) 단위로 자동 군집화하는 고도화된 클러스터링 로직 구현 플랜 작성 요망.

### 4. Native PDF Annotation System

**Linked user_report Items**
현재 user_report에 직접 대응 항목 없음 (Knowledge Sync Bridge 완료 후 진행).
구현 완료 후 관련 user_report 항목이 생기면 여기에 추가.

**Context**
Zotero에 의존하던 어노테이션 시스템을 자체 시스템으로 교체합니다. 옵시디언 내장 PDF Viewer를 활용하여 하이라이트와 메모를 `state.sqlite`에 직접 저장하고 오프라인 동기화합니다.

**Multi-Agent Debate Topics (For Codex & Claude)**
1. **`schema_guardian`**: 
   - `pdf_annotations` 테이블 스키마 설계 시, 옵시디언 캔버스(Canvas)와의 연동을 위해 어노테이션 블록(Block)을 어떻게 참조 가능하게 만들 것인가?
2. **`source_pair_analyst`**: 
   - 형광펜으로 밑줄 친 텍스트가 RAG 파이프라인의 `source_spans`로 직접 편입(Promotion)될 수 있도록 설계할 수 있는가?
3. **`plugin_ux_designer`** (New role): 
   - 플러그인 프론트엔드(`pdfCapture.ts` 주변)에서 Zotero의 형광펜 UX와 동일한 수준의 부드러운 하이라이팅 및 팝업 메모 UI를 어떻게 구현할 것인가? 백엔드와의 통신(IPC) 성능 최적화 방안은?

**Implementation Skeleton**
- `backend/src/curator/db.py`: `pdf_annotations` 테이블 생성.
- `plugin/src/pdf/*`: 형광펜 렌더링, 이벤트 리스너, IPC 전송 로직 추가.
- `backend/src/curator/mcp_server.py` 또는 IPC 라우터: 플러그인으로부터 어노테이션 생성/조회/삭제 요청을 받아 DB에 반영.
- `backend/src/curator/db_sync.py`: `pdf_annotations` 테이블을 Knowledge Sync Bridge Export/Import 대상에 포함.

### 🧊 Blocked / Icebox (대기 중인 보류 항목)
- 외부 의존성(라이브러리 업데이트 등) 문제로 당장 해결할 수 없는 항목들을 이곳에 보관합니다.
- (참고: 에이전트의 최우선 해결 의무에서 이 섹션의 항목들은 예외로 취급됩니다.)

---

## 📌 Current Focus & Future Updates

로드맵의 구체적인 To-Do 리스트는 유저의 Inbox인 `.agents/USER_REPORT.md`에서 본 문서의 `Triage & Queuing` 섹션으로 이관되어 관리됩니다. 본 문서는 대기열(Queue)과 현재 진행 상황 및 향후 방향성을 모두 통합 관리합니다.

### 🟢 지금 진행 중인 작업 (Current Active Milestone)
- **Knowledge Sync Bridge 파이프라인 구현** (최우선 과제 / Major)
  - **현황**: 기기 간 지식(`state.sqlite`) 파편화 문제를 해결하기 위해, JSONL 기반 Export/Import 파이프라인과 Tombstone 충돌 해결(LWW) 로직을 구축 중입니다.
  - **목적**: 이후 진행할 Native PDF Annotation 시스템의 필수 전제 조건입니다.

### ⏩ 앞으로 진행할 업데이트 방향 (Future Roadmap)
위의 현재 작업이 완료된 후, `USER_REPORT.md`를 기반으로 다음 규모의 업데이트들이 대기 중입니다 (진행 시 반드시 PLAN_TEMPLATE 작성 필수):
1. **Minor Quick Wins (Minor)**: 웹 검색 연동 검토, Obsidian 백링크 명시적 링킹 도입 여부 검증, Diff Viewer UI/UX 개선.
2. **RAG & Knowledge Quality Stabilization (Major)**: 검색 엔진(Qwen3 + FTS5) 심층 분석 및 보완, 수식 누락 해결을 위한 하이브리드 추출 도입, 엔티티 중복 방지를 위한 통합 로직, 보관소 용량 관리 가시성 제공.
3. **Native PDF Annotation System (Major)**: 외부 Zotero 의존성 제거, 옵시디언 내장 PDF Viewer를 활용한 자체 하이라이트/메모 동기화 체계 구축.

---

## 🤖 Multi-Agent Debate Protocol
(메이저/마이너 플랜 작성 시 에이전트들이 필수로 거쳐야 할 검증 시뮬레이션 역할)

- **`schema_guardian`**: `state.sqlite` 스키마 변경 시 `docs/specs/`와 동기화 무결성 방어.
- **`cli_regression_runner`**: 각 마일스톤 완료 후 `testbed/`에서 CLI 회귀 테스트 시나리오 실행.
- **`source_pair_analyst`**: 지식 정제 및 어노테이션 변경이 L1~L4 DAG 생태계에 미치는 파급 효과 분석.

## 📁 Evidence Ledger (사전 검증 장부)
문서화, DB 마이그레이션, 플러그인 코드가 실제 레포지토리와 볼트의 상태에서 어긋나지 않도록, 에이전트들은 `PLAN_TEMPLATE.md` 기획 단계에서 다음 사항을 반드시 수집하고 검증해야 합니다.

1. **Current Repository & Schema Reality**: 현재 스키마(`sources`, `synthesis_nodes` 등)가 시스템 스펙 문서를 정확히 반영하고 있는지 사전 팩트 체크.
2. **Current Dirty Worktree**: 사용자나 타 에이전트가 작업 중인 커밋되지 않은 변경 사항 파악 (강제 덮어쓰기 방지).
3. **Rollback Requirements**: 파괴적 작업(DB 변경 등) 전 안전한 백업 및 복구(Rollback) 포인트 지정.
