# Plan: Orchestrated Pipeline + Persona System

> 작성일: 2026-05-09  
> 대상 브랜치: `master`  
> 상태: **Phase 1–3 완료 / Phase 4(벤치마크 실행) 보류 / Full Orchestration 미구현**

---

## 배경과 목표

이 문서는 두 개의 대형 플랜이 한 사이클 안에서 진행된 경위와 결과를 기록한다.

### Orchestrated Pipeline 플랜

`wiki add` 파이프라인의 두 가지 구조적 문제를 해결하기 위해 시작됐다.

1. **Atom dedup 미작동** — `_find_existing_atom()`이 이름 substring 매칭만 해서, 다른 소스에서 온 의미상 동일한 atom이 중복 생성됐다.
2. **병렬성 없음** — L1→L2→L3가 완전히 순차적이었다. 멀티소스 ingest가 느리고, 소스 간 지식 충돌 해소 로직이 없었다.

제안 아키텍처: **Orchestrator-Worker-Coordinator** 패턴.

### Persona System 플랜

InCurator 엔진이 STEM/ML에 암묵적으로 편향되어 있고, 사용자별로 지식 관리 목적과 방식이 다름에도 시스템이 이를 반영할 방법이 없다는 문제를 해결하기 위해 시작됐다.

2-tier 페르소나: **Curator Persona** (vault 전역, `config.yml`) + **Artist Persona** (workspace별, `curate.yml`).

---

## 완료된 작업

### [Orchestrated Pipeline] Phase 1 — Atom Coordinator

**목적**: 서로 다른 소스에서 온 의미상 동일한 atom을 병합해 L2 품질 개선.

| 항목 | 파일 | 위치 |
|------|------|------|
| `ATOM_COORDINATOR_INSTRUCTIONS` 프롬프트 | `src/curator/prompts.py` | L285 |
| `build_atom_coordinator_messages()` | `src/curator/prompts.py` | L313 |
| `_run_atom_coordinator()` | `src/curator/ingest_llm.py` | L707 |
| `run_l1_to_l3()` 내 coordinator 호출 배선 | `src/curator/ingest_llm.py` | L1981 |

동작: L2 루프 완료 후 새 atom IDs + 같은 domain의 기존 atom 요약을 coordinator LLM에 전달 → `merge_pairs` 파싱 → `build_merge_atom_messages()` 재사용해 병합. `absorb_id` atom은 `redirects_to` frontmatter 마킹.

---

### [Orchestrated Pipeline] Phase 2 — Orchestrated Add (Hint-based + 함수 구조화)

**목적**: Orchestrator가 extraction plan을 분해하고, Worker가 task-scope 컨텍스트를 가지고 병렬 실행.

#### 구현된 것

| 함수 | 파일 | 위치 | 설명 |
|------|------|------|------|
| `ATOM_ORCHESTRATOR_INSTRUCTIONS` | `src/curator/prompts.py` | L335 | Orchestrator가 반환하는 JSON: `{ tasks: [{ scope, candidates[], context_hint }] }` |
| `build_atom_orchestrator_messages()` | `src/curator/prompts.py` | L374 | Orchestrator LLM call 메시지 빌더 |
| `_run_orchestrator_plan()` | `src/curator/ingest_llm.py` | L920 | Orchestrator 호출 → task list 반환. 실패 시 `None` (caller가 fallback) |
| `_extract_atoms_for_task()` | `src/curator/ingest_llm.py` | L989 | 1개 task의 모든 candidates 처리. **`scope` + `context_hint`를 `[Scope: ...] hint` 형태로 결합**해 각 atom 추출에 전달 |
| `_run_sequential_atoms()` | `src/curator/ingest_llm.py` | L1022 | 순차 fallback. streaming 사용. 기존 인라인 코드를 named function으로 추출 |
| `_run_parallel_workers()` | `src/curator/ingest_llm.py` | L1080 | TPE dispatcher. task 단위 병렬 실행. 실패 시 `_run_sequential_atoms()` fallback |
| `_run_pass1_atoms()` 리팩토링 | `src/curator/ingest_llm.py` | L1125 | orchestrator → parallel_workers → sequential_atoms 흐름으로 단순화 |

#### 수정된 버그

