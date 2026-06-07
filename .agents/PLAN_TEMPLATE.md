# Incurator Planning Blueprint (The Arena Model)

이 템플릿은 단순한 메모장이 아닙니다. 다수의 서브 에이전트들이 **치열한 비동기 토론(Asynchronous Debate)**을 거쳐 결론을 도출하는 설계 규격입니다.
단일 폭포수(Waterfall) 형식의 밋밋한 기획을 금지하며, 하위 폴더에서 여러 에이전트가 제안과 비판(Critique) 문서를 쏟아낸 뒤 최종 합의안만 루트 폴더에 마스터 플랜으로 남기는 구조를 따릅니다.

---

[!CRITICAL]
## 1. 아키텍처 기획 철학 및 프로세스 (The Arena Workflow)
1. **The Briefing (발제)**: 메인 에이전트가 새로운 토론 폴더(`.agents/plans/[feature_name]_arena/`)를 생성하고 해결해야 할 문제 정의서(`00_problem.md`)를 작성합니다.
2. **Fierce Debate (치열한 토론)**: 각 도메인(보안, DB, 프론트엔드, 성능 등)을 맡은 서브 에이전트 페르소나들이 자신의 관점에서 제안서(`01_proposal_*.md`)를 작성합니다.
3. **Cross-Critique (교차 비판)**: 에이전트들은 상대방의 제안서를 읽고 신랄한 비판 문서(`02_critique_*.md`)와 그에 대한 방어/수정 논리(`03_defense_*.md`)를 작성하며 기술적 합의점(Consensus)을 찾습니다.
4. **Master Plan Synthesis (통합)**: 토론이 완료되면 메인 에이전트가 토론 폴더를 벗어나 `.agents/plans/` 루트 디렉터리에 단 하나의 완벽한 마스터 플랜(`[XX]_[feature_name].md`)을 작성합니다. 이후 토론 폴더는 보존하거나 아카이브합니다.

---

[!CRITICAL]
## 2. 토론장(Arena) 문서 스켈레톤
하위 폴더(`_arena/`)에서 서브 에이전트들이 문서를 생성할 때 사용하는 뼈대입니다.

### 2.1 제안서 (Proposal Skeleton)
```markdown
# [Domain] Proposal: [Idea Title]
Date: YYYY-MM-DD | Agent Persona: [e.g. DB Architect / Frontend Expert]

## 1. Core Logic & Implementation
(구현에 사용할 핵심 설계, SQL문, 파이썬 수도코드, 아키텍처 다이어그램 등)

## 2. Pros & Cons
(자신이 제안한 구조의 장단점 및 현재 코드베이스에서의 한계 명시)
```

### 2.2 비판/방어 문서 (Critique Skeleton)
```markdown
# Critique on [Target Proposal]
Date: YYYY-MM-DD | Agent Persona: [e.g. Security Auditor]

## 1. Vulnerabilities & Flaws (치명적 결함 지적)
(기존 제안의 사이드 이펙트, 스키마 위반 사항, 엣지 케이스 누락 등을 매섭게 비판)

## 2. Suggested Alternatives (대안 제안)
(단순 비판을 넘어 어떻게 수정해야 하는지 구체적인 대안 제시)
```

---

## 3. 통합 마스터 플랜 스켈레톤 (Master Plan Template)
토론이 끝나면, 아래 뼈대를 복사하여 `.agents/plans/[XX]_[feature_name].md`를 작성하세요.

```markdown
# [Version] Master Implementation Plan (통합 명세서)

Date: YYYY-MM-DD
Status: APPROVED — Arena debate concluded. Specs are authored, tests are spec-first.

## Strict quality condition (절대 타협 불가 조건)
- (예: RAG 검색 성능은 반드시 기존 엔진과 동등/이상이어야 함)

## Locked design decisions (Arena 합의 사항)
- (토론장에서 확정된 아키텍처, 알고리즘, 스키마 및 호환성 유지 규약 요약)

## Evidence Ledger (증거 장부)
- 롤백 앵커, 현재 스키마 상황 등 코드 변경 전 확인해야 할 제반 사항.

## Execution Phases (구현 단계: 각 단계마다 TDD 및 CI 준수)
- **P1 — [DB Schema]**: 스키마 업데이트. (Verify: 마이그레이션 및 DB 무결성 정상 작동)
- **P2 — [Core Logic]**: 백엔드 로직 구현. (Verify: `pytest tests/test_*.py` 및 `ruff` 통과)
- **P3 — [Integration]**: 플러그인/UI 등 연동.
- **P4 — [Testbed Smoke]**: `wiki add/sync/query` 등 E2E Parity 검증.
```

---

> **LIFECYCLE & VERSIONING RULE REMINDER**:
> 1. **버전 및 체인지로그 갱신**: 모든 구현과 로컬 CI가 통과되면 버전 명세(`pyproject.toml` 등)를 올리고 `CHANGELOG.md`를 갱신합니다.
> 2. **리포트 갱신**: `USER_REPORT.md`에서 해결된 항목을 지우거나 옮깁니다.
> 3. **푸쉬 및 PR**: 모든 과정은 `AGENTS.md`에 명시된 `Universal Strict Workflow`에 따라 깃허브 PR을 올리는 것으로 종료됩니다.
