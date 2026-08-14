# Briefing: make the assistant read the document for the user

Date: 2026-08-09 | Convener: Claude Code | Status: OPEN for proposals

## 0. What the user asked for, in their words

> 1. popover 질문할때 어떤 개념들이나 논문들의 래퍼런스 예를들어 [8] 적혀있으면
>    그 논문에 대해 설명하고 어떤 수식까지 같이 질문에 있었으면 그 수식에 대한
>    답변을 하면됨. 이건 sidechat도 마찬가지
> 2. sidechat 같은 경우에는 좀 더 나아가서 지금 열려있는 vault 의 모든 파일들의
>    내용을 RAG에 담았다가 내 질문에 답변을 만들 때 사용해.
> 3. 개념같은거 찾을 때 인터넷같은거 적극적으로 사용해. 그리고 논문과 논문의
>    래퍼런스를 꼬리물어서 답변해야하는것도 필요할거야.
> 4. 책같은 경우에도 비슷해. 내가 사이드챗이나 popover를 통해 굳이 pdf 다른
>    페이지를 직접 방문 안해도 너가 그걸 찾아서 나한테 답변으로 보여주면 되는거고.

And on the failure they keep seeing:

> 답변할때 이 컨텍스트에 로드 됐는지 안됐는지 사용자가 알 필요 없잖아 …
> 지금 컨텍스트에 있냐 없냐니, 일반적으로 알려진 이야기니 아니니, 그런거
> 이야기할 필요없는데 자꾸함.

## 1. Both narration complaints are things WE instruct

Not model chattiness. Measured in the prompt sources.

**(a) "이 컨텍스트에 로드되지 않았어요"** — three sites told it to say so:
`chatContextPriority.ts` ("say you could not locate the referenced target"),
`crossReferenceResolver.ts` `UNRESOLVED_NOTE` ("say plainly that you could not
retrieve"), `promptRegistry.ts` ("say you could not retrieve it"). All three
shipped in v0.48.4. **Fixed in v0.53.3 / PR #152.**

**(b) "일반적으로 알려진 이야기"** — `promptRegistry.ts:78-83` does not merely
allow this, it **mandates it and supplies the sentence**:

```
"If the provided context and fetched pages do NOT contain the information "
"needed to answer the question, you may supplement your answer with your "
"general knowledge. When doing so, you MUST explicitly state that the "
"information comes from general knowledge, not from the document "
"(e.g. 'The document does not cover this, but based on general knowledge…'). "
"Never pretend that general knowledge came from the document."
```

The user is quoting our own example string back at us. **Still live on master.**

## 2. The prompt stack is bloated and prohibition-heavy

Measured across the modules that contribute text to one chat turn:

| module | prompt chars | negative directives |
|---|---:|---:|
| systemPrompt.ts | 7,991 | 12 |
| chatContextPriority.ts | 2,279 | 4 |
| promptRegistry.ts | 2,232 | 7 |
| crossReferenceResolver.ts | 2,616 | 1 |
| providerContextFormat.ts | 5,038 | 0 |
| **total** | **20,156** | **24** |

~5k tokens of rules before a single line of the paper. Published guidance is
consistent that instruction-following degrades as `do NOT` rules accumulate (the
"pink elephant" effect), and that a RAG assistant should not discuss the
retrieved context at all. We have 24 prohibitions and two rules that *require*
discussing it.

## 3. What comparable tools do that we do not

Benchmarked against **llm-for-zotero**, the closest published system (a Zotero
research agent). Its read-side tool surface:

| tool | what it does | do we have it |
|---|---|---|
| `read_paper` | PDF text, by section index | partial (`fetch_pdf_page`, by page only) |
| `search_paper` | ranked passages for a question | partial (`search_pdf_anchor`, read pages only) |
| **`view_pdf_pages`** | **renders pages as IMAGES, by page number or by question** | **NO** |
| **`search_literature_online`** | **CrossRef / Semantic Scholar lookup** | **NO** |
| `query_library` / `read_library` | Zotero discovery | partial (backend Zotero tools) |

Two architectural lessons worth copying:

1. **Locate with an index, show with a crop.** It uses a structured parse
   (MinerU: section ranges, page hints, tables, equations) *as the index that
   locates a figure*, then the model is shown **a precise crop taken from the
   source PDF**. That is the answer to our rasterized-equation problem: text
   locates, pixels answer. We proved the pixel half works — `claude-code`
   vision returned equation 29's LaTeX verbatim from a page render.
2. **Citations stay conservative until the page is verified**, then become
   clickable. Honesty as a UI state, not as a sentence the model must recite.

## 4. Ground truth in this vault

- `[8]`-style bibliography citations are **not a recognized pointer shape**. The
  resolver handles `(29)`, `Fig 19.1`, `Sec A4.2`, pages — nothing maps a
  citation number to a paper. The user's item 1 is entirely unbuilt.
- Vault RAG covers **ingested sources only**: 36 sources vs **137 markdown files
  on disk**. Item 2 is ~26% true.
- No web tool exists. Item 3 unbuilt.
- `fetch_pdf_page` reads any page; finding *which* page is the gap. Item 4 half.
- Reference resolution has an obvious ladder available: vault → Zotero (the
  user's library, already integrated) → web (CrossRef/Semantic Scholar).

## 5. The question for the Arena

Design the reading-assistant capability so that, for a question naming `[8]`, an
equation, a section, or a concept, the assistant **resolves the address, gets
the content, and answers** — without the user navigating, and without narrating
its own plumbing.

Every proposal must answer:

1. **One resolver or four features?** `[8]`, `Eq (29)`, "Sec C", "what is a
   Cauchy loss" are four address types. Is there one pipeline
   (resolve → fetch → answer) or are these separate?
2. **What is the fetch ladder** and what stops it? vault → Zotero → web has a
   cost and a privacy boundary. Name where it stops and what the user sees.
3. **Text or pixels?** We can read a page as text or as an image. State the rule
   for choosing, given that rasterized equations have no text at all.
4. **Citation chaining depth.** Paper → its `[8]` → that paper's `[12]`. Where
   does it terminate, and what stops a cycle?
5. **How does the prompt shrink?** 20,156 chars and 24 prohibitions is the
   current state. A proposal that only adds instructions is not acceptable.
   What comes OUT?
6. **What replaces provenance narration?** The user must still be able to tell
   paper-content from model-knowledge — but not by reading a sentence about it.
7. **Tests.** Which of these can be tested deterministically, and what is the
   honest gap?
