# Correction: I was wrong. The content the model went looking for is NOT ours to give.

Date: 2026-08-21 | Persona: main, correcting itself after the user demanded verification

## 1. What I claimed, and what is actually true

`02_critique_user.md` §1 said the vault *"has already indexed exactly that"* and
cited **240** FTS hits for `plucker` and **406** for `epipolar`. That query had
**no source filter**. Restricted to source 45 (Hartley — the book in the report):

| | |
|---|---|
| FTS hits, `plucker OR plücker`, **source 45** | **0** |
| FTS hits, `epipolar`, **source 45** | **0** |
| where the 240 hits actually came from | sources 25 (59), 37 (30), 14 (18), 18 (8), 12 (7), 16 (6) |

**The premise of my critique was false.** The model was not slowly re-deriving
something we had. It was reaching for something we do not have.

This is the second unverified count in this thread: earlier I reported "0 Plücker
spans" from a `LIKE` over `text_preview` and then dismissed it as my query being
wrong. Both were the same mistake — reporting a number without checking what it
was counting.

## 2. Why source 45 is unsearchable, measured

| | |
|---|---|
| `search_documents` rows for source 45 | 8,905 — all `record_type='source_span'` |
| body length of those rows | min 1, **avg 127, max 200** |
| `doc_len` vs `text_preview` length, sampled | **identical, every row** |
| published `knowledge_units` for source 45 | **0** |

So the indexed body **is** `text_preview`, capped at 200 characters. Anything past
the first 200 characters of a span is not searchable. And because L2 never
published, source 45 has **no `knowledge_unit` documents** — which is where full
statements live for every other source (source 25's bodies reach 1,758 chars).

## 3. And the term is absent from everything we hold

The L1 Context on disk, `CTX-cf1a7b4b.md`, **403,625 bytes** for a 673-page book:

- `epipolar` — **59 occurrences**
- `Plücker` / `Plucker` — **0 occurrences**
- lines containing both — **0**

`epipolar` appears 59 times in that file and **0 times in the search index for
source 45**, because the Context file is not indexed as a document at all. Only
104 of the book's 673 pages have a vision transcription.

So the answer to the user's question is not merely unindexed — for `Plücker` it
is **absent from every artifact we hold**.

## 4. The goal, restated correctly

> *"provider별로, 옵시디언에서 렌더링되지 않은 PDF 페이지의 질문을 했을 때, 그
> 곳의 정보들을 — 또는 인터넷 서칭 등 — 파고들어서 답변 생성하기."*

That is **ROADMAP 10**, recorded in RELAY as the paused goal: *"`search_pdf_anchor`
is still limited to already-rendered pages. `fetch_pdf_page` reads any page the
model can name, but nothing can locate one in an unread page."*

The agy shell-out is a **symptom** of that gap, not an independent defect. The
model ran PyPDF2 over 673 pages because nothing in the system can locate content
in a page nobody has opened.

## 5. What this does to the plan

- **①-b′ (structured-output retrieval loop) is not wrong, but it is not first.**
  A loop that retrieves from today's corpus returns 200-character previews and,
  for this source, nothing at all. Retrieval cannot precede having something to
  retrieve.
- **The prerequisite is ROADMAP 10**: make the content of un-rendered pages
  locatable — full span text indexed rather than previews, the L1 Context
  indexed, and vision transcription covering the pages a question actually
  touches (104/673 today).
- **B' and C keep their places**, but neither was ever the answer to the goal as
  the user states it. C stops one refusal from killing an 87-batch compile; B'
  bounds what a shelling model can reach. Neither makes an unread page answerable.

**Nothing here is ready to implement.** The next step is a briefing for ROADMAP
10 built on these measurements, not more design on top of a premise I did not
check.
