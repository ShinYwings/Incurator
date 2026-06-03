# 📖 사용자 가이드: Incurator 마스터하기

이 가이드는 **Curator Engine**을 운영하고 지식 DAG를 관리하는 데 필요한 기술적인 세부 사항을 다룹니다. 시스템의 설계 철학은 [프로젝트 철학 (ABOUT_KR.md)](../philosophy/ABOUT_KR.md)를, 기능 개요는 [README](../../README_KR.md)를 참조하세요.

---

## 📋 사전 준비 사항

시스템을 설치하기 전에 다음 도구들이 설치되어 있어야 합니다:

1.  **Python 3.10+**: 시스템의 핵심 로직이 Python으로 작성되었습니다.
2.  **터미널 (Terminal)**: 모든 명령어는 CLI 환경에서 실행됩니다.
3.  **노트 편집기 (Obsidian 권장)**: 지식 베이스의 시각화 및 편집을 위한 도구입니다. 옵시디언이 필수는 아니며 텍스트 파일을 볼 수 있는 에디터라면 무엇이든 가능하지만, 본 시스템은 옵시디언의 링크 구조와 플러그인 생태계에 최적화되어 개발되었습니다.
4.  **Node.js**: 검색 엔진(QMD) 빌드 및 MCP 서버 구동을 위해 필요합니다. (Ollama와 함께 `./setup.sh` 실행 시 자동으로 설치를 시도하며, 플러그인은 `wiki init` 과정에서 설치되므로 별도로 준비하실 필요가 없습니다.)
5.  **Curator Engine 백엔드**: 시스템 구동을 위해 하나 이상의 모델 백엔드가 필요하며, 로컬과 클라우드 방식을 모두 지원합니다.
    - **로컬 LLM (Ollama)**: 강력한 개인 정보 보호와 별도 비용 없는 사용이 가능합니다. (VRAM 필요)
    - **클라우드 LLM (Providers)**: Antigravity, Claude, OpenAI 등의 외부 엔진을 활용합니다. 로컬 자원(VRAM) 소모가 거의 없으며 고성능 추론이 가능합니다. (큐레이션 단계에서는 고가의 추론 전용 모델이 아닌 일반 범용 모델로도 충분히 안정적인 성능을 발휘합니다.)
    - **유연한 구성**: 사용자의 환경에 따라 어느 쪽이든 **Primary** 또는 **Fallback** 모델로 설정할 수 있습니다. 예를 들어 평소엔 로컬을 쓰다가 장애 시 클라우드로 전환하거나, 그 반대의 구성도 가능합니다.

> [!NOTE]
> **검증된 개발 환경**
> 본 시스템은 다음 환경에서 모든 기능 및 사용성 테스트가 완료되었습니다:
> - **운영체제**: Linux (Ubuntu 24.04), macOS
- **인터페이스**: **CLI** 전용 엔진입니다. 터미널 환경에서 직접 사용하거나, **IDE (antigravity)** 에이전트 환경에서 함께 활용할 수 있습니다.
> - **초기 개발 환경**: Incurator는 현재 개발 초기 단계이며, 개발자의 모든 실험과 검증은 **antigravity** 에이전트 환경에서 이루어졌습니다. 이로 인해 일부 내부 로직이 해당 환경에 최적화되어 있을 수 있습니다. 만약 다른 에이전트나 IDE에서 문제가 발생한다면, 특정 환경에 종속된 로직을 범용적으로 개선하는 기여를 언제든 환영합니다.
> - **하드웨어**:
>   - **Linux**: NVIDIA GeForce RTX 4070 Ti 12GB, RAM 64GB
>   - **macOS**: Apple Silicon (8GB RAM 환경 테스트 완료)
> - **최소 사양 및 하드웨어 성능**: 
>   - 검색 엔진(QMD) 구동을 위한 **최소 2.5GB VRAM**이 기본적으로 필요합니다.
>   - **로컬 모델(Ollama)** 사용 시: 선택한 모델 크기만큼의 추가 VRAM이 필요합니다 (8B 모델 기준 시스템 전체 약 10GB VRAM 점유 확인, 모델 크기보다 약 2GB 이상의 추가 여유 공간 권장).
>   - **클라우드 모델(Antigravity, Claude 등)** 사용 시: 추가적인 VRAM을 소모하지 않으므로, QMD 구동을 위한 최소 VRAM 사양만으로도 충분합니다.
>   - Ollama를 통해 CPU+GPU 혼합 추론이 가능하지만, 처리 속도가 매우 느려 실용적인 큐레이션이 어려울 수 있습니다. 가급적 모델 전체가 VRAM에 올라가는 환경을 권장합니다.


> [!TIP]
> **다중 기기 동기화**
> 여러 기기에서 동일한 Vault를 사용하려는 경우 **Syncthing** 사용을 강력히 권장합니다. 동기화 과정에서 활발히 수정 중인 데이터베이스(SQLite) 파일이 동시에 전송될 경우 데이터가 파손될 위험이 있습니다. Syncthing의 **제외(Ignore)** 기능을 활용하여 실시간으로 변하는 DB 정보가 동기화 대상에서 제외되도록 설정해야 합니다. 자세한 방법은 [동기화 제외 가이드](./SYNC_IGNORE_GUIDE_KR.md)를 참조하세요.

---

## 🧭 Incurator 운영 원칙 (Operational Principles)

Incurator의 강력한 성능을 유지하고 지식을 안전하게 관리하기 위해 다음 원칙을 준수하는 것을 권장합니다.

-   **단일 진실 공급원 (Single Source of Truth)**: 프로젝트마다 `wiki init`을 수행하여 여러 개의 작은 지식 베이스를 만드는 것보다, 당신의 모든 지식을 집약할 **단 하나의 메인 보관소(Vault)**를 운영하세요. `wiki init`을 실행한 폴더에는 전용 **Curator**가 상주하며, 지식은 한곳에 모여 응집될 때 비로소 유기적으로 연결되고 새로운 통찰로 **Increment(증분)** 됩니다. 
    -   **페르소나 기반의 저장소 분리**: 지식을 관리하는 '관점'이나 '전문 페르소나'가 근본적으로 달라야 하는 경우(예: STEM 전문가 vs 요리 전문가)에만 별도의 Vault를 운영하세요. 하나의 Incurator 인스턴스는 한 번에 하나의 Curator만 실행할 수 있으므로, 무분별한 Vault 분리는 지식의 연결성을 저해합니다.
