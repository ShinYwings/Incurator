# Defense: drill-down does not need tool calls, and my table was wrong

Date: 2026-08-21 | Persona: lead_architect, responding to the user

> *"모델이 스스로 파고들기 이게 중요한데. 다른 모델들은 1-b로 해도 파고들기
> 가능하지 않아?"*

## 1. Conceded: "one shot" was my drawing, not ①-b's constraint

`02_critique_user.md` §5 listed ①-b as *"no — one shot, we retrieve first"*
against ①-a's *"yes"*. That is wrong. Iteration is a question of **who runs the
loop**, not of how content reaches the model. Nothing about putting passages in a
prompt forbids a second round.

## 2. The shape: a retrieval loop driven by STRUCTURED OUTPUT

The model never calls anything. It either answers, or it states what it still
needs — as a field in the JSON it already has to return:

```
round 1: retrieve(question) → prompt(question + passages + schema)
         schema: {"answer": str} | {"need": [{"query": str, "source_id": int?}]}
round 2: if "need" → retrieve(need) → prompt(question + old + new passages)
         bounded: MAX_ROUNDS (3), and each round's budget is optimal_chunk_chars
```

Drill-down, with **zero** permission surface. The model asks; we fetch.

## 3. Why this lands on capability that already exists

- **`AntigravityCliClient.supports_structured_output = True`** — measured, and it
  is the ONLY CLI client that does (`ClaudeCodeClient`, `CodexCliClient`,
  `OllamaClient` are all False). v0.60.0 shipped `--json-schema` for precisely
  this, so the channel is built and in production.
- A 23,835-character prompt round-trips with its final line intact, so the
  carrier is proven at more than a full batch's size.
- The FTS corpus already answers the reported query: **240** documents for
  `plucker OR plücker`, **406** for `epipolar`, across 8,905 indexed spans and
  104 cached vision transcriptions.

## 4. Corrected comparison

| | ①-a MCP server | ①-b′ structured-output loop |
|---|---|---|
| permission surface | **needs `--dangerously-skip-permissions`** | **none** |
| model can drill down | yes | **yes** — it names what it needs; we fetch |
| who decides what is retrieved | the model, per call | the model per **round**, we execute |
| works for other providers | agy/CLI only | **all** — structured output or plain JSON |
| agy config involved | yes | no |
| testable without a live provider | hard | **yes**, with a fake client |
| new infrastructure | MCP wiring + the auto-approval decision | **a bounded loop** — the backend has none today |

`grep` for `tool_calls|tools=|function_call` across `backend/src/curator/`
returns **nothing**: the backend's LLM layer is one-shot structured output only.
The agent loop lives in the plugin, and the plugin routes CLI providers down its
own *"no-tools single-turn path"*. So the loop is genuinely new work either way —
but ①-b′ builds it without buying auto-approval, and ①-a does not build it at all
while requiring auto-approval.

## 5. Honest cost

①-b′ is more work than a one-shot injection and it is new backend
infrastructure. It also cannot do everything a tool loop can — the model cannot
run arbitrary computation, only ask for retrieval. For this item that is the
point: the reported failures are all *"find/read this content"*, which retrieval
answers, not computation.

**Direction: ①-b′ replaces ①-b as the primary fix.** C and B' keep their places
behind it.
