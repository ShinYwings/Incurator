# 06. 인프라 통합 및 CLI 마이그레이션 전략

---

## 1. 모델 명세 통합 (`shared/models.json`)

현재 모델 이름이 플러그인(`plugin/src/types.ts`)과 백엔드(`.curator/config.yml`, `llm.py`)에
분리 관리되어 런타임 불일치 오류 위험 존재.

### 1.1. 현황 파악 (AS-IS 불일치)

현재 모델 정보가 **4곳에 중복** 존재:

| 위치 | 형태 | 내용 |
|------|------|------|
| `llm.py` `DEFAULT_*` 상수 | Python 하드코딩 | `DEFAULT_GEMINI_FLASH_MODEL = "gemini-3.1-flash-lite-preview"` 등 |
| `config.py` `DEFAULT_CONFIG` | Python dict | `"gemini_flash_model": "gemini-3.1-flash-lite-preview"` 등 |
| `cli.py` `_MODEL_PRESETS` dict | Python 하드코딩 | Gemini/Claude 모델 태그별 선택 UI |
| `plugin/src/types.ts` `MODEL_OPTIONS` | TypeScript 하드코딩 | `antigravity`, `claude`, `openai` 별 모델 목록 |

**주목할 불일치**: 플러그인은 이미 provider를 `"antigravity"` 로 rename 했으나
백엔드는 `"gemini-cli"`, `"gemini_flash_model"` 등 구버전 키 그대로 사용 중.

### 1.2. 공통 `models.json` 신설

**파일 위치**: `backend/src/curator/data/models.json`
(pip install 시 백엔드 패키지에 번들됨. 플러그인이 MCP 경유로 접근)

```json
{
  "schema_version": 1,
  "providers": {
    "antigravity": {
      "cli_cmd": "agy",
      "install_cmd": "curl -fsSL https://antigravity.google/cli/install.sh | bash",
      "install_cmd_windows_powershell": "irm https://antigravity.google/cli/install.ps1 | iex",
      "models": [
        {
          "id": "gemini-3.1-flash-lite-preview",
          "label": "Gemini 3.1 Flash Lite (Preview)",
          "tier": "flash",
          "context_window": 1000000,
          "supports_vision": true
        },
        {
          "id": "gemini-3.1-pro-preview",
          "label": "Gemini 3.1 Pro (Preview)",
          "tier": "think",
          "context_window": 1000000,
          "supports_vision": true
        },
        {
          "id": "gemini-2.5-flash",
          "label": "Gemini 2.5 Flash",
          "tier": "flash",
          "context_window": 1000000,
          "supports_vision": true
        },
        {
          "id": "gemini-2.5-pro",
          "label": "Gemini 2.5 Pro",
          "tier": "think",
          "context_window": 1000000,
          "supports_vision": true
        }
      ]
    },
    "claude": {
      "cli_cmd": "claude",
      "install_cmd": "npm install -g @anthropic-ai/claude-code",
      "models": [
        {
          "id": "claude-sonnet-4-6",
          "label": "Claude Sonnet 4.6",
          "tier": "flash",
          "context_window": 200000,
          "supports_vision": true
        },
        {
          "id": "claude-opus-4-7",
          "label": "Claude Opus 4.7",
          "tier": "think",
          "context_window": 200000,
          "supports_vision": true
        }
      ]
    }
  }
}
```

**확정**: 공식 Antigravity CLI 문서 기준 설치 명령은
`curl -fsSL https://antigravity.google/cli/install.sh | bash` 이다. 백엔드는 이 값을
`models.json`에 저장하고, CLI UI/MCP는 같은 카탈로그를 읽는다.

### 1.3. 백엔드 로딩 전략

```python
# backend/src/curator/llm.py 또는 config.py

import importlib.resources

def load_models_json() -> dict:
    """pip 번들 models.json 로드. 실패 시 DEFAULT_* 상수로 폴백."""
    try:
        # Python 3.9+ importlib.resources
        ref = importlib.resources.files("curator") / "data" / "models.json"
        with ref.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}  # 폴백: DEFAULT_* 상수 사용

def get_default_model(provider: str, tier: str = "flash") -> str:
    """models.json → .curator/config.yml → DEFAULT_* 상수 우선순위로 기본 모델 반환."""
    data = load_models_json()
    provider_data = data.get("providers", {}).get(provider, {})
    for m in provider_data.get("models", []):
        if m.get("tier") == tier:
            return m["id"]
    # 최후 폴백: 하드코딩 상수 (삭제하지 말 것 — 번들 누락 방어)
    return _HARDCODED_DEFAULTS.get(f"{provider}.{tier}", "")
```

