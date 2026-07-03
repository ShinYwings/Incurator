# 📖 사용자 가이드: Incurator 마스터하기

이 가이드는 **Curator Engine**을 운영하고 지식 DAG를 관리하는 데 필요한 기술적인 세부 사항을 다룹니다. 시스템의 설계 철학은 [프로젝트 철학](../philosophy/ABOUT_KR.md)를, 기능 개요는 [README](../README_KR.md)를 참조하세요.

---

## 📋 사전 준비 사항

시스템을 설치하기 전에 다음 도구들이 설치되어 있어야 합니다:

1.  **Python 3.10+**: 시스템의 핵심 로직이 Python으로 작성되었습니다.
2.  **터미널 (Terminal)**: 모든 명령어는 CLI 환경에서 실행됩니다.
3.  **노트 편집기 (Obsidian 권장)**: 지식 베이스의 시각화 및 편집을 위한 도구입니다. 옵시디언이 필수는 아니며 텍스트 파일을 볼 수 있는 에디터라면 무엇이든 가능하지만, 본 시스템은 옵시디언의 링크 구조와 플러그인 생태계에 최적화되어 개발되었습니다.
4.  **Node.js**: Obsidian 플러그인 빌드와 플러그인 개발 도구 실행을 위해 필요합니다. (Ollama와 함께 `./setup.sh` 실행 시 자동으로 설치를 시도하며, 플러그인은 `wiki init` 과정에서 설치되므로 별도로 준비하실 필요가 없습니다.)
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
>   - 로컬 검색 기본값은 `llama-cpp-python`을 통해 Qwen3 0.6B embedding/reranker GGUF를 사용합니다(런타임 오버헤드 전 모델 파일 기준 약 1.28GB). Incurator는 검색 모델을 로드하기 전에 설정된 Ollama LLM 모델을 unload하여 VRAM 압박을 줄입니다.
>   - **채팅/큐레이션에 로컬 모델(Ollama)을 사용할 때**: 선택한 모델 크기만큼의 추가 VRAM이 필요합니다 (8B 모델 기준 시스템 전체 약 10GB VRAM 점유 확인, 모델 크기보다 약 2GB 이상의 추가 여유 공간 권장).
>   - **클라우드 모델(Antigravity, Claude 등)** 사용 시: 로컬 VRAM 부담은 줄어들지만, DB-native FTS5 검색은 여전히 로컬에서 실행됩니다.
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
-   **무결성 검증**: `wiki sync`로 구조적·논리적 무결성을 검증하고 지원되는 수리를 적용합니다. `.curator/Collections/`의 생성 파일은 폐기 가능한 projection이므로 수동 편집을 DB 변경 입력 경로로 사용하지 마세요.
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

초기화 중 짧은 인터뷰를 통해 **Curator 페르소나**(vault 전역 전문가 정체성)가 설정됩니다. 결과는 `.curator/settings.yml`에 저장되며 `wiki sync`, `wiki query` 전반에 자동으로 적용됩니다.

#### 📂 저장소(Vault) 디렉토리 구조
`wiki init` 명령을 실행하면 Incurator는 지식 관리를 위해 다음과 같은 구조를 초기화합니다. 인큐레이터는 지식이 기계와 인간에게 각각 다른 형태로 존재할 때 가장 효율적이라는 철학에 따라, 인간을 위한 공간(Root)과 기계 및 에이전트를 위한 AI 전용 공간(`.curator/`)을 실제 디렉토리 구조로 분리하여 관리합니다.

초기화 중 Incurator는 알려진 로컬 MCP 클라이언트 설정 파일(Gemini/Antigravity 및 vault-local Claude 설정)에 해당 vault의 `VAULT_ROOT`를 등록하려고 시도합니다. 이 쓰기는 best-effort입니다. 설정 파일이 없거나, 형식이 잘못되었거나, 쓸 수 없는 경우에도 초기화는 계속 성공하지만, CLI는 건너뛴 대상마다 경고를 출력합니다.

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
│   ├── settings.yml   # Vault 범위의 portable 설정 (페르소나, 동기화 정책 등)
│   ├── state.sqlite   # 중복 방지 해시, 소스Provenance, 인계 기록
│   ├── index.md       # DAG 라우팅 테이블 (L1~L4 노드 ID 목록)
│   ├── ledger.md      # HITL(인간 개입) 수정 및 승격 이력
│   └── Collections/   # 지식 계층(Layers) 마크다운 저장소
│       └── 04_Synthesis/   # [L4] 공유 코퍼스 전역 종합 노드 (SYN-, 파생 projection)
├── .gitignore         # Git 제외 설정 (자동 생성됨)
└── .stignore          # Syncthing 동기화 제외 설정 (자동 생성됨)
```

> [!NOTE]
> `01_Workspaces/`는 Vault 내부에 위치하는 것이 일반적이지만, 물리적으로 Vault 외부에 있는 프로젝트 디렉토리를 워크스페이스로 연결하여 독립적으로 운영할 수도 있습니다.

> [!TIP]
> 상세한 무시 항목(Ignore patterns) 및 동기화 최적화 방법은 [동기화 제외 가이드](./SYNC_IGNORE_GUIDE_KR.md)를 참조하세요.

---

## 📚 지식 소스 등록 (Knowledge Ingestion)

보관소의 물리적 구조가 준비되었다면, 이제 당신의 파편화된 지식들을 시스템에 주입할 차례입니다. 

Incurator의 지식 등록 과정은 **사용자가 파일을 정리(Organize)**하고, **시스템이 이를 읽어 지식 계층(L1~L4)으로 변환(Ingest)**하는 두 단계로 이루어집니다. 이렇게 수집된 데이터는 공유 Synthesis가 되고, 실제 사용 시 동적 workspace/query 렌즈가 필요한 근거를 선택합니다.

### 1단계: 파일 배치 (Organize)
먼저 사용자가 보유한 원본 파일(PDF, Markdown, HTML, 이미지 등)을 보관소의 성격에 맞는 폴더에 직접 배치합니다.
- `03_Notes/`: 직접 작성한 메모나 생각
- `04_Resources/`: 외부에서 수집한 논문, 아티클, 문헌 자료
- `05_Assets/`: 첨부 이미지나 데이터 파일

### 2단계: 구조적 지식 등록 (L1)
파일 배치가 끝났다면, Curator가 해당 파일을 읽고 구조적 L1 context로 등록하도록 명령합니다.

```bash
# 특정 파일을 지정하여 등록
wiki add 03_Notes/my_note.md