- **`scope` 필드 무시 버그**: 기존 코드는 orchestrator가 반환하는 `scope` 필드를 완전히 무시하고 `context_hint`만 썼다. `_extract_atoms_for_task()`에서 `scope`와 `context_hint`를 결합하도록 수정됨.

#### 현재 구현 한계 (의도된 미완성)

현재 Phase 2는 **hint-based orchestration**이다. Orchestrator가 candidate별 `scope`/`context_hint`를 제공하면, 각 atom은 여전히 개별 LLM call로 추출된다 (1 atom = 1 LLM call). 플랜의 최종 목표인 **Full Orchestration** (task 단위 단일 LLM call로 2–5 atoms 동시 추출)은 미구현이며, 벤치마크 결과로 구현 여부를 결정하기로 했다. 자세한 내용은 [미완료 항목](#미완료-항목)을 참조.

---

### [Orchestrated Pipeline] Phase 3 — Parallel Sync (Mode C)

**목적**: `wiki sync` Mode C Phase 1 concept 검증을 병렬로 실행해 속도 개선.

| 항목 | 파일 | 위치 |
|------|------|------|
| `ThreadPoolExecutor` 도입 | `src/curator/sync.py` | L782 |
| `max_parallel_verifications` config 키 | `src/curator/config.py` | `DEFAULT_CONFIG["sync"]` |

`config.yml`에 `sync.max_parallel_verifications: 4`로 설정 (기본값, cloud 기준 / 0 또는 1 = 비활성화). thread safety: 검증 단계는 읽기 전용 (파일 읽기 + LLM call)이라 GIL만으로 충분.

**Ollama 자동 처리**: Ollama는 기본적으로 inference를 1개씩 순차 처리한다 (`OLLAMA_NUM_PARALLEL` 기본값 1). 병렬 HTTP 요청을 보내도 Ollama 내부에서 큐잉되므로 스레드 오버헤드만 생긴다. `sync.py`에서 duck-typing으로 `OllamaClient` 여부를 감지해 자동으로 `max_workers = 1`로 강제한다 (FailoverClient의 primary가 Ollama인 경우도 포함).

---

### [Orchestrated Pipeline] Phase 4 — Benchmark Harness (코드만 완성, 실행 보류)

**목적**: 현재 아키텍처와 Full Orchestration을 deepseek-r1:8b 기준으로 비교 → 어느 구조를 쓸지 결정.

| 항목 | 파일 | 설명 |
|------|------|------|
| `BenchmarkRun` 데이터클래스 | `scripts/benchmark/benchmark.py` | L87 |
| `run_benchmark(scenario, model_key, results_dir)` | `scripts/benchmark/benchmark.py` | L327 |
| `compare_runs(path_a, path_b)` | `scripts/benchmark/benchmark.py` | L377 |
| GS_Testbed query set (4문항) | `scripts/benchmark/benchmark.py` | L47 |
| LLM-as-judge 품질 평가 | `scripts/benchmark/benchmark.py` | L265 |
| `wiki benchmark run` / `wiki benchmark compare` CLI | `src/curator/cli.py` | L4750+ |

**실행 방법**:
```bash
wiki benchmark run GS_Testbed --models gemini-flash --models deepseek-r1:8b
wiki benchmark compare results/run_a.json results/run_b.json
```

**보류 이유**: 실제 비교를 위해서는 Full Orchestration (아직 미구현)과 deepseek-r1:8b 로컬 모델이 필요하다. 벤치마크 코드는 준비됐으나 **실행은 Full Orchestration 구현 이후로 미룸**.

---

### [Persona System] Part A — 스키마 정의

#### A1. Global (Curator) Persona — `config.yml`

`src/curator/config.py` `DEFAULT_CONFIG["persona"]` (L249)에 DEFAULT STEM persona 추가:

```yaml
persona:
  area: "STEM"
  text: |
    Scientific and technical research vault.
    Focus on formal derivability, mathematical rigor, and algorithmic correctness.
  knowledge_artifacts: [equations, algorithms, research papers, experimental results]
  verification_philosophy: "mathematical derivability and citation-based evidence"
  exhibition_intent: "knowledge-worker"
  confidence:
    high_threshold: 0.85
    low_threshold: 0.55
  disambiguation_keywords: [Architecture, Optimization, Algorithm, Theory, Implementation]
  updated_at: ""
```

`get_curator_persona(config)` helper 추가 (L269).

#### A2. Workspace (Artist) Persona — `curate.yml`

`src/curator/curate_yml.py` `ArtistPersona` dataclass (L38):

```python
@dataclass
class ArtistPersona:
    domain: str = ""
    subdomain: str = ""
    text: str = ""
    exhibition_intent: str = "engineer"  # researcher | engineer | learner
    disambiguation_keywords: list[str]
    confidence: dict  # {"high_threshold": 0.85, "low_threshold": 0.55}
```

`load_curate_spec()`에서 `curate.yml`의 `persona:` 블록을 읽어 `ArtistPersona`로 파싱 (L150–165).

---

### [Persona System] Part B — 인터뷰 프롬프트 및 CLI 위저드

#### 프롬프트 (`src/curator/prompts.py`)

| 심볼 | 위치 | 설명 |
|------|------|------|
| `PERSONA_INTERVIEW_CURATOR_SYSTEM` | L1061 | Curator 인터뷰용 system prompt. `_CURATOR_PERSONA_FIELDS` JSON 스키마 포함 |
| `PERSONA_INTERVIEW_ARTIST_SYSTEM` | L1078 | Artist 인터뷰용 system prompt. `_ARTIST_PERSONA_FIELDS` JSON 스키마 포함 |
| `build_persona_interview_messages(history, is_workspace, project)` | L1112 | `is_workspace`에 따라 Curator/Artist system prompt 분기 |

두 system prompt는 LLM에게 각 타입별 필드 스키마를 명시해 올바른 JSON을 반환하도록 강제한다.  
**수정된 버그**: 기존에는 `is_workspace`/`project` 파라미터를 받아도 내부에서 무시했다 → 항상 동일한 generic 프롬프트 반환 → LLM이 잘못된 필드 반환. 분리된 system prompt로 해결.

#### CLI 위저드 (`src/curator/cli.py`)

| 함수 | 설명 |
|------|------|
| `_run_curator_persona_wizard(client, current_persona, recent_domains)` | Curator 인터뷰 루프. `current_persona` + `recent_domains`가 있으면 LLM에 기존 상태를 컨텍스트로 전달 (update 모드) |
| `_run_artist_persona_wizard(client, project)` | Artist 인터뷰 루프 |

`wiki persona update` 실행 시: `read_recent_domains(paths)`로 최근 ingestion 도메인을 읽어 wizard에 전달 → LLM이 현재 페르소나를 보고 정제 제안.

**CLI 명령어** (L4461+):
```
wiki persona                           # Curator persona 출력
wiki persona update                    # Curator 인터뷰 재실행
wiki persona update --workspace NAME   # Artist 인터뷰 재실행
```

---

### [Persona System] Part C — Persona 주입 포인트

모든 주입 포인트는 선택적(optional)이며 persona 없을 시 기존 동작과 동일.

| 주입 포인트 | 함수 | 파라미터 | 효과 |
|------------|------|----------|------|
| Concept 검증 | `build_theme_logic_verify_messages()` | `domain_context: str` | global persona `text` + `verification_philosophy`를 검증 컨텍스트에 주입 |
| Exhibition 검증 | `build_curation_logic_verify_messages()` | `domain_context: str` | 동일 |
| Concept 생성 | `build_theme_page_messages()` | `workspace_context: str` | workspace `text` + `domain`을 concept 생성 컨텍스트에 주입 |
| Exhibition 생성 | `build_curation_page_messages()` | `agent_context: str`, `exhibition_intent: str` | workspace `text`와 intent별 section 3 내용 동적 변경 |
| Curation planning | `build_curation_planning_messages()` | `high_threshold`, `low_threshold` | persona confidence 값으로 HITL 기준 threshold 치환 |
| Concept plan suffix | `_concept_plan_suffix()` in `ingest_llm.py` | workspace `disambiguation_keywords` | 동명 Concept 충돌 시 domain-aware suffix 사용 |

#### `exhibition_intent` 동적 지시문 (`src/curator/prompts.py` L541)

```python
_EXHIBITION_INTENT_DIRECTIVES = {
    "researcher": "Suggest specific follow-up papers, open hypotheses...",
    "engineer":   "Describe specific code, system, or pipeline implementation steps...",
    "learner":    "List the core concepts the learner should review...",
}
```

`"researcher"` / `"engineer"` / `"learner"` 에 따라 Exhibition section 3 ("Actionable Directives")의 내용이 달라진다. 기본값은 `"knowledge-worker"` generic 지시문.

---

### [Persona System] Part D — 데이터 흐름 연결

#### D1. `sync.py`

`run_sync()` 시작 시 global curator persona 로드 → `build_theme_logic_verify_messages()` / `build_curation_logic_verify_messages()` 호출 시 `domain_context` 전달 (L701).  
`_regenerate_concept()` / `_regenerate_exhibition()` 에서도 persona text + exhibition_intent 주입 (L868, L937).

#### D2. `ingest_llm.py`

`run_l4_scoped()` 진입 시 `curate.yml` `persona` 읽어 `ArtistPersona` 생성 → concept/exhibition 생성 함수에 `workspace_context`, `agent_context`, `exhibition_intent`, confidence threshold 전달.

#### D3. `query.py`

synthesis 생성 시 global curator persona `text` + `exhibition_intent` 주입 (L558):
```python
if agent_context:
    synthesis_user_content = f"## Agent Context\n{agent_context}\n\n{synthesis_user_content}"
```

#### D4. Global Persona 진화 (도메인 로깅)

`wiki add` 완료 후 새로 생성된 CTX 파일들의 frontmatter `domain` 필드를 수집해 `log.md`에 HTML comment로 기록:
```
<!-- domains:computer-vision,3d-gaussian-splatting date:2026-05-08 -->
```

`wiki persona update` 실행 시 `read_recent_domains(paths)` 로 최근 20개 항목 읽어 wizard에 전달 → LLM이 최근 ingestion 도메인을 보고 persona 정제 제안.

| 함수 | 파일 | 위치 |
|------|------|------|
| `_collect_domains_from_contexts()` | `ingest_llm.py` | L1949 |
| `_append_domain_log()` | `ingest_llm.py` | L1964 |
| `read_recent_domains()` | `ingest_llm.py` | L1974 |

---

### [Persona System] Part E — MCP Tools

`src/curator/mcp_server.py`에 자연어 persona 업데이트 툴 2개 추가:

| 툴 | 설명 |
|----|------|
| `curator_update_artist_persona(workspace_path, request)` | L159 — workspace `curate.yml`의 Artist persona를 자연어 요청으로 업데이트 |
| `curator_update_curator_persona(request)` | L249 — vault `config.yml`의 Curator persona를 자연어 요청으로 업데이트 |

예시:
```
curator_update_artist_persona("01_Workspaces/GS_Lab", "이론 중심으로 바꿔줘")
curator_update_curator_persona("요리 레시피도 다루게 넓혀줘")
```

---

### [Persona System] Part F — 문서 전체 업데이트

| 파일 | 내용 |
|------|------|
| `docs/philosophy/about.md` | 섹션 5 제목 "두 가지 차별점" → "세 가지 차별점". `셋째, 페르소나:` 항목 추가 |
| `docs/philosophy/about_EN.md` | 섹션 5에 아이템 6 `Persona: Expressing Your Knowledge Model` 추가 (목록 형식 통일) |
| `docs/guides/USER_GUIDE.md` | "Curator 페르소나" (L226) / "Artist 페르소나" (L240) 섹션 추가. `wiki persona` 명령어 사용법 포함 |
| `docs/guides/USER_GUIDE_EN.md` | 동일 내용 영문 |
| `docs/guides/MCP_USER_GUIDE.md` | `curator_update_artist_persona` / `curator_update_curator_persona` 툴 문서 추가 (L87) |
| `docs/guides/MCP_USER_GUIDE_EN.md` | 동일 내용 영문 |
| `docs/spec/system_behavior/incurator_v0.1.0.md` | Persona System 섹션 추가 (L149). 2-tier 구조, 주입 포인트 전체 목록, `wiki query` fallback 동작 |
| `docs/spec/curator_schema/SCHEMA_v0.1.0.md` | Curator/Artist persona 스키마 정의 (L424+) |
| `README.md` | 퀵스타트 step 3: `wiki persona update` 언급 추가 |
| `README_EN.md` | 동일 내용 영문 |

---

### [Persona System] Part G — STEM 편향 제거

기존 코드에 박혀 있던 STEM/ML 전용 표현들을 범용 표현으로 교체. 이로써 역사, 요리, 경영, 문학 등 비-STEM 지식도 자연스럽게 처리된다.

| 항목 | Before | After | 파일 |
|------|--------|-------|------|
| Atom type 열거 | `fact \| equation \| theoretical_constraint \| entity \| technique` | `fact \| claim \| entity \| procedure \| relationship` | `prompts.py` L69, `db.py` L113 |
| Concept 섹션 1 | `## 1. Core Architecture` | `## 1. Core Idea` | `prompts.py` L456, `ingest_llm.py` L631 |
| Concept 섹션 2 | `## 2. Interaction of Atoms` | `## 2. How the Atoms Connect` | 동일 |
| Concept 섹션 3 | `## 3. Mathematical Framework` | `## 3. Key Patterns` | 동일 |
| Exhibition 섹션 2 | `**2. Theoretical Foundation**` | `**2. Background & Evidence**` | `prompts.py` L529, `ingest_llm.py` L695 |
| 클러스터링 규칙 | `equation family` | `underlying principle or pattern` | `prompts.py` L286 |
| Concept 검증 | `Math fidelity: equations/symbols...` | `Precision fidelity: specific claims, formulas...` | `prompts.py` L580 |
| 예외 규칙 | ML/CV 전용 예시 (transmittance, alpha weights...) | domain-agnostic 원칙 | `prompts.py` L584 |
| Exhibition 검증 | `Theoretical chain correctness` | `Reasoning chain correctness` | `prompts.py` L609 |
| domain 예시 | `'computer-vision', 'mathematics', 'nlp'` | `'history', 'machine-learning', 'cooking', 'philosophy'` | `prompts.py` L59 |
| `_concept_plan_suffix()` 반환값 | 하드코딩 `"Mechanism"` | `plan.domain.split("-")[0].title()` 또는 `"Variant"` | `ingest_llm.py` L484 |
| `requires_math_rigor` 필드 | `synthesis` 테이블에 존재 | **제거** (어디서도 참조 안 됨) | `db.py` |

---

### [추가] L1 Summary 강화 (소형 모델 대응)

`SUMMARY_INSTRUCTIONS` (`prompts.py` L51)를 deepseek-r1:8b 등 소형 모델에서 충분한 정보를 추출하도록 대폭 강화:

- **FORBIDDEN 규칙**: "do NOT write 'the paper discusses X'" — 실제 내용 추출 강제
- **섹션별 최소 bullet 수**: 3–5개 이상
- **최소 `key_claims`**: 5개 이상 (목표 10–15개)
- **최소 `atom_candidates`**: 5개 이상, 상한 없음
- **원칙**: "Prefer to write TOO MUCH over too little"

---

## 미완료 항목

### Full Orchestration (Master LLM 패턴) — 미구현

**의도**: 진정한 Master LLM → 병렬 sub-agent (L1+L2 동시 처리) → 결과 통합 Coordinator 패턴.  
**현재 상태**: 현재 Phase 2는 "hint-based orchestration"에 해당한다.

| 비교 | 현재 구현 | Full Orchestration (미구현) |
|------|----------|-----------------------------|
| Orchestrator 역할 | `scope`/`context_hint` 힌트 제공 | 소스 분석 후 L1/L2/L3 전 레이어 작업 계획 수립 |
| 병렬 단위 | atom 단위 (1 atom = 1 LLM call) | task 단위 (2–5 atoms = 1 LLM call) |
| Coordinator | atom dedup만 (`_run_atom_coordinator`) | L1↔L2↔L3 간 cross-layer 논리 일관성 검증 및 병합 |
| 구현 상태 | **완료** | **미구현** |

**보류 이유**: 벤치마크로 현재 구조와 Full Orchestration 구조를 비교한 후 구현 여부 결정.  
**결정 기준**: GS_Testbed에서 deepseek-r1:8b 기준으로 `wiki benchmark run` 실행 → atom 품질, concept 일관성, 실행 시간 비교.

**다음 단계 (구현 시)**:
1. `build_task_batch_messages(scope, candidates[], excerpt)` 신규 프롬프트 — 1개 task에서 2–5개 atom을 한 번의 LLM call로 추출
2. `_extract_atoms_for_task()`를 batch LLM call 방식으로 변경 (현재는 candidate별 개별 call)
3. Cross-layer Coordinator: L1 요약 + L2 atoms + L3 concept plans를 한 LLM에 보내 논리 일관성 확인 후 조정
4. `wiki benchmark run GS_Testbed --models gemini-flash --models deepseek-r1:8b` 실행 및 결과 분석

---

### Benchmark 실행 — 보류

코드는 완성됐으나 아직 실행 안 됨. 실행 전제 조건:
1. Full Orchestration 구현 (비교 대상이 있어야 의미 있음)
2. `deepseek-r1:8b` Ollama 모델 pull

---

## 검증 결과 (이번 사이클 기준)

```
PYTHONPATH=src .venv/bin/python -m pytest tests/ -x -q
→ 22 passed

VAULT_ROOT=testbed wiki testbed init GS_Testbed --force
VAULT_ROOT=testbed wiki add
→ 5 sources, 50 atoms, 7 concepts, auto-sync clean

VAULT_ROOT=testbed wiki curate --workspace "testbed/01_Workspaces/Gaussian Splatting Geometry Lab"
→ 1 exhibition created, sync clean

VAULT_ROOT=testbed wiki lint
→ Health score: 100/100, 63 pages, 0 errors
```

---

## 관련 파일 전체 목록

| 파일 | 변경 내용 |
|------|-----------|
| `src/curator/prompts.py` | STEM 편향 제거, Coordinator/Orchestrator 프롬프트, exhibition_intent 지시문, 인터뷰 프롬프트, 주입 포인트 파라미터, SUMMARY_INSTRUCTIONS 강화 |
| `src/curator/ingest_llm.py` | `_run_atom_coordinator`, `_extract_atoms_for_task`, `_run_sequential_atoms`, `_run_parallel_workers`, `_run_pass1_atoms` 리팩토링, 도메인 로깅 함수, persona 전달 |
| `src/curator/sync.py` | Mode C 병렬 검증 (ThreadPoolExecutor), persona 주입 (`domain_context`, `workspace_context`, `agent_context`, `exhibition_intent`) |
| `src/curator/config.py` | DEFAULT STEM persona, `max_parallel_verifications` config 키, `get_curator_persona()` |
| `src/curator/curate_yml.py` | `ArtistPersona` dataclass, `load_curate_spec()` persona 파싱 |
| `src/curator/cli.py` | `_run_curator_persona_wizard`, `_run_artist_persona_wizard`, `wiki persona` 명령어, `wiki benchmark run/compare` 명령어 |
| `src/curator/query.py` | global persona agent_context 주입 |
| `src/curator/db.py` | `claim_type` comment 범용화, `requires_math_rigor` 필드 제거 |
| `src/curator/mcp_server.py` | `curator_update_artist_persona`, `curator_update_curator_persona` MCP tools |
| `scripts/benchmark/benchmark.py` | 신규 — BenchmarkRun, run_benchmark, compare_runs, GS_Testbed query set, LLM-as-judge |
| `docs/philosophy/about.md` | 섹션 5 제목/본문 페르소나 항목 추가 |
| `docs/philosophy/about_EN.md` | 섹션 5 아이템 6 페르소나 추가 |
| `docs/guides/USER_GUIDE.md` | Curator/Artist 페르소나 섹션 신규 |
| `docs/guides/USER_GUIDE_EN.md` | 동일 영문 |
| `docs/guides/MCP_USER_GUIDE.md` | 페르소나 MCP tools 문서 |
| `docs/guides/MCP_USER_GUIDE_EN.md` | 동일 영문 |
| `docs/spec/system_behavior/incurator_v0.1.0.md` | Persona System 섹션 추가 |
| `docs/spec/curator_schema/SCHEMA_v0.1.0.md` | Curator/Artist persona 스키마 정의 |
| `README.md` | 퀵스타트 persona 언급 추가 |
| `README_EN.md` | 동일 영문 |
