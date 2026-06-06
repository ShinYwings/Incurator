# [v0.3.3] Master Implementation Plan: Static Specs Refactoring & Cleanup

Date: 2026-06-06
Status: DESIGN ARTIFACT (이 문서 작성 중에는 코드를 수정하지 않음)
Scope: `user_report.md`의 8번 항목(스펙 정적화) 및 사용자 요청(Testbed 갱신, 추가 시스템 클린업)을 통합하여 v0.3.3 패치 릴리즈로 구현합니다.

> [!NOTE] User Review Completed
> 1. **`.qmd` 폴더 삭제 완료**: 사용자 승인 완료 및 시스템 잔재 청소 완료.
> 2. **기존 `testbed` 재생성 승인 완료**: `testbed/` 폴더 삭제 완료, 추후 P4 단계에서 재생성 예정.

## 0. Design constraints discovered from the codebase
- 백엔드 코드(`backend/src/curator/*.py`) 및 플러그인 타입 정의(`plugin/src/types.ts`) 곳곳의 주석과 문자열에 `SCHEMA_v0.3.1`, `SYSTEM_BEHAVIOR_v0.3.1` 등이 하드코딩되어 있습니다. 이를 모두 정규식을 통해 `_vX.Y.Z` 꼬리표를 떼어내야 합니다.

## 0.5 Docs Specs & Invariants
- `AGENTS.md`에 명시된 `STATIC SPECS MANDATE`에 따라, 스펙 문서들은 반드시 버전 꼬리표 없이 `SCHEMA.md`, `SYSTEM_BEHAVIOR.md` 같은 정적 파일명을 가져야 합니다.
- 스펙의 실제 버전(예: `v0.3.3`)은 마크다운 문서 최상단의 제목(Title) 또는 Frontmatter에만 기록되어야 합니다.

## Multi-Agent Role Reviews (다중 에이전트 관점 검증)
- **schema_guardian**: 스펙 문서들의 파일명이 정적(`SCHEMA.md` 등)으로 올바르게 변경되는지 검증.
- **cli_regression_runner**: `testbed_template/create_testbed.py` 내부의 낡은 버전 참조가 완벽히 제거되어, `wiki testbed init`이 정상 구동되는지 검토.
- **legacy_sweeper**: 루트의 `__pycache__` 삭제 완료. `.qmd` 잔재 청소 여부 검토. 하드코딩된 모든 과거 버전 의존성(`_v0.3.1`, `_v0.3.2` 등) 완전 소탕.

---

## Phases (each: implement -> unit tests -> `uv run pytest` + `ruff` green)

### P1 — [System Cleanup] (✅ 완료)
- 루트 디렉토리의 `__pycache__` 삭제 (완료)
- 구형 검색 엔진의 잔재인 `.qmd` 디렉토리 완전 삭제 (완료)
- 과거 버전명으로 오염된 기존 `testbed/` 디렉토리 완전 삭제 (완료)
- `docs/specs/*/archives/` 및 `.agents/plans/archives/` 완전 삭제 (완료)
- 플랜 파일명 정적화(`01_static_specs_refactoring.md` 등) 및 내부 링크 업데이트 (완료)

### P2 — [Global Dependency Hunt]
- 백엔드(`backend/src/`) 내 모든 Python 코드의 주석 및 문자열에서 `SCHEMA_v\d\.\d\.\d`, `SYSTEM_BEHAVIOR_v\d\.\d\.\d` 정규식 색인 후 정적 경로로 교체.
- 플러그인(`plugin/src/`) 내 TypeScript 코드의 주석에서 `PLUGIN_SCHEMA_v\d\.\d\.\d` 정적 경로로 교체.
- `scripts/dev/testbed_template/create_testbed.py` 및 관련 마스터 플랜 내의 하드코딩된 버전명 일괄 제거.

