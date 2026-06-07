# User Report

> **에이전트 참고**: 각 항목 옆 `→ plan` 링크가 해당 마일스톤 명세서입니다.
> 배치 작업 시 같은 plan에 묶인 항목들은 함께 처리하세요.



## 🚀 향후 해결할 미해결 항목 (To-Do)

### 📦 knowledge_sync_bridge.md 배치
- **[매이저 업데이트] Knowledge Sync Bridge 파이프라인 구현** → `knowledge_sync_bridge.md`
  - 현상: 기기 간 지식(`state.sqlite`)이 파편화되는 문제를 해결하기 위해, JSONL 기반 Export/Import 및 Tombstone 충돌 해결(LWW) 로직이 필요함 (PDF Annotation 마일스톤의 전제 조건).
  - 요구사항: `wiki db export` / `wiki db import` CLI 추가, 기기 종속 데이터 필터링, 그리고 `deleted_records` 기반의 무손실 라운드트립 동기화 체계 구축.

### 📦 minor_quick_wins.md 배치
- **[마이너 업데이트] 웹 검색 기능 구현 검토** → `minor_quick_wins.md`
  - 현상: 로컬 모델(Ollama, Deepseek 등) 사용 시 웹 검색 기능 연동을 지원할지 설계 및 구현 필요.
- **[검증 필요] L1~L4 생성 문서 내 Obsidian `[[wikilink]]` 명시적 링킹 도입 여부 검토** → `minor_quick_wins.md`
  - 현상: 백엔드 파이프라인에서 생성되는 L1~L4 문서들에 핵심 엔티티나 개념이 옵시디언 고유의 `[[wikilink]]` 문법으로 명시화되어 있지 않음.
  - 불확실성(Pending): 사용자 기억상 과거 DB 구조에서 백링크(Backlink) 추적 시 정규식 편의를 위해 `()` 또는 일반 마크다운 링크를 쓰느라 `[[wikilink]]`를 의도적으로 제거했을 가능성이 있음.
  - 요구사항: 무작정 프롬프트를 고치기 전에, 기존 백엔드 DB의 파싱 로직(`()` 백링크 처리 등)과 `[[wikilink]]` 문법이 충돌하지 않는지 아키텍처 레벨에서 검증 후 도입 여부 결정.
- **[마이너 업데이트] Diff Viewer UI/UX 개선** → `minor_quick_wins.md`
  - 현황: `plugin/src/ui/diffViewer.ts` (530줄)에 기능 구현은 되어 있으나 현재 UI/UX가 불편함.
  - 요구사항: 사용자가 직관적으로 변경사항을 수락/거절할 수 있도록 UI/UX 전반 개선. 예: 버튼/헝크 레이아웃 정리, 다크/라이트 테마 대응, 키보드 단축키 힌트 표시, 헝크 간 이동 UX 등.

### 📦 stabilization.md 배치
- **[매이저 업데이트] 검색 엔진 심층 분석 및 보완** → `stabilization.md`
  - 현상: qmd가 어떻게 동작하는지 repository를 심층 분석해서 search engine에서 부족한 부분 보완.
- **[매이저 업데이트] PDF 및 정제된 지식(Atom, Concept) 내 수학 수식 누락 문제 해결** → `stabilization.md`
  - 현상: 현재 `pymupdf4llm`을 기본 파서로 사용 중이나, 표나 텍스트 흐름 보존과 달리 복잡한 공학/수학 논문의 블록 수식은 완벽한 `LaTeX` 코드로 역변환(OCR)되지 않고 깨지거나 누락되어 L1에 온전히 반영되지 않음. 또한, Markdown 원본에는 수식이 유지됨에도 불구하고, 이를 바탕으로 L2(Atom), L3(Concept)로 지식을 정제하는 과정에서 LLM이 수식을 보존하지 않고 증발시키는 문제가 있음.
  - 팩트체크 필요: 아키텍처 개편에 앞서, 실제로 `pymupdf4llm`이 수식 영역을 마크다운으로 변환할 때 어떤 형태의 텍스트(Garbage text)로 파편화하여 뱉어내는지, 혹은 완전히 생략해버리는지에 대해 L1 생성 결과물에 대한 구체적인 팩트체크 및 디버깅이 선행되어야 함.
  - 개선 방향 (하이브리드 파이프라인): 팩트체크 결과에 따라, 페이지 전체를 VLM에 넘기는 대신 `pymupdf4llm`으로 텍스트와 뼈대를 빠르게 잡고 수식(Formula)으로 판별된 영역만 이미지 캡처 후 백엔드 VLM(Claude, Gemini 등)에게 넘겨 `LaTeX` 코드로 번역하는 **하이브리드 추출 방식** 도입 검토. 아울러 LLM 지식 추출 프롬프트 자체도 수식을 보존하도록 강화 필수.