-   **기계의 영역 존중 (AI 전용 공간)**: `.curator/` 폴더는 오직 에이전트와 시스템만을 위한 'AI 전용 공간'입니다. 이곳은 사람이 읽고 편집하기 어렵게 설계된 고밀도 데이터망이며, 수동으로 파일을 수정할 경우 지식 그래프의 정합성이 깨질 수 있습니다. 웬만한 상황에서는 이곳을 직접 건드리지 마세요.
-   **자가 치유와 무결성 (Self-Healing)**: 지식 그래프가 오염되었거나 링크가 깨졌다고 느껴진다면 `wiki sync` 명령을 실행하세요. Incurator는 오류를 추적하고 논리적 무결성을 회복하는 자가 치유 능력을 갖추고 있습니다. **특히 에이전트가 아닌 사용자가 직접 노드 파일을 수동으로 편집한 경우, 반드시 `wiki sync`를 실행하여 변경 사항을 전체 그래프에 전파해야 합니다.**
-   **워크스페이스의 유연성**: 지식의 저장소(Vault)는 하나여야 하지만, 작업을 수행하는 **워크스페이스(Workspace)**는 어디에 있어도 상관없습니다. 중앙의 메인 Vault와 연결하여 그곳의 지식을 소비하세요. '지식의 창고(Vault)'에는 큐레이터가 살고, '지식의 작업실(Workspace)'에는 아티스트가 삽니다. 창고는 하나지만 작업실은 무한히 늘어날 수 있습니다.

---

## 🚀 빠른 시작

### 1. 설치
설치 스크립트를 실행하여 환경을 설정하고 필요한 구성 요소를 빌드합니다.
```bash
./setup.sh
```

### 2. 저장소(Vault) 초기화
지식 저장소로 사용할 디렉토리를 선택하고 초기화합니다.
```bash
wiki init <path/to/your/obsidian-vault>
```

초기화 중 짧은 인터뷰를 통해 **Curator 페르소나**(vault 전역 전문가 정체성)가 설정됩니다. 결과는 `.curator/config.yml`에 저장되며 `wiki sync`, `wiki query` 전반에 자동으로 적용됩니다.

#### 📂 저장소(Vault) 디렉토리 구조
`wiki init` 명령을 실행하면 Incurator는 지식 관리를 위해 다음과 같은 구조를 초기화합니다. 인큐레이터는 지식이 기계와 인간에게 각각 다른 형태로 존재할 때 가장 효율적이라는 철학에 따라, 인간을 위한 공간(Root)과 기계 및 에이전트를 위한 AI 전용 공간(`.curator/`)을 실제 디렉토리 구조로 분리하여 관리합니다.

```text
<vault_root>/
├── .obsidian/         # 옵시디언 설정 및 플러그인
├── 00_System/         # 사용자 정의 폴더 (예: sandbox, inbox 등 자유롭게 구성)
├── 01_Workspaces/     # [Artist Space] 프로젝트별 작업실 (개별 구조는 아래 참고)
├── 02_Wiki/           # [Human Space] 인간이 검증하고 승격시킨 최종 지식
├── 03_Notes/          # [Source] 인간의 원본 메모 (Immutable, 수정 불가)
├── 04_Resources/      # [Source] 외부 참조 자료 및 문헌 (Immutable, 읽기 전용)
├── 05_Assets/         # 이미지, PDF 첨부파일 등 미디어 자산
├── 06_Archives/       # 더 이상 사용하지 않는 소스 보관소
├── .curator/          # [AI Space] 시스템 핵심 데이터 및 SQLite DB (AI 전용 공간)
│   ├── config.yml     # LLM 백엔드, 모델, 경로 설정
│   ├── state.sqlite   # 중복 방지 해시, 소스Provenance, 인계 기록
│   ├── index.md       # DAG 라우팅 테이블 (L1~L4 노드 ID 목록)
│   ├── ledger.md      # HITL(인간 개입) 수정 및 승격 이력
│   └── Collections/   # 지식 계층(Layers) 마크다운 저장소
│       └── 04_Exhibitions/ # [L4] 에이전트용 맞춤형 전시물 (유일하게 생성되는 마크다운 계층)
├── .gitignore         # Git 제외 설정
└── .stignore          # Syncthing 동기화 제외 설정
```

> [!NOTE]
> `01_Workspaces/`는 Vault 내부에 위치하는 것이 일반적이지만, 물리적으로 Vault 외부에 있는 프로젝트 디렉토리를 워크스페이스로 연결하여 독립적으로 운영할 수도 있습니다.

> [!TIP]
> 상세한 무시 항목(Ignore patterns) 및 동기화 최적화 방법은 [동기화 제외 가이드](./SYNC_IGNORE_GUIDE_KR.md)를 참조하세요.

---

## 📚 지식 소스 등록 (Knowledge Ingestion)

보관소의 물리적 구조가 준비되었다면, 이제 당신의 파편화된 지식들을 시스템에 주입할 차례입니다. 

Incurator의 지식 등록 과정은 **사용자가 파일을 정리(Organize)**하고, **시스템이 이를 읽어 지식 계층(L1~L3)으로 변환(Ingest)**하는 두 단계로 이루어집니다. 이렇게 수집된 데이터는 이후 워크스페이스에서 전시물(Exhibition)로 가공되어 실제 작업에 활용됩니다.

### 1단계: 파일 배치 (Organize)
먼저 사용자가 보유한 원본 파일(PDF, Markdown, HTML, 이미지 등)을 보관소의 성격에 맞는 폴더에 직접 배치합니다.
- `03_Notes/`: 직접 작성한 메모나 생각
- `04_Resources/`: 외부에서 수집한 논문, 아티클, 문헌 자료
- `05_Assets/`: 첨부 이미지나 데이터 파일

### 2단계: 지식 요약 및 정제 (Ingest)
파일 배치가 끝났다면, Curator가 해당 파일을 읽고 지식 계층(L1~L3)으로 요약·정제하도록 명령합니다.

```bash
# 특정 파일을 지정하여 등록
wiki add 03_Notes/my_note.md

# 인자를 생략하면 보관소 전체를 스캔하여 변경사항을 한 번에 등록
wiki add
```

