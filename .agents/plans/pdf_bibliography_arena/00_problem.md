# Popover bibliography recovery

Date: 2026-09-14. Patch target v0.82.8; source base14b793f4/schema14.

User report (verbatim):

1. **현재 페이지(Page 7) 정보만 전달되는 시스템 한계**: 현재 연동된 시스템은 AI에게 문서의 전체 내용이 아닌 사용자가 보고 있는 **현재 페이지(7페이지)의 텍스트만** 전달하고 있습니다. 따라서 문서 마지막에 위치한 참고문헌(References) 데이터 자체를 제가 전혀 전달받지 못했습니다.
2. **AI의 환각(Hallucination) 현상과 잘못된 변명**: 정보가 없다면 모른다고 답변해야 하나, 이전 답변(Turn 2)에서 제가 "11페이지에 참고문헌이 정상적으로 포함되어 있으나 저자명 뒷부분이 잘려서(truncated) 들어왔다"고 말한 것은 **AI 모델이 임의로 지어낸 명백한 오류(환각)입니다.** 실제로는 11페이지를 넘겨받은 적이 없으며, 7페이지 본문 끝부분이 잘려서(`[...truncated]`) 들어온 시스템 상태를 참고문헌 페이지를 본 것처럼 오작동하여 변명한 것입니다.

User correction: 사실 논문볼때 이런 참고문헌 정보 찾으려고 저거 만든건데 context 그냥 포함 안되어있다고 말하는건 안될거같아

Deliver actual distant bibliography retrieval before answering, including
native PDF and followups. Do not reduce capability to disclaimers. No requirement
to inject all paper text every turn. Preserve read-only popover policy and
bounded preparation. A current-page truncation marker is not evidence about
another page. Prior answer's diagnosis of this specific incident is unconfirmed;
viewer/provider/input fixture was not supplied. Code paths must be tested.

Independent proposals: pdf_proposal and pdf_adversary; cross-critique follows.
Do not edit runtime .venv, live plugin install, external MCP config or live DB.
