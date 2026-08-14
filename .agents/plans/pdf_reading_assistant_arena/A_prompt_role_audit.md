# Domain Analysis A: the prompt encodes a scope-limiter, not the assistant's role

Date: 2026-08-09 | Agent Persona: convener (measured, not argued)

## 0. The role, as the user defines it

> agent를 통해 pdf 의 논문이나 책을 읽는 것에 대해 도움을 주고, 작성했던 노트들을
> 리마인드 할 수 있게 해주고, 앞서 말한 정보들로부터 새로운 가치를 찾을수있게
> 도와주는 역할이 sidechat과 popover 채팅의 역할이야.

Three duties:
1. **Read with me** — papers and books in PDF.
2. **Remind me what I wrote** — surface my own notes.
3. **Find new value** — produce something from (1) and (2) I did not already have.

## 1. What the prompt actually instructs

Measured over every prompt-bearing string literal (>60 chars) in
`systemPrompt.ts`, `chatContextPriority.ts`, `promptRegistry.ts`,
`crossReferenceResolver.ts` — 20,156 chars total.

| duty | sentences enabling it | sentences limiting it |
|---|---:|---:|
| 1. read / explain the document | 32 | 13 |
| 2. remind me of my own notes | 6 | 3 |
| 3. find new value / synthesis | 4 | 0 |

Duty 1 is heavily specified. Duty 3's four "enabling" hits are **not role
instructions at all** — they are MCP tool descriptions (`curator_query` "returns
a synthesized answer", `curator_fetch_context` "a curated evidence pack"). There
is **no sentence anywhere telling the assistant that finding new value is part
of its job.**

## 2. The contradiction that suppresses duty 2

Exactly **two sentences in 20,156 characters** mention the user's own notes, and
each cancels itself in the same breath:

> "You should actively use the background context to enrich your answer and
> connect it to the user's existing notes, **but avoid outputting a generic
> summary of the background context**."

> "You MUST actively use the pinned and visible Obsidian context … to enrich
> your answer, connecting the explanation of the selected text to the user's
> existing notes and current page/ToC, **but you MUST NOT explain the background
> context itself**."

And in the same assembled prompt, from `promptRegistry.ts`:

> "**Answer ONLY about** the `<primary_focus_selection>` in the latest request …
> **Do NOT explain, summarize, or modify the whole document** unless the latest
> request explicitly asks for it, regardless of earlier turns."

and from `chatContextPriority.ts`:

> "**You MUST NOT explain the entire document or current page** when a primary
> focus selection is provided."

A model reading this stack sees one hedged permission to connect to notes and
three unhedged prohibitions against talking about anything but the selection.
The safe policy — the one it takes — is to answer narrowly about the selection
and never volunteer a connection. **That is precisely the behaviour the user is
complaining about.**

## 3. Why it got this way, and why that matters for the fix

These prohibitions are not careless. Each was added to stop a real failure: the
model explaining the whole page when asked about one line, summarising pinned
context back at the user, proposing edits nobody asked for. They worked.

The defect is that **the prompt was only ever given the negative half of the
job.** Nothing was ever added on the other side saying what the assistant is
*for*. So the stack reads as a list of things not to do, with the actual role
inferable only from the tool descriptions.

This is the same failure mode as the narration bug, one level up: we told the
model what to avoid, it complied exactly, and the compliance is the complaint.

## 4. The two narration mandates (already partly fixed)

- **"이 컨텍스트에 로드되지 않았어요"** — three sites instructed it. Fixed in
  v0.53.3 (PR #152).
- **"일반적으로 알려진 이야기"** — `promptRegistry.ts:78-83` still MANDATES it and
  supplies the sentence verbatim:
  `"you MUST explicitly state that the information comes from general knowledge,
  not from the document (e.g. 'The document does not cover this, but based on
  general knowledge…')"`. **Still live on master.**

## 5. Consequence for the plan

Any fix that only adds capability (citation resolution, web lookup, page
fetching) will land in a prompt that tells the model to answer narrowly and say
nothing it was not asked. **The prompt has to be re-posed around the three
duties before new tools can be felt.** That ordering is the finding.
