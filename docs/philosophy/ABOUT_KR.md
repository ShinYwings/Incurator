# 📐 Incurator 프로젝트 철학

이 문서는 Incurator가 왜 만들어졌는지, 어떤 문제를 해결하려 했는지를 다룹니다. 기술적인 사용법은 [사용자 가이드](../guides/USER_GUIDE_KR.md)를, 시스템 기능 개요는 [README](../README_KR.md)를 참조하세요.

---

## 🎯 궁극적인 비전: "노트 필기를 위한 Cursor (Ask Gemini for Obsidian)"

Incurator의 궁극적인 목표는 **"노트 필기를 잘 하기 위한 (노트를 읽고 책이나 논문으로부터 인사이트를 뽑기 위한) 옵시디언 기반의 AI 노트 시스템"**이 되는 것입니다. 

가장 적절한 비유는 개발자들을 위한 혁신적인 AI 시스템인 **Cursor**나 **Antigravity**입니다.
- Cursor가 복잡한 Codebase를 잘 파악하기 위해 백엔드에 고도화된 RAG 시스템을 구축하듯, **Incurator 백엔드**는 방대한 지식과 문헌을 이해하기 위한 RAG/DAG 컴파일러입니다.
- 이 강력한 엔진을 실제로 활용하는 프론트엔드 환경(Cursor IDE의 역할)이 바로 **옵시디언(Obsidian) 익스텐션 사이드바**입니다. 
- 옵시디언 내에서 작동하는 이 에이전트 UI는 마치 크롬의 **'Ask Gemini' 시스템을 미믹(Mimic)**하는 것을 지향합니다. 사용자가 현재 읽고 있는 노트나 논문의 맥락을 완벽히 파악한 상태에서, 대화를 통해 새로운 통찰을 이끌어냅니다.

## 💡 핵심 철학: "내가 가진 지식을 Increment 하자"

이러한 비전 위에서, 우리의 철학은 **"기존의 지식을 재활용하여 새로운 지식을 쌓아 올리는(Increment) 것"**입니다. 파편화된 정보들을 유기적으로 연결하고 합성하여 더 높은 차원의 인사이트를 만들어내는 과정을 자동화하고 최적화하기 위해 설계되었습니다.

## 1. 지식의 축적과 연결: Zettelkasten에서 Incurator까지

우리의 핵심 철학을 잘 나타내는 대표적인 학습 방법론이 바로 **제텔카스텐(Zettelkasten)**입니다. 제텔카스텐은 다음 4단계를 거쳐 지식을 구축합니다.

1. **임시 메모 (Fleeting Notes):** 떠오르는 아이디어를 즉각적으로 기록
    
2. **문헌 메모 (Literature Notes):** 학습한 내용을 자신의 언어로 요약
    
3. **영구 메모 (Permanent Notes):** 하나의 아이디어를 독립된 원자(Atom) 형태로 정립
    
4. **연결 및 결합 (Linking & Synthesis):** 영구 메모들을 서로 연결하여 새로운 아이디어 창출
    

옵시디언(Obsidian)과 같은 노트 앱은 이 철학을 바탕으로 만들어졌습니다. 옵시디언의 가장 큰 특징인 `[[wikilink]]`나 Graph View는 **사람이 직접** 지식의 연결망을 시각적으로 확인하고, 이전에 쌓아올린 지식을 탐색하여 새로운 지식을 만들 때 활용하자는 목표를 가집니다.

이를 데이터 및 AI 관점에서 해석하여, LLM이 지식 탐색과 연결 과정을 자동화한 시스템이 바로 **Incurator**입니다.

- **프로세스:** `Raw Data` ➡️ `Ingest (Summary -> Atoms -> Concepts -> Synthesis)` ➡️ `Wiki (Synthesis as new Raw)`
    

제텔카스텐과 Incurator의 공통된 아이디어는 결국 **"사전 지식을 '요약 ➡️ 원자화 ➡️ 개념(Concept) 생성 ➡️ 개념들의 합성'이라는 요약·정제 프로세스를 통해 발전시킨다"**는 것입니다.

## 2. LLM Wiki의 한계