# 인자를 생략하면 보관소 전체를 스캔하여 변경사항을 한 번에 등록
wiki add
```

이 명령을 통해 Curator는 원본 데이터를 파싱하고 L1 권위 상태를 `state.sqlite`에 즉시 기록합니다. 작은/중간 문서는 CTX projection의 `Source Sections`에 원문을 inline으로 포함하고, 책이나 긴 PDF 같은 대형 문서는 원본 파일에서 필요한 구간만 on-demand로 읽습니다. 점검용 CTX 마크다운은 `.curator/Collections/01_Contexts/`에 emit되며, parser가 만든 같은 문서 heading 링크는 broken wikilink가 되지 않도록 평문으로 렌더링합니다. 이 projection은 폐기 가능하며 DB가 권위 상태입니다. L2 원자적 사실과 L3 개념을 queue에 넣거나 컴파일하려면 `wiki build`를 별도로 실행합니다.

PDF text parsing은 pymupdf4llm의 host Tesseract OCR을 암묵적으로 실행하지
않으며, image/scanned page 추출은 명시적으로 설정한 vision model을 사용합니다.

> [!NOTE]
> **수동 파이프라인 실행**: `wiki query`와 `search_curator`는 검색 전용 작업으로, pending 소스를 자동으로 등록하거나 처리하지 않습니다. 새 파일을 등록하려면 `wiki add`를, L2~L4 레이어를 구축하려면 `wiki build`를, 쿼리 전 DAG 무결성을 확인하려면 `wiki sync`를 실행합니다.

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
- 같은 외부 문서를 다시 참조해도 stub이 중복 생성되지 않습니다. backend는 각 참조를 안정적인 `logical_source_id`(Zotero의 경우 `zotero:<attachmentKey>`)로 식별하여 기존 stub을 재사용합니다. `state.sqlite` 행이 사라지고 stub 파일만 디스크에 남아 있어도 마찬가지여서, 더 이상 `04_Resources/References/` 아래에 `<name>-2.md` 같은 중복본이 나타나지 않습니다.
- Zotero reference는 `zotero:<attachmentKey>`와 content hash만 저장합니다.
  PDF를 열 때마다 backend가 현재 기기의 Zotero database에서 key를 실제
  파일로 해석하며, 해석된 PDF 절대경로는 `.curator/`에 저장하지 않습니다.
- 일반 external reference는 `@<root_key>/<relative-path>`를 저장합니다.
  기기별 root 값은 repo-local `.cache/config/config.yml`에만 존재합니다.
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

`workspace init`은 선택한 에이전트의 top-level 룰 파일만 설치합니다. Codex와
Antigravity는 둘 다 `AGENTS.md`를 사용하므로, 선택한 런타임이 그 파일의
managed Curator block을 소유합니다. `CLAUDE.md`는 `--agent claude-code`일
때만 작성됩니다. 생성되는 block에는 Curator navigation 규칙만 들어가며,
Incurator 저장소의 release plan, roadmap, agent inbox 같은 개발 워크플로우
파일을 가져오면 안 됩니다. `curate.yml`의 `vault_root` 필드는 vault 위치를
기록합니다. 이 값은 **워크스페이스 디렉토리 기준 상대 경로**(예: `01_Workspaces/<proj>/`
아래 워크스페이스라면 `../..`)로 작성되므로, vault가 기기마다 다른 절대 경로에
마운트되더라도 동기화된 `curate.yml`이 그대로 유효합니다. 절대 경로도 동작합니다.
MCP 서버가 실행 중일 때는 기기별 `VAULT_ROOT` 환경변수가 이 필드보다 우선하며,
`vault_root`는 standalone 도구 호출 시에만 참조되는 fallback입니다. `workspace init`을
다시 실행하면 정말로 stale해진 `vault_root`만 이식 가능한 상대 경로로 치유하고,
이미 현재 vault로 해석되는 값은 건드리지 않습니다.

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

`.agents/curator/` 하위 파일은 Incurator가 소유하며, 매 init/sync 시 최신 템플릿으로 덮어씌워집니다. 선택된 top-level 에이전트 룰 파일의 managed block 외부 내용은 절대 수정되지 않습니다.

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

goal:
  primary: "이 프로젝트 지식을 설명하고 확장합니다."
  audience: "engineer"      # researcher | engineer | learner | writer | generalist
  deliverables: ["curated-context"]
  success_criteria:
    - "모든 사실 주장은 소스 근거를 인용합니다."

sources:
  include: []
  #  - "03_Notes/**"
  #  - "02_Wiki/my-topic/**"
  exclude: []
  reference_mode:
    allow_external: true
    require_rebind_approval: true

knowledge:
  domains: []
  topics: []
  disambiguation_keywords: []
  avoid_merges: []

output:
  format: "context-pack"
  style: "dense-technical"
  citation_style: "curator-source-spans"
  include_sections: ["Evidence Map", "Synthesis", "Open Questions"]

reasoning:
  default_mode: "auto"      # auto | local | global | explore | source-section
  allowed_modes: ["local", "global", "explore"]
  exploration_enabled: true
  max_followups: 5
  require_insight_candidates: false

verification:
  min_confidence: 0.60
  high_threshold: 0.85
  require_source_spans: true
  allow_general_knowledge: false
  contradiction_policy: "surface-and-flag"

backprop:
  enabled: true
  source_truth_policy: "never_rewrite_original_source"
  derived_insight_policy: "record_then_promote_or_patch_generated"
  ambiguous_merge_policy: "needs_review"

prompts:
  profile: "default"
  output_language: "same_as_latest_request"
  prompt_overrides: {}
```

> **v0.3.1**: 이전 anchor 필드는 제거되었습니다 — 고정된 워크스페이스별
> 생성 파일은 더 이상 없습니다. `curate.yml`은 이제 공유 DAG 위에서 쿼리 시점
> 검색을 편향시키는 동적 Curation 렌즈를 구동합니다.
>
> 워크스페이스 Artist 페르소나 도구는 prompt 편집을 위해 여전히 `persona:` 블록을
> 관리할 수 있지만, 실행 가능한 curation policy는 위의 구조화된 KRS 섹션에서
> 컴파일됩니다.

**주요 필드:**

| 필드 | 설명 |
| ---- | ---- |
| `goal.audience` | curation 출력의 대상: `researcher`, `engineer`, `learner`, `writer`, `generalist` |
| `sources.include` / `sources.exclude` | vault 상대 경로 기준 source scope. `include`가 비어 있으면 전체 tracked source가 대상이며, exclude가 항상 우선합니다. |
| `sources.reference_mode` | Zotero/linked resource 같은 외부 reference 정책 |
| `knowledge.domains` / `knowledge.topics` | curation과 plan에 사용하는 workspace relevance 용어 |
| `knowledge.avoid_merges` | 서로 구분되어야 하는 concept의 false-merge guard |
| `reasoning.allowed_modes` / `reasoning.default_mode` | workspace가 사용할 수 있는 retrieval route와 기본 route 선호 |
| `verification.min_confidence` | curation lens에 적용되는 신뢰도 하한 |
| `verification.allow_general_knowledge` | 근거가 없을 때 저장되지 않은 일반 지식을 사용할 수 있는지 여부 |
| `backprop.*` | feedback 및 derived insight writeback 정책 |
| `prompts.*` | prompt profile, 출력 언어, prompt-family override |

> [!TIP]
> `wiki workspace init`이 초기 `curate.yml`을 작성합니다. 이후 workspace Artist
> 페르소나는 `wiki persona update --workspace <name>` 또는
> `curator_update_artist_persona` MCP 툴로 업데이트할 수 있습니다.

보관소와 워크스페이스가 모두 준비되었습니다. 이제 Curator가 당신의 질문에 어떻게 답변하고, 에이전트와 어떻게 협업하는지 확인해 보세요.

---

## 🔍 지식 활용 및 큐레이션 (Utilization)

이제 수집된 지식을 바탕으로 답변을 얻거나 에이전트용 데이터를 최종 합성합니다.

### 동적 Curation Lens를 이용한 지식 검색
Incurator의 가장 핵심적인 작동 방식입니다. 당신은 그저 질문하거나 대화하기만 하면 됩니다.