이 명령을 통해 Curator는 원본 데이터를 파싱하고 L1 Context를 즉시 데이터베이스(`state.sqlite`)의 레코드로 작성합니다. 마크다운 파일을 생성하여 저장소를 오염시키지 않고, 고속의 DB 레코드로 관리됩니다. 작은/중간 문서는 원문을 DB에 inline으로 보존하고, 책이나 긴 PDF 같은 대형 문서는 원본 파일에서 필요한 구간만 on-demand로 읽습니다. L2 원자적 사실 추출과 L3 개념 연결 역시 DB 레코드로 기록되며 build worker에 큐잉합니다. 결과는 `.curator/state.sqlite` 내부에 저장됩니다.

> [!TIP]
> `wiki add`에 파일이나 폴더 경로를 지정하지 않으면, Curator는 설정된 모든 소스 디렉토리(`03_Notes`, `04_Resources` 등)를 훑어 새로 추가되거나 변경된 파일을 자동으로 찾아내어 일괄 처리합니다.

- 등록된 소스 목록은 `wiki source ls`로 확인할 수 있습니다.
- 특정 폴더 내의 파일들을 재귀적으로 모두 등록하려면 `-r` 옵션을 사용하세요.

지식이 보관소에 안전하게 등록되었다면, 이제 이를 특정 프로젝트에서 실제로 활용하기 위해 당신만의 '작업 공간'을 준비할 차례입니다.

---

## 📄 외부 PDF와 Reference Mode

논문 PDF처럼 외부 앱(Zotero, iCloud, Syncthing, 브라우저 다운로드 폴더 등)이 소유한 파일은 두 가지 방식으로 Incurator에 연결할 수 있습니다.

### 1. Reference Mode

파일을 복사하지 않고 원래 위치에 둔 채 Incurator backend에 source로
등록합니다. Zotero, iCloud, Syncthing, 브라우저 다운로드 폴더 등 외부 위치에서
열린 PDF의 기본 동작입니다.

- backend는 파일의 content hash를 계산하고 `state.sqlite`에 source record를 생성합니다.
- `04_Resources/`에는 PDF 복사본이 아니라 작은 markdown reference stub을 만듭니다.
- `external_path`는 현재 파일 위치를 가리키는 hint입니다. 진짜 identity는 content hash와 logical source identity입니다.
- 자동 생성된 reference stub에는 기본적으로 PDF 절대 경로를 쓰지 않습니다.
  따라서 외부 PDF 라이브러리의 로컬 위치가 다른 기기에도 안전하게 동기화할 수 있습니다.
- iPad 필기나 외부 앱 수정으로 PDF hash가 바뀌면 backend는 이를 Hash Drift로 감지해야 합니다.
- 파일 위치가 바뀌면 backend는 configured external roots 안에서 재발견을 시도할 수 있지만, 최종 rebind는 인간 승인 후에만 수행해야 합니다.

### 2. Copy Import

Copy Import는 파일을 vault가 직접 관리해야 할 때 명시적으로 선택하는 예외
동작입니다. PDF를 `04_Resources/` 아래로 복사합니다.

- `03_Notes/`에는 PDF를 넣지 않습니다. `03_Notes/`는 사람이 직접 작성한 노트의 영역입니다.
- 활성 노트가 `03_Notes/Vision/Foo.md`라면 기본 목적지는 `04_Resources/Vision/Foo/<pdf-file>.pdf`가 됩니다.
- 연결된 노트가 없으면 기본 목적지는 `04_Resources/Inbox/<pdf-file>.pdf`입니다.
- 같은 이름의 파일이 이미 있으면 덮어쓰지 않습니다. 같은 해시라면 기존 파일을 재사용하고, 다른 해시라면 suffix를 붙이거나 사용자가 다른 목적지를 선택해야 합니다.

Obsidian 플러그인은 PDF를 열었을 때 즉시 viewer context를 만들 수 있지만, 장기 지식화와 source provenance는 backend ingest가 담당합니다. 즉, 열린 PDF에 대해 바로 질문하는 것은 plugin의 PDF context engine이 처리하고, 이후 durable RAG/source tracking은 Incurator backend가 처리합니다.

---

## 🎨 워크스페이스 관리 (Workspace Management)

워크스페이스는 **아티스트** (인간 + 에이전트)가 실제 프로젝트를 수행하는 독립적인 작업실입니다.

> [!IMPORTANT]
> **위치의 자유**: 워크스페이스는 반드시 Vault 내부(`01_Workspaces/`)에 있을 필요가 없습니다. 당신이 현재 작업 중인 시스템상의 **어떤 프로젝트 디렉토리**라도 `wiki workspace init`을 통해 Curator와 연결된 워크스페이스로 변신시킬 수 있습니다.

### 🏗️ 에이전트를 Curator에 연결하기

프로젝트 디렉토리에서 아래 명령으로 에이전트와 Curator를 연결합니다:

```bash
wiki workspace init <path/to/workspace> --agent <agent>
```

사용 중인 에이전트에 맞는 `--agent` 값을 선택하세요:

| 에이전트            | `--agent` 값    | 생성/수정되는 룰 파일          |
| ------------------- | --------------- | ------------------------------ |
| Claude Code         | `claude-code`   | `CLAUDE.md`                    |
| OpenAI Codex        | `codex`         | `AGENTS.md`                    |
| Antigravity         | `antigravity`   | `AGENTS.md`                    |
| 에이전트 없음 (CLI) | `none`          | —                              |

`--project`는 프로젝트 고유 슬러그를 지정합니다. (기본값: 디렉토리 이름)

> [!TIP]
> **현재 워크스페이스 판별 기준**:
> Curator는 **현재 디렉토리(CWD)**와 그 상위 디렉토리를 탐색하여 `curate.yml` 파일을 찾습니다. 프로젝트 폴더 안에 들어가 명령어를 실행하면 별도 지정 없이 자동으로 워크스페이스를 인식합니다.

---

### 🔄 초기화 시 세 가지 시나리오

`wiki workspace init`은 대상 디렉토리의 현재 상태를 감지해 동작을 자동으로 조정합니다.

#### 시나리오 1: 빈 디렉토리

`curate.yml`, 에이전트 룰 파일, `.agents/curator/` 하위 파일이 모두 새로 생성됩니다.

#### 시나리오 2: 기존 에이전트 룰 있음 (Curator 미연결)

`CLAUDE.md`, `AGENTS.md` 등 에이전트 룰 파일은 있지만 Curator가 아직 연결되지 않은 상태입니다.

Incurator는 자체 LLM을 사용하여 기존 룰 파일을 읽고, 세션 시작/쿼리 루프/세션 종료 등 적절한 위치에 Curator hooks를 자동으로 통합합니다. 기존 룰은 그대로 보존됩니다.