대부분의 LLM Wiki는 초기 Raw 데이터를 넣은 이후의 과정(Ingest, Wiki 생성)을 인간의 개입 없이 LLM이 전담하는 구조를 가집니다. 여기서 심각한 문제점 두 가지가 발생합니다.

### A. 질 좋은 Synthesis 창출의 한계 (Reasoning 부족)

LLM은 데이터를 정해진 규칙에 따라 분해하고 재조립하는 데는 탁월합니다. 그러나 단순히 주먹구구식으로 모델 크기만 키워 추론 성능을 높이려 했기 때문에, Raw File들 사이에서 진정으로 가치 있는 'Insight'를 찾아내어 새로운 지식을 쌓아 올리는 데는 한계가 있습니다. 즉, **질 좋은 Synthesis(새로운 지식)를 만들기 위해서는 반드시 사람의 개입(Human-in-the-loop)이 필요**합니다.

### B. 막대한 토큰 소모와 비용 문제

위 과정을 사람이 직접 개입하며 GPT나 Claude 같은 구독형/상용 Agent 서비스와 협업하여 진행한다고 가정해 보겠습니다. 사전 지식을 '추출'하고 '컨셉을 잡는' 초기 단계에서부터 상용 Agent를 사용하면 토큰이 순식간에 소모되어 엄청난 비용이 발생합니다. 상용 Agent의 Thinking 모델은 데이터의 단순 분해/조립보다는 **'고도의 추론 능력 향상'**에 초점이 맞춰져 있으므로, 단순 작업에 이런 무거운 모델을 사용하는 것은 극도의 낭비입니다. 위대한 지식의 창출도 좋지만, 그 과정에서 우리의 통장 잔고가 먼저 0에 수렴하는 비극은 막아야 하니까요 💸.

## 3. Incurator의 접근: 역할 분리와 Local Model의 도입

**Incurator 역시 LLM Wiki입니다.** 다만, 위의 한계를 해결하기 위해 파이프라인의 역할을 명확히 분리합니다.

데이터를 분해하고 재조립하는 과정(`Summary -> Atoms -> Concept`)은 고도의 추론 능력이 거의 필요하지 않습니다. LLM이 매우 잘 해낼 수 있으면서도 인간의 개입 역시 최소화해도 되는 영역입니다.

**따라서, 이 데이터 분해 및 재조립 단계는 집 컴퓨터에서 돌아가는 가벼운 Local Model(예: Ollama 등) 또는 비추론 모델이 전담하도록 분리합니다.** 로컬 embedding, expansion, reranking 모델은 검색 비용을 줄이고, 설정된 생성 모델은 지식 구조화를 담당합니다.

최종 목표인 **'새로운 인사이트 도출(Synthesis)'** 단계에서는 반드시 **인간**이 개입하여, 데이터가 분해/조립된 결과를 바탕으로 에이전트와 끝없이 토론하며 새로운 지식을 창출해 내야 합니다.

- **AI 전용 공간 (`.curator/`)**: `state.sqlite`가 권위 상태이며, 생성된 CTX/ATM/CON/SYN 마크다운은 폐기 가능한 점검 projection입니다.
- **인간 전용 공간 (`02_Wiki/`)**: 명시적으로 승격된 human-reviewed 지식만 지속되는 상설 공간입니다.

## 4. 시스템 아키텍처: 미술관 큐레이터(Curator)와 아티스트(Artist)

이러한 협업 구조를 시스템으로 구현하기 위해, 우리는 **미술사에서의 큐레이션(Curation) 과정**을 메타포로 차용했습니다.

### 🏛️ The Curator (Manager of the Vault)
The Curator resides in the **Vault**, the home of your knowledge. It focuses on refining and displaying data rather than deep reasoning:

1. **수집 및 선별 (Collection & Selection):** Raw Data를 수집.
    
2. **분석 및 맥락화 (Analysis & Contextualization):** 데이터를 Summary하고 Atom으로 분해.
    
3. **공간 기획 및 구조화 (Spatial Planning & Structuring):** 분해된 원자들을 Concept 단위로 엮어 기계와 Agent가 읽기 쉽게 맥락을 형성.
    
4. **큐레이션 및 소통 (Curation & Engagement):** 고정 subset을 저장하는 대신, 워크스페이스 지식 요구 명세서(`curate.yml`)를 live DAG 위의 동적 retrieval lens로 적용합니다.
    

