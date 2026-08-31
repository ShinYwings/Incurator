# Resilience Proposal: Fix The Local Pipeline Before The Network Ever Matters
Date: 2026-08-31 | Agent Persona: resilience_engineer

## 0. Thesis, stated up front

The briefing frames this as a network-permission bug: `read_url` got auto-denied,
`fetch_url` should have been reachable instead, therefore fix the tool grant and
the prompt's claim about it. That framing is not wrong, but it is answering the
less important question. The user's literal ask was **"find a reference's title
in a paper I have open."** That is not a web-retrieval task. It is a
local-document lookup task, and this repository already ships a complete,
working, zero-network pipeline built for exactly it:
`citationResolver.ts` + `citationContext.ts` parse the paper's own bibliography,
cache it, and hand the model the exact entry text for a cited work — no HTTP
call anywhere in that path. The pipeline exists, it is wired into the popover,
and it still produced an empty turn. That is the finding this proposal is built
around: **the answer was sitting in a page of the open PDF, the code that reads
that page and hands it to the model was already running, and a combination of
narrow gating conditions kept it from firing** — so the model, told (falsely,
per the briefing's own item 6) that it had no MCP tools and (falsely, per §4 of
this document — a NEW finding) that it had a local page-fetch tool it could use
instead, reached for the one tool its CLI runtime actually offered: `read_url`.

Sealing the network story is real and worth doing. But it treats a symptom.
Even with `fetch_url` correctly wired and correctly described, a citation asked
about "in the question, not the selection," or written in a bibliography with a
non-English heading, or expressed in a non-bracket citation style, will *still*
leave the model without the reference text in context and *still* send it
looking for a tool — just a better-behaved one. The fix that actually serves
"find a reference's title" is making sure the local mechanism reliably fires
for the shapes of that question people actually ask, so the network path is
needed only for what it should be needed for: content that truly is not in the
document.

## 1. Trace: what the popover actually puts in context (Design Q1)

### 1.1 The popover always has a selection, never an empty one

`quickQueryPopover.ts` has exactly two entry points that set `capturedSelection`
— `handleSelectionChange` (mouseup-triggered floating button,
`plugin/src/ui/quickQueryPopover.ts:207-237`) and `openForCurrentSelection`
(hotkey-triggered, `plugin/src/ui/quickQueryPopover.ts:244-262`). Both bail out
with a "select some text first" `Notice` (line 252) or simply remove the button
(line 215-216) when `selection.toString()` is empty. So by construction, every
popover turn carries a non-empty `this.capturedSelection` — the highlighted
passage. This matters because it rules out "the user asked with no selection at
all" as an explanation; whatever happened, it happened with real selected text
on hand.

### 1.2 The reference/citation resolution call, and what feeds it

`runQuery` (`plugin/src/ui/quickQueryPopover.ts:508-588`) calls
`resolveSelectionContextAsync` (defined in `plugin/src/context/pdfReferenceContext.ts:517-553`)
with **`this.capturedSelection`** as the text to scan — never `question`
(line 537-538). `resolveSelectionContextAsync` fans out into two independent,
parallel local resolvers on that same text (lines 532-548):

```
const [resolved, citations] = await Promise.all([
  resolveSelectionReferencesAsync(selectedText, source, fetchPageText, locatePages),
  resolveSelectionCitations(selectedText, /* documentId */, fetchPageText),
]);
```

- **`resolveSelectionReferencesAsync`** (`crossReferenceResolver.ts` +
  `pdfReferenceContext.ts:270-487`) handles *structural* pointers: "Section
  A4.2," "Figure 19.1," "Eq. (3)," "p.580." This is the machinery documented in
  the file's own header comment as mirroring AllenAI ScholarPhi / Semantic
  Reader. It is not what "a reference's title" usually means, though a
  bibliography entry pointed at by page number would resolve through it too.

- **`resolveSelectionCitations`** (`citationContext.ts:59-74`, backed by
  `citationResolver.ts`) is the one that actually answers "what is `[12]`":
  it extracts bracket-numbered citation markers from the text
  (`extractCitationNumbers`, `citationResolver.ts:183-210`), and if any are
  found, loads the document's bibliography (`loadBibliography`,
  `citationContext.ts:84-101`) and resolves each number against it
  (`resolveCitations`, `citationResolver.ts:245-260`), returning the literal
  bibliography line — title, authors, venue, year, exactly as printed.

### 1.3 The bibliography load is entirely local, and it is not cheap for no reason

`loadBibliography` → `scanForBibliography` (`citationContext.ts:103-130`) does
this, with **zero network I/O**:

1. Starts `TAIL_SCAN_PAGES` (= 6) pages from the physical end of the document
   and scans forward, because the module's own header comment records the
   measurement that motivated this: on the paper this was built against, the
   References heading was one page from the end, while scanning forward from
   page 1 would have meant reading the whole paper first.
