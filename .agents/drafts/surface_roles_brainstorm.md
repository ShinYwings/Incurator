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

## 5. Open questions, not yet answered

1. **Does the provider's search reach the user's own PDFs at all?** No — 21 MB
   fails. So does "search other pages of the open PDF" mean *we* index and serve
   them (ROADMAP 10), or that we hand the model a page range to `read_file`?
   Untested: whether agy can read a *small* PDF, and whether a text extract we
   write to a temp file is a legitimate channel.
2. **What happens on a raw-API provider?** The user excluded them ("api 제외").
   DeepSeek has no built-in search, so the shared floor is not uniform across
   providers. Does the popover degrade, or does it fall back to our retrieval and
   accept the latency?
3. **Is 12.8 s the right target for the popover?** It is 5–8× better than today
   but still not instant.
4. **Should the sidechat keep the LLM query expansion at all?** It costs 34–50 s
   and its own docstring says the ASCII fallback is a real query for exactly the
   mixed-script input this vault produces.