### 🎨 The Artist (Resident of the Workspace: Human + Agent)
The Artist resides in the **Workspace**, the painter's studio where projects or research happen. Drawing a new painting (Synthesis) requires immense creativity and reasoning. 이 Artist가 숨쉬고 활동하는 무대가 바로 **옵시디언 익스텐션 사이드바(Ask Gemini UI)**입니다.

1. **Workspace:** 화가의 작업실이자, 사용자가 노트를 읽고 문서를 분석하는 옵시디언 환경입니다.
    
2. **Agent의 상주:** 강력한 추론 능력을 가진 Agent는 옵시디언 사이드바(익스텐션)에 상주하며 인간의 보조자 역할을 합니다. 사용자가 현재 열어둔 노트나 논문의 맥락을 실시간으로 파악하며 대화에 참여합니다.
    
3. **사전 지식의 활용:** 사용자가 질문을 던질 때, Agent는 정제된 live DAG에서 선택된 bounded evidence pack을 trace와 함께 가져옵니다.
    
4. **인사이트 도출 (Synthesis):** 최종적으로 인간과 Agent가 협업하고 토론하여 새로운 그림(Synthesis = New Raw Data)을 창조해 냅니다.

    

    

## 5. 시스템의 핵심: 세 가지 차별점

LLM Wiki는 대부분 지식의 닫힌 순환(수집 → 처리 → 활용 → 재입력)을 지향합니다. Incurator도 이 흐름을 따르는 LLM Wiki지만, 세 가지 측면에서 다른 LLM Wiki들과 차별화됩니다.

첫째, **맞춤형 지식 전달**입니다. `curate.yml`의 프로젝트 목적과 필요 지식은 쿼리 시점의 동적 Curation lens로 작동하여 live graph에서 관련 근거를 선별하고 랭킹합니다. 워크스페이스별 고정 전시물을 저장하지 않으므로 stale subset 없이 도메인 오염을 줄입니다.

둘째, **사전 지식 교정**입니다. 사전 지식의 오류나 새로운 인사이트에 대한 피드백은 correction, contradiction, derived insight, style-only, promotion, ambiguous proposal로 분류됩니다. source truth는 보호되며, 실제 generated knowledge 변경은 별도의 검토 동작을 거쳐야 합니다.

`wiki add`와 `wiki build`는 source-grounded L1-L4 지식을 컴파일하는 **순방향 빌드(Forward Pass)**입니다. 인간과 에이전트의 수정 요청은 분류된 proposal로 들어오며 generated record를 조용히 덮어쓰지 않습니다. 승인된 후속 동작과 무결성 검증을 통해 source, generated knowledge, promoted human knowledge 사이의 감사 가능한 경계를 유지합니다.

셋째, **페르소나: 당신의 지식 모델을 표현하다.** 제텔카스텐은 구조를 강요하지 않습니다 — 사용자가 지식을 바라보는 방식 자체가 구조가 됩니다. Incurator의 **페르소나 시스템**은 이 철학을 시스템 수준에서 구현합니다. `wiki init` 시 인터뷰를 통해 설정되는 **전역 페르소나**는 당신이 어떤 분야에서 어떤 목적으로 지식을 쌓는지를 시스템에 각인시킵니다. 

이 페르소나는 각 Vault마다 상주하는 **Curator의 정체성**입니다. 지식은 단일한 공간에 응집되어 있을 때 가장 강력한 연결성(**Increment**)을 가지지만, 만약 당신이 "과학자"로서의 지식 체계와 "요리사"로서의 지식 체계를 완전히 분리하여 각기 다른 전문가(Curator)에게 맡기고 싶다면, 그때가 바로 Vault를 나눌 때입니다. 큐레이터는 구조를 부과하는 것이 아니라, 당신이 선택한 **전문가적 시선**으로 지식을 해석하고 전시할 뿐입니다. 

워크스페이스별 **로컬 페르소나**는 그 위에서 프로젝트의 맥락을 덧씌워, 동일한 큐레이션 엔진이 도메인마다 전혀 다른 방식으로 지식을 해석하고 전시하게 만듭니다.
