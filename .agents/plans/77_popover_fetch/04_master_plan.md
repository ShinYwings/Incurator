# v0.77.0 Master Implementation Plan — the popover answers from the paper it is holding

## 0. What changed after the Arena ran

The Arena was briefed on the wrong problem, and the user corrected it mid-flight
(2026-08-31):

> 내가 저때 참고문헌의 제목을 물어본거는 같은 pdf 파일 안에 있는 마지막 장에
> 적혀있는거 찾는거거든?

The reference title was in the paper's own bibliography, in its last pages. The
network was never involved. `fetch_url` — which the briefing built its whole
decision around, and which the user approved under that framing — fixes nothing
here. The approval stands and is not revoked, but it is no longer this release's
subject.

`03_proposal_degradation` had independently reached the same conclusion before
the correction arrived, which is the only reason the Arena is still usable.

## 1. Objective

A Quick Query popover question about a citation in the open PDF is answered from
that PDF's own bibliography, with no tool call and no network. When a tool IS
denied, the user sees something useful instead of the CLI's internal diagnostic
presented as an answer.

## 2. Explicit Non-Goals

- Granting `read_url`. Never; an unguarded fetcher on the untrusted-material
  path is what `incurator_fetch` exists to avoid.
- Per-invocation MCP server scoping. `02_proposal_enforcement` established by
  static inspection of the installed binary — never executing it — that agy has
  no `--mcp-config` / `--allowed-mcp-servers` flag, and that the registry is one
  global file every invocation reads at startup. Any per-call narrowing is a
  TOCTOU race with a concurrent sidebar call. Not attempted.
- Narrowing the popover's OS-sandbox write roots. Real, and genuinely
  per-invocation, but it is containment work on a release whose subject is a
  wrong answer. It goes to ROADMAP, not here.
- Author-year and parenthetical citation styles. The report is about `[N]`.
- Making the popover fetch URLs. Approved, unrelated to this bug, deferred.

## 3. Strict Quality Conditions & Release Gates

Each phase passes before the next begins:
`npx vitest run -c ./plugin/vitest.config.ts`, `cd plugin && npx tsc --noEmit`,
`scripts/backend-check ruff|mypy|pytest`. The `agy` CLI is never invoked; the
conftest guard and the argv scan stay intact.

## 4. Locked Design Decisions

### D1. The popover resolves citations from the typed question, not only the selection

`quickQueryPopover.ts:537` passes `this.capturedSelection` into
`resolveSelectionContextAsync`. The chat sidebar passes the typed message
(`ChatSidebarView.ts:1455`). So a user who types "reference 12의 제목이 뭐야?"
without dragging `[12]` gets no citation resolution at all — on a paper whose
bibliography is sitting in memory.

**Decision:** the popover resolves over the selection AND the question. Union,
not replacement: a selected `[12]` must keep working when the question does not
repeat the number.

### D2. Stop promising a tool that does not exist on this path

`shouldInjectLocalTools` returns `false` whenever `useCli` is true — for every
policy, `local-only` included (`messageUtils.ts:60-77`). `shouldUseCli` is true
for antigravity. So the popover's own prompt promising *"you may fetch a page of
that document by number to follow a reference"* is false on the surface the user
was actually using.

**Decision:** the prompt states what is true for the provider in hand. A model
told it has a page-fetching tool, that finds it absent, reaches for the nearest
substitute — which is exactly `read_url`, the one URL tool not in the allow-list.
This is the root of the reported failure.

**Rejected:** exposing the PDF page reader as a second local MCP server, the way
`incurator_fetch` is exposed. It would work and it is the better long-term shape,
but it is a new always-on subprocess and a new tool contract in a release that
exists to fix a wrong answer. ROADMAP.

### D3. The same prompt must stop claiming "NO MCP tools" on the agy path

True for API providers, where the plugin decides injection. False for agy, which
reads its own registry — `syncAgyMcpConfig()` runs unconditionally in the
antigravity branch and `ephemeral` only empties `--add-dir`.

**Decision:** wording becomes provider-aware. `01_proposal_prompt_contract`'s
shape is adopted — a small exhaustive union threaded as a parameter, NOT a new
`ToolPolicy` value, because `ToolPolicy` drives real enforcement and none of that
enforcement changes here.

**Both call sites must change.** `boundaryConstraints` is emitted twice:
directly from `quickQueryContext.ts:208`, and again through `buildRecencyAnchor`
(`promptRegistry.ts:169`) at the end of the prompt, the highest-attention
position. Fixing one leaves the stale claim as the last thing the model reads.

### D4. A permission denial is not an answer

When stdout is empty, `LLMClient.ts:2166-2172` recovers stderr and promotes it to
the answer. `extractAntigravityAnswerFromStderr`'s status-line filter does not
recognise the denial text, so it survives; the empty-answer check at 2224-2241
then never fires because the recovered string is non-empty. The user is shown the
CLI's internal diagnostic, styled as a reply.

**Decision:** classify denial-shaped stderr and refuse to promote it. The turn
then falls into the existing empty-answer path and reports a real failure.

### D5. The bibliography heading is not English-only

`BIBLIOGRAPHY_HEADING = /^[\s#*]*(references|bibliography|works cited)[\s:]*$/im`
(`citationResolver.ts:45`). A paper whose heading is `참考文헌` or `参考文献`
defeats the parser even though the page text is already in memory. Cheap to fix,
and the vault's owner reads Korean papers.

## 5. Scope Exclusions & Stop Conditions

Stop and report if D1's union turns out to change what the sidebar sends (it must
not — the sidebar is not touched), or if D4's classifier would swallow a real
answer that merely mentions permissions.

## 6. Evidence Ledger

`05_evidence.md`, written before the first code change.

## 7. Execution Phases

- **P1 — D4.** Denial stops being an answer. Smallest, and it is what made the
  failure silent. Tests: a denial-shaped stderr yields the empty-answer failure,
  a real answer mentioning the word "permission" still passes through.
- **P2 — D1.** The popover resolves citations over selection ∪ question. Tests:
  question-only resolves; selection-only still resolves; both resolves once.
- **P3 — D2 + D3.** Provider-aware prompt truth, at both emission sites. Tests:
  CLI popover prompt does not promise the page tool and does not claim "no MCP
  tools"; API popover string is pinned byte-for-byte so it cannot drift.
- **P4 — D5.** Heading match covers Korean/Japanese/Chinese forms. Tests: each
  heading form finds the bibliography.
- **P5** — docs (PLUGIN_SCHEMA §13.5/§13.7 and the popover sections of
  PLUGIN_GUIDE, English first then `_KR`), CHANGELOG, version bump to 0.77.0
  across the four manifests. Minor: new user-facing behaviour.
