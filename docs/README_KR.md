# 🧠 Incurator (인큐레이터): 멀티 에이전트 워크스페이스를 위한 지식 컴파일러

[English](README.md) | **한국어**

**"노트 필기를 위한 Cursor, 옵시디언 안의 Ask Gemini"**

Incurator의 궁극적인 목표는 **노트 필기를 잘 하기 위한 (문헌을 읽고 인사이트를 뽑아내기 위한) 옵시디언 기반의 AI 노트 시스템**이 되는 것입니다. 

개발자들이 복잡한 코드베이스를 파악하기 위해 **Cursor**나 **Antigravity**를 사용하듯, Incurator는 방대한 지식과 노트를 이해하기 위한 고도화된 RAG/DAG 컴파일러(백엔드)와, 이를 활용해 사용자와 소통하는 옵시디언 익스텐션 사이드바(프론트엔드)로 구성됩니다. 옵시디언 내의 에이전트는 크롬의 **'Ask Gemini' 시스템을 미믹(Mimic)**하여, 당신이 현재 읽고 있는 문헌의 맥락을 완벽히 파악한 채 새로운 통찰의 합성을 돕습니다.

Incurator는 파편화된 데이터를 구조화된 **방향성 비순환 그래프(DAG)**로 변환하여, 지식을 유기적으로 배양(Incubate)하고 확장(Increment)할 수 있게 돕는 비용 효율적인 지식 시스템입니다.

> 이 시스템이 어떤 문제를 해결하려 하는지, 그리고 왜 이런 구조로 설계되었는지는 [프로젝트 철학](philosophy/ABOUT_KR.md)에서 다룹니다.

---

## 🏛️ 핵심 메타포: 큐레이터(Curator)와 아티스트(Artist)

대부분의 AI 지식 베이스는 LLM을 단순한 검색 엔진으로 취급하기 때문에 실패합니다. 우리는 이 과정을 두 가지 뚜렷한 역할로 분리했습니다.

### ⚙️ 큐레이터 (보관소의 관리자 / 지식 정제 엔진)
큐레이터는 **보관소(Vault)**에 상주하며 지식 정제를 담당하는 백그라운드 엔진입니다. 4계층 근거 사슬의 권위 상태는 `state.sqlite`에 저장하고, `.curator/Collections/` 마크다운은 DB에서 emit되는 폐기 가능한 점검 projection으로 사용합니다.
1.  **L1 Contexts**: source 구조, section/page locator, provenance.
2.  **L2 Atoms**: 더 이상 쪼개지지 않는 source-grounded 사실.
3.  **L3 Concepts**: 여러 source를 가로지르는 개념과 community report.
4.  **L4 Synthesis**: 코퍼스 전체에서 공유되는 `SYN-` 종합 근거.

### 🎨 아티스트 (워크스페이스의 주인 / 추론 에이전트 + 인간)
아티스트는 실제 작업실인 **워크스페이스(Workspace)**에 상주합니다. `curate.yml`의 KRS는 쿼리 시점의 동적 Curation lens를 편향합니다. 쿼리는 답변 또는 evidence pack과 trace를 반환하며 고정 Exhibition 파일을 쓰지 않습니다. 검토된 결과는 명시적 승격을 통해서만 `02_Wiki/`에 지속됩니다.

---

## 🌟 왜 이 시스템인가요?

Incurator는 대부분 지식의 닫힌 순환(수집 → 처리 → 활용 → 재입력)을 지향합니다. Incurator도 이 흐름을 따르는 Incurator지만, 두 가지 측면에서 다른 Incurator들과 차별화됩니다.

### 1. 맞춤형 지식 전달 (Specification-Driven Curation)

인간이 `curate.yml`로 프로젝트 목적과 필요 지식을 명시하면, 쿼리 시점의 Curation lens가 live graph에서 관련 근거를 선별하고 랭킹합니다. 워크스페이스별 고정 subset을 저장하지 않으므로 stale 전시물 없이 도메인 오염을 줄입니다.

### 2. 사전 지식 교정 (Prior Knowledge Correction)

인간과 에이전트가 사전 지식의 오류를 발견하면 correction proposal을 제출할 수 있습니다. 시스템은 source truth를 보호하면서 제안을 분류하고 영향받은 generated record를 식별하며, 실제 교정 적용은 별도의 검토 동작을 요구합니다. derived insight는 별도로 추적하며 명시적 승격 전에는 지속 인간 지식이 되지 않습니다.

### 3. 토큰 최적화 (AI를 위한 FinOps)
사전 지식을 요약·원자화하는 **단순 컴파일**은 비추론 모델에, 복잡한 계산이나 정교한 추론이 필요한 **창의적 합성**은 추론 모델에 맡기세요. 역할 분리로 지식 관리 비용을 획기적으로 낮춥니다.

### 4. AI와 인간을 위한 이원화 및 모노레포(Monorepo) 구조
Incurator는 파이썬 백엔드 데몬(`backend/`)과 Obsidian 플러그인 클라이언트(`plugin/`)를 **단일 리포지토리(Monorepo)**로 통합하여 제공합니다. 지식은 기계와 인간에게 각각 다른 형태로 존재할 때 가장 효율적입니다.
-   **AI 공간 (`.curator/`)**: `state.sqlite`가 단일 진실 공급원입니다. `.curator/Collections/`에는 점검용 CTX/ATM/CON/SYN 파생 projection이 있습니다.
-   **인간 공간 (`02_Wiki/`)**: 명시적으로 승격된 human-reviewed artifact만 지속되는 상설 공간입니다.
-   **클라이언트 공간 (`incurator-obsidian-agent`)**: 열린 PDF, split view, chat UI, provider 선택, import/rebind 승인 같은 사용자 상호작용을 담당합니다. 장기 source registry와 RAG provenance는 backend가 담당합니다.