2. On the first page whose text contains the literal heading pattern (parsed
   by `parseBibliography`, gated by `BIBLIOGRAPHY_HEADING`,
   `citationResolver.ts:45,65-71`), it fetches up to `CONTINUATION_PAGES` (= 5)
   more pages and folds them in via `parseBibliographyContinuation`
   (`citationResolver.ts:86-89`) — because, again per the measured comment, a
   references section commonly spans several pages and prints its heading
   exactly once.
3. Every page fetch in this chain goes through `fetchPageText`, which in the
   popover is `this.plugin.fetchActivePdfPage(pageNum, pinnedDocumentId)`
   (`quickQueryPopover.ts:562-563`) — a call into the plugin's own PDF.js-backed
   viewer state, already holding the document bytes in memory because the user
   has the file open. No HTTP request, no `agy`, no MCP round-trip.
4. The result is cached per `documentId` (`citationContext.ts:37,88-101`,
   `documentKey` fallback wired at `quickQueryPopover.ts:547-551` specifically
   because Obsidian's native PDF viewer and untracked PDFs have no
   `searchDocumentId`) so a second question about a different citation in the
   same paper costs nothing further.

This is a genuinely well-built, already-shipped local answer path. The
question this proposal actually has to answer is not "does it exist" — it does
— but "why did it not fire for this user's question."

### 1.4 The four conditions under which the reference list does NOT reach the model

Tracing the gates in order of how likely each is to be what happened:

**(a) The citation marker is not a `[N]`-bracket.** `extractCitationNumbers`
runs one regex, `BRACKET_GROUP = /\[(\d{1,3}(?:\s*[,–—-]\s*\d{1,3})*)\]/g`
(`citationResolver.ts:175`). It matches `[8]`, `[8, 9]`, `[1-3]` and nothing
else. `resolveSelectionCitations` has an even earlier short-circuit: it probes
the selection against a synthetic 999-entry bibliography (`PROBE`,
`citationContext.ts:80-82`) before touching the document at all
(`citationContext.ts:69`), and if that probe finds nothing, the whole
mechanism — including the tail scan that would otherwise find and cache the
bibliography — never runs. A paper citing in author–year style
("Vaswani et al. (2017) showed…"), a paper using superscript numerals that PDF
text extraction flattens to bare digits with no surrounding brackets, or a
paper using parenthetical numerics ("(12)" instead of "[12]") all produce zero
matches, unconditionally, regardless of how good the bibliography scan
downstream is. This is a real, structural, format-based gap and it is common —
author–year is the dominant citation style outside CS/ML venues.

**(b) The bibliography heading is not literally English.**
`BIBLIOGRAPHY_HEADING = /^[\s#*]*(references|bibliography|works cited)[\s:]*$/im`
(`citationResolver.ts:45`). `parseBibliography` (`citationResolver.ts:65-71`)
returns an empty `Map` immediately if no line matches this pattern — and that
empty map propagates silently all the way up through `collectBibliography`
(`citationResolver.ts:99-119`) and `scanForBibliography`
(`citationContext.ts:103-130`) with no diagnostic anywhere. A paper whose
references section is headed "참고문헌," "Referências," "Literatur," or any
non-English equivalent is functionally invisible to this parser even though
the page holding it was fetched, read, and sitting right there in
`texts.get(pageNum)`. This is exactly the shape of defect the resilience angle
cares about: the byte-for-byte content the model needed was in the process's
own memory and the code discarded it for a vocabulary mismatch.

**(c) Citation/reference extraction reads only the SELECTION, never the
QUESTION — and this is inconsistent with the sidebar's own design.**
This is the finding I consider the strongest candidate explanation, because it
requires no assumption about paper language or citation style at all — it
fires on the ordinary, unremarkable way people ask this kind of question.
Compare the two call sites directly:

```
// popover — quickQueryPopover.ts:537-538
resolveSelectionContextAsync(
  this.capturedSelection,      // the highlighted passage
  { ...activeContext.pdfPage, ... },
  (pageNum) => this.plugin.fetchActivePdfPage(pageNum, pinnedDocumentId)
)
```

```
// chat sidebar — ChatSidebarView.ts:1844-1845
resolveSelectionReferencesBlockAsync(
  query,                        // the user's TYPED chat message
  { outline, windowPages, ... },
  async (pageNum) => { ... }
)
```

`query` at that call site is the sidebar's chat input: the caller
(`ChatSidebarView.ts:1455-1459`) invokes
`buildIncuratorProviderContext(activeCtx, lastUserMessage?.content || "", ...)`
— literally the text of the user's most recent chat message. I.e. the sidebar
treats **what the user typed** as the text to scan for citation numbers,
because in a chat interface there usually is no separate "selection."
The popover has both a selection AND a free-typed question box, and it feeds
only the selection into extraction. `quickQueryContext.ts`'s
`buildQuickQueryMessages` bears this out: `args.question` is placed into the
prompt purely as `` `Question: ${args.question}` `` (line 222) and is never
passed to any reference/citation extractor.

