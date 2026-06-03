1. eye-off 기능 제대로 동작안함. eye off 하고 send 보내면 eye off 상태로 입력되어야하는데 send 보내고나면 eye off가 다시 eye 상태로 바뀌고 (첫번째 문제점, 계속 그 상태 유지해야함, purple pin만 해당) 그 eye상태가 send 보내고 난다음에도 계속 유지된 채로 있음.

2. antigravity ide의 sidechat 의 UI 를 분석해서 obsidian agent의 sidechat ui ux 개선시켜줘. 거의 탈바꿈해야할거같은데 (좋아요 싫어요 버튼 이런건 필요없을듯)

3. 채팅 답변 받을때 sidebar에서 renderning이 다 깨져서 나와. 그다음 쿼리를 쳐주거나 새로고침을 해줘야 rendering이 됨. 

그리고 모든 답변 내용을 곧이 곧대로 다 채팅에 넣어버리니까 가끔씩 cpu 터짐. (채팅 답변 볼륨이 크면 왜케 cpu 터지는거지??? 이 문제 해결해줘)
지금은 파일 변경, 수정, 생성 내용을 채팅창에다가 다 때려 박는데 그거 대신에 md 파일 생성 수정 삭제 실행시 내용은 md 파일에 직접 반영하는게 좋음. sidechat에는 요약된 내용만 넣는 걸로. 왜냐하면 script 파일에서 변경내용을 보면서 sidechat에서는 그 이유만 들으면 됨. (cli 기반 agent이면 그럴수도 있겠는데 (확인 필요) deepseek api는 네이티브로 다 개발 가능할텐데)