```text
Found existing claude-code setup. Integrating Curator knowledge navigation...

Proposed changes to CLAUDE.md:
  ## My Existing Rules            ← 기존 룰 보존
+ ## Curator Knowledge Navigation  ← LLM이 추가
+
+ **Session start** — call curator_check_workspace() ...
  ...

Apply Curator integration to CLAUDE.md? [Y/n]:
```

- **Y**: 파일이 Curator hooks가 통합된 버전으로 교체됩니다.
- **N**: 에이전트에게 직접 붙여넣을 수 있는 프롬프트가 출력됩니다. 이 프롬프트를 에이전트에게 전달하면 에이전트가 직접 룰 파일을 수정합니다.

LLM을 사용할 수 없는 경우, 프롬프트가 자동으로 출력되고 Curator 블록이 룰 파일 앞에 prepend됩니다.

#### 시나리오 3: Curator 이미 연결됨 (복원 / 업데이트)

`curate.yml`과 Curator 런타임 파일이 이미 존재하는 상태입니다. `.agents/curator/` 하위 소유 파일들은 최신 템플릿으로 덮어씌워지고, 에이전트 룰 파일의 managed block은 마커 사이 내용만 교체됩니다. managed block 외부의 기존 내용은 절대 수정되지 않습니다.

---

### 📁 초기화 후 생성되는 파일 구조

```text
<your_project_dir>/
├── curate.yml                           # 지식 요구 명세서
├── CLAUDE.md (또는 AGENTS.md) # 에이전트 룰 파일 — managed block 삽입
└── .agents/curator/
    ├── shared/rules.md                  # Curator 전체 행동 규칙
    ├── shared/sync.md                   # 동기화 워크플로우
    ├── runtime/<agent>.md               # 에이전트별 런타임 가이드
    └── workflows/
        ├── workspace_loop.md            # 세션 워크플로우
        └── session_closeout.md          # 세션 종료 체크리스트
```

`.agents/curator/` 하위 파일은 Incurator가 소유하며, 매 init/sync 시 최신 템플릿으로 덮어씌워집니다. 에이전트 룰 파일의 managed block 외부 내용은 절대 수정되지 않습니다.

---

### MCP로 초기화 (CLI 없이)

에이전트가 이미 MCP 서버에 연결되어 있다면, 채팅 세션에서 직접 워크스페이스를 초기화할 수 있습니다:

```text
curator_workspace_init(
  workspace_path="/absolute/path/to/project",
  project="my-project",
  description="이 워크스페이스의 목적"
)
```

MCP 툴은 연결된 에이전트 런타임을 자동 감지하고 동일한 세 가지 시나리오 로직을 적용합니다. 기존 룰 파일이 있으면 자동으로 LLM 통합을 시도하고, LLM을 사용할 수 없는 경우 `integration_prompt`를 반환합니다.

전체 MCP 툴 레퍼런스는 [MCP 사용법 가이드](./MCP_USER_GUIDE_KR.md)를 참고하세요.

---

### `curate.yml` — 워크스페이스 설정 레퍼런스

`curate.yml`은 워크스페이스 수준의 설정 파일입니다. Curator에게 어떤 지식을 어떻게 전시할지 알려주고, 이 프로젝트의 큐레이션 스타일을 제어하는 **Artist 페르소나**를 내장합니다.

```yaml
project: "my-project"
description: "my-project 지식 워크스페이스"

# Artist 페르소나 — wiki workspace init 마법사가 자동 생성.
# Curator가 이 프로젝트용 Exhibition을 준비하는 방식을 제어합니다.
persona:
  domain: ""               # 예: "computer-vision", "biochemistry"
  subdomain: ""            # 더 구체적인 세부 분야
  goal: ""                 # 이 워크스페이스의 큐레이션 목표 (2~4문장)
  exhibition_intent: "engineer"  # researcher | engineer | learner
  disambiguation_keywords: []    # 이 워크스페이스 특화 검색 키워드
  confidence:
    high_threshold: 0.85   # 이 이상 → 고신뢰도 Exhibition
    low_threshold: 0.55    # 이 이하 → HITL 검토 큐
  updated_at: ""

# 소스 선택 — vault root 기준 fnmatch 글로브.
# include 목록이 비어 있으면 전체 소스에서 지식을 가져옵니다.
sources:
  include: []
  #  - "03_Notes/**"
  #  - "02_Wiki/my-topic/**"
  exclude: []

# search_curator 결과의 최소 신뢰도 하한선.
min_confidence: 0.60

# 활성 Exhibition 앵커 — wiki curate가 자동으로 설정.
# 비워 두면 자동 감지, 특정 ID를 입력하면 해당 Exhibition으로 고정.
exhibition: ""
```

**주요 필드:**

| 필드 | 설명 |
| ---- | ---- |
| `persona.exhibition_intent` | `researcher` — 검증할 가설; `engineer` — 구현 단계; `learner` — 복습할 개념 |
| `persona.confidence` | 워크스페이스별 신뢰도 임계값 (vault 전역 설정을 덮어씀) |
| `sources.include` | 이 워크스페이스에 공급할 vault 파일 범위 (비어 있으면 전체) |
| `min_confidence` | 이 값 미만의 Exhibition은 `search_curator` 결과에서 제외 |
| `exhibition` | 매 세션의 primary context로 사용할 Exhibition ID |

> [!TIP]
> `persona:` 블록은 `wiki workspace init` 시 Artist 페르소나 마법사가 자동으로 생성합니다. 이후 `wiki persona update --workspace <name>` 또는 `curator_update_artist_persona` MCP 툴로 업데이트할 수 있습니다.

보관소와 워크스페이스가 모두 준비되었습니다. 이제 Curator가 당신의 질문에 어떻게 답변하고, 에이전트와 어떻게 협업하는지 확인해 보세요.

---

## 🔍 지식 활용 및 큐레이션 (Utilization)

이제 수집된 지식을 바탕으로 답변을 얻거나 에이전트용 데이터를 최종 합성합니다.

### 지식 검색 및 자동 업데이트 (Intent-based Curation)
Incurator의 가장 핵심적인 작동 방식입니다. 당신은 그저 질문하거나 대화하기만 하면 됩니다.