So: a user who highlights a passage and then types "이 12번 레퍼런스 제목이
뭐야?" or "what's the title of reference 12" — putting the citation NUMBER in
their question rather than re-selecting the literal `[12]` marker from the
passage — gets nothing from either resolver, on the popover, even on a paper
that is entirely well-formed (English heading, bracket-numbered citations,
bibliography within the tail-scan window). The exact mechanism built to answer
this exact question never sees the number, because it never looks at the box
the number was typed into. This is not a hypothetical: it is the natural
phrasing of "find a reference's title" as a *question about the document*
rather than as *re-selecting the citation marker itself*, and it is currently
un-tested — `quickQueryContext.test.ts`'s pointer-resolution tests
(`plugin/src/context/quickQueryContext.test.ts:65-135`) all put the pointer in
`selectedText`; none puts it in `question`.

**(d) The tail-scan window is bounded and silent on a miss.** `TAIL_SCAN_PAGES
= 6` and `CONTINUATION_PAGES = 5` (`citationContext.ts:26,29`) are sound,
documented, measured defaults — but a paper with supplementary material,
appendices, or an author-bio page after the references (common) can push the
References heading further than 6 pages from the physical end, and
`scanForBibliography` returns an empty map with no signal that it looked and
found nothing versus never looked at all. `CacheEntry.searched: true`
(`citationContext.ts:31-35`) records the negative result for caching purposes
only — it is never surfaced to the prompt.

## 2. Where the jetski auto-deny text becomes the user's result (Design Q2)

This is a precise mechanical trace, not a paraphrase, because "the user got
nothing" undersells what actually happens — the user does not see a blank
bubble, they see a paragraph of CLI permission diagnostics presented with the
same styling as a real answer.

1. `LLMClient.ts:2166-2172`: when the antigravity provider's stdout is empty
   after `cleanCliOutput` (which is a no-op for antigravity —
   `LLMClient.ts:3208-3210` only filters for `provider === "openai"`), the code
   falls back to `extractAntigravityAnswerFromStderr(fullStderr)`
   (`messageUtils.ts:296-304`).

2. That function strips ANSI codes and drops any line matching
   `isAntigravityStatusLine` (`messageUtils.ts:268-294`) — spinner glyphs,
   `"thinking/processing/generating/starting/loading/initializing/connecting/
   authenticating/requesting/waiting"`-prefixed lines, `"mcp servers
   available/using tool/running tool/calling tool/tool use/tool result"`-
   prefixed lines, and `"antigravity|gemini ... generating|thinking|
   processing"` lines. **The jetski auto-deny explanation matches none of
   these patterns.** It is not a spinner, it does not begin with any of the
   listed progress verbs, and it is not the `"MCP servers available"`
   announcement — it is agy's own explanation of why a *specific tool call*
   was refused. It survives the filter intact and becomes
   `recoveredAntigravityAnswer` at `LLMClient.ts:2168-2170`.

3. `LLMClient.ts:2180-2182` emits that recovered text as a normal streaming
   chunk (`onChunk({ text: recoveredAntigravityAnswer, done: false })`) —
   there is no branch that distinguishes "recovered from stderr because it
   looked like a real answer that got mis-routed" from "recovered from stderr
   because it was the only thing there, including diagnostics."

4. `LLMClient.ts:2188-2241` computes `emittedAnswer` from `trimmedOutput`
   (which is now the jetski text, since `fullOutput` was overwritten at line
   2170). Because `emittedAnswer.length` is **not** zero, the code skips both
   the "CLI failed, no answer" branch (`code !== 0 && emittedAnswer.length ===
   0`, line 2221) and the "exit 0 but no answer" branch (`emittedAnswer.length
   === 0`, line 2224) — the two branches that would have produced a real error
   message telling the user something went wrong. Execution falls through to
   the final `else` at lines 2237-2241:
   ```
   onChunk({ text: "", done: true });
   this.recordUsage(provider, observedUsage);
   resolve(fullOutput);
   ```
   `fullOutput` here **is** the jetski explanation. It resolves as a
   successful completion, identically to a genuine model answer.

So: the mechanism this codebase built specifically to rescue a genuine answer
that agy occasionally routes through stderr instead of stdout (proven correct
and tested at `llmClient.test.ts:908-919`, `"recovers answer-like stderr text
while dropping progress lines"`) has no way to tell a real rescued answer apart
from a rescued *error message*, and the permission-denial text is close enough
in shape — plain sentences, no spinner glyphs, no recognized progress verb —
to pass as one. The user sees a fluent paragraph of prose explaining
`read_url`, `settings.json`, and `--dangerously-skip-permissions`, formatted
and delivered exactly like an answer to their question about the paper. This
is worse than a blank turn: a blank turn signals failure; this signals success
while being infrastructure noise.