### 5. 외부 리소스 무손실 통합 (Reference Mode & Hash Drift 방어)
Zotero와 같은 외부 레퍼런스 PDF 파일들을 보관소 내부로 강제 복사하여 대역폭을 낭비하지 않는 **Reference Mode**를 지원하는 방향으로 설계되어 있습니다. 사용자가 vault-managed copy를 원하면 `04_Resources/` 아래 목적지를 승인해 복사할 수 있고, 원본 위치를 유지하고 싶으면 외부 파일의 Content Hash와 logical source identity를 추적합니다. iPad의 Apple Pencil 필기로 인해 파일 해시가 변동(Hash Drift)되거나 물리적 파일 위치가 바뀌어도, 인간의 확인 절차를 거쳐 지식의 연결 고리를 안전하게 치유합니다.

### 6. 지식의 집약과 성장 (Concentration & Growth)
지식은 파편화되어 분산되어 있을 때가 아니라, **단일한 공간에 응집되어 있을 때** 비로소 진정으로 연결되고 성장(**Increment**)할 수 있습니다. Incurator는 흩어진 정보를 하나의 진실 공급원(Single Source of Truth)으로 모아, 지식이 서로 유기적으로 연결되고 더 높은 차원으로 합성될 수 있는 환경을 제공합니다. 

따라서 지식을 관리의 편의를 위해 여러 Vault로 나누는 것은 권장하지 않습니다. 하지만 지식을 대하는 **큐레이터의 페르소나(전문성)**가 근본적으로 달라야 하는 경우(예: STEM 전문 큐레이터 vs 요리 전문 큐레이터)에는 별도의 Vault를 운영하여 독립적인 지식 체계를 구축하는 것이 효과적입니다.

---

## 🛠️ 시작하기 (Getting Started)

### 📋 사전 준비 사항
- **필수 환경**: Python 3.10+, 터미널, 노트 편집기 (Obsidian 권장)
- **백엔드 계정**: 클라우드 모델(Antigravity, Claude 등) 사용 시 API 키 또는 구독 계정이 필요합니다.
- **자동화 안내**: Ollama(로컬 모델), Node.js(검색 엔진) 및 GitHub CLI(`gh`) 설치, 그리고 모노레포 백엔드 패키지와 플러그인 빌드는 루트 디렉토리의 `./setup.sh` 실행 시 한 번에 자동으로 처리됩니다.
- 상세 정보는 [사용자 가이드](guides/USER_GUIDE_KR.md)를 참조하세요.

### 🚀 빠른 시작
1.  **설치**: `./setup.sh` (백엔드 패키지, 플러그인 빌드, Ollama, Node.js, GitHub CLI 등을 한 번에 자동 통합 설치합니다.)
2.  **초기화**: `wiki init <path/to/your/obsidian-vault>`
    > **단일 보관소 원칙**: `wiki init`을 실행한 모든 폴더에는 전용 **Curator**가 상주하게 됩니다. Incurator는 한 번에 하나의 Curator만 실행할 수 있으므로, 지식의 연결성을 극대화하기 위해 모든 지식을 집약할 **단 하나의 메인 보관소(Vault)**를 운영하는 것을 강력히 권장합니다.
    > 
    > **예외 (페르소나 분리)**: 만약 지식을 관리하는 '관점'이나 '전문 페르소나'를 완전히 다르게 가져가고 싶다면(예: STEM 보관소 vs 요리 보관소) 별도의 Vault를 생성하세요. 각 Vault의 Curator는 자신만의 고유한 세계관으로 지식을 정제합니다.
3.  **페르소나 설정**: `wiki init` 중 인터뷰를 통해 지식 도메인을 설정합니다. 이후 `wiki persona update`로 언제든 재설정 가능합니다.
4.  **지식 등록 (요약 및 정제)**: `wiki add <file>`은 instant L1만 만들며, `wiki build`가 L2/L3를 queue에 넣거나 컴파일합니다. 플러그인의 명시적 Add Source 동작은 instant L1 등록과 L2/L3 queueing을 함께 수행합니다.
5.  **지식 활용 (검색)**: `wiki query "질문"` 또는 MCP 검색은 sessionless 답변/evidence pack과 trace를 반환합니다.

> [!NOTE]
> **개발자 전용 기능**: `wiki testbed` 명령어는 새로운 시나리오 검증 및 개발을 위한 도구입니다. 일반적인 지식 관리 상황에서는 사용하지 마십시오.

더 자세한 사용법은 [사용자 가이드](guides/USER_GUIDE_KR.md)를 확인해주세요.

---

## 🤝 함께 만들어가기 (Contribution)

사용해 보시다가 불편한 점이나 어려운 부분이 있다면 언제든 말씀해 주세요. 특히, 문제를 직접 해결하여 다른 사용자들이 같은 어려움을 겪지 않도록 도와주시면 프로젝트 성장에 큰 힘이 됩니다. 

버그 수정이나 기능 개선에 참여하고 싶으시다면 [컨트리뷰션 가이드](guides/CONTRIBUTION_GUIDE_KR.md)를 확인해 주세요!

---

## 🔗 연결 링크
- [사용자 가이드](guides/USER_GUIDE_KR.md)
- [컨트리뷰션 가이드](guides/CONTRIBUTION_GUIDE_KR.md)
- [MCP 연동 가이드](guides/MCP_USER_GUIDE_KR.md)
- [동기화 제외 가이드](guides/SYNC_IGNORE_GUIDE_KR.md)
- [프로젝트 철학](philosophy/ABOUT_KR.md)