쿼리는 워크스페이스든 Vault든 동일하게 **세션리스**입니다 — 답변 + `QTR-` 트레이스를
반환하며 vault 파일을 쓰지 않습니다:
- **워크스페이스 쿼리**: `curate.yml`이 스코프에 있으면 그 페르소나/KRS가 Curation
  렌즈(어떤 증거를 선택하고 어떻게 랭킹할지)를 편향시킵니다.
- **Vault 쿼리**: 활성 노트가 워크스페이스 폴더 안에 있지 않은 일반 채팅은 `default`로
  해석되며 KRS 편향이 없습니다 — 열지 않은 무관한 프로젝트 워크스페이스에 묶이지 않습니다.

**요청별 언어 처리**: 에이전트는 각 질문의 언어를 유니코드 스크립트로 매번 새로 감지하고(한국어, 영어, 중국어, 일본어, 러시아어 등) 그 언어로 답하며, 영어는 내부 검색/추론 언어로만 사용합니다. 출력 언어는 메시지마다 독립적으로 따라갑니다. 언어 메타데이터는 응답/트레이스 전용이며 어디에도 저장되지 않습니다.

`wiki query`와 `curator_query`는 현재 컴파일된 DAG를 읽어 sessionless 답변과 `QTR-` trace를 반환합니다. `search_curator`는 답변 합성 없이 검색 결과를 반환합니다. 쿼리는 source를 등록하거나 pending L2/L3 job을 실행하거나 고정 Exhibition 파일을 쓰지 않습니다. 컴파일된 DAG를 갱신하려면 `wiki add`와 `wiki build`를 명시적으로 실행합니다.

> [!TIP]
> 활성 workspace 경로가 `curate.yml` KRS 적용 여부를 결정합니다. workspace
> 밖에서는 `default` vault scope를 사용합니다.

### 답변을 지속 지식으로 승격
쿼리 답변은 저장되지 않습니다. 보존하려면 `02_Wiki/`(사람이 큐레이션하는 공간)로
승격하세요 — 플러그인의 승격 동작 또는 MCP `curator_promote_insight` 도구를 사용합니다.
승격은 `02_Wiki/`에만 쓰며, 소스 진실(`03_Notes/`, `04_Resources/`)은 건드리지 않습니다.

### 지식 그래프 정제
지식 그래프(L2 Atom → L3 Concept → 공유 L4 Synthesis)를 정제하려면:
```bash
wiki build
```

> [!TIP]
> **한 번에 업데이트**: `wiki add`, `wiki build`, `wiki sync`를 일일이 실행하는
> 대신 `wiki update` 하나로 전체 파이프라인(디스커버리 → L1 → L2/L3 → 벡터
> 임베딩 → 검증)을 동기적으로 한 번에 처리할 수 있습니다.

---

## 🔄 피드백 루프 및 무결성 검토 (HITL & Sync)

지식은 대화와 수정을 통해 점진적으로 완성됩니다.

1.  **합성 (Synthesis)**: 워크스페이스에서 에이전트와 대화하며 새로운 통찰을 도출합니다.
2.  **피드백 및 수정**: 대화 중 사전 지식의 오류를 발견하면 MCP 도구로 분류된 correction proposal을 제출합니다. proposal은 생성 노드를 자동으로 덮어쓰지 않습니다.
3.  **무결성 검토**: 승인된 후속 변경은 별도의 검토 workflow로 적용하고, `wiki sync`로 구조적·논리적 무결성을 검증합니다.
4.  **승격 (Promotion)**: 확정된 통찰은 `02_Wiki/`로 이동시켜 인간이 읽기 좋은 위키로 승격시킵니다.
5.  **순환 (Loop)**: 승격된 위키 내용은 다음 주기에서 새로운 소스로 인식되어 다시 시스템에 흡수됩니다.

이러한 선순환 구조는 지식이 단순히 저장되는 것에 그치지 않고, 끊임없는 상호작용과 검증을 통해 더 높은 수준의 통찰로 진화하게 만듭니다.

---

## 🧾 클레임 수준 지지(Support) 및 컴파일러 무결성 (v0.8.0)

v0.8.0부터 모든 source-supported 지식 유닛(L2 클레임)은 단순히 실재하는
span id를 인용한다는 이유만으로 신뢰되지 않고, 명시적인 **support status**를
갖습니다:

| `support_status` | 의미 |
| :--- | :--- |
| `verified` | 검증된 최소 지지 레코드가 1개 이상 존재하고, 그 evidence hash가 현재 소스 텍스트와 일치합니다. |
| `unchecked` | v0.8.0 이전에 생성되었거나 아직 검증되지 않았습니다. 사용자에게는 보이지만, 재검증 전까지 새 컴파일에는 투입되지 않습니다. |
| `failed` | 검증 결과 인용된 span이 실제로 클레임을 지지하지 않는 것으로 판명되었습니다. 하위 지식에서 제외됩니다. |
| `stale` | 검증 이후 클레임의 근거가 되는 소스 텍스트가 변경되었습니다. 재검증 전까지 제외됩니다. |

실제 사용에서 의미하는 바:

- **업그레이드는 안전하고 정직합니다**: v0.8.0 마이그레이션은 기존 클레임을
  모두 `unchecked`로 표시합니다 — 어떤 것도 조용히 "verified"로 승격되지
  않습니다. 일반적인 `wiki build` 실행이 새 계약에 따라 재컴파일합니다.
- **수식은 1급 시민입니다**: 핵심 수식에 의존하는 클레임은 수식을 본문에
  온전히 유지하거나, 정확한 수식 증거를 링크합니다. 소스 추출에 존재하는
  수식을 증류(distillation) 과정에서 조용히 누락시키는 것은 요약 선택이
  아니라 결함으로 취급됩니다.
- **부분 빌드는 없습니다**: 중간에 실패한 컴파일은 아무것도 발행하지
  않습니다 — 기존 지식, 프로젝션, 검색 인덱스는 그대로 서비스를 계속합니다.
  큰 PDF나 긴 Markdown 파일은 L2가 실패한 추출 배치를 더 작은 source-span
  보존 배치로 다시 시도한 뒤에 포기합니다. 이때 L2는 active model이
  선언한 안전한 chunk budget을 사용하며, CLI model이 그 budget을 property로
  노출하는 경우도 동일하게 처리합니다. 좁힌 배치 중 하나라도 검증에 계속
  실패하거나 provider가 capacity/timeout 오류를 내면, 그 배치에서 즉시
  멈추고 실패한 prompt trace를 기록하며, 그 실행에서 새로 추출한 L2 unit은
  발행하지 않습니다.
  변경 없는 빌드를 다시 실행해도 중복이나 변형이 생기지 않습니다.
- **생성된 L2는 영어로 유지됩니다**: `wiki build`는 생성된 Atom 이름과
  statement를 프로그램으로 검증합니다. 모델이 생성 L2 필드에 한국어 등
  비영어를 쓰면 한 번 repair retry를 수행하고, 그래도 실패하면 해당 Atom을
  발행하지 않고 L2를 실패 상태로 표시합니다.
- **소스 편집은 스스로 정리합니다**: 소스를 편집/삭제/분할하면 근거를 잃은
  클레임은 retire 처리되어(감사 가능하게 보존되지만 답변에는 더 이상
  나타나지 않음) 오래된 중복이 남지 않습니다.