**`DEFAULT_*` 상수 처리 방침**: `llm.py`의 `DEFAULT_GEMINI_FLASH_MODEL` 등 상수는
**삭제하지 않고 유지**. `models.json` 번들이 누락될 경우(패키징 오류, 개발 환경 등)의
최후 방어선 역할. `_HARDCODED_DEFAULTS` dict로 통합하여 가독성만 개선.

### 1.4. 플러그인 로딩 전략

플러그인은 직접 `models.json`을 읽을 수 없으므로 **MCP 경유**:

```python
# mcp_server.py 신규 도구
def get_available_models() -> dict:
    """models.json에서 provider별 모델 목록 반환. 플러그인 UI 동적 로드용."""
    data = load_models_json()
    return {
        provider: [{"id": m["id"], "label": m["label"], "tier": m["tier"]}
                   for m in info.get("models", [])]
        for provider, info in data.get("providers", {}).items()
    }
```

- 플러그인 `plugin/src/types.ts`의 `MODEL_OPTIONS` 하드코딩은 **점진적 마이그레이션**:
  v0.2.1: MCP에서 받아서 동적 렌더링, 하드코딩은 오프라인 폴백으로 유지
  v0.2.2: 하드코딩 완전 제거

### 1.5. 설정 우선순위 (확정)

```
1순위: Obsidian data.json (사용자가 UI에서 선택한 값)
2순위: .curator/config.yml (vault별 설정)
3순위: ~/.config/curator/config.yml (글로벌 설정)
4순위: models.json (패키지 번들 기본값)
5순위: llm.py 하드코딩 상수 (최후 방어선)
```

### 1.6. 기기 간 설정 동기화

사용자가 플러그인 UI에서 확정한 모델 → `.obsidian/plugins/incurator/data.json` 저장.
백엔드 실행 시 이 파일을 최상위 오버라이드로 강제 상속.

---

## 2. Antigravity CLI (`agy`) 전면 마이그레이션

### 2.1. 변경 대상 요약표

| 구버전 | 신버전 | 비고 |
|--------|--------|------|
| `npm install -g @google/gemini-cli` | `curl -fsSL https://antigravity.google/cli/install.sh \| bash` | 공식 Antigravity CLI 설치 명령 |
| `gemini` 명령어 | `agy` 명령어 | subprocess 호출 |
| `which gemini` 설치 검증 | `which agy` | `_cli_installed()` |
| `GEMINI_CLI_TRUST_WORKSPACE` env | agy 동등 환경변수 확인 필요 | |
| `"gemini-cli"` provider 키 | `"antigravity-cli"` | config/cli 전체 |
| `"gemini_flash_model"` config 키 | `"antigravity_flash_model"` | 하위 호환 필요 |
| `"gemini_think_model"` config 키 | `"antigravity_think_model"` | 하위 호환 필요 |
| `GeminiCliError` 예외 클래스 | `AntigravityCliError` | llm.py |
| `GeminiCliClient` 클래스 | `AntigravityCliClient` | llm.py |
| `_get_gemini_fallback_chain()` | `_get_antigravity_fallback_chain()` | llm.py |
| `_make_gemini_cli()` factory | `_make_antigravity_cli()` | llm.py |
| `DEFAULT_GEMINI_FLASH_MODEL` | `DEFAULT_ANTIGRAVITY_FLASH_MODEL` | llm.py |
| `DEFAULT_GEMINI_THINK_MODEL` | `DEFAULT_ANTIGRAVITY_THINK_MODEL` | llm.py |

### 2.2. 하위 호환성 처리 (config 키 마이그레이션)

기존 사용자의 `.curator/config.yml`에 `gemini_flash_model`이 있을 경우 마이그레이션:

```python
# config.py의 load_config() 함수에 추가
def _migrate_legacy_llm_keys(llm_cfg: dict) -> dict:
    """구버전 gemini_* 키를 antigravity_* 로 마이그레이션."""
    mapping = {
        "gemini_flash_model": "antigravity_flash_model",
        "gemini_think_model": "antigravity_think_model",
    }
    for old_key, new_key in mapping.items():
        if old_key in llm_cfg and new_key not in llm_cfg:
            llm_cfg[new_key] = llm_cfg.pop(old_key)
    return llm_cfg
```

`"gemini-cli"` provider 키도 동일:

```python
if llm_cfg.get("primary") == "gemini-cli":
    llm_cfg["primary"] = "antigravity-cli"
if llm_cfg.get("fallback") == "gemini-cli":
    llm_cfg["fallback"] = "antigravity-cli"
```

### 2.3. 영향 파일 (전수 목록)

**가장 중요 — 이전 플랜에서 누락됨:**

