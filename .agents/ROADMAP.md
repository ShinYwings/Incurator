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
- 현재 큐에 대기 중인 항목이 없습니다. (모두 마일스톤으로 편입됨)

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