There is no existing test that would catch this. `llmClient.test.ts:908-919`
tests the *positive* case (a genuine answer accidentally on stderr should
survive); nothing tests the *negative* case (a CLI-emitted policy/error
message on stderr should NOT survive as an answer).

## 3. Degradation options for an auto-denied / empty turn (Design Q3)

This section is not my primary angle, but the task requires me to weigh it
honestly, so I do.

**Option A — classify-and-reject at the recovery boundary.** Give
`extractAntigravityAnswerFromStderr` (or a wrapper around its call site) a
second check: does the recovered text match the shape of a CLI
permission/tool-denial diagnostic (e.g. contains `"no output produced"` +
`"auto-denied"` + a `permissions.allow` mention — the phrasing is a fixed
template agy emits, not free-form model prose)? If so, do NOT treat it as
`recoveredAntigravityAnswer`; instead let `emittedAnswer` stay empty so the
EXISTING `emittedAnswer.length === 0` branch (`LLMClient.ts:2224-2236`) fires,
producing the honest error the codebase already has: *"antigravity returned no
answer (empty response) ... this usually means quota/capacity is exhausted,
the request timed out, or the model returned nothing."* That message is not
perfectly accurate for this specific cause, but it is honest about the shape
of the failure — the user is told something went wrong, not handed diagnostics
as content.
- **Cost**: purely mechanical, a pure-string classifier, unit-testable with the
  literal string from the briefing, zero agy invocations to build or verify.
  Does not recover an answer — the user still needs to retry or the model
  still needs better context (see Option C).

**Option B — retry once with an explicit no-tools instruction.** On detecting
the same shape as Option A, re-invoke the CLI with an appended system
instruction such as "You have no tool access this turn; answer only from the
context already provided." I recommend against this as the primary fix, for
three concrete reasons grounded in this codebase rather than in the abstract:
1. It doubles CLI cost and latency for every occurrence, including
   genuinely quota-exhausted turns misclassified into this bucket — and quota
   exhaustion is explicitly the FIRST thing `isQuotaErrorMessage` /
   `isUnambiguousQuotaError` already try to catch earlier in the same function
   (`LLMClient.ts:2088-2092, 2210-2220`), so a retry heuristic here would be
   racing an existing, more specific quota-detection path rather than
   complementing it.
2. Retrying does not fix the reason the model reached for a tool. If the
   reference text genuinely never made it into context (per §1.4), a
   "no-tools" retry does not conjure that text — it produces a *different*
   failure mode, a confidently wrong or hedged answer with no citation
   grounding, which is arguably worse than an honest "I couldn't find this"
   because it looks like an answer.
3. It directly works against the instruction already written into
   `boundaryConstraints`'s `local-only` case
   (`promptRegistry.ts:70-85`): *"Answer from the provided context and any
   page you fetch or read first; where those do not cover the question,
   answer it from your general knowledge of the field rather than stopping."*
   That sentence already tells the model what to do when it lacks specific
   grounding. The model did not follow it here because — per §4 below — it was
   told it had a tool path that does not exist on this code path at all, not
   because the instruction is missing.

**Option C — pre-empt: make sure the content is in context before the CLI is
spawned, so the tool call is never reached for.** This is what §4 below
proposes concretely. It costs nothing at answer time (no retry, no doubled
latency), it directly serves the literal user request rather than papering
over its absence, and it shrinks — without eliminating — the population of
turns that ever reach the Option A/B decision at all.

