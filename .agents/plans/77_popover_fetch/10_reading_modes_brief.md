# Briefing — what a reader actually wants, across the three things they read

## Where this came from

User, 2026-08-31, after the reference-lookup bug was traced:

> 모든 케이스를 고려해서 만들어주면 안돼? 내가 논문이나 책, 그리고 md 노트 파일
> 읽을 때 popover 창이나 sidechat에서 어떤걸 원하겠어? 멀티 에이전트를 사용해서
> 이 문제에 대해 상의한다음, popover창이나 sidechat의 query 프로세스를 개선시켜봐

The reference bug was one instance of a general shape: the question the reader
asked implied a piece of the document that the pipeline never went and got. That
shape is not specific to bibliographies, and it is not specific to papers.

## What was already fixed in this release, so nobody re-proposes it

- A denied tool no longer masquerades as an answer.
- Citation resolution reads the typed question, not only the highlight.
- A bibliography-seeking question gets the reference list even with no `[N]`.
- The bibliography heading matches Korean/Japanese/Chinese forms.
- The prompt states what the provider actually gives it, at both emission sites.

## The axis is the reader's ACTION, not their needs

Corrected by the user mid-Arena, and the correction is the most important line in
this brief:

> 어떤걸 필요로 하겠어가 아니라 내가 어떤 행동을 하겠어가 맞겠다. 그로 인해 어떻게
> 프로세스를 만들어야할지. 저 위에 계속 반례가 생기니 말하는거야

Not "what would I need" — "what would I DO", and the process derived from that.
They said it because counterexamples kept appearing.

They are right, and the reason is structural. A needs-list is a LIST: a
bibliography case, a cross-reference case, a figure case. Every kind of thing a
reader might point at is a separate entry, the pipeline has one hand-written
resolver per entry, and the entry nobody wrote is a silent empty answer. This
release opened by concluding the popover needed a URL fetch tool; the answer was
in the last pages of the PDF already open. That is what a list produces.

An action generalises where a need does not. The actions:

1. **Select a passage and ask about it.**
2. **Type a question naming something, without selecting it.**
3. **Follow a pointer the text makes** — `[12]`, "see Fig. 4", "Section 3.2",
   "Eq. (7)", "p. 214", `[[a wikilink]]`.
4. **Ask where something was defined earlier** — the answer may be 200 pages back.
5. **Ask what I already concluded** — my own notes, not the document.
6. **Compare two documents.**

Every one of those holds for a paper, a book, and a markdown note. So the
document kind is a CHECK on a design, not the axis of it.

The question this Arena must answer: is the right shape ONE resolution step —
*what does this question point at, inside the thing the reader is holding, and go
get it* — replacing N per-kind resolvers? Or is the special-case set defensible on
evidence? Answer it either way, but answer it.

## The three things this vault holds

1. **Papers** — PDFs. Structured: abstract, sections, equations, figures, tables,
   bibliography at the end. Cross-references everywhere. Much of the content is
   drawn, not typeset.
2. **Books** — also PDFs, but long. A chapter is bigger than a whole paper. Table
   of contents matters, index matters, "where was that defined" matters, and the
   answer to a question is often 200 pages from where the reader is sitting.
3. **Markdown notes** — the reader's own, in the vault. No pages. Wikilinks
   instead of citations. The reader wrote them, so "what did I conclude about X"
   is a different question from "what does this paper claim".

## The two surfaces

- **Quick Query popover** — ephemeral, read-only, no edits, triggered from a
  selection while reading. Should be fast.
- **Chat sidebar** — persistent, full tool surface, edits allowed, conversation
  has history.

## Ground rules for any proposal

- No new always-on subprocess and no new external dependency.
- The CLI path injects no plugin tools. Anything the model needs must be IN the
  context by the time the turn starts, or reachable through the MCP registry the
  CLI already loads.
- The prompt-budget gate is real: `promptRoleBudget.test.ts` caps prose across
  the prompt files at 17,000 chars and caps prohibitions. Proposals that add
  instruction text must say what they remove.
- Retrieval is DB-native (FTS5 + vector + RRF + rerank). No second search engine.
- The popover keeps `allowEdits: false`.
