# 가이드: 개발용 Testbed 시나리오 생성

이 가이드는 격리된 환경에서 Incurator의 동작을 검증하기 위한 개발 검증 시나리오(testbeds) 생성 및 관리 방법을 설명합니다.

[English Guide](DEV_SCRIPTS_GUIDE.md)

## 1. 시나리오 구조
모든 시나리오는 `tests/scenarios/<scenario_name>/`에 위치합니다. `testbed_template`을 시작점으로 사용하세요.

테스트베드 생성은 `wiki testbed init <scenario_name>` 명령
(`backend/src/curator/testbed_manager.py`에 구현)이 담당합니다. 별도의
부트스트랩 스크립트는 없으며, CLI가 유일한 진입점입니다.

```text
tests/scenarios/<scenario_name>/
├── MASTER_PLAN.md          # [필수] 목표 및 설정 지침
├── stage/                  # [필수] 원시 소스 파일들 (L0)
│   ├── 01_Workspaces/      # 워크스페이스 정의 (curate.yml)
│   ├── 03_Notes/           # 샘플 마크다운 노트
│   └── 04_Resources/       # 샘플 레퍼런스 PDF/HTML
├── mock_zotero_env/        # [선택] 레퍼런스 모드 테스트용 모의 Zotero 데이터 디렉토리
├── dialogues/              # [선택] 자동화 스크립트 (.sh 또는 .py)
└── fixture_workspace_rules/ # [선택] 이 시나리오를 위한 에이전트 규칙
```

## 2. 단계별 생성 방법

### 1단계: 폴더 초기화
`tests/scenarios/testbed_template`을 `tests/scenarios/my_scenario`로 복사합니다.

### 2단계: 마스터 플랜 정의 (`MASTER_PLAN.md`)
이 문서는 시나리오의 정체성입니다. 다음 사항을 반드시 포함해야 합니다:
- **시나리오 이름**: 명확한 제목.
- **문제 정의**: 어떤 버그나 기능을 테스트하고 있나요?
- **검증 목표**: 성공 기준이 무엇인가요? (예: "Atom ATM-123이 특정 논리적 추론을 포함해야 함").

### 3단계: 스테이지 데이터 채우기 (`stage/`)
동작을 재현하는 데 필요한 최소한의 파일들을 `stage/`에 배치합니다.
- 반드시 **익명화된** 데이터를 사용하세요. 개인적인 노트를 커밋하지 마세요.
- 워크스페이스 쿼리를 테스트한다면 `01_Workspaces/`에 최소 하나의 워크스페이스가 존재해야 합니다.

### 4단계: 자동화 다이얼로그 작성 (`dialogues/`)
다이얼로그는 검증을 자동화합니다.
- `dialogues/verify_fix.sh`를 생성합니다.
- 모든 명령어에 `VAULT_ROOT=testbed`를 사용합니다.
- **예시**:
  ```bash
  # 1. 초기화
  wiki testbed init my_scenario --force
  
  # 2. 파이프라인 실행
  VAULT_ROOT=testbed wiki add "03_Notes/bug_report.md"
  VAULT_ROOT=testbed wiki sync
  
  # 3. 단언 (Assert)
  if grep -q "Expected Insight" testbed/.curator/Collections/02_Atoms/*.md; then
    echo "✓ Success"
  else
    echo "✗ Failed"
    exit 1
  fi
  ```

## 3. 실행 워크플로우
1. **발견**: `wiki testbed list`를 실행하여 새 시나리오를 확인합니다.
2. **초기화**: `wiki testbed init <name> --force`를 실행합니다.
3. **실행**: 다이얼로그 스크립트를 수동으로 실행합니다: `bash tests/scenarios/<name>/dialogues/verify_fix.sh`.

## 4. 벤치마크 스크립트

저장소에서 추적되는 benchmark harness는 `scripts/benchmarks/`에 둡니다. 이는
testbed scenario가 아니며 `wiki testbed list`에 표시되지 않습니다.

- `scripts/benchmarks/search_parity_bench.py`는
  `docs/benchmarks/SEARCH_PARITY_v0.3.2.md`에 문서화된 v0.3.2 DB-native search
  vs qmd parity 측정을 재현합니다.
- 서로 다른 llama-cpp model stack을 로드하는 benchmark row는 분리 실행하세요.
  일부 host에서는 all-in-one wrapper가 덜 안정적일 수 있습니다.