- **5. [매이저 업데이트] 지식 정제용 LLM과 쿼리 확장(HyDE)용 LLM 설정 분리 및 UI/CLI 노출** → `stabilization.md`
  - 현상: 사용자의 VRAM 환경과 용도(지식 정제용 무거운 모델 vs 쿼리 확장용 가볍고 빠른 로컬 모델)에 맞게 각각 독립적으로 모델을 선택할 수 있도록 설정 옵션을 명확히 제공해야 함.
  - 팩트체크 필요: 현재 백엔드 설정(`config.py`) 내부에 `query_expander` 관련 구조가 어느 정도 준비되어 있는지, 그리고 CLI(`wiki config provider`)와 플러그인 대시보드 UI에서 사용자가 이 두 모델을 직관적으로 따로 선택할 수 있도록 노출되어 있는지 팩트체크 및 검증 후 미비점 보완 필요.
- **6. [매이저 업데이트] GraphRAG급 엔티티 통합(Entity Resolution)(이게 적용되어도 되는건지 확인 필요), 노이즈 필터링 및 보관소 용량 관리(Vault Quota) 아키텍처 설계** → `stabilization.md`
  - 현상: 현재 자체 DB(`graph_entities`, `graph_relations`) 구조상 동의어나 유사 개념이 파편화되어 중복 저장되거나 노이즈 엣지가 무한 증식할 위험이 있음. `.curator` DB와 마크다운 파일들이 방치되면 컴퓨터 디스크 용량이 터질 수 있음.
  - 요구사항 1 (노이즈 필터링): 추출된 지식을 DB에 꽂아넣기 전/후로 임베딩 유사도 및 LLM을 활용해 동일한 엔티티를 병합하고 연결선 가중치를 정밀하게 최적화하는 파이프라인 아키텍처 설계 요망.
  - 요구사항 2 (용량 관리/Context Compat): 무한 증식을 막기 위해 보관소 최대 용량(Default: 200GB) 제한(Quota) 개념 도입.
  - 요구사항 3 (UI/UX 가시성): 사용자가 용량 압박을 직관적으로 인지할 수 있도록, **Claude Code 스타일의 원형 프로그레스 바(Circle Bar)** 형태의 UI를 도입. 
    - **옵시디언 에이전트**: 채팅창 상단에 상시 표시.
    - **CLI**: `wiki status` 출력 결과에 텍스트 대시보드 표시.
    - `wiki init` 시에도 명시적으로 용량 정책 안내 및 설정.
- **7. [매이저 업데이트] 전역적 사고(Global Sensemaking)를 위한 계층적 군집화 알고리즘 설계 플랜 작성** → `stabilization.md`
  - 현상: 수백 편의 논문 전체를 아우르는 거시적 통찰력(Global Summary)이나 커뮤니티 단위의 요약 기능이 부족함.
  - 요구사항: MS GraphRAG의 Leiden 알고리즘 등을 벤치마킹하여, 파편화된 L2(Atom) 지식들을 수학적으로 묶어 L3(Concept/Community) 단위로 자동 군집화하는 고도화된 클러스터링 로직 구현 플랜 작성 요망.

### 📦 pdf_annotation_system.md 배치
- **[매이저 업데이트] Native PDF Annotation System 도입 (Zotero 의존성 제거)** → `pdf_annotation_system.md`
  - 현상: 외부 Zotero 시스템에 의존하던 PDF 하이라이팅 및 어노테이션을 자체 시스템으로 교체해야 함.
  - 요구사항: 옵시디언 내장 PDF Viewer를 활용하여 하이라이트와 메모를 `state.sqlite`(`pdf_annotations` 테이블)에 직접 저장하고 오프라인 동기화(Sync Bridge 연동)하며, Zotero 수준의 매끄러운 하이라이팅 UX 및 팝업 메모 UI를 구현.


## 🧊 Blocked / Icebox (대기 중인 보류 항목)
- 외부 의존성(라이브러리 업데이트 등) 문제로 당장 해결할 수 없는 항목들을 이곳에 보관합니다.
- (참고: 에이전트의 최우선 해결 의무(Global Priority Rule)에서 이 섹션의 항목들은 예외로 취급됩니다.)