### P3 — [Docs & Test Files Renaming (Use `git mv`!)]
- **CRITICAL**: 모든 파일명 변경과 이동은 반드시 `git mv` 명령어를 사용해 히스토리 단절을 막으세요.
- `docs/specs/curator_schema/SCHEMA_v*.md` -> `SCHEMA.md`
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v*.md` -> `SYSTEM_BEHAVIOR.md`
- `docs/specs/plugin_schema/PLUGIN_SCHEMA_v*.md` -> `PLUGIN_SCHEMA.md`
- 각 문서 내부의 최상단 헤더 버전을 `v0.3.3`으로 갱신.
- **가이드/README 영구 정적화 (Version-Agnostic)**: `README.md`, `README_KR.md`, `CONTRIBUTION_GUIDE.md` 등 사용자 대면 문서에 하드코딩된 과거 버전(`v0.2.0`) 텍스트를 찾아 아예 버전에 종속되지 않는 범용적인 문구로 일괄 정제합니다.
- `backend/tests/test_v031_*.py` 및 `test_v032_*.py` 파일들의 이름에서 버전 접두어(`_v031`, `_v032`)를 일괄 제거 (예: `test_synthesis.py`).
- **마크다운 크로스링크 보완**: 문서 내부에 `[링크](SCHEMA_v0.3.2.md)` 형식으로 걸려있는 마크다운 자체의 내부 크로스링크도 404가 나지 않게 `SCHEMA.md`로 일괄 교체합니다.

### P4 — [Testing Directory Unification & Testbed TDD Overhaul]
단순히 빈 폴더만 만드는 것을 넘어, 에이전트(AI)가 사람의 개입 없이 100% 자동화된 TDD 사이클을 돌릴 수 있도록 테스트베드의 사용성과 구조를 대폭 개선합니다.
0. **디렉토리 대통합 (All-in-One)**: 
   - **Monorepo 철학 유지**: 유닛 테스트는 각자 생태계에 맞게 `backend/tests/`와 `plugin/src/**/*.test.ts`에 그대로 유지합니다.
   - **E2E Testbed 전역 관리**: `scripts/dev/testbed_template` 등 시나리오 폴더 ➔ `tests/scenarios/` 하위로 이동 (**반드시 `git mv` 사용**)
   - **문서 대통합 (README 이동)**: 레포지토리 루트의 `README.md` 및 `README_KR.md`를 `docs/` 폴더 안으로 이동(`git mv`). (GitHub는 루트에 README가 없으면 자동으로 `docs/README.md`를 메인으로 띄워줍니다.)
   - **경로 계산 튜닝 (CRITICAL)**: 이동된 스크립트 내부의 `Path(__file__).parents[X]` 등 상대 경로 뎁스를 새로운 `tests/` 위치에 맞게 다시 튜닝하여 `FileNotFoundError`를 방지하세요.
   - **룰 가이드라인 동기화**: `AGENTS.md`와 `CLAUDE.md` 내부의 로컬 CI 테스트 가이드 명령어도 `uv run pytest tests/backend/`로 업데이트하세요.
1. **스크립트 중앙화**: 기존 `create_testbed.py`를 `tests/create_testbed.py`로 이동. `--scenario <이름>` 인자를 받도록 구조 개선.
2. **에이전트 룰 업데이트 (Schema Mismatch 대응)**:
   - 복잡하고 깨지기 쉬운 스크립트단 자동 감지 대신, 에이전트의 뇌(`AGENTS.md`, `CLAUDE.md`)에 직접 룰을 주입합니다.
   - *"DB 스키마를 수정했을 경우, 에이전트는 반드시 `wiki testbed init <scenario> --force`를 호출하여 기존 테스트베드를 폭파하고 리부트해야 한다"*는 강력한 규칙을 명시합니다.
3. **Auto-Seeding (파이프라인 자동 구동)**: 테스트베드 디렉토리 생성 직후 백그라운드에서 전체 파이프라인(`wiki update` 등)을 한 번 구동. **(주의: 무한 대기 병목을 막기 위해, 생성 스크립트 실행 시 로컬 LLM을 무시하고 Mock 또는 Flash 모델 환경변수를 사용하도록 강제하세요.)**
4. **검증**: `uv run pytest tests/backend/` 및 `ruff check`를 실행하여 코드베이스 전역의 정합성 최종 확인.

---

> **LIFECYCLE & VERSIONING RULE REMINDER**:
> 1. **버전 및 체인지로그 갱신**: 모든 구현과 로컬 CI(pytest, ruff 등)가 통과되면 `pyproject.toml`, `package.json` 버전을 올리고 `CHANGELOG.md`를 갱신합니다.
> 2. **리포트 및 플랜 삭제**: `user_report.md`에서 해결된 8번 항목을 지우고, 이 플랜 파일 역시 워크스페이스에서 **전면 삭제**합니다.
> 3. **푸쉬 및 PR**: 피처 브랜치(`feature/static-specs`)에서 상세한 PR Description과 함께 PR을 올립니다.