- **`wiki lint`가 전부 감사합니다**: lint에 Compiler Integrity 섹션이 추가되어
  unsupported/failed/stale 클레임, evidence hash 불일치, formula status
  문제를 보고하고, 릴리스를 막아야 하는 발견 사항이 있으면 0이 아닌 종료
  코드로 종료합니다.

---

## 🧭 에이전트 컨텍스트 팩 (Plan F target)

자체 추론을 수행하는 에이전트는 답변 대신 `curator_fetch_context`의 normalized
context pack을 사용할 수 있습니다. 이 pack은 하나의 `QTR-*` root trace, 여기에
연결된 하나의 `RTR-*` retrieval execution, 재현 가능한 snapshot id, 명시적인
budget accounting, source locator, omission reason, expansion/verification handle을
포함합니다. 향후 `wiki query` 합성은 별도의 retrieval path를 다시 실행하지 않고
동일한 pack 위에서만 수행됩니다.

---

## 🕸️ 그래프 품질 (v0.9.0)

v0.9.0은 검증된 클레임을 신뢰할 수 있는 지식 그래프로 바꿉니다. 두 이름이
실제로 같은 대상인지를 구별하고, 관계가 얼마나 독립적으로 지지되는지를
추적하며, 정확한 클레임에 근거한 커뮤니티 요약을 만듭니다 (스펙: SCHEMA.md §21,
SYSTEM_BEHAVIOR.md §27).

실제 사용에서 의미하는 바:

- **병합은 신중하고 가역적입니다**: 시스템은 이름이 비슷하다는 이유만으로 두
  엔티티를 조용히 합치지 않습니다. 동의어와 약어는 안전 검사를 통과한 뒤에만
  병합되고, 모호한 이름(동음이의어)은 결정 전까지 분리해 둡니다. 수락된 병합은
  원본 엔티티와 모든 관계를 복원하며 정확히 되돌릴 수 있습니다.
- **지지는 정직하게 셉니다**: 같은 소스의 복사본 10개가 뒷받침하는 관계는 10번이
  아니라 1번의 독립 확인으로 셉니다. 빌드를 다시 실행하면 지지를 덮어쓰지 않고
  진짜 지지를 누적합니다.
- **커뮤니티 보고서에는 교차 확증이 필요합니다 (독립 소스 ≥2개)**: 관계는 서로
  **독립적인 소스 2개**가 그것을 주장할 때 비로소 *active* 상태가 되어 커뮤니티
  보고서의 근거가 될 수 있습니다. 단 하나의 소스에서만 발견된 클레임은(그 소스
  안에서 몇 번을 다시 언급하더라도) 확증되지 않은 상태로 남아 아직 커뮤니티를
  구성하지 않습니다. 따라서 주제마다 소스가 하나뿐인 Vault에서는, 두 번째 독립
  소스가 같은 관계를 확증하기 전까지 커뮤니티 보고서가 거의 또는 전혀 생성되지
  않습니다. 이는 의도된 동작입니다 — Plan C 보고서는 소스 간 교차 확증된 사실에만
  근거합니다.
- **약한 엣지는 숨기지 않고 격리합니다**: self-loop, 모순, 지지 없는 엣지,
  위험한 "다리(bridge)" 링크는 사유와 재admission 조건과 함께 따로 보관되어
  커뮤니티 요약을 조용히 좌우하지 않습니다. 완전히 지지된 관계만 커뮤니티를
  구성합니다.
- **안정적이고 설명 가능한 커뮤니티**: 같은 그래프는 매번 같은 커뮤니티 계층을
  만듭니다. 커뮤니티 보고서는 정확한 지지 클레임을 인용하며, 기존 "클러스터
  전체 요약" 폴백은 사라지고, 입력이 바뀐 오래된 보고서는 retire 후
  재생성됩니다.
- **`wiki lint`가 그래프도 감사합니다**: lint에 Graph Quality 섹션이 추가되어
  병합되어 사라진 엔티티 참조, 지지 없는 active 관계, 해소되지 않은 엔드포인트,
  근거 없는 보고서 발견 사항, 동음이의어 오병합을 표시하고, 릴리스를 막아야
  하는 발견 사항이 있으면 0이 아닌 종료 코드로 종료합니다.

---

## 🧑‍🎨 페르소나 설정

Incurator에는 두 가지 페르소나 레이어가 있으며, 각각 다른 수준에서 동작합니다.

### Curator 페르소나 — Vault 수준

`wiki init` 실행 시 짧은 인터뷰를 통해 설정됩니다. wizard는 첫 질문을 바로 표시하고, 각 질문이 단일 선택인지 다중 선택인지 표시하며, verification source와 artifact type 같은 다중 선택 질문에서는 `1,4`처럼 쉼표로 구분한 번호를 받을 수 있습니다. 마지막 persona JSON이 저장되면 인터뷰는 즉시 종료됩니다. 결과는 `.curator/settings.yml`에 저장되며, `wiki sync`와 `wiki query` 전반에 전역으로 적용됩니다.

```bash
wiki persona              # 현재 Curator 페르소나 확인
wiki persona update       # 인터뷰를 다시 실행하여 재설정
```

인터뷰를 건너뛰면 기본 STEM 페르소나가 적용됩니다.

> [!IMPORTANT]
> **Curator 페르소나는 Vault의 전문가 정체성을 정의합니다.** 근본적으로 다른 전문가 관점(예: STEM 연구자 vs. 요리사)이 필요하다면, 페르소나를 바꾸는 것이 아니라 새로운 Vault를 만들어야 합니다.

### Artist 페르소나 — 워크스페이스 수준

`wiki workspace init` 마법사가 자동으로 생성하며, `curate.yml`의 `persona:` 블록에 저장됩니다. 이 프로젝트에서만 Curator 페르소나를 덮어써, `output_intent`, 신뢰도 임계값, disambiguation 키워드를 워크스페이스별로 세밀하게 조정합니다.

```bash
wiki persona update --workspace <name>   # 인터뷰로 Artist 페르소나 재설정
```

또는 채팅 세션에서 `curator_update_artist_persona` MCP 툴로 업데이트할 수 있습니다.

