# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

## 📝 User Inbox

- **[sidechat] partial selection + LaTeX 복사 불가 문제**: MathJax가 수식을 SVG로 교체하는 구조 때문에 드래그 선택 영역만 LaTeX 포함해서 복사하는 게 불가능. `pointer-events: none` CSS 시도 및 Cmd+Shift+C / 우클릭 메뉴 시도 모두 전체 메시지 복사만 되어 revert. 근본 해결책 후보: (1) MathJax 대신 KaTeX로 교체 — KaTeX는 DOM 텍스트 노드를 보존해서 브라우저 selection이 수식을 가로질러 작동함, (2) 각 `mjx-container` 위에 LaTeX 소스를 담은 투명 텍스트 overlay `<span>` 을 얹는 방식. 우선순위 낮음.
- PDF LaTeX 변환 기능(우클릭 "Convert to LaTeX")에서 사용하는 LLM 모델을 사용자가 선택할 수 있도록 settings에 "Fast/Light model" 옵션 추가 필요. 현재는 메인 모델을 그대로 사용하는데, LaTeX 변환처럼 간단한 작업엔 qwen2.5:0.5b 같은 경량 로컬 모델을 별도 지정할 수 있어야 함. Ollama 사용자 기준 추천 기본값은 `qwen2.5:0.5b`. 더 작은 용량 쓸수 있는거 있으면 찾아봐.

- obsidian agent가 한 채팅 세션 안에 있는 모든 기록을 답변할 때 사용하지? 안되있으면 되게 하는게 좋은지 인터넷에서 최신기법같은거 뒤져서 확인해보고 (노트 특화), 만약 만들었거나 있으면 채팅창 compat 하는 기능 추가해야함. 채팅 세션 최대 길이 (최대 토큰 길이) 만큼 얼마나 찼는지 원형 progress bar로 쿼리 표시 아래 실시간으로 표시되고 그 버튼 누르면 해당 채팅 세션 대화 기록 compat 되도록 해야겠다. 

- github cl (gh) 가 왜 설치해야는지 모르겠음. 이미 .git으로 관리중인데. sidechat에서 vault 내 파일들 history 참조하는 용도로 쓸라했거든. (예를 들어, 이거 예전에 내가 어떻게 썼더라? 어 이거 기록이 있었던거 같은데 지금 안보이네? ~시간 전에 썼던거 다시 복구하고싶음.) commit 이나 push같은 버전 관리는 직접함 (다른 플러그인 통해서, 거기는 gh 필요로 안함).