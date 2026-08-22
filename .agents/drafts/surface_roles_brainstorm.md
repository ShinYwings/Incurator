# Draft: what the popover and the sidechat are each FOR

Date: 2026-08-22 | Status: brainstorm, nothing decided, no code

## 1. Measured capability of a CLI-routed model (agy, `-p` mode)

Everything here is a real invocation on this machine today. This is the fact base
the role split should rest on, and most of it contradicts what the code assumes.

| capability | result |
|---|---|
| built-in **web search** | **works** — live, `877 stars, 2026-08-22`, and the count moved between two runs |
| web search **with `--json-schema --output-format json`** | **works**, `num_turns: 1`, **12.8 s** |
| `read_file` on a text file | **works** — returned `CHANGELOG.md`'s first line |
| read a **21 MB PDF** | **fails** — "Agent execution terminated due to error" |
| **shell** command | **denied** — `permission check failed` |
| **our MCP** tools | **denied** — same gate |

Two things follow immediately.

**The permission gate is narrower than we thought.** v0.62.x work concluded that
agy tool use needs `--dangerously-skip-permissions`. That is true of *shell* and
of *our MCP server*. It is **not** true of agy's own web search or `read_file`,
which need no flag at all. The plugin routes CLI providers down a "no-tools
single-turn path" on the assumption that they have nothing; they have quite a lot.

**Its search is far cheaper than ours.** A whole turn including a live web search
cost **12.8 s**. Our pre-turn vault fetch costs **59–99 s**, of which
`curator.query_search_terms` alone is 34–50 s. We are paying an LLM to write
search terms for a search engine, while the provider will simply search.

## 2. What this does to plan 05's locked decisions

- §2 Non-Goals: *"Not granting the popover model MCP or filesystem tools."* Still
  intact. agy's own tools are not ours to grant or withhold — they are already
  there, and we neither wire them nor authorise them. The plan never drew this
  line because at the time a CLI-routed model was assumed toolless.
- §4.2: *"Resolve BEFORE the turn; do not make the model chase."* The reason
  given is that `MAX_RECURSION = 5` is shared across tool families. That budget
  is **ours**. agy chasing inside its own turn spends none of it — measured,
  `num_turns: 1`. So §4.2 constrains what we make the model chase through *our*
  tools, and says nothing about the provider's internal behaviour.

Neither has to be reopened for the user's proposal. That is worth stating
plainly, because my last three proposals each violated one of them.

## 3. The split, as the user framed it

> 두 개 모두 CLI 자체의 검색 성능에 의존할 수 있다. 또한 열려있는 PDF의 다른
> 페이지들의 정보를 검색할 수 있어야 한다. 대신 sidechat은 popover와 다르게 vault
> 안에 있는 정보들을 사전 정보로 추가적으로 활용한다.

Restated against the measurements:

**Shared floor (both surfaces).**
- Lean on the provider's own search rather than re-implementing it. Free, fast,
  no permission gate, no recursion cost.
- Reach **other pages of the open PDF** — cited references, a distant section.
  This one we must serve ourselves: agy cannot open a 21 MB PDF. `fetch_pdf_page`
  already reads any page the model can **name**; what is missing is the ability to
  **locate** content in a page nobody has opened. That is ROADMAP 10, and it is
  the real prerequisite for the shared floor.

**Popover = the document.** Selection, its neighbourhood, other pages of the same
PDF, resolved citations, plus whatever the provider looks up itself. **No vault
retrieval.** Fast by construction.

**Sidechat = the document + your vault.** Everything above, and the vault
evidence pack as prior context. Slower on purpose, because it is the surface you
choose when you want your own knowledge brought in.

## 4. Where this says v0.62.3 went wrong

I put the vault fetch in the **popover** — the one surface that should not have
it — and left the sidechat's own vault retrieval gated off behind a condition
(`l3_status='done'`, true for 0 of 44 sources) that could never pass. Exactly
backwards on both counts.

The user also rejected my proposed remedy: *"답변을 검색에 묶어야 돼."* Answering
first and folding evidence in later breaks the binding between the answer and its
evidence. For the sidechat that binding is the point.

## 5. ANSWERED (2026-08-22): the capability is provider-specific, and claude already has it

The user asked me to judge Q1. Measured across the installed CLIs:

| | agy | claude CLI | codex |
|---|---|---|---|
| built-in web search, live | **yes** (877, 2026-08-22) | **yes** (877, 2026-08-22) | untestable — see below |
| 588 KB PDF | **yes** | **yes** | — |
| 4.1 MB PDF | **yes** | — | — |
| **21 MB book** | **FAILS** ("Agent execution terminated") | **YES, and it searches inside it** | — |
| shell command | denied | — | — |
| our MCP tools | denied | — | — |

**The finding that decides the design.** Asked whether the 21 MB Hartley book
covers Plücker line coordinates, the claude CLI answered:

> *"Yes — §3.2.2 \"Lines\" (Ch. 3, Projective Geometry & Transformations of 3D,
> PDF pp. 88–90) presents the Plücker matrix and defines \"Plücker line
> coordinates\" explicitly (24 mentions total)."*

Section, chapter, page range, and a mention count. That is **the user's original
failing question**, answered — the one where agy shelled out to PyPDF2 over 673
pages and was denied. And note it read the file at the **iCloud Zotero path**, so
TCC did not block it either.

**So my earlier judgement was wrong in an important way.** I concluded "agy cannot
open a 21 MB PDF, therefore *we* must serve the pages". The correct statement is
narrower: **agy** cannot; **claude can, including retrieval within the document**.

**Judgement.** The shared floor should be *"let the provider read the document
when it can, and fall back to serving pages when it cannot"* — not a single
strategy for all providers. Consequences:

- For claude-routed users, "reach other pages of the open PDF" **works today**
  with no new machinery, and ROADMAP 10 is not on their critical path.
- For agy (>4 MB) and for API providers, we still have to serve it. ROADMAP 10
  stays necessary, but for a narrower population than I claimed.
- The capability has to be **probed or declared per provider**, not assumed. The
  plugin's current "CLI providers get no tools" path is wrong for all three CLIs.

**codex is unmeasurable right now**, and for a config reason rather than a
capability one: `The 'gpt-5.6-sol' model is not supported when using Codex with a
ChatGPT account`. That is its own defect to file, not evidence about codex.

## 6. Open questions, not yet answered

1. ~~Does the provider reach the user's PDFs?~~ **Answered in §5** — claude does,
   agy does not above ~4 MB.
2. **API providers have no built-in search.** User's call: document it as a known
   limitation and leave it low on the roadmap — *"당장은 안정적으로 돌아가는 게
   우선"*. Not a blocker; a documented gap.
3. **12.8 s for the popover.** User's call: *"빠르면 빠를수록 좋은데 더 좋은 답변을
   얻을 수 있으면 이 정도도 나쁘지 않아."* Accepted as a target.
4. **Does dropping the LLM query expansion cost answer quality?** Still open, and
   the user is explicit that the sidechat trades time for quality: *"sidechat은
   시간 걸리더라도 답변 품질을 높이는 게 우선."* So this must be **measured**, not
   assumed — compare the evidence each path retrieves for the same question.
5. **Where exactly is agy's PDF ceiling?** Between 4.1 MB and 21 MB. Worth
   knowing if agy stays a routed provider for document questions.