시스템은 워크스페이스 또는 일반 Vault 환경에 따라 **이원화된 아키텍처(Dual Architecture)**를 사용합니다:
- **Workspace Agent**: 워크스페이스가 지정된 경우, `curate.yml`에 정의된 **Pinned Exhibition**과 페르소나를 사용하며 임시 파일을 생성하지 않습니다.
- **Vault Agent**: 일반 Vault 환경에서 질의하는 경우, 세션별로 **임시(Ephemeral) L4 Exhibition**을 동적으로 생성하고 글로벌 폴백 페르소나를 사용합니다. 활성 노트가 워크스페이스 폴더 안에 있지 않은 일반 채팅은 Vault 세션으로 취급되어, 임시 Exhibition이 `default`로 스코프되며 사용자가 열지 않은 무관한 프로젝트 워크스페이스에 묶이지 않습니다.

**요청별 언어 처리**: 에이전트는 각 질문의 언어를 유니코드 스크립트로 매번 새로 감지하고(한국어, 영어, 중국어, 일본어, 러시아어 등) 그 언어로 답하며, 영어는 내부 검색/추론 언어로만 사용합니다. 출력 언어는 메시지마다 독립적으로 따라가므로, 이전 질문이 한국어였더라도 영어 질문에는 영어로 답합니다. 언어 메타데이터는 생성된 Exhibition 파일에 저장되지 않으며, 답변 캐시는 출력 언어로 키가 구성되어 stale 언어 캐시 답변을 받지 않습니다.

**L3 제약 조건 및 가비지 컬렉션(GC)**:
- L4 Exhibition은 일치하는 **L3 Concept이 있을 때만 생성**됩니다. 관련 L3가 없으면 L4 생성을 건너뛰고 즉시 답변을 반환합니다.
- Vault 세션 중에 생성된 임시 L4 Exhibition은 `ephemeral: true`로 마킹되며, 지식 베이스 오염을 방지하기 위해 24시간 후 `wiki lint`에 의해 자동 삭제(Garbage Collected)됩니다.

`wiki query`를 실행하거나 에이전트와 대화(`curator_query` / `search_curator`)하는 **그 시점**에, 시스템은 필요한 지식이 최신이 아니라면 **즉시 파이프라인을 가동하여 최종 답변을 합성**합니다.

> [!TIP]
> **"그냥 쓰세요. 나머지는 시스템이 알아서 합니다."**
> 지식을 활용하려는 "의도"가 발생했을 때 큐레이션이 트리거되므로, 사용자가 매번 어떤 워크스페이스인지 지정하거나 파이프라인을 수동으로 돌릴 필요가 없습니다. (명령어를 실행한 폴더 위치를 통해 시스템이 자동으로 맥락을 파악합니다.)

### (참고) 고급 수동 강제 큐레이션
디버깅, workspace-agent 복구, 강제 업데이트가 필요한 경우에만 제한적으로 사용합니다. `wiki curate`는 직접 호출할 수 있지만, 일반 사용자는 보통 직접 L4 Exhibition을 생성하지 않고 query 또는 workspace agent를 사용해야 하므로 기본 `wiki --help` 표면에서는 숨겨집니다.
```bash
wiki curate
```
- **워크스페이스 자동 선택**: 현재 폴더나 상위 폴더에 `curate.yml`이 있다면 해당 명세를 따릅니다.
- **기본값 (Fallback)**: 워크스페이스가 없는 상태에서 `wiki curate`를 실행하면, Curator는 `01_Workspaces/Curator Workspace`라는 **기본 작업 공간을 자동으로 생성**하여 전체 지식을 대상으로 합성을 시작합니다.
    - > [!WARNING]
    > **향후 제거 예정**: 이 자동 생성 기능은 현재 v0.1.0 개발 및 디버깅 단계에서의 편의를 위해 한시적으로 제공됩니다. 향후 버전에서는 명확한 지식 관리 경계를 위해 워크스페이스(`curate.yml`)가 없는 상태에서의 자동 합성을 제한할 예정이므로, 가급적 `wiki workspace init`을 통한 정석적인 설정을 권장합니다.

---

## 🔄 피드백 루프 및 자가 치유 (HITL & Sync)

지식은 대화와 수정을 통해 점진적으로 완성됩니다.

1.  **합성 (Synthesis)**: 워크스페이스에서 에이전트와 대화하며 새로운 통찰을 도출합니다.
2.  **피드백 및 수정**: 대화 중 사전 지식의 오류를 발견하면 MCP 도구를 통해 즉시 노드를 수정합니다.
3.  **자가 치유 (Self-Healing)**: 노드가 수정되면 `wiki sync`가 자동으로 실행되어 그래프를 역추적(Backprop)하고 일관성을 회복합니다. 수동으로 무결성을 검증하려면 `wiki sync`를 직접 실행하세요.
4.  **승격 (Promotion)**: 확정된 통찰은 `02_Wiki/`로 이동시켜 인간이 읽기 좋은 위키로 승격시킵니다.
5.  **순환 (Loop)**: 승격된 위키 내용은 다음 주기에서 새로운 소스로 인식되어 다시 시스템에 흡수됩니다.

이러한 선순환 구조는 지식이 단순히 저장되는 것에 그치지 않고, 끊임없는 상호작용과 검증을 통해 더 높은 수준의 통찰로 진화하게 만듭니다.

---

## 🧑‍🎨 페르소나 설정

Incurator에는 두 가지 페르소나 레이어가 있으며, 각각 다른 수준에서 동작합니다.

### Curator 페르소나 — Vault 수준

`wiki init` 실행 시 짧은 인터뷰를 통해 설정됩니다. wizard는 첫 질문을 바로 표시하고, 각 질문이 단일 선택인지 다중 선택인지 표시하며, verification source와 artifact type 같은 다중 선택 질문에서는 `1,4`처럼 쉼표로 구분한 번호를 받을 수 있습니다. 마지막 persona JSON이 저장되면 인터뷰는 즉시 종료됩니다. 결과는 `.curator/config.yml`에 저장되며, `wiki sync`와 `wiki query` 전반에 전역으로 적용됩니다.

```bash
wiki persona              # 현재 Curator 페르소나 확인
wiki persona update       # 인터뷰를 다시 실행하여 재설정
```

인터뷰를 건너뛰면 기본 STEM 페르소나가 적용됩니다.

> [!IMPORTANT]
> **Curator 페르소나는 Vault의 전문가 정체성을 정의합니다.** 근본적으로 다른 전문가 관점(예: STEM 연구자 vs. 요리사)이 필요하다면, 페르소나를 바꾸는 것이 아니라 새로운 Vault를 만들어야 합니다.