**Recommendation**: Option C as the primary investment (this is the
resilience-engineer's actual proposal, §4), Option A as the mandatory backstop
for what Option C cannot reach (content genuinely absent from the document,
citation styles out of scope for this pass, vault-wide questions unrelated to
the open PDF). Option B is explicitly NOT recommended for the reasons above —
it should be treated as a considered-and-rejected alternative in the master
plan, not a follow-up TODO, unless a future measurement shows Option A's
error-message outcome is unacceptably common in practice.

## 4. The cheap, high-value LOCAL fix (Design Q4)

Five concrete changes, ordered by cost/value, each scoped to files already
identified above. None require touching the network story at all.

### 4.1 Feed the question into extraction, not just the selection

The fix is not "concatenate `selectedText + question` and extract once." The
position-sensitive parts of `crossReferenceResolver.ts` — specifically
`resolveWithNearbyPageHints` (`crossReferenceResolver.ts:634-682`), which
matches an unresolved reference to an explicit-page reference within 64
characters of it (`distance > 64` cutoff, line 657) — rely on `ref.index`
meaning "character offset within one coherent span of prose." Concatenating
two unrelated strings (a highlighted passage and a separately-typed question)
would put both sets of matches into one offset space where a citation typed at
the start of the question could spuriously "adjacency-match" against a page
reference at the end of the selection, or vice versa, corrupting a heuristic
that is already carefully tuned (see the extensive comments at
`crossReferenceResolver.ts:634-660` about why the 64-char bound exists).

The correct shape is two independent extraction passes over the same context,
merged after resolution:

```ts
// pdfReferenceContext.ts — sketch, not the final signature
export async function resolveSelectionContextAsync(
  selectedText: string,
  question: string,          // NEW — the popover's free-typed question
  source: PdfReferenceSource | undefined,
  fetchPageText: ...,
  locatePages?: ...
): Promise<{ block: string; provenance: ProvenanceRecord }> {
  const [selResolved, qResolved, selCitations, qCitations] = await Promise.all([
    resolveSelectionReferencesAsync(selectedText, source, fetchPageText, locatePages),
    resolveSelectionReferencesAsync(question, source, fetchPageText, locatePages),
    resolveSelectionCitations(selectedText, citationSource, fetchPageText),
    resolveSelectionCitations(question, citationSource, fetchPageText),
  ]);
  const resolved = dedupeReferences([...selResolved, ...qResolved]);
  const citations = dedupeCitations([...selCitations, ...qCitations]); // by .num
  ...
}
```

`dedupeCitations` is trivial (citations already dedupe within one call by
`num`, `citationResolver.ts:250-256` — the same `Set<number>` pattern extends
across the merge). `dedupeReferences` needs a key of `kind + label` (or
`kind + sectionNumber/objectNumber`) since `ResolvedReference` has no natural
identity today; this is a few lines, not a redesign. The bibliography-load
cost is unaffected — `loadBibliography` is already cached per document
(§1.3.4), so running the citation extractor twice against the same document
costs one cache hit, not a second scan.

Call-site change in `quickQueryPopover.ts:537-538`: pass `question` alongside
`this.capturedSelection`. This is the cheapest, highest-value change in this
proposal — it requires no new format support, no new language support, just
routing text that is already sitting in a local variable to a resolver that
is already running.

### 4.2 Structural (not vocabulary-list) bibliography heading detection

Rather than growing `BIBLIOGRAPHY_HEADING` into a hardcoded list of translated
headings (which only ever covers languages someone remembered to add — a
half-measure that will keep failing silently for the next language), add a
structural fallback that fires independent of wording: a short line (say,
under 4 space-separated tokens, matching the existing heading candidates'
shape) immediately followed by two or more `ENTRY_START`-shaped lines
(`citationResolver.ts:48`, already used to detect entries) is treated as a
bibliography heading even when its text does not match the English pattern.
Pseudocode:

```ts
const STRUCTURAL_HEADING_CANDIDATE = /^[\s#*]{0,4}\S+(\s+\S+){0,3}[\s:]*$/;

function findHeadingLine(lines: string[]): number {
  const vocab = lines.findIndex((l) => BIBLIOGRAPHY_HEADING.test(l));
  if (vocab !== -1) return vocab;
  for (let i = 0; i < lines.length - 1; i++) {
    if (!STRUCTURAL_HEADING_CANDIDATE.test(lines[i])) continue;
    if (ENTRY_START.test(lines[i + 1]) && ENTRY_START.test(lines[i + 2] ?? "")) {
      return i;
    }
  }
  return -1;
}
```

This keeps the existing English-vocabulary path as the fast, precise first
check (so ordinary papers are unaffected) and only falls through to the
structural check when it fails — which is exactly when a non-English or
unusually worded heading is the explanation. It is genuinely testable without
knowing every language's word for "References": feed it "참고문헌" followed by
two `[N] ...`-shaped lines and it should pass, by structure, without the code
ever encoding the Korean word anywhere.

### 4.3 Parenthetical numeric citations — explicitly declined this pass

Extending `BRACKET_GROUP` to also match `(12)` looks cheap and is not: it
collides head-on with the already-existing, already-tested equation-label
carve-out. `crossReferenceResolver.ts`'s `DISPLAY_EQUATION_LABEL_RE`
(line 309) exists precisely to claim bare parenthesised numbers like `(19.11)`
for equations, and `citationResolver.test.ts` already asserts the citation
side must NOT claim them (`"ignores an equation label, which is parenthesised
not bracketed"`, line 132). A numeric-only single-digit parenthetical, `(12)`,
is genuinely ambiguous between "citation 12" and "equation 12" without
document-level context neither resolver currently shares with the other. I am
declining this as a Non-Goal for this proposal rather than shipping a
regex that silently reopens that collision; it belongs in a follow-up that
gives both resolvers a shared disambiguation pass (e.g., prefer equation
only when a display-math line or a nearby `=`/operator character supports it,
which `DISPLAY_EQUATION_MATH_RE`, line 310, already computes for a different
purpose and could be reused).

### 4.4 Name a scan miss instead of staying silent

When `collectBibliography` returns empty after the full tail-scan window has
been exhausted (i.e., `scanForBibliography` reaches `lastPage` without ever
returning early), emit a short, honest status note into the context — mirrored
on the existing `UNRESOLVED_NOTE` pattern (`crossReferenceResolver.ts:716-725`)
that already tells the model "not found" rather than asserting absence it
cannot verify:

```
<citation_lookup_status note="Scanned the last N pages of this document for a
References/Bibliography section and did not find one recognizably formatted.
If the paper has one outside that range, or in a format not detected here,
answer from what the selection and surrounding pages establish rather than
guessing a title." />
```

This costs nothing at scan time (the negative result is already computed and
cached — `citationContext.ts:99`, `searched: true`) and directly narrows the
population of turns that fall through to "model has nothing, reaches for a
tool" — it gives the model the same honest permission to answer from what it
has, or say plainly it could not find the bibliography, that `UNRESOLVED_NOTE`
already grants for structural cross-references.

### 4.5 Fix the prompt's claim about the local-fetch tool on the CLI path — the finding that closes the loop

This is the piece that most directly explains why the model reached for
`read_url` specifically, and it is a NEW finding beyond what `00_problem.md`
already established for MCP.

`boundaryConstraints`'s `"local-only"` case
(`promptRegistry.ts:70-85`) tells the model: *"Your only tools read the PDF the
user already has open, and nothing else: you may fetch a page of that document
by number to follow a reference instead of telling the user to navigate
there... where `read_pdf_page_image` is among the tools you were given..."*

This describes `fetch_pdf_page` / `read_pdf_page_image` / `search_pdf_anchor`
— the local tools defined in `localPdfTools.ts` and injected via
`shouldInjectLocalTools` (`messageUtils.ts:60-77`). But trace that function's
actual gating:

```ts
export function shouldInjectLocalTools(
  toolPolicy: ToolPolicy, hasLocalRunner: boolean, useCli: boolean
): boolean {
  switch (toolPolicy) {
    case "none": return false;
    case "auto":
    case "local-only":
      if (useCli) return false;      // <-- HERE
      return hasLocalRunner;
    ...
  }
}
```

`useCli` is computed by `shouldUseCli` (`LLMClient.ts:1788-1791`):
```ts
private shouldUseCli(_messages: LLMMessage[]): boolean {
  if (this.settings.provider === "ollama" || this.settings.provider === "deepseek") return false;
  return true;
}
```

`useCli` is `true` for **every provider except ollama and deepseek** —
including `antigravity` (agy), which is the provider in this bug report. This
is a locked decision, not an oversight: `llmClient.test.ts:778`,
`"never injects local tools on CLI providers (locked decision)"`, tests
exactly this and the comment at `messageUtils.ts:56-58` explains why (keeping
the v0.23.0 CLI sandbox contract untouched — a CLI subprocess is not driven
through the plugin's own tool-call loop the way a direct API call is).

The consequence: on the `agy` path, `injectLocal` is `false`
unconditionally (`LLMClient.ts:1343`), `localTools` is `[]`
(`LLMClient.ts:1346`), and the request that reaches `agy` carries **no
plugin-provided tools of any family** — the `_streamChatSingleTurn` call at
`LLMClient.ts:1348-1356` passes `tools: undefined`. The `fetch_pdf_page`
capability the prompt describes to the model in the exact sentence quoted
above **does not exist on this execution path, structurally, for any CLI
provider, always** — not "sometimes denied," not "needs a permission grant"
like the MCP case — it is simply never offered as a callable function.

So the model on this turn was told two things about its tool access, one of
which the briefing already establishes was false (no MCP tools — actually had
`mcp(*)`) and one of which this document establishes is *also* false in the
opposite direction (a local page-fetch tool it could use "instead of telling
the user to navigate there" — never actually offered). Both misstatements
point the model at the SAME conclusion: reach outside the sanctioned local
mechanism, because the prompt describes a local one that isn't there. What
`agy` actually offers, once the model looks for any way to get more
information, is its own native toolset — `read_url` among them — because that
is what genuinely exists on this path, unlike either of the two capabilities
the prompt claimed.

**The fix**: correct the `"local-only"` case in `boundaryConstraints` so its
CLI-path wording matches what `shouldInjectLocalTools` actually delivers.
Since `boundaryConstraints` does not currently branch on `useCli` (it only
branches on `toolPolicy`), and `promptRegistry.ts` is deliberately import-free
and sits below both consumers (comment at lines 10-13), the surgical options
are either (a) pass a `hasLocalTools: boolean` alongside the existing
`SurfaceProfile` so the function can honestly render either wording, computed
by the caller from the same `shouldInjectLocalTools` check already run before
the prompt is built, or (b) rewrite the `"local-only"` prose to describe only
what is unconditionally true on every path that uses it — dropping the
tool-invocation language entirely and keeping only the passive "answer from
provided context and any page you fetch or read first" framing, since for the
CLI path there is no "fetch" to promise. Option (a) is more precise (the
popover DOES get the local tools on a direct-API provider, e.g. a future
Claude-API-backed popover) but touches an extra parameter across two files;
option (b) is one string edit in `promptRegistry.ts` and is honest on every
path today, at the cost of being needlessly modest on the (currently
nonexistent) direct-API popover case. Recommend (b) for this pass — it is
correct everywhere the popover actually ships today (antigravity, codex,
claude CLI are the supported CLI-spawned providers) and does not block on a
larger plumbing change. This should land in the SAME edit that fixes the MCP
wording (problem.md item 5-6), since both are the identical defect class in
the identical function, and shipping them separately risks the fix for one
re-introducing exactly the inconsistency the other just closed.

With 4.1–4.4 reducing how often the model lacks the reference text, and 4.5
removing the false promise that sent it looking for a substitute tool, what
remains for the model in the genuinely-uncovered case is exactly the sentence
`boundaryConstraints` already contains: answer from general knowledge or say
plainly the document doesn't establish it, rather than reaching for anything.

## 5. Testing without ever invoking the real `agy` CLI (Design Q5)

Invoking `agy` is forbidden — it spends the user's own account/quota — and
none of the proposed tests need it. Every function touched above is pure or
takes an injected fetcher; the existing test suite already proves this pattern
works (`llmClient.test.ts`'s CLI-settings tests read/write a real
`settings.json` file but never spawn the `agy` binary; the stderr-recovery
tests operate on literal fixture strings).

**`plugin/src/context/citationResolver.test.ts`** (extend, pure functions,
no I/O):
- New case in `describe("extractCitationNumbers")`: assert the CURRENT
  behavior that author-year and parenthetical forms are NOT matched (locks in
  the Non-Goal from §4.3 as a documented, intentional boundary rather than an
  silent gap — so a future change to this regex has to consciously touch this
  test).
- New case in `describe("parseBibliography")`: feed
  `"참고문헌\n[1] Vaswani et al. Attention is all you need. 2017.\n[2] ..."`
  and assert the §4.2 structural fallback returns a non-empty map with the
  correct entries, once implemented. This test should be written to FAIL
  against the current code first (proving the gap), then pass after 4.2 lands.
- New case verifying the structural fallback does NOT false-positive on an
  ordinary short heading followed by an ordinary numbered list that is not a
  bibliography (e.g. "Steps\n1. Do this\n2. Do that") — required per the
  honest Con in §6 below.

**`plugin/src/context/citationContext.test.ts`** (extend,
`resolveSelectionCitations` already takes an injected `fetchPageText`, no
process spawn):
- New case: with a bibliography reachable only via the §4.2 structural
  detector, confirm `resolveSelectionCitations` still resolves end-to-end
  through the existing cache/scan machinery — proves the fix composes with the
  existing scan-and-cache logic, not just the parser in isolation.

**`plugin/src/context/quickQueryContext.test.ts`** (extend
`buildQuickQueryMessages` tests, pure function, fixture-driven — see existing
`describe` block at line 65):
- New case mirroring `"injects a resolved-cross-references block when the
  selection is a pointer"` (line 65) but with the pointer/citation number in
  `question` and an unrelated `selectedText` — asserts the merge from §4.1
  reaches the final prompt. This is the test that most directly encodes "a
  citation typed in the question, not re-selected from the passage, still
  resolves" — the concrete failure mode this proposal centers on.

**`plugin/src/agent/llmClient.test.ts`**, inside the existing
`describe("Antigravity CLI stderr recovery")` block (lines 901-926, pure
string function, zero process spawn):
- New case: feed `extractAntigravityAnswerFromStderr` the literal string from
  `00_problem.md`'s "The report" section (`"jetski: no output produced — a
  tool required the \"read_url\" permission that headless mode cannot prompt
  for, so it was auto-denied. Add an allow-rule..."`) and assert it is
  classified as a denial/diagnostic, NOT as `recoveredAntigravityAnswer` (once
  Option A from §3 is implemented as a second predicate alongside
  `isAntigravityStatusLine`). Written against current code, this test fails
  today — that failure IS the reproduction of the bug from `00_problem.md`,
  entirely offline.
- New case: confirm the existing "recovers a genuine answer from stderr" test
  (line 908-919) still passes after the new predicate is added — proves the
  fix does not regress the mechanism it is built to distinguish from.

**`plugin/src/context/promptRegistry.test.ts`** (extend
`describe("boundaryConstraints")`, pure string function):
- New case: assert the `"local-only"` string, after §4.5, contains no claim of
  a tool capability (`fetch a page`, `read_pdf_page_image`) that
  `shouldInjectLocalTools("local-only", /*hasLocalRunner*/ true, /*useCli*/
  true)` would contradict — i.e. a lightweight cross-check between the prompt
  string and the actual gating function, so this specific defect class (prompt
  promises what code does not deliver) cannot silently reopen the way it did
  for MCP. This test imports both `boundaryConstraints` and
  `shouldInjectLocalTools` and is pure on both sides.

All of the above run under `cd plugin && npx vitest run -c ./vitest.config.ts`
(per `AGENTS.md`/`CLAUDE.md` §9), entirely offline, and the plugin's separate
`npx tsc --noEmit` gate from the same directory. None require a live `agy`
binary, a network connection, or spending the user's account quota — the
existing test suite already establishes every technique used above (fixture
strings for `messageUtils`, injected async fetchers for the resolvers,
in-memory settings.json round-trips for the CLI config writer that don't touch
the real binary).

## 6. Pros & Cons

### Pros

- **Directly serves the literal request.** "Find a reference's title" is a
  local-document lookup, and every fix above makes the pipeline built for
  exactly that more likely to fire, using code that already ships, is already
  tested in its happy path, and needs no new architecture, no new permission
  surface, and no SSRF-adjacent review.
- **Shrinks the population that ever reaches the network/degradation
  question**, rather than making that path more forgiving. Every turn resolved
  locally is a turn that never touches `agy`'s own tool registry at all, so it
  cannot be affected by whatever permission story the other proposals land on.
- **The §4.5 finding is a strict net positive independent of the MCP
  decision.** Whether the popover ends up with `fetch_url` wired in or not, the
  model should never be told about a `fetch_pdf_page` tool it structurally
  cannot receive on the CLI path. This is the same class of harm as the MCP
  fiction the briefing already condemns, just discovered in the opposite
  direction (promising a capability, not denying one falsely described as
  absent), and it should be fixed in the same prompt-registry edit.
- **Everything proposed is a pure function or takes an injected fetcher.**
  Every test named in §5 runs offline, fast, and without spending the user's
  `agy` account — matching the hard constraint on this whole debate.
- **Nothing here requires a schema change, a new tool, or a new permission
  grant** — it is entirely inside `plugin/src/context/` and one string in
  `promptRegistry.ts`, which keeps the blast radius small and the stability
  tiebreaker satisfied without giving up capability.

### Cons — what this does NOT solve, stated plainly

- **Does not help when the user genuinely wants a live web lookup** — "has
  this been cited since," "what's the DOI," "is there a newer version of this
  paper." That is a real `fetch_url` use case and this proposal deliberately
  leaves it to whichever proposal owns the network-tool story. §4 makes the
  local path good enough that fewer *reference-title* questions need the
  network, not that the network path becomes unnecessary.
- **Author–year citations remain entirely unresolved.** "(Smith et al., 2020)"
  is not a two-line regex tweak — a real fix needs a new extraction grammar
  keyed on surname+year pairs, fuzzy-matched against bibliography entries
  (which don't reliably print in a fixed position relative to the marker the
  way `[N]` does). I am naming this as a real, likely-common gap, not solving
  it here; it is a legitimate follow-up milestone, not a "cheap fix."
- **Parenthetical numeric citations `(12)` remain unresolved by design**, per
  §4.3's decision to decline rather than risk reopening the equation-label
  collision. A paper using that style still falls through to whatever the
  network/degradation proposal decides for it.
- **The structural heading detector (§4.2) is a heuristic and needs a real
  red-team pass**, not just the positive test case — a short line followed by
  two numbered lines is a plausible false-positive shape (a numbered
  "Contents," "Steps," or "Limitations" section). I've named the required
  negative test in §5, but writing the detector defensively enough to pass it
  is real work, not a rubber stamp.
- **`TAIL_SCAN_PAGES` / `CONTINUATION_PAGES` stay at their current bounds.** A
  bibliography further than 6 pages from the physical end, or spanning more
  than 5 continuation pages, is still silently missed by the *parser* — §4.4
  only makes that miss honest (a status note) rather than fixing the scan
  depth. Widening the scan trades directly against the documented "bounded so
  a bad locator can't turn one question into dozens of fetches" constraint
  already in `pdfReferenceContext.ts`; re-balancing that budget is a
  performance/product tradeoff outside a resilience-focused proposal and
  should be measured (how often does a real paper's bibliography sit beyond
  page −6?) before anyone touches the constant.
- **A truly rasterized or absent bibliography (no text layer) is still a dead
  end for this whole pipeline**, local or networked — nothing here reads
  pixels. That case needs the vision-capable `read_pdf_page_image` escalation
  the prompt already describes for OTHER content types, and even that tool is
  unavailable on the CLI path per §4.5's own finding. This proposal narrows
  the empty-turn population; it does not claim to eliminate it, and §3's
  Option A remains the necessary backstop for whatever is left.
- **This proposal does not itself decide what happens when all of the above
  still comes up empty.** §3 recommends Option A as the minimum backstop but
  implementing it is not scoped here in detail (predicate design for
  recognizing agy's specific denial-message template needs its own care so it
  doesn't over-fire on a genuine answer that happens to mention "permission"
  or "access" in its prose — a red-team question for whoever owns that piece).