- `backend/src/curator/llm.py` — **핵심 변경 대상**:
  - `GeminiCliError` → `AntigravityCliError`
  - `GeminiCliClient` class 전체 rename + `CLI = "agy"` + `INSTALL_CMD` 업데이트
  - `_get_gemini_fallback_chain()` → `_get_antigravity_fallback_chain()`
  - `DEFAULT_GEMINI_FLASH_MODEL`, `DEFAULT_GEMINI_THINK_MODEL` rename
  - `_make_gemini_cli()` → `_make_antigravity_cli()`
  - `build_client()` 내 `"gemini-cli"` 키 → `"antigravity-cli"`
  - `_PRIMARY_ERRORS` dict 키 변경
  - `make_client_by_key()` 분기 조건 변경
  - `describe_backend()` 출력 문자열 변경
  - `FailoverClient._CLI_PRIMARY_FAILOVER_ERRORS` 업데이트

- `backend/src/curator/cli.py`:
  - `_cli_installed("gemini")` → `_cli_installed("agy")`
  - `"gemini-cli"` provider 문자열 전체 치환
  - `_MODEL_PRESETS["gemini-cli"]` → `_MODEL_PRESETS["antigravity-cli"]`
  - `"gemini_flash_model"`, `"gemini_think_model"` config 키 치환
  - `cli_cmd = "gemini"` 분기 → `"agy"`
  - `pkg_name = "@google/gemini-cli"` → 새 설치 명령
  - `GEMINI_CLI_TRUST_WORKSPACE` env var 처리 (agy 동등 env var 확인 후)
  - `wiki config provider --primary gemini-cli` help text 업데이트
  - `wiki status` 출력 텍스트의 "antigravity" 표현

- `backend/src/curator/config.py`:
  - `DEFAULT_CONFIG["llm"]["gemini_flash_model"]` → `"antigravity_flash_model"`
  - `DEFAULT_CONFIG["llm"]["gemini_think_model"]` → `"antigravity_think_model"`
  - `_migrate_legacy_llm_keys()` 함수 추가

- `plugin/src/types.ts`:
  - 이미 `"antigravity"` provider로 rename 완료 ✅
  - `MODEL_OPTIONS["antigravity"]` 모델 목록을 `models.json` 동적 로드로 교체 (v0.2.1 부분 적용)

- `AGENTS.md`, `CLAUDE.md` — 설치 가이드 갱신
- `setup.sh` — 설치 스크립트 (agy 설치 명령으로 교체)
- `docs/guides/USER_GUIDE_KR.md` — 사용자 가이드의 gemini-cli 언급

### 2.4. 주의사항 및 미결 사항

1. **agy CLI의 프롬프트 입력 인터페이스**: v0.2.1 구현은 `agy --print`와 stdin 경로를
   사용한다. 현재 `agy`는 안정적인 `--model` 플래그를 제공하지 않으므로, 백엔드의
   모델 선택값은 카탈로그/UI/추적 정보로 유지하고 실제 agy 모델 전환은 agy 자체 설정
   (`/model` 또는 Antigravity settings)에 위임한다.

2. **`GEMINI_CLI_TRUST_WORKSPACE` 환경변수**: gemini-cli가 현재 vault의 파일 읽기를
   허용하는 환경변수. agy에서 동등한 환경변수 이름을 확인해야 함.

3. **Fallback chain 모델 이름**: `_get_antigravity_fallback_chain()`은 Gemini 모델 계보
   (lite → flash → pro)를 그대로 유지. agy도 동일 모델 ID를 지원하는지 확인 필요.

---

## 3. 크로스 소스 Concept 병합 프로토콜

새 소스가 추가될 때 기존 DAG의 CON/EXH를 어떻게 확장하는가에 대한 명시적 규칙.

### 3.1. 병합 판단 기준

```python
CONCEPT_MERGE_THRESHOLD = 0.72  # 코사인 유사도 임계값

def should_merge(draft: ConceptDraft, existing: ConceptNode) -> bool:
    """
    임베딩 유사도 + 도메인 일치 + Atom 겹침 비율로 병합 여부 결정
    세 조건 중 두 가지 이상 충족 시 병합
    """
    sim = cosine_similarity(draft.embedding, existing.embedding)
    domain_match = draft.domain == existing.domain
    atom_overlap = len(set(draft.atom_ids) & set(existing.atom_ids)) / len(draft.atom_ids)

    score = sum([
        sim > CONCEPT_MERGE_THRESHOLD,
        domain_match,
        atom_overlap > 0.3
    ])
    return score >= 2
```

### 3.2. 병합 후 연쇄 업데이트

```
CON-xyz 업데이트 (새 ATM 흡수)
  → CON-xyz를 참조하는 EXH 목록 조회
  → 각 EXH를 ingest_jobs에 'l4_exhibitions' 타입으로 재큐잉
  → IngestWorker가 비동기로 EXH 재합성
```

기존 EXH의 `is_verified_by_human=true` 이면 재합성 건너뜀.
