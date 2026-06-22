# Urgent Hotfix: Backend vs Plugin Config Isolation & UI Sync

**[USER NOTE ON PM FAILURE]**: "Gemini 라는 PM은 병신임. 핀트 하나도 못알아들어서 이상하게 수정함"

The human user has ordered the Executor to handle this as an urgent hotfix on the current branch, based on the following RAW context and logs provided by the user.

## CRITICAL DIRECTIVE (NO COMPRESSION)
The user explicitly commanded: "절대로 내용 요약하지 말고 있는 그대로 다 써" (Do NOT summarize the content, write it exactly as it is). The following sections contain the exact problem context, the terminal output, the UI screenshot, and the chronological raw chat log from the user.

---

## 1. The Core Bug (Dashboard vs `wiki status` Desync)

**User Context:**
"지금 당장 써야하는데 dashboard랑 wiki status랑 sync가 안맞네. 지금 브랜치에서 핫픽스 커밋으로 고쳐줘.
wiki init 으로 맨처음에 primary랑 fallback 을 설정한 다음에 
dashboard왔더니 저렇게 나왔음. 그래서 fallback이랑 fallback PDF ingest 랑 latex region 설정 다시 바꾸고 apply 눌렀는데 Jobs 창 갔다오니까 다시 원상복구되어있음. 그리고 Recommended Ollama model 저거는 ollama 설정할때만 나오게 해줘."

**Terminal State (`wiki status` output):**
```text
base) ➜  Incurator git:(feature/prompt-architecture-refactoring) ✗ wiki status   

╭──────────────────────────────────────────────────╮
│ incurator  @ /Users/shin/shinywings/second_brain │
╰──────────────────────────────────────────────────╯
                                      Config                                      
  Primary                   Antigravity CLI  (gemini-3.5-flash)  · medium effort  
  Fallback                  Ollama  (qwen2.5:3b)                                  
  Account                   Authenticated                                         
  Ollama host               http://localhost:11434                                
  Search backend            native                                                
  Reranking                 on                                                    
  Embedding                 llama-cpp::qwen3-embedding-0.6b                       
  Search engine             native-0.24.0  in-DB FTS5 + vector                    
            Sources             
  Raw source files          27  
  Sources tracked (DB)      1   
  Sources summarized        1   
  (L1)                          
  Ingest runs               0   
          Collections          
  L1 Contexts/              1  
  L2 Atoms/                 0  
  L3 Concepts/              0  
  L4 Synthesis/             0  
  total                     1  
```

**Dashboard State (Image):**
![Dashboard State](file:///Users/shin/.gemini/antigravity-ide/brain/63af16c9-5c27-4c16-bd1d-3b37b14b304d/media__1782147924117.png)

---

## 2. Chronological Raw Chat Log (The User's Exact Directives)

1. "@[/Users/shin/shinywings/Incurator/.cache/config/config.yml] config파일은 여기서 참조해야하는거 아니야? backend 관련된건 다 여기로 넣기로 했는데"
2. "plugin의 .curator 에 config.yml 이랑 device 정보 있어야해? backend 관련된거 .curator에는 다 뺄수있어? backward compat 도 고려하지 말고. legacy 다 지우고."
3. "backend 정보는 기기마다 다르기때문에 plugin에서 정보가 공유되면 안된단말이야"
4. "plugin에 config.yml 이름을 바꿔버리자 그냥 너가 헷갈려하는거 같음. 또한 runtime도 Incurator .cache로 옮기는게 나을거같은데?"
5. "그리고 Ollama 추천 조건부 (line 1049-1068): primary/fallback에 Ollama가 선택된 경우에만 표시"
6. "pdf도 ollama 쓸수있어.."
7. "아니 wiki 명령어로 설정 바꾸는건 runtime에  write 함?"
8. "아니 persona 이런것도 다 그래야하는거 아녀?"
9. "그니까 wiki 명령어로 backend 설정 바꾸면 runtime 폴더 안에있는 파일들이 바뀌어야하고 그 정보를 plugin이 그냥 가져다 쓰는 구조여야함. (apply 제외) 거의다 read exec 밖에 없어야한다고. backend 정보를 plugin쪽에다가 write 할일은 거의 없어야한다고. zotero도 어떻게보면 backend 정보지 기기마다 path가 다르니까"
10. "엥 기존처럼 dashboard로 설정은 그대로 할 수 있어야하는데 settings.ts보면 다 지운거같은데... 아니지?? 그리고 draft로 하는게 아니라 지금 당장써야하는데 이거때매 못쓰고 있음... 당장 고쳐야해"
11. "미친 또 다 삭제할라하네  .cache/plugin/runtime 으로 바꿔줘"
12. "그리고 project.yml 말고 settings.yml 이런게 더 나음."
13. ".cache/plugin/runtime 보면서 생각하는건데 vault가 여러개 일수 있는거 알지? @[/Users/shin/shinywings/Incurator/backend/src/curator/constants.py:L15] 이것도 settings로 바꾸는게 낫지 않을까?"
14. "아니 잠깐만   여러 vault가 한개의 incurator를 접근하는데 너 지금 하는말이 논리적으로 맞다고 생각해?  그리고 .cahce/config/config.yml 그대로 하고 plugin에있는 config.yml 을 settings.yml 으로 바꾸라니까? 둘이 이름이 같으니까 너가 계속 헷갈려하잖아"
15. "아니 plugin 용 변수이름이랑 backend 용 변수이름이랑 분리가 안되어있어서 헷갈리는건가??????? 스트레스받네"
16. "아니 plugin 이 여러개 잇을수 있는데 cache/plugin/runtime 라고 하면 모든 Plugin이 똑같은 json 참조하잖아... 그냥 너 꺼져라."
17. "이 채팅 세션에서 내가 했던 내용 담아다가 relay에 urgent 핫픽스로 처리하게 만들어. 절대로 내용 요약하지 말고 있는 그대로 다 써"
18. "a single Obsidian vault can have *multiple plugins* installed 시발 이럴줄 알았다. single incurator can have multiple obsidian vault 인데"

---

## 3. Executor Instructions
Read the raw logs and context above. The PM (Gemini) failed to implement this correctly. You (the Executor) must execute the hotfix on the current branch immediately, satisfying every constraint listed by the user.