→ 전체 `persona:` 필드 레퍼런스는 [위의 `curate.yml` 섹션](#curateyml--워크스페이스-설정-레퍼런스)을 참고하세요.

---

## 🐙 Git 연동

Incurator는 이미 Git으로 관리 중인 vault를 Obsidian 안에서 점검하고,
일상적인 Git 워크플로우를 sidechat으로 실행할 수 있게 합니다. 이 기능은
이미 Git을 쓰고 있고 scheduled commit도 따로 운용하는 vault를 전제로 합니다.
기존 로컬 `git`만 사용하며 **GitHub CLI(`gh`) 의존성이 없고** 플러그인이 GitHub
token을 저장하지도 않습니다. (HTTPS push 인증이 필요하면 플러그인 밖, 평소 쓰는
git credential helper가 처리합니다.) 플러그인은 수동 Commit/Push 버튼 묶음을
추가하지 않습니다.

### 대화형 Git 동기화 (Sidechat)

Sidechat은 현재 vault에 대해 결정적인 backend Git 명령을 실행할 수 있습니다.

- **상태 확인**: *"푸시되지 않은 변경 사항이 있나요?"*, *"GitHub 상태
  어때?"*라고 물으면 branch, upstream, ahead/behind, dirty file,
  `.curator/` ignore 경고를 요약합니다.
- **Push**: *"push해줘"*, *"이 vault GitHub에 올려줘"*라고 말하면 backend가
  `git push`를 실행합니다. 단, upstream이 있고 branch가 behind/diverged 상태가
  아닐 때만 실행합니다.
- **선택 텍스트 히스토리**: Markdown 텍스트를 선택하고 *"이 내용 예전에
  어떻게 바뀌었는지 히스토리 찾아줘"*라고 물으면, backend가 현재 Markdown
  파일에서 선택 텍스트 또는 정규화된 excerpt를 git history에서 찾아 관련 commit과
  제한된 patch snippet을 반환합니다.
- **파일 히스토리**: 현재 Markdown 파일의 history를 물으면 최근 commit과 요약을
  보여줍니다.

scheduled commit job은 이 흐름과 같이 사용할 수 있습니다. scheduler가 이미 commit을
만든다면, Incurator sidechat은 push 전에 commit을 새로 만들 필요가 없습니다. 명시적
요청을 위한 guarded commit backend primitive는 있을 수 있지만, 기본 대화형 워크플로우는
status/history/push입니다.

> [!TIP]
> **.gitignore 권장 사항**
> 무엇이 추적되는지는 Git이 결정합니다. Incurator는 `.gitignore` 기준으로 파일을
> stage하거나 검사하며, ignored file은 추가하지 않습니다. `.curator/`는 생성된
> SQLite DB와 vector/search index를 담으므로 ignore하는 것이 좋습니다. `.curator/`가
> ignore되어 있지 않으면 Git status 결과가 경고만 표시하고 `.gitignore`를 조용히
> 수정하지 않습니다.

<a id="cli-reference"></a>

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
| `wiki update` | **한 번에 처리하는 파이프라인**: `add` → `build --wait` → 벡터 임베딩 → `sync`를 동기적으로 실행하여 vault 전체를 한 명령으로 최신화합니다. `--force`로 기존 레이어를 재빌드하고 `--no-sync`로 마지막 검증을 건너뜁니다. | 평소 "그냥 최신으로 맞춰줘" 명령 |
| `wiki add <file>` | 소스를 등록하고 L1 Context 레코드를 데이터베이스에 즉시 생성합니다 (구조 기반, LLM 없음). | 새로운 정보를 추가할 때 |
| `wiki build` | 등록된 L1 Context에서 L2 Atom + L3 Concept를 데이터베이스 레코드로 추출/컴파일합니다. 기본은 백그라운드 워커에 큐잉 후 자동으로 데몬 프로세스를 분리 실행하며, `--wait`는 즉시 동기 실행합니다. Build는 완료 시 **항상 벡터 임베딩을 (재)생성**합니다 — atom 변경이 없거나 큐가 비어 있어도 실행되므로, 별도의 `wiki reindex --embed` 없이 검색이 벡터까지 수렴합니다. (큐는 내부적으로 drain되며, `jobs` 명령 그룹은 백그라운드 워커용으로 남아 있지만 `wiki --help`에서는 숨겨집니다.) | 지식 그래프 심층 구축 시 |
| `wiki source ls` | 등록된 소스 목록을 확인합니다. | 수집된 데이터 현황 파악 시 |
| `wiki source show <id>` | 특정 소스의 상세 정보와 처리 상태를 확인합니다. | 소스 오류 진단 시 |
| `wiki source rm <id>` | 원본 파일은 보존한 채 소스 등록과 생성된 파생 레코드를 제거합니다. vault 소스 파일까지 지우려면 `--delete-file`을 명시합니다. | 잘못된 소스를 제거할 때 |
| `wiki source retry <id>` | aggregate 오류뿐 아니라 L1/L2/L3/L4 layer 오류가 있는 소스를 재처리합니다. | 소스 처리 실패 후 재시도 시 |

### 2-1. 설정 및 LLM 백엔드 관리

| 명령어 | 설명 |
| :--- | :--- |
| `wiki config provider` | LLM 백엔드 (Ollama / Claude Code / Antigravity / Codex / DeepSeek) 와 모델을 대화형으로 설정합니다. |
| `wiki config models list` | 현재 백엔드에서 사용 가능한 모델 목록을 표시합니다. |
| `wiki config models use <tag>` | 사용할 모델을 직접 지정합니다. |
| `wiki models ensure` | 로컬 검색 모델 의존성과 GGUF 파일을 설치/갱신합니다. `setup.sh`는 `INCURATOR_SKIP_MODELS=1`이 설정되지 않은 한 이 명령을 자동 실행합니다. |
| `wiki models status` | 로컬 검색 모델 상태, 캐시 경로, 의존성 상태를 JSON으로 표시합니다. |
| `wiki config get <key>` | 특정 설정 값을 조회합니다. (예: `wiki config get llm.primary`) |
| `wiki config set <key> <value>` | 특정 설정 값을 변경합니다. `llm.*`, `search.*`, `external.*` 같은 기기별 key는 `.cache/config/config.yml`에 기록합니다. `--local`은 `.curator/settings.yml`에 속하는 portable vault-scoped key에만 사용하세요. |

`wiki config provider` 또는 project-scoped `wiki config set --local` 실행 후 CLI는 플러그인 dashboard runtime snapshot을 즉시 갱신하려고 시도합니다. 예상 가능한 로컬 실패(예: `.curator/runtime/`에 쓸 수 없거나, 실행 중인 플러그인이 `state.sqlite`를 잠시 잠금, 또는 `config set --local` 중 병합된 config를 parse할 수 없음)가 발생해도 설정 변경 자체는 성공하며, CLI는 경고를 출력합니다. dashboard는 이후 다시 refresh할 수 있습니다.

### 3. 고도화 및 최적화 (Curation)
| 명령어 | 설명 | 사용 시점 |
| :--- | :--- | :--- |
| `wiki build` | L2 Atom, L3 Concept, 공유 L4 Synthesis 레이어를 정제합니다. | 지식 그래프 구축/갱신 |
| `wiki sync` | 무결성 검증 및 자가 치유를 수행합니다. | 노드 수정 후 일관성 회복 시 |
| `wiki sync --reemit` | DB 레코드에서 파생 L2/L3/L4 마크다운 projection(ATM/CON/SYN)을 재생성하고 DB-native search row를 갱신합니다. | DB 레벨 정정 후 projection 갱신 시 |
| `wiki reindex` | 권위 레코드에서 DB-native 검색 인덱스(FTS5 + chunk)를 재구축합니다. `--embed`를 추가하면 chunk 벡터 임베딩도 (재)생성합니다. 평상시에는 `wiki build`가 이미 자동으로 임베딩하므로, `--embed`는 주로 모델/임베더 변경 후의 수동 복구 경로입니다. | 모델/설정 변경 후, 또는 검색이 어긋날 때 |

> **v0.3.1**: 고정 staging 명령은 제거되었습니다. L4는 이제 공유 **Synthesis**
> 레이어(‎`wiki build`가 자동 생성)이며, 큐레이션은 쿼리 시점의 동적 렌즈(`wiki query`)입니다.
> 정정은 생성된 L4 파일 편집이 아니라 MCP
> `curator_propose_correction` 도구로 전달합니다.

### 4. 지식 활용 (Utilization)
| 명령어 | 설명 | 사용 시점 |
| :--- | :--- | :--- |
| `wiki query "..."` | 질문에 대한 정제된 답변을 얻습니다. | 지식을 활용한 답변 필요 시 |
| `wiki query "..." --route explore` | v0.3.2 큐레이션-네이티브 오케스트레이터(DB 그래프 + DB-native hybrid search)로 라우팅하고 쿼리 트레이스를 남깁니다. | 연결 발견, 라우트 지정 |
| `wiki inspect synthesis <SYN-…>` | synthesis node의 L4→L1 근거 체인을 내보냅니다. machine-readable 출력이 필요하면 `--json`을 추가합니다. | 생성된 synthesis가 왜 존재하는지 증명할 때 |
| `wiki inspect answer <QTR-…>` | 기록된 query trace 뒤의 근거 체인을 내보냅니다. machine-readable 출력이 필요하면 `--json`을 추가합니다. 오케스트레이션된 쿼리는 retrieval trace를 포함한 하나의 authoritative QTR을 저장합니다. | Sources & Trace의 답변을 감사할 때 |
| `wiki workspace init` | 워크스페이스를 초기화합니다. | 새 프로젝트 시작 시 |

#### v0.3.2 큐레이션-네이티브 쿼리 라우트

`wiki query "..." --route <route>` 는 큐레이션-네이티브 `QueryOrchestrator`로
답합니다. 라우트:

- `auto` — 오케스트레이터가 선택 (결정적 우선).
- `local` — source span 기반 정밀 엔티티/사실 답변.
- `global` — 공유 L4 Synthesis 노드를 앞세우고 커뮤니티 리포트로 뒷받침하는 광역 종합.
- `explore` — 연결(메모리 경로) 발견 + 잠정 인사이트 후보.
- `source-section` — 특정 원본의 span으로 범위 한정.

쿼리는 **세션리스**입니다: 답변 + `QTR-` 트레이스를 반환하며 vault 파일을 쓰지
않습니다. 지속 아티팩트는 `02_Wiki/`로의 명시적 승격을 통해서만 생깁니다.
모든 orchestrator query는 나중에 `wiki inspect answer <QTR-…>`로 감사할 수 있도록
`QTR-` trace를 지속 저장합니다.

`--route`가 없으면 `auto`가 실행됩니다. v0.3.2 검색은 DB-native입니다:
FTS5 lexical retrieval, chunk-level vector, typed query expansion(`lex`/`vec`/
`hyde`), RRF, best chunk에 대한 configured reranking을 사용합니다.
`--mode`(hybrid|lex|vec)는 lower-level retrieval mode이며, `--route`와는 별개의
축입니다.

Tier-2 LLM/HyDE query expansion은 기본적으로 recovery mechanism으로 켜져
있습니다. Incurator는 먼저 raw lexical/vector confidence를 확인한 뒤 lexical hit이
부족하거나 vector confidence가 낮을 때만 configured expansion을 사용합니다. 그래서
이미 확실한 검색 순위는 흔들지 않고, paraphrase가 심한 miss만 회복합니다.

### 4-1. 프롬프트 & 인사이트 (v0.3.1)

| 명령어 | 설명 |
| :--- | :--- |
| `wiki prompt list [--family F]` | 등록된 프롬프트 계약(id, 버전, 패밀리, 목적)을 나열합니다. |
| `wiki prompt show <PROMPT_ID>` | 프롬프트의 템플릿, 검증자, 출력 모델을 표시합니다. |
| `wiki prompt trace <PTR-…>` | 기록된 프롬프트 실행(모델, 검증자 상태, 해시)을 검사합니다. |
| `wiki prompt eval` | 오프라인 프롬프트 평가 픽스처를 실행합니다(LLM 불필요). |
| `wiki inspect synthesis <SYN-…>` | L4 Synthesis node 하나의 read-only audit report를 검사합니다. community report, graph entity/relation, source span, prompt trace, warning을 포함합니다. |
| `wiki inspect report <REP-…>` | L3 community report 하나의 source support를 검사합니다. |
| `wiki inspect answer <QTR-…>` | query answer 하나의 지속 저장된 route, 선택 근거, prompt trace, warning을 검사합니다. |
| `wiki insight list [--workspace P] [--status pending]` | 잠정 인사이트 후보를 나열합니다. |
| `wiki insight show <INS-…>` | 인사이트 후보 하나를 표시합니다. |
| `wiki insight promote <INS-…>` | 후보를 `02_Wiki/`의 영구 노트로 승격합니다(명시적·사람 승인). |

인사이트 후보는 **잠정적이며 사람이 검증한 진실이 아닙니다.** 승격은 `02_Wiki/`에만
기록하고 원본 폴더는 절대 수정하지 않습니다. 동일 기능은 MCP로 외부 에이전트에도
제공됩니다 — [MCP 사용 가이드](./MCP_USER_GUIDE_KR.md) §3.6 참고.

### 5. 개발자 전용 도구 (Developer Only)
| 명령어 | 설명 | 사용 시점 |
| :--- | :--- | :--- |
| `wiki testbed init` | 테스트용 가상 보관소(`testbed/`)를 구축합니다. | 새로운 기능을 안전하게 검증하고 싶을 때 |
| `wiki testbed list` | 사용 가능한 테스트 시나리오 목록을 확인합니다. | 검증할 시나리오를 선택할 때 |

> [!CAUTION]
> **테스트 베드 주의사항**: 위 명령어들은 실제 지식 베이스가 아닌 개발용 임시 저장소를 다룹니다. 일반적인 지식 관리나 실제 프로젝트 수행 중에는 사용하지 마십시오.

---

## 🔄 기기 간 지식 동기화 (`wiki db`)

Incurator는 모든 지식을 `.curator/state.sqlite`에 저장합니다. SQLite 파일은 Syncthing, iCloud, Dropbox 같은 파일 동기화 도구로는 안전하게 병합할 수 없으므로, `wiki db` 명령어를 통해 JSONL 기반 내보내기/가져오기 파이프라인을 제공합니다.

### 동작 방식

1. **내보내기**: 기기 A에서 지식 베이스를 내보내면 `.jsonl` 파일이 생성됩니다.
2. **전송**: 파일을 기기 B로 전달합니다 (scp, AirDrop, Syncthing, USB 등).
3. **가져오기**: 기기 B에서 가져오기 실행 → 최신 레코드 우선(LWW) 병합, 삭제된 레코드는 Tombstone으로 전파, `wiki reindex` 자동 실행.

### `wiki db export`

```bash
wiki db export                              # .curator/export-YYYYMMDD.jsonl로 내보내기
wiki db export --out ~/Desktop/kb.jsonl     # 출력 경로 지정
wiki db export --since 2026-01-01T00:00:00Z # 이후 변경된 레코드만 증분 내보내기
wiki db export --compress                   # gzip 압축 (.jsonl.gz)
```

### `wiki db import`

```bash
wiki db import ~/Desktop/kb.jsonl          # 가져오기 후 자동 reindex
wiki db import ~/Desktop/kb.jsonl --dry-run # 실제 변경 없이 미리 보기
wiki db import ~/Desktop/kb.jsonl --skip-reindex  # reindex 없이 가져오기만
```

> [!NOTE]
> 기기 로컬 데이터(벡터 임베딩, 백그라운드 잡 상태)는 내보내기 파일에 **절대 포함되지 않습니다**. 가져오기 후 `wiki reindex`가 자동으로 로컬 검색 인덱스를 재구축합니다.

### `wiki db autosync` — Syncthing 기반 자동 동기화

이미 vault 폴더를 **Syncthing**으로 동기화하고 있다면, `wiki db autosync`가 위의 수동 내보내기/가져오기를 손댈 필요 없는 Zotero급 흐름으로 바꿔 줍니다.

```bash
wiki db autosync             # 피어 가져오기 + 충돌 병합 + 변경 시 자기 스냅샷 내보내기
wiki db autosync --dry-run   # 실제 변경 없이 미리 보기
```

기기 간 안전성을 보장하는 방식:

- **기기당 파일 1개.** 각 기기는 자기 `.curator/sync/dev-<id>.jsonl`만 쓰고 나머지는 읽기만 합니다. 두 기기가 같은 파일을 쓰지 않으므로 Syncthing이 쓰기-쓰기 충돌을 만들지 않습니다.
- **Last-Write-Wins 병합.** 레코드는 타임스탬프 기준으로 행 단위 병합되고, 삭제는 tombstone으로 전파됩니다. 두 기기에서 오프라인으로 각각 편집해도 모두 살아남으며 — 파일 통째 덮어쓰기는 없습니다.
- **무한 루프 없음** — 취약한 해시 가드 없이. 기기는 자기 파일을 가져오지 않고, 실제로 변경이 있을 때만 다시 내보냅니다.
- **Syncthing 충돌 파일**(`*.sync-conflict-*`)은 일반 피어로 가져와(항상 데이터 안전) `.curator/runtime/sync_conflicts/`에 보관됩니다.

`.curator/state.sqlite`와 `.curator/sync_state.json`은 기기 로컬로 유지되며(`.stignore` 제외), `.curator/sync/`의 JSONL 파일만 기기 간 이동합니다. Obsidian 플러그인은 `wiki db autosync`를 자동으로 실행해 줍니다 — 플러그인 가이드 참고.

**CLI 명령 후 자동 내보내기 (v0.30.0부터 기본 켜짐).** `auto_sync.enabled`의 기본값은 `true`입니다: 변경을 일으키는 모든 CLI 명령(`wiki add`, `wiki build`, `wiki sync`, `wiki update`)이 끝날 때 이 기기의 스냅샷을 기록하므로, Obsidian 플러그인이 꺼진 기기에서도 피어들이 항상 최신 지식을 받습니다. 끄려면 `.curator/settings.yml`에 `auto_sync.enabled: false`를 설정하세요. Syncthing이 없어도 내보내기는 무해한 로컬 파일일 뿐입니다.

> [!WARNING]
> v0.30.0 이전에는 이 내보내기가 opt-in이었고 **오직** `wiki update`에서만 동작했습니다. `wiki add`/`build`로 수집하는 기기(또는 플러그인이 꺼진 기기)는 조용히 내보내기를 건너뛰었고, 다른 기기는 오래된 스냅샷에 수렴했습니다 — 전형적인 증상이 다른 기기의 대시보드에 예전의 더 작은 소스 개수가 표시되는 것입니다. 이제 `wiki db autosync --dry-run`이 내보내기 대기 여부(`would_export`)를 보고하므로 오래된 스냅샷을 한눈에 알 수 있습니다.

---

## 🧩 설정 관리 (Configuration)

Incurator는 YAML 파일을 직접 수정하지 않아도 `wiki config` 명령어를 통해 설정을 안전하고 편리하게 관리할 수 있습니다. `llm`, `search`, `external` 같은 기기별 block은 `.cache/config/config.yml`에 저장되고, portable vault 동작은 `.curator/settings.yml`에 남습니다.

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

선택한 강도는 `.curator/settings.yml` 의 `llm.primary_effort` / `llm.fallback_effort` 에 저장되며, 비워 두면 각 CLI의 기본 강도를 사용합니다.

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

### 2-1. 검색 모델 준비 (`wiki models`)
DB-native search는 채팅/큐레이션 LLM과 별도의 로컬 검색 모델을 사용합니다.
기본값은 chunk embedding용 `llama-cpp::qwen3-embedding-0.6b`와 answer-path
reranking용 `llama-cpp::qwen3-reranker-0.6b`입니다. `wiki models ensure`는
설정된 GGUF를 `~/.cache/incurator/models/`에 다운로드하고, 필요한 경우
`llama-cpp-python`을 설치하며, vault가 있을 때는 vault별 모델 경로를
설정에 기록합니다. `wiki models ensure --smoke`는 관련 passage가 무관한
passage보다 높게 ranking되는지 확인하는 작은 live sanity check도 실행합니다.
모델이 없더라도 검색은 FTS5/RRF degraded mode로 계속 사용할 수 있습니다.

보통은 직접 실행할 일이 없습니다: `setup.sh`가 설치/업데이트 시 준비하고,
Obsidian 대시보드의 **System** 카드가 현재 embed/reranker 모델 정체성과 health를
보여줍니다 — **Embed model** / **Reranker** 행을 클릭하면 재준비할 수 있습니다
(`wiki plugin models refresh`). 모델이 정상이 된 뒤 벡터 인덱스를 (재)구축하려면
`wiki reindex --embed`를 실행합니다(plain `wiki reindex`는 FTS5/chunks만
다시 만듭니다). backend만 수동 복구해야 한다면
`uv pip install -e './backend[rerank]'`를 실행하세요. 저장소 루트에서
`uv pip install -e .`를 실행하지 마세요. Python 프로젝트는 `backend/` 아래에
있습니다.

### 3. 상태 확인 (`wiki status`)
보관소의 건강 상태와 AI 엔진의 가동 현황을 입체적으로 진단하는 종합 대시보드입니다. 시스템 운영 중 의문이 생긴다면 가장 먼저 확인해야 할 명령어입니다.

```bash
wiki status
```

최신 sync report에 확인할 항목이 있으면 `wiki status`가 review 세부사항을 표시할지 물어볼 수 있습니다. 이 세부사항은 점검하거나 수리해야 할 무결성 진단 결과이며, status 명령 자체가 실패했다는 뜻은 아닙니다.
state DB 파일은 존재하지만 기본 테이블이 빠진 상태라면, 이제 `wiki status`가 통계를 읽기 전에 스키마를 자동으로 보정합니다.

`--json`을 붙이면 포맷된 표 대신 기계 판독용 라이브 페이로드(`{status, sources, jobs}`)를 출력합니다:

```bash
wiki status --json
```

Obsidian 플러그인 대시보드는 이 라이브 `--json` 출력을 직접 읽으므로, 캐시된 스냅샷 파일이 아니라 항상 현재 백엔드 상태를 반영합니다.

### 3-1. 생성 상태 초기화 (`wiki reset`)

```bash
wiki reset
wiki reset --force
```

`.curator/settings.yml`과 vault의 source folder는 보존하면서 생성된 Curator
상태를 초기화합니다. tracking database (DB 내장 검색 인덱스 포함), generated Collections,
dashboard/index/overview/ledger/log 파일, sync report, transient staging 파일,
build trace canvas, device registry, sidechat session state를 제거합니다. 오래된
generated state, device metadata, chat context 때문에 backend와 plugin 상태가
어긋날 때 사용합니다.

이 명령어는 크게 세 가지 영역의 데이터를 실시간으로 집계하여 출력합니다. 각 항목의 의미와 활용 방법은 다음과 같습니다:

#### ⚙️ 구성 설정 (Config)
시스템의 '두뇌'와 '눈'이 제대로 세팅되었는지 확인합니다.
-   **Primary / Fallback 모델**: 현재 지식 추출과 합성을 담당하는 주력 LLM과 비상용 LLM을 보여줍니다. 의도한 모델이 활성화되어 있는지 확인하세요.
-   **Reranking (리랭킹)**: 검색 결과의 정밀도를 높이는 2차 검증 프로세스의 활성화 여부입니다. 고품질 답변이 필요하다면 `on` 상태여야 합니다.
-   **Query expansion**: recovery-only Tier-2 expansion을 실행할 수 있는지 표시합니다. 사용할 수 없어도 deterministic lexical/vector expansion은 계속 실행되고 trace에 degraded stage가 기록됩니다.
-   **Search readiness**: DB-native FTS5 준비 상태, embedded chunk 수, vector readiness, provider/model, degraded stage를 표시합니다.
-   **Search index degradation**: embedding, query expansion, reranking이 사용할 수 없더라도 lexical FTS5 search는 계속 작동합니다. Query trace에는 `vector_unavailable`, `query_expander_unavailable`, `reranker_unavailable` 같은 경고가 기록됩니다. provider/model 설정을 고친 뒤 `wiki reindex`로 chunk와 embedding을 다시 빌드하세요.

#### 📂 지식 원천 현황 (Sources)
원본 데이터가 지식화되는 '파이프라인의 입구'를 점검합니다.
-   **Raw source files**: 보관소 폴더 내에 물리적으로 존재하는 파일의 총개수입니다.
-   **Sources summarized (L1)**: `l1_status=done`인 소스 수입니다. `wiki add`는 LLM 없이 구조 기반 L1 Context를 즉시 만듭니다. L1 page에는 검색용 영어 source guide와 크기 인식 source sections가 들어갑니다. 작은/중간 문서는 원문을 inline하고, 대형 문서는 preview와 marker만 두며 정확한 원문 증거는 원본 파일에서 on-demand로 읽습니다. L2/L3 추출은 별도 단계로, `wiki build`로 실행합니다 (작업을 큐잉하고 자동으로 백그라운드 데몬을 분리 실행하여 비동기 처리하며, `--wait`는 동기 실행).
-   **Ingest runs**: 지금까지 수행된 총 수집 횟수입니다. 이 수치가 높을수록 지식 베이스가 빈번하게 업데이트되었음을 의미합니다.

#### 🧠 지식 밀도 (Collections)
파이프라인의 각 단계별 처리 현황을 나타냅니다. L1은 즉시 생성되고, L2·L3와 공유 L4 Synthesis 레이어는 MCP background worker, `wiki jobs run`, 또는 `wiki build`로 처리됩니다. worker가 claim하기 전의 queued job은 `wiki jobs cancel <id>`로 취소하고, 완료/실패/취소된 job은 `wiki jobs rerun <id>`로 다시 queue에 넣을 수 있습니다. 이미 queued 상태인 job에 `wiki jobs rerun <id>`를 실행하면 중복을 만들지 않고 성공 no-op으로 처리됩니다.

-   **L1 Contexts**: DB에서 `l1_status=done`인 소스 개수입니다.
-   **L2 Atoms**: DB에서 실제 serving되는 원자적 사실 레코드 개수입니다.
-   **Fallback Atoms**: DB에 임시로 저장된 낮은 신뢰도의 Atom 레코드 개수입니다.
-   **L3 Concepts**: L2 Atom에서 형성된 live 교차 소스 community report 개수입니다.
-   **L4 Synthesis**: 현재 community report에서 증류된 공유 코퍼스 전역 교차 인사이트입니다(DB `synthesis_nodes`, `04_Synthesis/SYN-*.md`로 투영).

이 수치는 authoritative DB serving record에서 계산합니다.
`.curator/Collections/` 파일은 폐기 가능한 projection이므로 pipeline truth로
집계하지 않습니다. Source span에 근거한 live report가 있어야 L3-ready이며,
오류 없이 끝났더라도 eligible report가 없으면 `skipped`로 표시합니다.
`wiki sync --reemit`은 orphan CTX projection을 제거하고 현재 DB에서 L2-L4
projection을 다시 만들며 source file은 수정하지 않습니다. 또한 기존 terminal
L3/L4 badge를 live report와 synthesis node에 맞춰 조정하여 구버전의 stale
`done` 값을 복구합니다.

> [!TIP]
> **파이프라인 현황 진단**: L4가 0이면 source의 L4 열을 확인하세요.
> `pending`은 build/worker가 아직 global L3/L4를 끝내지 않았다는 뜻이고,
> `skipped`는 build는 끝났지만 현재 corpus에 eligible community report/synthesis가
> 없다는 terminal 상태입니다. `wiki build`를 실행하거나 백그라운드 worker가 L3를
> 끝내도록 기다리는 것은 `pending`인 경우에만 필요합니다.

### 4. 외부 리소스 연동 (Zotero & Reference Mode)
Incurator는 Zotero 등의 외부 PDF 파일들을 보관소로 복사하지 않고 원본 그대로 참조(Reference Mode)할 수 있으며, 원할 경우 사용자가 승인한 `04_Resources/` 목적지로 안전하게 복사할 수도 있습니다.
- **설정**: 옵시디언 플러그인 설정의 "Zotero Library Path"를 입력하거나 터미널에서 `wiki config set external.zotero.path ~/Documents/Zotero` 명령을 사용하여 Zotero 루트 경로를 지정합니다.
- **Reference Mode**: Zotero 리소스는 content hash와
  `logical_source_id=zotero:<attachmentKey>`로 추적하고, 일반 external
  리소스는 `@<root_key>/<relative-path>`를 사용합니다. 절대경로는 durable
  state에 저장하지 않습니다.
- **Copy Import**: 파일을 vault 내부로 가져오는 경우에도 목적지는 `03_Notes/`가 아니라 `04_Resources/`입니다. 같은 이름의 파일을 덮어쓰지 않고, 동일 해시는 재사용하며, 충돌 시 suffix 또는 사용자 선택 목적지를 사용합니다.
- **Hash Drift와 자가 치유**: iPad 등에서 Apple Pencil로 PDF에 주석을 달면 내용 해시가 변경됩니다. 파일이 이동하거나 해시가 변경되어 연결이 끊어진 경우, 옵시디언 플러그인 UI를 통해 재연결(Re-bind)을 승인하면 backend가 고유 식별자(`logical_source_id`)를 기준으로 새로운 해시와 경로를 찾아 치유(Healing)합니다.

### 5. OS 환경별 경로 분리 (Platform-aware Config)
Linux와 macOS 환경을 번갈아 사용하는 경우, Syncthing 동기화로 인한 절대 경로 충돌을 방지하기 위해 플랫폼별 설정이 철저히 분리됩니다.
- **플러그인 설정**: 옵시디언 플러그인 설정 메뉴에서 `Linux Binary Path`와 `macOS Binary Path`를 각각 별도로 입력합니다. 에이전트는 실행 중인 운영체제(`process.platform`)에 맞춰 올바른 백엔드 실행 파일을 자동 호출합니다.
- **기기별 설정 (`.cache/config/config.yml`)**: Zotero 라이브러리 경로 등 기기 종속적인 로컬 설정은 Vault 내부가 아닌 저장소 루트의 `.cache/config/config.yml` 파일에서 관리됩니다. Vault-scoped 이식 가능 설정은 `.curator/settings.yml`에 저장됩니다.