## 5. 모범 사례
- **상태 최소화**: 테스트에 엄격하게 필요한 파일만 포함하세요.
- **문서 우선**: 코드를 읽지 않고도 다른 개발자가 테스트를 이해할 수 있을 만큼 `MASTER_PLAN.md`가 명확해야 합니다.
- **정리**: 테스트가 `testbed/` 외부에 임시 파일을 생성하는 경우, 다이얼로그 스크립트에서 이를 정리하세요.

## 6. 플러그인 개발 및 모노레포 빌드

Incurator는 Python 백엔드(`backend/`)와 Obsidian 플러그인(`plugin/`)을 모두 포함하는 모노레포 구조를 사용합니다.

### 설치 스크립트
저장소 루트에서 `./setup.sh`를 실행하여 Python 백엔드 종속성(`uv` 사용), Node.js/Ollama, 로컬 DB-native 검색 모델(`wiki models ensure`)을 자동으로 설치합니다. 모델 준비를 건너뛰려면 `INCURATOR_SKIP_MODELS=1`을 설정하세요. Obsidian 플러그인은 이제 `wiki init` 실행 시 상호작용 방식으로 설치됩니다.

### OBSIDIAN_PLUGIN_DIR 재정의
파일을 수동으로 복사하거나 불안정한 심볼릭 링크를 생성하지 않고 로컬에서 Obsidian 플러그인을 개발하려면 `OBSIDIAN_PLUGIN_DIR` 환경 변수를 사용할 수 있습니다.
`OBSIDIAN_PLUGIN_DIR`이 설정되면 (예: `export OBSIDIAN_PLUGIN_DIR=/path/to/second_brain/.obsidian/plugins/incurator-plugin`), 플러그인의 `esbuild.config.mjs`가 동적으로 빌드 출력 디렉토리(outdir)를 덮어씁니다.
이를 통해 `plugin/` 디렉토리에서 `npm run dev`를 실행하고 변경 사항을 즉시 활성화된 Obsidian Vault에 반영할 수 있습니다.

`plugin/deploy.sh`도 동일한 규칙을 따릅니다. 기본값은 로컬 Linux 개발 Vault 경로지만, `OBSIDIAN_PLUGIN_DIR`이 이미 설정되어 있으면 해당 경로로 배포합니다. 이로 인해 스크립트를 macOS와 Linux 모두에서 사용할 수 있습니다:

```bash
cd plugin
OBSIDIAN_PLUGIN_DIR=/Users/<you>/path/to/second_brain/.obsidian/plugins/incurator-obsidian-agent ./deploy.sh
```

### 근거 기반 경로 마이그레이션

백엔드가 상위 디렉토리를 탐색하여 Vault 루트, Testbed 루트, 번들 에셋, 플러그인 출력 경로를 발견하기 때문에 경로 마이그레이션은 위험도가 높습니다. `parents[N]`, 상대 경로 또는 빌드 출력 위치를 변경하기 전에:

1. 현재 경로, 예상되는 새 경로, 그리고 가정을 증명하는 명령어를 기록하세요.
2. 변경 사항이 백엔드/플러그인 경계에 영향을 미치는 경우 마스터 빌드 플랜을 업데이트하세요.
3. 변경된 경로를 테스트하는 가장 작은 명령어를 실행하세요.
4. 가능한 경우 관련된 전체 검사를 실행하세요.

예를 들어, 백엔드를 루트 `src/`에서 `backend/src/`로 이동하는 경우 다음 검사를 동반해야 합니다:

- `wiki testbed init testbed_template --force`
- `VAULT_ROOT=<testbed> wiki status`
- parser fixture 경로
- MCP launch 경로
- plugin 빌드 출력 경로

### 외부 리소스 Testbeds

레퍼런스 모드(Reference Mode) 및 복사 임포트에는 명시적인 fixture가 필요합니다:

- `stage/04_Resources/` 하위에 복사된 PDF fixture 하나
- 생성된 testbed 루트 외부에 있는 외부 PDF fixture 하나
- 동일 이름/다른 해시의 충돌(collision) 케이스 하나
- 파일 이동 또는 rebind 제안 케이스 하나
- `curator_search_source` 또는 `curator_get_pdf_page`를 검증하는 페이지 출처(provenance) 단언문 하나

개인 Zotero 라이브러리나 개인 PDF를 커밋하지 마세요. 공개 fixture용으로는 최소한의 퍼블릭 도메인 PDF나 합성 텍스트 PDF를 사용하세요.