### Artist 페르소나 — 워크스페이스 수준

`wiki workspace init` 마법사가 자동으로 생성하며, `curate.yml`의 `persona:` 블록에 저장됩니다. 이 프로젝트에서만 Curator 페르소나를 덮어써, `exhibition_intent`, 신뢰도 임계값, disambiguation 키워드를 워크스페이스별로 세밀하게 조정합니다.

```bash
wiki persona update --workspace <name>   # 인터뷰로 Artist 페르소나 재설정
```

또는 채팅 세션에서 `curator_update_artist_persona` MCP 툴로 업데이트할 수 있습니다.

→ 전체 `persona:` 필드 레퍼런스는 [위의 `curate.yml` 섹션](#curateyml--워크스페이스-설정-레퍼런스)을 참고하세요.

---

## 🛠️ 핵심 명령어 (CLI Reference)

사용자의 워크플로우에 따른 주요 명령어 요약입니다.

### 1. 초기화 및 설정 (Setup)
| 명령어 | 설명 | 사용 시점 |
| :--- | :--- | :--- |
| `wiki init <path>` | Curator 보관소를 초기화합니다. | 처음 시스템을 시작할 때 |
| `wiki config <key>` | 모델 및 환경 설정을 수정합니다. | 프로바이더 변경 시 |
| `wiki status` | 저장소 상태 및 통계를 확인합니다. | 전반적인 건강 상태 체크 시 |
| `wiki persona` | 전역 페르소나를 확인하고 업데이트합니다. | 큐레이션 방향 조정 시 |

### 2. 지식 수집 및 관리 (Ingestion)
| 명령어 | 설명 | 사용 시점 |
| :--- | :--- | :--- |
| `wiki add <file>` | 소스를 등록하고 L1 Context 레코드를 데이터베이스에 즉시 생성합니다 (구조 기반, LLM 없음). | 새로운 정보를 추가할 때 |
| `wiki build` | 등록된 L1 Context에서 L2 Atom + L3 Concept를 데이터베이스 레코드로 추출/컴파일합니다. 기본은 백그라운드 워커에 큐잉, `--wait`는 즉시 실행. | 지식 그래프 심층 구축 시 |
| `wiki source ls` | 등록된 소스 목록을 확인합니다. | 수집된 데이터 현황 파악 시 |
| `wiki source show <id>` | 특정 소스의 상세 정보와 처리 상태를 확인합니다. | 소스 오류 진단 시 |
| `wiki source rm <id>` | 소스 등록을 해제하고 생성된 L1 노드를 삭제합니다. | 잘못된 소스를 제거할 때 |
| `wiki source retry <id>` | 오류 상태 소스를 재처리합니다. | 소스 처리 실패 후 재시도 시 |

### 2-1. 설정 및 LLM 백엔드 관리

| 명령어 | 설명 |
| :--- | :--- |
| `wiki config provider` | LLM 백엔드 (Ollama / Claude Code / Antigravity / Codex / DeepSeek) 와 모델을 대화형으로 설정합니다. |
| `wiki config models list` | 현재 백엔드에서 사용 가능한 모델 목록을 표시합니다. |
| `wiki config models use <tag>` | 사용할 모델을 직접 지정합니다. |
| `wiki config get <key>` | 특정 설정 값을 조회합니다. (예: `wiki config get llm.primary`) |
| `wiki config set <key> <value>` | 특정 설정 값을 변경합니다. (예: `wiki config set llm.model gemini-3.5-flash`) |

### 3. 고도화 및 최적화 (Curation)
| 명령어 | 설명 | 사용 시점 |
| :--- | :--- | :--- |
| `wiki curate` | L4 Exhibition을 합성합니다. 기본 help에서는 숨겨집니다. | 고급/디버깅용 workspace curation |
| `wiki sync` | 무결성 검증 및 자가 치유를 수행합니다. | 노드 수정 후 일관성 회복 시 |
| `wiki refresh` | 변경된 L3 Concept를 기존 L4 Exhibition에 반영하되, 인간/agent 편집을 덮어쓰지 않습니다. | 새 Concept를 기존 Exhibition으로 전파할 때 |

### 4. 지식 활용 (Utilization)
| 명령어 | 설명 | 사용 시점 |
| :--- | :--- | :--- |
| `wiki query "..."` | 질문에 대한 정제된 답변을 얻습니다. | 지식을 활용한 답변 필요 시 |
| `wiki workspace init` | 워크스페이스를 초기화합니다. | 새 프로젝트 시작 시 |

### 5. 개발자 전용 도구 (Developer Only)
| 명령어 | 설명 | 사용 시점 |
| :--- | :--- | :--- |
| `wiki testbed init` | 테스트용 가상 보관소(`testbed/`)를 구축합니다. | 새로운 기능을 안전하게 검증하고 싶을 때 |
| `wiki testbed list` | 사용 가능한 테스트 시나리오 목록을 확인합니다. | 검증할 시나리오를 선택할 때 |

> [!CAUTION]
> **테스트 베드 주의사항**: 위 명령어들은 실제 지식 베이스가 아닌 개발용 임시 저장소를 다룹니다. 일반적인 지식 관리나 실제 프로젝트 수행 중에는 사용하지 마십시오.

---

## 🧩 설정 관리 (Configuration)

Incurator는 `.curator/config.yml` 파일을 직접 수정하지 않아도, `wiki config` 명령어를 통해 모든 핵심 설정을 안전하고 편리하게 관리할 수 있습니다.

### 1. 프로바이더 설정 (`wiki config provider`)
Incurator의 지능을 담당하는 LLM 백엔드를 설정합니다. 시스템은 두 개의 백엔드 계층을 가집니다.

- **Primary Backend**: 모든 작업의 주 엔진입니다. 당신의 하드웨어 사양이나 예산에 맞춰 가장 적합한 모델을 선택하세요.
- **Fallback Backend (Failover)**: 주 엔진이 네트워크 장애나 API 제한 등으로 응답하지 않을 때 업무를 인계받는 보조 엔진입니다. 주 엔진과 다른 유형(예: 클라우드 ↔ 로컬)을 지정하면 시스템의 안정성이 더욱 높아집니다.

> [!NOTE]
> `Primary`와 `Fallback`은 설정 방식이 동일하며, 아래의 모든 프로바이더를 자유롭게 교차 선택할 수 있습니다.

> [!TIP]
> provider가 quota, rate-limit, capacity 초과를 보고하면 Incurator는 이를 명시적인 오류로 표시하고 빈 LLM 답변을 정상 결과로 받아들이지 않으며 설정된 Fallback 백엔드로 전환합니다. Obsidian sidechat도 이 오류를 quota/capacity 메시지로 표시하므로 provider/model을 바꾸거나 reset 시점까지 기다릴 수 있습니다.

#### 지원 프로바이더 목록
| 프로바이더 | 유형 | 특징 |
| :--- | :--- | :--- |
| `ollama` | 로컬 | DeepSeek, Llama 3 등 로컬 모델 사용 (비용 무료, 오프라인 가능) |
| `antigravity-cli` | CLI | Google Antigravity CLI (`agy`)를 통한 추론 (가장 빠르고 안정적인 무료 옵션). Gemini 3.5 Flash / 3.1 Pro 외에 Claude·GPT-OSS 모델도 노출됩니다 |
| `claude-code` | CLI | Anthropic 공식 `claude` 명령어를 통한 추론 (Sonnet 4.6 / Opus 4.7 / Haiku 4.5) |
| `codex-cli` | CLI | OpenAI 공식 `codex` 명령어를 통한 추론 (GPT-5.5 / 5.4 / 5.4-mini / 5.3-codex / 5.2) |
| `deepseek-api` | API key | DeepSeek의 OpenAI 호환 API를 통한 추론 (`DEEPSEEK_API_KEY` 또는 암호화된 로컬 backend secret; 현재 모델 `deepseek-v4-flash` / `deepseek-v4-pro`) |

```bash
# 위자드를 따라 Primary와 Fallback을 한 번에 설정
wiki config provider
```

#### 추론 강도 (Reasoning Effort)

모델을 고른 뒤에는 **추론 강도(effort)** 를 함께 선택할 수 있습니다. 이는 각 CLI가 노출하는 사고 깊이 옵션과 1:1로 매핑됩니다.

- `claude-code` → `claude --effort <low|medium|high|xhigh|max>`
- `codex-cli` → `codex -c model_reasoning_effort=<low|medium|high|xhigh>`
- `antigravity-cli` → `agy`는 별도 플래그가 없어, 선택한 강도가 프롬프트 힌트로 전달됩니다 (best-effort).

위자드는 모델별로 사용 가능한 강도만 보여주며 (예: Gemini 3.1 Pro 는 `low`/`high`), 강도가 하나뿐인 모델은 자동 선택됩니다. 플래그로 직접 지정할 수도 있습니다:

```bash
# Primary 를 GPT-5.5 + high effort 로 즉시 설정
wiki config provider --primary codex-cli --model gpt-5.5 --effort high
wiki config provider --primary deepseek-api --model deepseek-v4-flash
wiki config provider --primary deepseek-api --model deepseek-v4-pro --api-key-env DEEPSEEK_API_KEY
```

DeepSeek에서 `--api-key-env`에는 실제 `sk-...` 키 값이 아니라 환경변수 이름
(`DEEPSEEK_API_KEY` 같은 값)을 넣어야 합니다.
`--api-key sk-...`를 넘기면 키는 shared vault 밖 backend encrypted local secret store에 저장되고, config에는 secret reference만 기록됩니다.

선택한 강도는 `.curator/config.yml` 의 `llm.primary_effort` / `llm.fallback_effort` 에 저장되며, 비워 두면 각 CLI의 기본 강도를 사용합니다.

CLI 기반 provider(`antigravity-cli`, `claude-code`, `codex-cli`)는 backend가 실행되는 머신에서 해당 CLI에 현재 로그인된 계정을 사용합니다. 다른 계정을 쓰려면 provider CLI 자체(`agy`, `claude`, `codex login`)에서 계정을 전환하세요. DeepSeek는 다릅니다. `DEEPSEEK_API_KEY`, 암호화된 로컬 `llm.deepseek-api.api_key_secret`, 또는 legacy plaintext `llm.deepseek-api.api_key`의 API 키를 사용하므로 계정 선택은 브라우저 로그인 세션이 아니라 키로 결정됩니다. 새로 저장하는 키는 vault sync로 유출되지 않도록 encrypted local secret path를 사용해야 합니다.

### 2. 모델 관리 (`wiki config models`)
현재 프로바이더에서 사용할 세부 모델을 확인하고 변경합니다.

```bash
# 사용 가능한 모델 및 추천 리스트 확인
wiki config models list

# 특정 모델로 즉시 전환 (Ollama의 경우 미설치 시 자동 다운로드)
wiki config models use gemma2:9b
```

- `wiki config models list`는 현재 시스템 성능과 프로바이더 특성에 맞는 최적의 모델들을 추천해 줍니다.
- `wiki config models use`를 통해 모델을 변경하면, 시스템이 해당 모델의 가용성을 즉시 검증하고 설정 파일에 반영합니다.
- `wiki config secret list/delete`로 로컬 encrypted backend secret을 마스킹된 상태로 확인하거나 삭제할 수 있습니다.

### 3. 상태 확인 (`wiki status`)
보관소의 건강 상태와 AI 엔진의 가동 현황을 입체적으로 진단하는 종합 대시보드입니다. 시스템 운영 중 의문이 생긴다면 가장 먼저 확인해야 할 명령어입니다.

```bash
wiki status
```

최신 sync report에 확인할 항목이 있으면 `wiki status`가 review 세부사항을 표시할지 물어볼 수 있습니다. 이 세부사항은 점검하거나 수리해야 할 무결성 진단 결과이며, status 명령 자체가 실패했다는 뜻은 아닙니다.
state DB 파일은 존재하지만 기본 테이블이 빠진 상태라면, 이제 `wiki status`가 통계를 읽기 전에 스키마를 자동으로 보정합니다.

### 3-1. 생성 상태 초기화 (`wiki reset`)

```bash
wiki reset
wiki reset --force
```

`.curator/config.yml`과 vault의 source folder는 보존하면서 생성된 Curator
상태를 초기화합니다. tracking database, generated Collections,
dashboard/index/overview/ledger/log 파일, sync report, transient staging 파일,
build trace canvas, device registry, sidechat session state를 제거합니다. 오래된
generated state, device metadata, chat context 때문에 backend와 plugin 상태가
어긋날 때 사용합니다.

이 명령어는 크게 세 가지 영역의 데이터를 실시간으로 집계하여 출력합니다. 각 항목의 의미와 활용 방법은 다음과 같습니다:

#### ⚙️ 구성 설정 (Config)
시스템의 '두뇌'와 '눈'이 제대로 세팅되었는지 확인합니다.
-   **Primary / Fallback 모델**: 현재 지식 추출과 합성을 담당하는 주력 LLM과 비상용 LLM을 보여줍니다. 의도한 모델이 활성화되어 있는지 확인하세요.
-   **Reranking (리랭킹)**: 검색 결과의 정밀도를 높이는 2차 검증 프로세스의 활성화 여부입니다. 고품질 답변이 필요하다면 `on` 상태여야 합니다.
-   **QMD binary**: 검색 엔진의 핵심 바이너리 상태입니다. `installed`가 아니거나 `not found`라면 `wiki reindex`나 재설치가 필요할 수 있습니다.
-   **Search index degradation**: `wiki reindex`는 먼저 BM25 index를 갱신한 뒤 vector embedding을 시도합니다. embedding이 실패해도 BM25 search는 최신 상태로 유지되고 vector search만 stale로 표시됩니다. `qmd doctor`로 embedding 환경을 확인한 뒤 `wiki reindex`를 다시 실행하세요.

#### 📂 지식 원천 현황 (Sources)
원본 데이터가 지식화되는 '파이프라인의 입구'를 점검합니다.
-   **Raw source files**: 보관소 폴더 내에 물리적으로 존재하는 파일의 총개수입니다.
-   **Sources summarized (L1)**: `l1_status=done`인 소스 수입니다. `wiki add`는 LLM 없이 구조 기반 L1 Context를 즉시 만듭니다. L1 page에는 검색용 영어 source guide와 크기 인식 source sections가 들어갑니다. 작은/중간 문서는 원문을 inline하고, 대형 문서는 preview와 marker만 두며 정확한 원문 증거는 원본 파일에서 on-demand로 읽습니다. L2/L3 추출은 별도 단계로, `wiki build`로 실행합니다 (기본은 백그라운드 워커 큐잉, `--wait`는 동기 실행).
-   **Ingest runs**: 지금까지 수행된 총 수집 횟수입니다. 이 수치가 높을수록 지식 베이스가 빈번하게 업데이트되었음을 의미합니다.

#### 🧠 지식 밀도 (Collections)
파이프라인의 각 단계별 처리 현황을 나타냅니다. v0.2.1 기본 흐름에서는 L1이 즉시 생성되고, L2·L3는 MCP background worker 또는 `wiki jobs run`으로 처리되며, L4는 workspace-agent 흐름 또는 숨겨진 고급 `wiki curate` 명령에서 생성됩니다. worker가 claim하기 전의 queued job은 `wiki jobs cancel <id>`로 취소하고, 완료/실패/취소된 job은 `wiki jobs rerun <id>`로 다시 queue에 넣을 수 있습니다.

-   **L1 Contexts**: DB에 저장된 소스 요약 레코드 개수입니다.
-   **L2 Atoms**: DB에 저장된 원자적 사실 레코드 개수입니다.
-   **Fallback Atoms**: DB에 임시로 저장된 낮은 신뢰도의 Atom 레코드 개수입니다.
-   **L3 Concepts**: DB에 저장된 교차 소스 클러스터링(개념) 레코드 개수입니다.
-   **L4 Exhibitions**: 워크스페이스 명세(`curate.yml`)에 따라 마크다운 파일로 합성된 전시물입니다.

> [!TIP]
> **파이프라인 현황 진단**: L4가 0이라면 아직 워크스페이스에서 Exhibition이 생성되지 않은 것입니다. MCP를 통해 `search_curator`를 호출하면 workspace curation이 실행되어 L4가 생성될 수 있습니다. 수동 `wiki curate`는 고급/디버깅용으로 계속 사용할 수 있지만 기본 help 표면에서는 숨겨집니다.

### 4. 외부 리소스 연동 (Zotero & Reference Mode)
Incurator는 Zotero 등의 외부 PDF 파일들을 보관소로 복사하지 않고 원본 그대로 참조(Reference Mode)할 수 있으며, 원할 경우 사용자가 승인한 `04_Resources/` 목적지로 안전하게 복사할 수도 있습니다.
- **설정**: 옵시디언 플러그인 설정의 "Zotero Library Path"를 입력하거나 터미널에서 `wiki config set external.zotero.path ~/Documents/Zotero` 명령을 사용하여 Zotero 루트 경로를 지정합니다.
- **Reference Mode**: 외부 리소스는 파일의 내용 해시(Content Hash), `external_path` hint, 고유한 `logical_source_id`로 추적됩니다. 구현에 따라 `04_Resources/`에는 proxy note 또는 backend source anchor가 생성될 수 있지만, durable state는 backend가 소유합니다.
- **Copy Import**: 파일을 vault 내부로 가져오는 경우에도 목적지는 `03_Notes/`가 아니라 `04_Resources/`입니다. 같은 이름의 파일을 덮어쓰지 않고, 동일 해시는 재사용하며, 충돌 시 suffix 또는 사용자 선택 목적지를 사용합니다.
- **Hash Drift와 자가 치유**: iPad 등에서 Apple Pencil로 PDF에 주석을 달면 내용 해시가 변경됩니다. 파일이 이동하거나 해시가 변경되어 연결이 끊어진 경우, 옵시디언 플러그인 UI를 통해 재연결(Re-bind)을 승인하면 backend가 고유 식별자(`logical_source_id`)를 기준으로 새로운 해시와 경로를 찾아 치유(Healing)합니다.

### 5. OS 환경별 경로 분리 (Platform-aware Config)
Linux와 macOS 환경을 번갈아 사용하는 경우, Syncthing 동기화로 인한 절대 경로 충돌을 방지하기 위해 플랫폼별 설정이 철저히 분리됩니다.
- **플러그인 설정**: 옵시디언 플러그인 설정 메뉴에서 `Linux Binary Path`와 `macOS Binary Path`를 각각 별도로 입력합니다. 에이전트는 실행 중인 운영체제(`process.platform`)에 맞춰 올바른 백엔드 실행 파일을 자동 호출합니다.
- **글로벌 설정 (`~/.config/curator/config.yml`)**: Zotero 라이브러리 경로 등 기기 종속적인 로컬 설정은 Vault 내부가 아닌 OS 사용자 홈 디렉토리의 전역 설정 파일에서 관리됩니다.
