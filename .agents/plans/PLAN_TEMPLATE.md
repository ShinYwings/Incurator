# Incurator Planning Blueprint (Master Template)

이 템플릿은 단순한 메모장이 아닙니다. 과거 `v0.3.2_search` 시절의 치밀한 다중 문서 분할(Multi-Document Committee) 프로세스와 **스펙 우선(Spec-First), TDD(Test-Driven Development) 철학**을 강제하는 절대적인 기획 규격입니다.
서브 에이전트들은 아래 제공된 마크다운 스켈레톤을 복사하여 모든 기획 문서를 작성해야 합니다.

---

## 1. 아키텍처 기획 철학 및 프로세스 (The Master Intent)
1. **Spec-First & TDD**: 런타임 코드를 수정하기 전에 `docs/specs/`의 스펙(SCHEMA, SYSTEM_BEHAVIOR, PLUGIN)을 먼저 정의하고, 실패하는 테스트 코드를 먼저 작성해야 합니다.
2. **도메인 분할 (Domain Artifacts)**: 거대한 주제는 A, B, C 도메인 문건(`A_*.md`, `B_*.md`)으로 나누어 심층 리서치와 대안 검토를 진행합니다.
3. **엄격한 단계별 검증 (Strict Phases)**: 마스터 플랜에 적힌 단계(P1, P2...)는 반드시 `[구현 -> 단위 테스트 -> pytest 및 ruff 통과]`를 확인한 뒤에만 다음으로 넘어갈 수 있습니다.

---

## 2. 도메인 분석 문서 템플릿 (Domain Artifact Skeleton)
`A_*.md`, `B_*.md` 파일을 생성할 때 이 뼈대를 그대로 복사하세요.

```markdown
# [A/B/C] — [Domain Name] Design (e.g. Retrieval Engine Design)

Date: YYYY-MM-DD
Status: DESIGN ARTIFACT (이 문서 작성 중에는 코드를 수정하지 않음)
Scope: 이 문서가 다루는 구체적인 시스템 범위 설명.

## 0. Design constraints discovered from the codebase (코드베이스에서 발견된 제약 사항)
- (예: 기존 `SearchHit` 반환 규격을 깨면 클라이언트가 고장나므로 호환성을 유지해야 함.)

## 0.5 Docs Specs & Invariants (공식 스펙 기반 주의/경고 사항)
- `docs/specs/`와 `docs/guides/`를 정독한 뒤, 이번 설계 시 절대 위반해서는 안 되는 기존 스키마 제약, 불변성(Invariants), 혹은 주의해야 할 사이드 이펙트를 기록하세요.
- (예: `SCHEMA_vX.Y.Z.md`에 정의된 `03_Notes/`는 인간 검증 영역이므로 머신이 함부로 수정해서는 안 됨)

## 1. [Component 1] Layer (예: FTS5 Lexical Layer)
### 1.1 Alternatives & Trade-offs (대안 및 장단점 분석)
- Option A: (설명 및 Pros/Cons)
- Option B: (설명 및 Pros/Cons)

### 1.2 Decision: [결론 요약]
**결정 사항**: Option B를 선택한다. 이유는...

### 1.3 Implementation Logic (구현 로직 / SQL / Pseudocode)
(구현에 사용할 핵심 SQL문, 알고리즘, 파이썬 수도코드 작성)
```

---

## 3. 통합 마스터 플랜 템플릿 (Master Plan Skeleton)
도메인 분석이 끝나면, 아래 뼈대를 복사하여 `[XX]_[feature_name].md` (예: `01_static_specs_refactoring.md`)를 작성하세요.

```markdown
# [Version] Master Implementation Plan (통합 명세서)

Date: YYYY-MM-DD
Status: APPROVED — implementing in phases. Specs are authored, tests are spec-first.

## Strict quality condition (user-mandated, non-negotiable)
- (절대 타협 불가 조건 명시. 예: RAG 검색 성능은 반드시 기존 엔진과 동등/이상이어야 함)

## Locked design decisions (위원회 합의 사항)
- (도메인 문서에서 확정된 아키텍처, 알고리즘, 스키마 요약)

## Contracts preserved (호환성 유지 규약)
- (수정하더라도 변경되어서는 안 되는 기존 API 규격이나 반환값 형태 명시)

## Multi-Agent Role Reviews (다중 에이전트 관점 검증)
- **schema_guardian**: (스키마 계층, 프리픽스, 프론트매터 위반 여부 검토)
- **source_pair_analyst**: (03_Notes와 04_Resources 통합/병합 로직 검토)
- **topic_boundary_checker**: (02_Wiki 토픽 경계 침범 여부 검토)
- **cli_regression_runner**: (testbed에서 CLI 명령어 회귀/사이드이펙트 발생 여부 검토)
- **local_slm_simulator**: (클라우드 LLM 차단 시 로컬 SLM 대체 검증 방안)
- **legacy_sweeper**: (제거 대상이 된 레거시 코드나 문서의 잔재 여부)

## Phases (each: implement -> unit tests -> `uv run pytest` + `ruff` green)
- **P1 — [DB Schema]**: 스키마 업데이트. (Verify: DB 마이그레이션 정상 작동)
- **P2 — [Core Logic]**: 백엔드 로직 작성. (Verify: `pytest tests/test_*.py` 통과)
- **P3 — [Integration]**: 플러그인 UI 연동.
- **P4 — [Testbed Smoke]**: `wiki add/sync/query` E2E 테스트 및 Parity 검증.
```

---

## 4. 증거 장부 템플릿 (Evidence Ledger Skeleton)
코드 수정에 들어가기 직전, 아래 뼈대를 복사하여 `[XX]_roadmap_evidence.md` 장부를 만드세요.

```markdown
# [Version] System Build Evidence Ledger

## 1. Rollback Requirements Before Destructive Operations
- Git 롤백 앵커 생성 및 DB 백업 여부 확인.

## 2. Current Schema & Reality To Recheck
- 현재 DB 스키마 구조 및 변경 대상 핵심 파일 경로.

## 3. Known Validation Results (사전/사후 검증 결과)
- Testbed 회귀 테스트 통과 여부 및 오류 로그 기록.
```

---

> **LIFECYCLE & VERSIONING RULE REMINDER**:
> 1. **버전 및 체인지로그 갱신**: 모든 구현과 로컬 CI(pytest, ruff 등)가 통과되면 `pyproject.toml`, `package.json` 버전을 올리고 `CHANGELOG.md`를 갱신합니다.
> 2. **리포트 및 플랜 삭제**: `user_report.md`에서 해결된 항목을 지우고, 사용된 플랜 파일들(`A_*.md`, `MASTER_PLAN.md` 등) 역시 워크스페이스에서 **전면 삭제**합니다. (과거 맥락은 Git 히스토리에만 보존)
> 3. **푸쉬 및 PR**: 모든 과정은 `AGENTS.md`에 명시된 12단계 `Antigravity Strict Workflow`에 따라, 피처 브랜치 작업 후 상세한 PR Description과 함께 PR을 올리는 것으로 종료됩니다.
