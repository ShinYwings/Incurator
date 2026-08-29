# Obsidian Plugin Guide (incurator-agent)

> The Incurator Obsidian plugin brings an AI assistant directly into your Obsidian Vault.  
> Use it standalone or connect it to the Curator backend (wiki CLI) for knowledge-graph-backed answers.

[한국어 가이드](PLUGIN_GUIDE_KR.md)

---

## 1. Installation

Plugin installation is now handled interactively via the **`wiki init` wizard** when creating a vault.

```bash
# 1. Install backend dependencies
./setup.sh

# 2. Initialize vault and auto-install plugin
wiki init /path/to/vault
```

During `wiki init`, if you choose to build the plugin, the output (`main.js`, `manifest.json`, `styles.css`) is copied to  
`<vault>/.obsidian/plugins/incurator-obsidian-agent/` automatically.

In Obsidian, go to **Settings → Community Plugins → Installed Plugins** and enable `AI Agent`.

Incurator v0.40.0 and later require Obsidian 1.1.0 or newer because synced
session/profile commits use Obsidian's atomic adapter processing API. Obsidian
1.0.x remains on the compatible Incurator v0.39.2 release through
`versions.json`.

> **Note:** If you need to build the plugin manually, run `npm install` and `npm run build` inside the `plugin/` directory.

---

## 2. Chat Sidebar

### Opening

| Method | Action |
| --- | --- |
| Click the bot ribbon icon in the left sidebar | Toggle chat sidebar |
| `Cmd+Shift+;` | Toggle chat sidebar |

### Features

- **Multi-turn conversation**: Session history is preserved. Create and switch between multiple sessions.
- **Codex-style sidebar**: New chat and conversation history live in the top thread header; history opens as an in-sidebar searchable drawer.
- **Streaming responses**: Enabled by default; can be turned off in settings.
- **Sticky scroll**: While a response streams, the view follows the new text only when you are already scrolled to the bottom. If you scroll up to read earlier text, your position is preserved — completing a response no longer yanks the view down to the latest message.
- **Context references**: Attach text, PDF pages, or image snippets to your messages.
- **Plan mode**: With `chatMode: plan`, the AI presents a step-by-step plan before acting.
- **Incurator integration**: When connected to a Curator backend, traceable DAG evidence is injected as context.

---

## 3. Inline Edit

Select text in a Markdown editor then run the **Inline Edit** command to open the
inline prompt widget. This command ships **without a default hotkey** (`Cmd+K` is
reserved by Obsidian/other bindings) — assign your own in **Settings → Hotkeys**
if you want a shortcut.

- **No selection**: The whole document is used as context for the edit command.
- **With selection**: Only the selected region is targeted.
- **Result display**: Changes are shown as an inline diff; choose Accept or Reject.
- **Chat edit review**: When sidechat proposes Markdown SEARCH/REPLACE edits,
  the diff opens **immediately** in the target note's in-editor Diff Viewer when
  that note is the one you're already looking at (or no note is focused). If a
  different note is focused, a compact `✏️ <filepath> · Review Diff` pill is
  shown instead so the diff never steals your editor; click it to open the diff.
- **Edit-loop review (v0.14.0, relaxed in v0.24.0)**: When the agent proposes a
  file change it is *asked* to walk a visible, four-phase loop — **Analysed →
  Reviewed → Updated → Reviewed**. When it does, each phase appears as its own
  labeled, collapsible section in the chat answer (the proposed diff lives under
  *Updated*), so you can see the agent understand the gap, critique its plan, make
  the change, and check its own work before you accept anything. **As of v0.24.0
  this is a quality hint, not a hard gate:** if a model (especially a small or
  token-limited one) skips the phases but still produces a valid edit, the diff is
  **still fully reviewable** — the answer shows the edit pills plus a small
  *"the model skipped its self-review steps"* note with an optional **Re-run with
  review** button. You no longer get stuck with "I made an edit" but no diff. Pure
  questions that propose no edits show no phases and no note.
- **Cut-off answers auto-continue (v0.24.0)**: models with an output-token cap
  (notably Gemini) sometimes stop mid-answer — often in the middle of an edit
  block. The plugin now detects this and automatically asks the model to continue
  from exactly where it stopped (up to three times), stitching the pieces together
  without duplicating text or breaking the edit block. If it's still cut off after
  that, a **↪ Continue** button appears so you can resume it manually.
- **Resilient SEARCH matching**: the agent's SEARCH text no longer has to match
  the file byte-for-byte. Leading/trailing whitespace and indentation-level drift
  are tolerated, so a correct edit applies even when the model re-indents. The
  match is **ambiguity-safe**: if two or more places could match, the edit is
  refused (you get a "could not find" notice) rather than risking the wrong spot.
  A very large single replacement triggers a "review carefully" notice.
- **No raw code dump in chat**: Code edits never flood the conversation. While
  the answer streams, every `ai-agent-edit` block is hidden behind a single
  *[Generating code edit…]* placeholder; once the answer completes each edit
  collapses into a compact pill. The full before/after lives in the Diff Viewer,
  not the chat transcript. Any stray edit markers (`<<<<`/`====`/`>>>>`) from a
  malformed block are stripped from the rendered message.
- **Diff Viewer navigation**: the floating toolbar shows a hunk counter (e.g.
  `1/1`, `2/8`); with more than one change, ↑/↓ (or Tab / Shift+Tab) move between
  hunks and Y/N accept/reject the current one (Enter = accept all, Esc = reject all).
  **Focus-safe shortcuts (v0.24.0)**: these keys only act while the diff editor or
  its toolbar is focused — pressing Enter in the chat box no longer accidentally
  applies an open diff. Opening a diff focuses it for you, so the keys work right away.
- **Order-independent multi-edit (v0.24.0)**: when one answer proposes several
  edits to the same file, accepting one can no longer break another's match —
  every edit is located against the original file. If some edits can't be placed,
  you get a clear "skipped N (not found / overlapping)" note instead of a vague
  warning, and the rest still open for review.
- **Accept All keeps your place (v0.14.1)**: accepting all changes leaves the
  cursor at the first changed line, not the bottom of the document.
- **Toolbar anchors to the change (v0.14.1)**: when a diff opens off-screen, the
  editor scrolls the first change into view first, so the Accept/Reject toolbar
  appears next to the change instead of jumping to the top of the screen.
- **Honest edit-proposal pills (v0.14.1)**: each `✏️ <file>` review pill reflects
  the live file — it shows **✓ Applied** if the edit already appears in the file
  and **⚠ Not found** if the SEARCH text no longer matches, so you don't get a
  confusing "could not find" only after clicking. Reviews open one at a time, so
  clicking a second pill never hijacks the first file's diff. Path matching also
  falls back to a case-insensitive full-path match, fixing spurious "file not
  found" on existing notes without retargeting same-named notes in other folders.
  **✓ Applied** is shown when the replacement block is unambiguous, or when a
  deletion proposal's SEARCH text is already gone and the replacement is empty.
  Applied/not-found pills do not re-run review. The agent describes its edits as
  *proposed and pending your Accept* — nothing is written to disk until you accept.
- **Diff mode**: Choose `inline` or `side-by-side` in settings.

```text
Select text in editor
       │
       │ Inline Edit command
       ▼
Inline prompt widget (enter command)
       │
       ▼
LLM generates suggestion → Diff shown → Accept / Reject
```

---

## 3.5 Quick Query on Selection (In-line Copilot)

Select any text — in a Markdown note, reading view, or PDF — and a single
floating **✨ Ask AI** button appears next to the selection. Click it (or press
`Cmd+Shift+K` with text selected) to open a small popover for a one-off question
about that passage. This works like a lightweight `wiki query` aimed at quick
lookups while reading, e.g. resolving "참조: [섹션 4.2]" or interpreting
"Eq. (3)에 의해…".

- **Mouse or keyboard selection**: Both a mouse drag and a keyboard selection
  (Shift+Arrow / Shift+Home/End, or Ctrl/Cmd+A) surface the button; collapsing
  the selection back to a caret hides it.
- **Formulas are preserved**: When your selection spans rendered MathJax, the
  captured passage keeps the LaTeX source (`$...$` / `$$...$$`) instead of empty
  SVG — so dragging across a formula no longer drops it, regardless of Live
  Preview's render timing.
- **Single button**: A selection only ever shows one button — no toolbar.
- **Your API key survives updates** (v0.62.4): keys entered in settings are
  stored encrypted outside the vault, so an update no longer clears them. Note
  that Obsidian's key and the backend's `wiki config` key are configured
  separately on purpose — setting one does not change the other. The key is
  **per-device by design**: it is kept outside the vault precisely so it cannot
  ride Obsidian Sync or Syncthing, which means you enter it once on each machine
  you use. It survives updates and reinstalls on that machine, not a move to a
  new one.
- **It looks at your other notes too** (v0.62.3): before answering, the popover
  searches your vault for passages that bear on the question and names the note
  each one came from, so "what else have I written about this?" reaches beyond
  the file you are reading. It is one lookup done up front — the popover still
  gets no tools and makes no extra round trips.
- **Persistent popover**: The popover has just a query input and an **Ask**
  button. There are no preset/quick buttons. Once opened, it stays open while
  you click or scroll elsewhere; close it with **×** or `Esc`.
- **Multiple popovers**: Opening a quick query for another selection creates a
  separate popover instead of replacing the previous one. Each popover keeps its
  own answer, position, minimized state, and short follow-up trace.
- **Move and minimize**: Drag the popover header to place it anywhere in the
  current window. Use the minimize control to collapse it to the header without
  losing the answer or follow-up state.
- **Question title**: After each submission, the header title updates to the
  latest question so a minimized popover stays identifiable.
- **Focused answer display**: After you submit, the input row hides while the
  answer streams (no chat-bubble layout). Once the answer completes, a compact
  follow-up input returns in the same popover.
- **Follow-up questions**: Follow-ups in the same popover keep a short
  in-memory trace of the prior quick-query turns. Closing the popover discards
  that trace; it is never written to chat history.
- **Current page + ToC context**: The selected passage is always the primary
  focus. The active Markdown/PDF page, nearby PDF window text, and available
  Markdown/PDF outline are sent as background context so references like
  "section 4.2", "Eq. (3)", bare equation labels like "(19.11)", or the current
  page's heading can be resolved without letting the full document overpower the
  selection.
- **Reference following**: If the selected text is itself a pointer such as
  "see Section A4.2 (p580)", "Figure 19.1", "Result A4.1", or "(19.11)", the
  plugin first tries to resolve the referenced target from the PDF
  outline/window text/search hits and sends that target as
  `<resolved_cross_references>` before the generic page background. When the
  pointer includes an explicit page locator such as `Section 11.1.2, p281`, or
  a bare numbered object such as `(3.5)`, the open Incurator PDF viewer first
  uses the PDF ToC to fetch the smallest matching section range through
  PDF.js, then falls back to a capped chapter range only when the ToC has no
  exact section. Theorem-style pointers accept appendix-lettered numbering
  (`Result A4.1`, `Corollary B2.3`), and `Appendix 4` ToC titles answer to
  `A4`-style numbers so appendix anchors resolve too.
- **Your own project notes are consulted (v0.57.0)**: when you ask the sidebar
  a question while working inside `01_Workspaces/<project>/`, the assistant also
  looks through the notes you wrote in that project and surfaces what you
  already concluded, attributed to you.

  Three things about how it is scoped:

  - **Your notes are not ingested.** Nothing from a workspace enters the
    knowledge graph, the database, or `.curator/`. They are read at the moment
    you ask and nowhere else, so your project's working state stays project-local.
  - **Only the project you are in.** Ask outside a workspace and nothing is
    consulted — it does not search your whole vault, and it will not surface a
    different project's notes.
  - **The agent's own files are skipped.** `.agents/`, `CLAUDE.md`, `AGENTS.md`,
    and `GEMINI.md` inside a workspace are instructions to a tool, not your
    thinking. Having the assistant quote its own plans back to you as "notes you
    wrote" would be worse than saying nothing.

  Your notes are presented to the model as *your working notes*, not as
  established fact — so it should say "you concluded X" rather than asserting X.

- **Citations resolve to the paper they name (v0.56.0)**: select a passage
  containing `[8]` and ask about it, and the assistant already has the
  bibliography entry `[8]` points to — no extra round trip, no asking you to
  scroll to the References section.

  It finds the References section by scanning backward from the end of the
  document, and follows it across pages: a bibliography prints its heading once
  and then continues for two or three more pages, so stopping at the heading
  page would miss most of it.

  **A bracket that does not match the bibliography is ignored, silently.**
  `[8]` is ambiguous — it is also how footnotes (`[^8]`), markdown reference
  links (`[text][8]`), and array indices (`arr[8]`) are written. Rather than
  guess, the assistant treats a number with no matching entry as "not a
  citation" and says nothing about it. A selection with no citation at all never
  causes the References section to be read, so asking about code costs nothing.

- **Where each answer came from (v0.56.0)**: when a question needed a lookup, a
  quiet line appears under the answer listing what was consulted —
  `Eq. (29) — p.11 · [8] — Bartoli et al., 2005`.

  It is built from what the assistant actually retrieved, not from reading its
  answer back, so it cannot claim a source that was not used. A pointer that
  could not be reached reads **"not retrieved"**, never "absent from the paper" —
  the drag-to-select popover searches only the pages already loaded, so failing
  to find something is a statement about the search, not about the document.
  A question that needed no lookup shows no line at all.

- **When the text layer does not have it (v0.55.0)**: some PDFs render their
  displayed equations and figures as images, so the label never appears in the
  extracted text and no amount of *text* searching will locate it. The
  assistant can now look at the page instead of reading it. When the text it
  fetched does not contain the equation, figure, or scanned insert you asked
  about, it renders that page and reads the pixels through the same extraction
  model the manual snip uses — including pages you have never scrolled to, and
  including your own handwritten margin notes, which no text layer contains.

  Two consequences worth knowing:

  - **You no longer have to snip an equation to ask about it.** Ask about
    "equation 29" and the assistant fetches the page, notices the equation is
    not in the text, and reads it off the page image.
  - **It is deliberately rationed.** Rendering a page and sending it to a
    vision model is far more expensive than reading text, so a single question
    gets a small number of page images. The assistant spends them on the pages
    that actually need pixels and answers everything else from text.
  - **How far it can reach still depends on where you asked from.** The
    drag-to-select popover works from the pages already loaded, and
    whole-document search needs the backend running. Reading a page as an image
    widens what the assistant can do with a page it has; it does not change
    which pages each surface can go looking through in the first place.

  Pointers whose text cannot be found are listed in an
  `<unresolved_cross_references>` block. That block is addressed to the
  assistant, not to you: it says a rasterized target is missing from the text
  layer, not from the paper, and to go read that page as an image before
  settling for less. Only where no page-reading tool is available does it fall
  back to describing the target from the surrounding material. Either way the
  answer you see should be about the paper, not a report on what the assistant
  did or did not receive.

  A pointer that resolves through a neighbour is not reported as missing. When
  you select something like `(Section 11.1.2, p281)`, the page and the section
  are one reference, and its text appears once under the section. It is not
  also listed as unretrievable.
- **Printed vs physical page numbers (v0.40.3)**: book PDFs usually have front
  matter, so printed page 581 is *not* PDF page 581. A `p581`-style locator is
  mapped through, in order: the PDF's own page labels; a front-matter offset
  inferred from the printed header/footer numbers of pages the reader has
  already seen (accepted only when at least two pages agree by clear
  majority); a scan of known pages whose printed header matches; and finally
  the literal page number — which is kept only until the fetched page's own
  header disproves it. A page whose header names a different printed number is
  never injected as the resolved target: Ask AI prefers saying the target
  could not be located over confidently quoting the wrong page. When the
  literal guess is disproven, its header still reveals the document's true
  offset, and one bounded repair fetch retrieves the correct physical page.
- **In-document positions, not folders**: Positional phrases like "문서 위쪽",
  "앞부분", "top of the document", or "end of the page" are treated as positions
  **within the current document's content/outline**, never as the file system.
  The popover has no filesystem access, so it never lists or invents folder/file
  names — asking for the "top of the document" summarizes that region's text
  instead of browsing the parent directory.
- **Tool-isolated (v0.19.0)**: The popover is hard-isolated from MCP tools — even
  if you have MCP servers (including Incurator) enabled for the chat sidebar, the
  popover injects **zero** MCP tools. It can never run a script, create a file, or
  reach the filesystem, your vault, or your Zotero library. If you want full agent
  capabilities (RAG over the knowledge base, file edits, MCP tools), use the chat
  sidebar instead of the popover.
- **Page-turning without you (v0.41.0)**: the popover can now turn pages of the
  PDF you already have open. The assistant always receives the document's table
  of contents with page numbers, so it can reason "that result is in Appendix 4,
  around page 617" — but until v0.41.0 it had no way to get there and could only
  tell you to go look. It now has exactly one read-only ability: fetch a page of
  the open PDF by number. That covers the cases automatic reference-following
  cannot: a reference discovered only *after* reading the target page, a target
  named in your question rather than in the text you selected, and prose
  references like "as shown in the previous chapter" that carry no number. For
  papers with no embedded table of contents, it can additionally search the
  pages it has already seen, since it has no map to navigate by.

  This does not widen the isolation above: the page reader is not an MCP tool
  and cannot touch the filesystem, your vault, or Zotero. It is limited to the
  PDF already open in front of you, refuses page numbers outside that document,
  and stops after a bounded number of page fetches per question. If no PDF is
  open, the ability is not offered at all. CLI providers (Antigravity `agy`,
  Claude, Codex) do not get the page reader — they keep automatic
  reference-following only.
- **Sandboxed CLI providers (v0.23.0)**: when your provider is a CLI agent
  (Antigravity `agy`, Claude, or Codex), that agent has its own built-in tools the
  v0.19.0 MCP isolation doesn't govern. The plugin now contains them: the popover
  runs the CLI **tool-free**, and the chat sidebar's tools are **scoped to your
  data** — the agent can **read** your vault and the configured Zotero library, but
  can only **write inside your vault**. Your Zotero library is treated as read-only,
  so the agent can't modify or delete it, and it can't create files or run scripts
  anywhere outside your vault. Antigravity's own `--sandbox` is ineffective, so the
  plugin wraps it in an OS sandbox (macOS built-in; **Linux requires `bubblewrap` —
  install it with `sudo apt install bubblewrap` or `sudo dnf install bubblewrap`**).
  If no OS sandbox is available, **Antigravity is blocked** (it would have no
  containment at all), while **Claude and Codex still run** under their own weaker
  built-in limits. Windows CLI sandboxing is not yet supported.

  Antigravity 1.1.3 and later also deny tools that need an interactive approval
  when the plugin launches `agy` in headless (`-p`) mode. The plugin therefore
  preserves your Antigravity CLI settings and adds three rules under
  `permissions.allow` in `~/.gemini/antigravity-cli/settings.json`:
  `read_file(*)`, `command(wiki)` so the Incurator MCP server can be started,
  and — since v0.71.0 — `mcp(*)` so its tools can actually be **called**.

  Registering the server and granting `command(wiki)` were never enough on their
  own, and this is why `agy` appeared to have Incurator's tools but could not use
  them. Two things were missing, both measured against agy 1.1.22 rather than
  assumed:

  - **Calling an MCP tool needs its own permission, and only the wildcard works.**
    `mcp(incurator_fetch)` and `mcp(fetch_url)` were both auto-denied; `mcp(*)`
    let the call through. Same shape as `read_file` — a scoped rule here grants
    nothing at all.

    **What that costs you, stated plainly.** `mcp(*)` is a wildcard over the MCP
    permission class, not a grant scoped to Incurator: it lets headless `agy`
    call tools on **every** MCP server in its registry, including any you added
    yourself with `agy mcp add`. It is still narrower than the CLI's blanket
    permission-skip flag, which Incurator refuses — that approves every tool
    class including the shell, while this approves no class but MCP — and the
    scoped forms were measured and grant nothing, so there is no third option.
    If you keep sensitive MCP servers registered with `agy`, that is the
    trade-off to weigh.
  - **The server has to be registered where the CLI looks.** Incurator used to
    write `~/.gemini/settings.json`; `agy` reads its MCP registry from
    `~/.gemini/config/mcp_config.json` — the file `agy mcp add` writes and
    `agy mcp list` shows. It is now written too. Servers you added yourself
    with `agy mcp add` are kept, and a server you delete or disable in
    Incurator's settings is actually unregistered — Incurator tracks which names
    it manages and removes only those. If `agy mcp list` shows `incurator`,
    registration is working.

> [!IMPORTANT]
> **If you saw `jetski: no output produced` repeatedly, this is why — and it
> took three attempts to actually fix (v0.56.1).**
>
> Until v0.53.1 the rule was written `$read_file$()`, a form Antigravity does
> not recognise: it prunes unrecognised rules and deletes the emptied
> `permissions` object, so the grant survived **zero** runs. v0.53.1 corrected
> that to `read_file()` and confirmed the rule now *stayed* in the file — which
> it does, while granting nothing. Every image read was still auto-denied for
> another three releases, behind a rule that looked correctly configured.
>
> Measured against agy 1.1.13: only `read_file(*)` is honoured. An exact path
> (`read_file(/path/to/file.png)`) is refused, and so is `read_file(/tmp/*)`.
> For reads, a path-scoped rule is not a narrower grant — it is no grant.
>
> Nothing you configured was wrong. Updating rewrites the rule and removes the
> dead one; you do not need to edit the file yourself.

> [!WARNING]
> **What `read_file(*)` costs you, stated plainly.**
>
> That rule lets the Antigravity CLI read **any file your user account can
> read** — not just the page images Incurator hands it. agy accepts no narrower
> form (an exact path is refused), and the OS sandbox Incurator wraps the CLI in
> restricts *writes*, never reads. So while the rule was broken the door was
> shut by accident; making image reading work opens it.
>
> The grant is **global and lasting**: one file under `~/.gemini`, honoured by
> every later `agy` run on your account, including the `wiki` ingest pipeline —
> which is the part that processes PDFs and web pages you did not write. A
> prompt-injected instruction inside an ingested source can ask the model to
> read an unrelated file, and its contents can end up in your knowledge base.
>
> What is *not* granted matters too. Incurator adds exactly two rules, and
> Antigravity auto-denies anything unapproved in headless mode, so the CLI still
> cannot write files or run arbitrary shell commands. The realistic worst case
> is a secret being read into your own vault, not silently sent somewhere.
>
> **To avoid the trade entirely**, point PDF extraction at a vision model reached
> over an API (Dashboard → LLM Provider → PDF/LaTeX extraction model). An API
> provider receives the image bytes directly, so no filesystem permission is
> involved and this rule is never needed.


  `command(wiki)` is deliberately scoped to the `wiki` binary the plugin itself
  configures — Incurator never writes a bare `command()`, which would approve
  running anything. This lets an open PDF or an attached
  image be read without a prompt; it does not approve writes, shell commands,
  network tools, or arbitrary paths. `--add-dir` still determines which vault and
  configured Zotero directories are visible, and the OS sandbox still restricts
  writes. Invalid JSON is never replaced automatically. The obsolete
  `~/.gemini/policies/incurator-read.toml` created by Incurator v0.36.3 is removed
  only when it retains Incurator's generated-file marker; user-authored policies
  are left untouched.
- **Markdown rendering**: The answer renders as Markdown (math/LaTeX included)
  once the stream completes. Math is normalized before rendering — backtick-wrapped
  spans such as `` `$x^2$` `` are unwrapped to `$x^2$` so LaTeX renders as a
  formula instead of monospace text (matching the chat sidebar behavior).
- **Copyable**: The answer text stays selectable so you can drag-copy it. Rendered
  math is stamped with its LaTeX source before the copy handler runs, matching the
  chat sidebar behavior.
- **Scrollable & capped**: The popover is size-capped (`max-height`/`max-width`);
  long answers scroll inside it.
- **Ephemeral**: It is a temporary window. Closing it with the `×` button or
  `Esc` discards that popover's exchange only — it never pollutes the chat
  sidebar history. Clicking outside an open popover only clears the floating
  trigger button; it does not close existing popovers. Each open popover owns
  its cancellation signal, so closing one does not stop another popover or the
  chat sidebar, and it does not replace the sidebar's own Stop target. If a
  popover is closed while PDF context is still being prepared, no provider
  process or HTTP request starts afterward. Provider-specific error messages,
  including Ollama reachability errors, do not replace normal cancellation.
  Non-streaming CLI queries preserve the selected per-call model and the same
  GUI-safe CLI search path as streaming queries.

The passage you selected is sent as the primary context together with your
question and the current page/outline as background, using the currently
configured AI provider/model. Disable the feature with **Settings → AI Provider
→ Quick query on selection** if you do not want the button to appear.

```text
Drag-select text
       │
       │ ✨ Ask AI button appears
       ▼
Popover: [ question input ] [ Ask ]
       │  submit
       ▼
Input hides → streamed answer only (copyable, scrollable)
       │  follow-up input returns
       ▼
Ask another question about the same selection (optional)
       │  close (×, Esc, click outside)
       ▼
Discarded — chat history untouched
```

---

## 3.6 Copy as Markdown from the AI chat and popover (`Cmd/Ctrl+C`)

When you drag-select part of an assistant reply in the **chat sidebar** or
quick-query popover and press **Cmd/Ctrl+C**, the selection is copied as
**Markdown** — formatting *and* math — instead of the browser's flattened plain
text:

- **Formatting is preserved**: bold, italics, headings, bullet/numbered lists,
  links, and tables come back as Markdown (`**bold**`, `## heading`, `- item`,
  `[text](url)`), via Obsidian's own `htmlToMarkdown`.
- **Formulas are preserved**: rendered math is restored to its **LaTeX source**
  (`$...$` inline, `$$...$$` block) instead of the empty MathJax SVG — so you can
  paste a derivation straight into a note as editable LaTeX.
- **Selection-scoped**: Only the region you selected is copied — not the whole
  message.

---

## 3.7 Copy note formulas in Reading View (`Cmd/Ctrl+C`, `Cmd/Ctrl+X`)

Drag-select part of a note in **Reading View** and press **Cmd/Ctrl+C** (or
**Cmd/Ctrl+X**): if the selection contains a rendered formula, it is copied as
**Markdown with the LaTeX source restored** (`$...$` inline, `$$...$$` block)
instead of the empty MathJax SVG. The selection visually *skipping* the formula
while you drag is normal — the formula is still captured. Works in pop-out windows
too.

- **Selection-scoped**: only the dragged region is copied. A formula the selection
  only partially overlaps is captured **whole** (a half-formula is not useful).
- **Non-math copies are unchanged**: a selection with no formula is left to
  Obsidian's native clipboard — the plugin does not intercept it.
- **Live Preview / Source mode** already preserve `$...$` natively (CodeMirror
  copies the document source), so they need no special handling; the plugin only
  augments **Reading View**, which otherwise loses the source.
- **`Cmd/Ctrl+X`** in read-only Reading View copies the LaTeX but (correctly)
  deletes nothing; in Live Preview, native cut already removes the source.

> **How it works.** Obsidian renders Reading-View math as CHTML and keeps **no**
> LaTeX source in the page DOM. The plugin registers a Markdown post-processor that
> re-parses each rendered section's source and stamps it back onto every formula as
> `data-tex` (only when the parsed and rendered formula counts match exactly, so a
> mis-parse can never attach the wrong source). The copy handler then reads that
> stamp — the same mechanism the chat sidebar uses (§3.6).

---

## 4. Line Reference (`Cmd+Shift+L`)

Adds the currently viewed content to the chat as a context reference.

| View type | Behavior |
|-----------|----------|
| **Markdown file** | Adds text near the cursor as a context reference |
| **PDF viewer** (with selection) | Adds selected text to context |
| **PDF viewer** (no selection) | Adds the full current page as context (text/image/both per `pdfCaptureMode`) |

Text selection in the Incurator PDF viewer starts only on actual text spans. Dragging over empty PDF margins does not create a selection region.

When sidechat sends a message, context added explicitly through selection,
line reference, or PDF snipping is treated as the primary focus. A pinned
explicit snippet, selected text, crop, or line range remains the primary focus
even after it is pinned. Pinned whole files/pages and automatically visible tabs
remain background grounding unless the question explicitly asks about them. A
pinned or attached context chip can be toggled invisible/excluded; it stays
visible in the chip row but is not sent to the model until toggled visible
again.

The context row distinguishes **open** tabs from **prompt-included** tabs.
Every open Markdown/PDF tab appears as a chip, including an inactive tab hidden
behind the selected tab in the same tab group. The currently visible tab in
each split starts eye-on and is included as background context. Hidden
tab-group members start eye-off and are not sent in tab lists, file bodies,
outlines, continuity summaries, or edit targets until you explicitly turn
their eye on or pin them. Exact duplicate views of the same source/page may
share one chip; different PDF pages remain distinct.

For selected-context questions, the plugin also supplies current-page structure
as background grounding: Markdown headings are sent as a compact outline, and
PDF outline/window context is included when available. These outline/page blocks
are supplementary; the selected text, line range, or crop remains the answer's
target.

**Localized focus in long sessions (v0.19.0):** In a long chat — especially after
earlier whole-document edits — a freshly added `Cmd+Shift+L` selection used to be
ignored, with the agent reverting to modifying the whole file. The plugin now
appends a high-priority invariant block at the very end of each request (the
position of strongest model attention) that re-asserts "answer only about the
current selection; do not edit the whole document unless explicitly asked." So a
localized question late in a long session is honored regardless of earlier turns.

**Edit-affordance suppression for localized questions (v0.21.0):** The v0.19.0
anchor was still being fought by the edit machinery: a `Cmd+Shift+L` line range is
also an *editable* range, so the same request carried both "answer only" (the
anchor) and "you may edit these lines / you are in an edit-review loop." In long,
edit-heavy sessions the edit signal sometimes won and the agent proposed a
whole-file edit to a simple question. Now, when your latest turn is a **question**
about a selection (a primary-focus selection is present and the message is not an
edit request), the plugin omits the editable-selection affordance and the
edit-review-loop contract entirely, so the answer-only anchor is unopposed. Asking
for an edit ("rewrite this line…", "fix the grammar here") still gives you the full
edit/diff flow as before.

When an assistant answer contains a page or section link such as `#page=604`,
`p.604`, `#section=A4.2`, or `§19.3`, clicking that link in the chat sidebar
jumps the open Incurator PDF viewer to the resolved page. Section links resolve
through the active PDF outline. Printed page links such as `p.580` use the PDF's
native PageLabels map when the Incurator PDF viewer exposes one, so front-matter
offsets do not force `p.580` to mean physical page 580. Ordinary web and vault
links keep their normal behavior. Generated vault block locators with an explicit
block anchor, such as `Auto Calibration#^8f735d` or a rendered label like
`Auto Calibration > ^8f735d`, open through Obsidian's normal vault-link
navigation.

### Assistant Vault-Page Wikilinks

When the Sidechat provider has an exact vault-relative path from the context you
included, a usable Incurator evidence locator, or a tool result, it can cite that
page as an Obsidian wikilink such as
`[[02_Wiki/Optimization/Auto Calibration|Auto Calibration]]`. A known heading
or block is retained (`[[02_Wiki/Optimization/Auto Calibration#Method]]` or
`[[02_Wiki/Optimization/Auto Calibration#^8f735d]]`). Markdown targets omit the
`.md` suffix, while non-Markdown suffixes such as `.pdf` are preserved.

This contract is shared by every selectable Sidechat provider and model. It does
not send a whole-vault filename list to the model, guess links from page-like
words, or rewrite ordinary answer text after generation. If the exact target is
not grounded, the assistant must leave the name as plain text. Valid visible-note
links are rendered and opened by Obsidian itself, preserving native click,
modifier-click, and hover behavior. For included Markdown/PDF context, the plugin
supplies the completed safe `vault_link_target` literal so smaller local models
can copy the exact link instead of rebuilding a path from its display label;
external or unsupported file paths never receive such a target.

### Curator DAG Wikilinks

The Curator knowledge DAG (L1–L4 nodes: `CTX-`, `ATM-`, `CON-`, `SYN-`) is stored
under the hidden `.curator/Collections/` folder. Obsidian does not index files in
hidden (dot-) folders, so a curator wikilink such as `[[02_Atoms/ATM-9f8e7d6c]]`
would otherwise render as a dead, unresolved link with no click, hover, graph, or
backlink behavior.

The plugin closes this gap: any rendered curator-layer wikilink
(`[[01_Contexts/CTX-…]]`, `[[02_Atoms/ATM-…]]`, `[[03_Concepts/CON-…]]`,
`[[04_Synthesis/SYN-…]]`, with or without the `.curator/Collections/` prefix or a
trailing `.md`) becomes a **clickable link that opens the hidden DAG page**. This
works in the chat sidebar answer, the quick-query popover answer, and the reading
view of an opened DAG page. When the target file exists it renders as a normal,
resolved link; when it is missing it is marked with a `is-missing` style so a
stale citation is visible rather than silently broken.

Because the DAG lives in a hidden folder, these nodes still do not appear in
Obsidian's native Graph view or core Backlinks pane — use the chat **Sources &
Trace** panel for backlink-style provenance. Ordinary web and vault links keep
their normal behavior; only curator-layer link targets are rewritten.

Synthesized answers also cite the **original source documents** behind each
claim — e.g. `[[04_Resources/Some Paper]]` — in addition to the curator node.
Those source files are normal, visible vault files, so their links resolve and
click through natively (and DO appear in Graph view / backlinks). When an answer
draws on a high-level synthesis that spans several papers, every contributing
source document is cited, not just the first.

When a selected Markdown line range is attached and the user asks to fix,
rewrite, polish, translate, or otherwise modify that selected text, the
assistant should return an `ai-agent-edit` SEARCH/REPLACE proposal. If the user
only asks a question about the selection, the assistant answers normally and
does not propose an edit.

When the latest request uses a selected PDF/text region as an example and asks
to change all similar Markdown-file occurrences, the selected region is treated
as a clue, not as the only edit target. The plugin sends the full content of
prompt-included Markdown tabs as edit-target context so the assistant can find
matching HTML/Markdown lines across the file, preserve the existing syntax form,
and propose SEARCH/REPLACE hunks for review in the Markdown editor. An open but
eye-off hidden tab is never an edit target.

### Markdown Position Restore

When Obsidian shuts down, the plugin saves the active editing-mode Markdown file's cursor and scroll position as the last workspace position. After restarting Obsidian, the plugin waits for the workspace layout and retries restoring that file and position.

The last workspace position is stored as a separate snapshot; per-file positions are kept only as a secondary cache for up to 100 file paths.

---

## 5. PDF Snipping (`Cmd+Shift+X`)

Drag-select a region of a PDF to capture both its image and the text it contains.

1. Open a PDF in the Incurator viewer (right-click `.pdf` → Open with Incurator)
2. Press `Cmd+Shift+X` to enter snipping mode
3. Drag over the desired area — it is captured as an image
4. The captured crop is automatically attached to the chat sidebar context

> **Note**: Snipping only works in the Incurator PDF viewer (`EXTERNAL_PDF_VIEW_TYPE`).  
> For Obsidian's built-in PDF viewer, use `Cmd+Shift+L` to reference the whole page.

The Incurator PDF viewer lazy-renders nearby pages and coalesces scroll work to
one animation frame, so page-number detection and lazy rendering do not run once
per raw scroll event.

A crop captures **only the text lines inside the rectangle you drew** (region-scoped),
not the whole page. That snipped text becomes the crop's **primary focus** — the
core subject of your question — so the model answers about the region you boxed
instead of burying it under the full-page background context. The crop never
re-injects the entire page text (or its RAG hits) into the primary focus; the
full page is still available separately as background context.

**How the crop reaches the model (v0.28.0).** If your main chat model is
vision-capable (Antigravity, Claude, Codex, or a vision Ollama model), the crop
image is handed **directly** to that model — the chat reads it through a scoped,
sandboxed image channel. There is **no separate transcription step**, so pressing
Send shows "Thinking…" instantly instead of freezing while a backend model runs.
If the active model is text-only, the crop falls back to backend transcription
(its LaTeX/region text grounds the answer) and sidechat tells the model when image
details are unavailable instead of silently ignoring the crop. The snipped region
text always rides along as a caption, so even a scanned, text-less crop stays the
primary focus and is never buried. When the latest message already carries a
user-selected crop/image, the plugin uses that local context as the fast path and
skips backend whole-PDF context/RAG calls for that turn.

---

## 6. PDF Processing Settings

The plugin offers three capture modes when using a PDF as context.

| `pdfCaptureMode` | Description |
|------------------|-------------|
| `text` | Extract text layer only (fast, token-efficient) |
| `image` | Capture page as image (requires vision-capable model) |
| `both` | Send text + image together (default, most accurate) |

### Additional PDF options

| Setting | Default | Description |
|---------|---------|-------------|
| `pdfWindowRadius` | `1` | Pages before/after current page to include |
| `pdfOutlineEnabled` | `true` | Include PDF table of contents in context |
| `pdfRagEnabled` | `true` | Enable RAG search across the full PDF |
| `pdfRagTopK` | `5` | Number of top RAG results to retrieve |
| `pdfVisionFallback` | `true` | Attach an image only when text-mode capture is scanned-like or has no usable text |
| `pdfFullDocumentIndex` | `true` | Index the entire PDF for better RAG accuracy |

PDF context is assembled in this order:

1. Local PDF.js page text and attached crop/image context. If the PDF viewer
   exposes substantial selectable DOM text, that text remains the fast path and
   does not trigger image fallback.
2. Registered, L1-complete durable CTX projection context when local viewer
   text/window/image context is unavailable.
3. Read-only backend PDF parsing when neither local context nor a usable durable
   projection is available. This fallback never registers the PDF.
4. Optional backend whole-PDF RAG only when backend PDF context is being used,
   `pdfRagEnabled=true`, and the source is tracked.

For a PDF-focused turn, Sidechat also follows an explicit reference in the
latest question, not only one inside selected/cropped text. For example, if the
visible page ends at equation (9) and the user asks about `Eq. (10)` or
`수식 (10)`, Sidechat checks the known page window first. If the exact label is
missing, it requests a small bounded adjacent-page set one page at a time through
the read-only PDF context service (next page first, `radius=0`) and stops at the
first exact match. If the bounded scan ends without that exact label, Sidechat
fails closed: it does not turn a loose same-number search hit into a resolved
target. Automatic latest-question lookup runs only against the active PDF, or
against a PDF explicitly attached as primary context with the same canonical
document identity. Merely visible, pinned-background, or prompt-included PDF
tabs cannot claim a reference from a Markdown-focused question. The matching
page is sent as `<resolved_cross_references>` before the normal PDF window.
External Zotero/iCloud PDFs stay outside the provider's native filesystem roots;
the provider receives the resolved text, not direct file access. Sidechat uses
the same cross-reference resolver as the Ask AI popover, so the v0.40.3
printed-vs-physical page mapping (label map → inferred front-matter offset →
printed-header scan → verified literal guess, always failing closed on a
contradicted page) applies to Sidechat pointer resolution identically.

Sidechat and quick-query popovers share the same backend PDF page cache when a
content hash or registered source identity is available:
`.cache/pdf_pages/<content_hash>/<page>.txt`. Reference Mode stubs under
`04_Resources/` keep portable identity only; absolute local paths and page text
caches stay in backend state/cache so macOS and Linux devices can resolve their
own local PDF locations independently.

The chat sidebar logs backend PDF context, PDF RAG, and Curator query timings to
the developer console so slow turns can be diagnosed without guessing which
stage is blocking.

Treat PDF chat and PDF knowledge refinement as separate workflows:

- Normal chat over an open PDF uses the viewer fast path. It answers from the
  current page, nearby page text, selected text, or crop image without requiring
  durable Incurator ingestion or a blocking backend PDF context call.
- Passive chat never imports or registers an untracked PDF. Registration only
  occurs through an explicit purple-chip **Add to Incurator** action.
- Purple context chips and **Add to Incurator** start durable knowledge
  refinement. They register the PDF as a source, create instant L1 context, and
  queue L2/L3 build jobs.
- Queued L2/L3 jobs run through **Incurator Dashboard > Jobs > Run queued** or
  the CLI command `wiki jobs run`. This keeps the PDF viewer responsive while
  long LLM-heavy refinement runs as explicit background work.
- In the Jobs tab, queued jobs can be cancelled before a worker claims them, and
  completed, failed, or cancelled jobs can be requeued with **Rerun**.

---

## 7. AI Provider Settings

The plugin supports Antigravity, Claude, OpenAI Codex, Ollama, and DeepSeek. In settings, provider and model can be adjusted separately. In the chat sidebar footer, a single model menu switches both at once using `Provider · Model` labels. Reasoning/effort appears only for models whose backend catalogue entry declares effort levels.
For Antigravity CLI 1.1.5+, chat passes the selected model with `--model` and
the selected level with `--effort`; the latter is required for a base slug such
as `gemini-3.6-flash`.

> [!NOTE]
> **Built-in web search is a CLI-provider capability only.** Antigravity
> (`agy`), Claude, and Codex run their vendor's own CLI, so those providers can
> answer a question by searching the web themselves — measured at roughly 13 s
> for a single-turn `agy --print` lookup. The **DeepSeek API** provider speaks
> plain chat-completions and is given no search tool, so it can only answer from
> the context the plugin sends it: your vault evidence, the open note, and the
> selection. This is a limitation of the provider's API, not a plugin setting —
> there is nothing to enable. If you need the model to look something up on the
> web, switch to a CLI provider for that question.

The Settings page shows the selected model's context window on the **Model**
row instead of as a separate setting. This is the provider/CLI token capacity;
individual attached documents are still clipped by a conservative character
guard, not an exact tokenizer-aware allocation of the whole model window.

**Vision extraction models (v0.22.0):** PDF math extraction uses dedicated
**vision** models, configured in the **Incurator Dashboard → LLM Provider** card,
separate from your main chat model. Two rows:

- **PDF ingest model (full-page)** — when set, `wiki add`/Add Source transcribes
  each PDF page with this vision model so L1 gets proper LaTeX (instead of the
  approximate text-layer extraction). Leave empty to keep the fast pymupdf4llm path.
- **LaTeX/region extract model (light)** — a small region-OCR model used by the
  right-click **Convert to LaTeX** action (and as the text-only fallback for chat
  snips). Leave empty to fall back to the PDF ingest model. Convert to LaTeX calls
  the backend extractor, which requests a strict
  `<transcription>...</transcription>` block and strips common explanatory prose
  before copying the result. The selected prose is preserved and equations are
  rewritten with `$...$` / `$$...$$` LaTeX delimiters. For Antigravity, the
  backend passes the full transcription request as the `agy --print` prompt and
  applies the exact selected `--model`. An explicit LaTeX or PDF-ingest fallback
  model uses `low` when that model supports it; fixed/no-effort models omit the
  effort flag. If neither dedicated row is configured, the main-model fallback
  keeps its selected effort. Provider work logs are not transcription output.
  **Note (v0.28.0):**
  the **Cmd+Shift+X** chat snip no longer routes here when your main chat model is
  vision-capable — that model now reads the crop image directly (faster, no double
  round-trip). This light model still applies when the chat model is text-only.

**Convert to LaTeX — what the messages mean (v0.52.1).** Earlier versions showed
one message, "Check Incurator Dashboard → LLM Provider", for every failure, which
often sent you to fix a provider that was working. Each outcome now says what
actually happened:

| Message | What it means | What to do |
|---|---|---|
| `LaTeX copied to clipboard.` | Success. | — |
| `Reading N unencoded symbol(s) from the page image…` | Normal, and usually followed by success. Your selection contains symbols the PDF does not encode as text (see below), so the region is read as an image instead. | Nothing — wait for it. |
| `This selection has N symbol(s) the PDF does not encode as text …` | Same condition, but the page image could not be captured to read them. | Scroll the page fully into view and retry, or snip with **Cmd+Shift+X**. |
| `The model returned an empty transcription for this selection.` | The backend ran fine; the model gave nothing usable back. | Retry, or widen the selection so it carries more context. |
| `Converted, but the clipboard write was refused: …` | The transcription succeeded and only the clipboard step failed (usually a focus issue). | Click into the window and retry. |
| `LaTeX conversion failed: <detail> …` | A real backend or provider failure on the text path, with the underlying error included. | Read the detail; check the LLM Provider card if it names the provider. |
| `LaTeX conversion failed while reading the page image: <detail>. Nothing was copied.` | The same, on the image path. Stated separately so it is clear the clipboard was left untouched. | As above. |

**Why maths sometimes takes the image route (v0.52.3).** A LaTeX paper embeds
its symbols in Computer Modern font subsets, and those subsets frequently ship
without a `/ToUnicode` map. When one does, the PDF genuinely does not record
*which character* a glyph is — only how to draw it — and pdf.js hands back a
null byte in its place. On `3D Line Mapping Revisited` page 4, the ten lambdas
of equation (3) all arrive that way.

There is no way to recover those symbols from the text, because they are not in
the text; they exist only in the rendered pixels. So when your selection
contains any of them, Convert to LaTeX crops that region from the page and
sends the **image** to the vision model, which reads the equation as drawn. You
will see `Reading N unencoded symbol(s) from the page image…` and then the
normal result.

> [!WARNING]
> v0.52.1 handled this badly and v0.52.2 still did: it deleted those glyphs so
> the text could be sent anyway. The model then transcribed an equation with
> every λ missing, and the wrong result was copied to your clipboard looking
> perfectly plausible. If you copied maths with v0.52.1 or v0.52.2, re-check it.

Separately, numeric-only lines (an equation number, a table cell, a page number)
are no longer dropped from the transcription, so a selection that is entirely
numbers converts instead of coming back empty.

Ingest vision runs on your existing provider's **CLI subscription** (Ollama, or the
`claude`/`agy`/`codex` CLIs) — **no extra API keys**. Only vision-capable models
appear in the dropdowns. This replaces the v0.21.0 `latexModel` plugin setting.

> [!NOTE]
> The **Incurator Dashboard → Overview → LLM Provider** card edits the current
> machine's cached model settings in `.cache/config/config.yml`. Each model
> dropdown is paired with an **effort dropdown** that shows only the levels the
> selected model exposes (models with no effort show `—`). Applying saves
> Primary/Fallback and their effort values through `wiki config`, so these
> machine-local choices do not leak into the synced vault `.curator/settings.yml`.
> The model list is bundled from the backend's single-source `data/models.json`
> catalogue when the plugin is built, so model names do not depend on MCP startup.
>
> Below the model dropdowns, an **Ollama models** section lists the recommended Ollama models from `data/models.json` annotated for this machine: each shows an **installed** badge when already pulled or an **exceeds RAM** badge when its `vram_gb` is larger than detected RAM, and not-yet-installed models get a **Pull** button (`wiki plugin models pull`) that runs `ollama pull` and refreshes. This makes the "switch to a local model, then resume the build" flow (see the Sources tab **Retry errored sources** button) work end to end.

### 7.1 Antigravity (default)

Accesses Google Gemini models via the Antigravity CLI (`agy`).

```bash
# Login
agy login
# Or use the plugin command: Login to Antigravity CLI
```

| Model | Description |
|-------|-------------|
| `gemini-3.5-flash` | Default. Fast and efficient |
| `gemini-3.6-flash` | Current fast Gemini vision model |
| `gemini-3.1-pro` | High-quality reasoning |
| `claude-sonnet-4-6` | Fixed-thinking Claude variant exposed by `agy` |
| `claude-opus-4-6-thinking` | Fixed-thinking Opus variant exposed by `agy` |
| `gpt-oss-120b` | Text-only medium-effort model |

`antigravityPrintTimeoutSec`: Maximum wait time for CLI response (default 300 seconds)

### 7.2 Claude

Accesses Anthropic models via Claude Code CLI (`claude`).

```bash
# Login
claude login
# Or use the plugin command: Login to Claude CLI
```

Effort is model-specific. Sonnet 4.6 supports `low` / `medium` / `high` / `max`;
Fable 5 and Opus 4.8 also support `xhigh`; Haiku 4.5 has no effort control.

| Model | Default effort |
| --- | --- |
| `claude-sonnet-4-6` | `high` (plugin default) |
| `claude-fable-5` | `high` |
| `claude-opus-4-8` | `high` |
| `claude-haiku-4-5` | None |

### 7.3 OpenAI Codex

Accesses GPT models via OpenAI Codex CLI (`codex`).

```bash
# Login
codex login
# Or use the plugin command: Login to OpenAI Codex CLI
```

`codexReasoningEffort` is model-specific. Sol and Terra support `low` /
`medium` / `high` / `xhigh` / `max` / `ultra`; Luna stops at `max`; GPT-5.5
stops at `xhigh`. `ultra` may automatically delegate work in Codex.

| Model | Description |
| --- | --- |
| `gpt-5.6-sol` | Default; frontier agentic coding (`low` default effort) |
| `gpt-5.6-terra` | Balanced everyday agentic coding (`medium` default) |
| `gpt-5.6-luna` | Lighter-weight agentic coding (`medium` default) |
| `gpt-5.5` | Visible compatibility model (`medium` default) |

### 7.4 Ollama (Local)

Connects directly to a local Ollama server via HTTP. No authentication required, fully offline.

```bash
# Start the Ollama server
ollama serve

# Pull a model
ollama pull qwen2.5:7b
```

Settings:

- **Ollama host**: Server address (default: `http://localhost:11434`)
- **Model**: Type a model name directly or click **Fetch models** to list installed models
- Vision support varies by model (e.g. `gemma3:12b` supports vision, `qwen2.5:7b` does not)

### 7.5 DeepSeek API

Connects to DeepSeek's OpenAI-compatible API with an API key. It does not use
OAuth or a browser CLI login.

Settings:

- **API key**: Store a device-local key in plugin settings, or leave it blank and
  set `DEEPSEEK_API_KEY` in the Obsidian process environment. A key entered in
  settings is saved when the field loses focus, encrypted under the machine-local
  `.cache/config/secrets/` — never in the vault, so it is not synced and must be
  entered once per device.
- **Model**: Choose from the backend catalogue. As of 2026-08-23 the current
  DeepSeek API model ids are `deepseek-v4-flash`, `deepseek-v4-pro`, and
  `deepseek-v4-flash-vision-exp` (experimental, vision-capable). All three carry
  a **1M-token context window** — the catalogue previously recorded 128K, which
  under-reported the window on the Model row by a factor of eight.
- Legacy aliases `deepseek-chat` and `deepseek-reasoner` are not preferred
  because DeepSeek schedules them for deprecation on 2026-07-24.

Quota or capacity errors from any provider are rendered directly in sidechat so
the user can switch provider/model or configure a fallback instead of seeing an
empty answer. **A quota error is decided from the CLI's error output, never from
the answer** (v0.62.5): the detector is a keyword matcher looking for "capacity",
"quota", "429" and "rate limit", and those are ordinary words in CUDA and
computer-vision writing, so scanning the answer text discarded good answers and
reported them as quota failures. Stdout is consulted only when the run produced
no answer at all, because some CLIs print the refusal there. The detector also
matches **phrases providers actually emit** (`RESOURCE_EXHAUSTED`, `No capacity
available`, `Individual quota reached`, `insufficient balance`, `rate limit`, a
word-bounded `429`) rather than bare words, so ordinary prose cannot trigger it. If a CLI provider (e.g. Antigravity `agy`) finishes with **no
answer** — for example after `Thinking…` when the token/quota is exhausted or the
request times out — the plugin now surfaces a clear error instead of spinning
forever or showing an empty bubble.

Antigravity `agy` print mode normally writes the final answer to stdout and
progress/status lines to stderr. If the CLI exits successfully with empty stdout
but stderr contains non-status answer text, the plugin recovers that text as the
assistant answer. Pure progress stderr such as `Thinking…`, model startup, or
MCP status remains hidden inside the thinking/status block and is not treated as
an answer.

### Authentication status and Sign out

Each provider's **Authentication** row shows its current state:

- **DeepSeek** distinguishes a key saved in the plugin (`✓ API key configured
  (saved in plugin)`) from one provided by the environment (`✓ Using
  DEEPSEEK_API_KEY from environment`). Since v0.62.4 the saved key lives
  encrypted in the machine-local `.cache/config/secrets/` — **not** in the
  plugin's `data.json` and **not** in `.curator` — so deleting `.curator` or
  running `wiki reset` does not clear it; use **Sign out** to remove it. The command
  palette action **Check DeepSeek API Key** checks for either the saved plugin
  key or `DEEPSEEK_API_KEY`; it does not launch a browser login flow.
- **CLI providers** (Antigravity, Claude, Codex) authenticate through their own
  CLI. The plugin reports an account email only when it can read one from the
  CLI's files (Codex). Antigravity `agy` 1.0.5 keeps its session in the OS
  keychain and exposes no account command, so the plugin shows a neutral
  `agy CLI session` rather than guessing an account.
- **Sign out** clears what the plugin controls (the cached credential, the saved
  DeepSeek key, and any plugin-readable credential files). Because CLI providers
  keep their real session in their own keychain/config, fully signing out may
  still require running the provider CLI (`agy`, `claude`, `codex`); the Sign out
  notice says so when relevant.
  Signing out removes the saved DeepSeek key from the encrypted store as well as
  from the plugin's settings (v0.71.0). Before that fix it only cleared the
  settings half, so the key came back at the next restart while the panel still
  reported it as cleared. Signing out with no key saved is not an error, and
  signing out of the plugin does not touch the backend's own DeepSeek key — the
  two are configured separately on purpose.

---

## 8. MCP Server Configuration

Configure the plugin to use external MCP tools. This section is for non-Incurator
tool servers and external agent integrations. The local Incurator backend
integration uses backend commands instead of starting `wiki mcp`.

Go to **Settings → AI Agent → MCP Servers** and add a server:

```json
{
  "name": "my-external-tools",
  "command": "example-mcp-server",
  "args": [],
  "env": {
    "VAULT_ROOT": "/path/to/your/vault"
  },
  "enabled": true
}
```

> **Important**: `VAULT_ROOT` must point to your Vault directory (where `.curator/` lives).  
> Do not set it to the wiki system (Incurator code) path or a testbed path.

### Tool-calling wire format (DeepSeek / Ollama)

The MCP **server transport** is implemented natively in the plugin (JSON-RPC over
stdio) and is provider-neutral. When the plugin runs its in-process agent loop
against an HTTP provider (DeepSeek or Ollama) and feeds MCP tools to the model,
it talks to that provider's `/v1/chat/completions` endpoint.

The function names shown to a model are sanitized transport identifiers. The
plugin keeps an explicit map back to each server's original tool name, including
when punctuation or embedded separators would otherwise produce the same
sanitized name. Restarting or stopping a server rejects its in-flight requests;
a stale exit from the old process cannot mark the restarted server offline, and
late stdout bytes from that process cannot enter the restarted server's fresh
JSON framing buffer.

As of **2026-06-05**, that tool-calling exchange follows the **OpenAI-compatible
chat-completions convention** (`tools`, `tool_calls`, `role: "tool"`, and an
empty-string `content` on tool-call turns). This is **not** a dependency on
OpenAI the vendor — it is the wire protocol that DeepSeek and Ollama themselves
expose; it is currently the only request shape those servers accept. Providers
with their own native tool schema (Anthropic Claude, Google Gemini/Antigravity)
use separate adapters and are unaffected. If DeepSeek/Ollama change their
accepted schema in the future, only the OpenAI-compatible adapters need updating.

---

## 9. Incurator Integration

With `incuratorEnabled: true`, the plugin can use Curator backend features.

### How it works

```text
User types a chat message
      │
      │ (Incurator integration active)
      ▼
IncuratorClient calls hidden backend JSON commands
(`wiki plugin source ...`, `wiki plugin pdf ...`, `wiki plugin context fetch`,
`wiki plugin context expand`, `wiki plugin context verify`,
`wiki plugin context feedback`, `wiki plugin query`)
      │
      ▼
Traceable DAG evidence injected as system context
      │
      ▼
LLM generates answer grounded in retrieved evidence
```

### Incurator settings

| Setting | Default | Description |
|---------|---------|-------------|
| `incuratorEnabled` | `true` | Enable Curator backend integration |
| `incuratorRepoPath` | `""` | **Optional override.** Absolute path to the Incurator repository. Normally left blank — the backend reports its own repo path via `wiki plugin version`. Set this only to override the auto-detected path. |
| `incuratorDefaultDestination` | `04_Resources` | Default folder for PDF reference stubs or explicit copy imports |
| `incuratorDefaultImportMode` | `reference` | Add mode for files (`reference` creates a link stub; `copy` copies into the vault) |
| `incuratorPdfAssetFolder` | `""` (empty) | Base vault folder for images extracted from non-Zotero add-source PDFs. Each PDF uses a sanitized source-name subfolder. Empty means the backend default `05_Assets/<source-name>/`. Zotero PDFs ignore this and use their import profile's asset folder. |
| `incuratorStatusPolling` | `true` | Poll for source processing status updates |

A successfully registered source — `Queued`, `Building...`, or any state from
L1 ready through full L4 Synthesis — shows a non-import badge. The ready states
collapse to **Added** (v0.5.6); `Queued` and `Building...` keep their own labels
while the background build runs. All of these registered states are inert:
clicking them does nothing, so an already-registered source can never be
re-imported by accident. Hover the badge to see the exact layer state in the
tooltip. If a later status refresh finds the source `stale`, `moved`, `changed`,
`missing`, or in `error`, the badge switches back to that actionable label and
becomes clickable again. Any layer error is shown as an error instead of a
healthy badge.

### Setup/Rebuild Banner

The Incurator backend and the Obsidian plugin may be rebuilt at different times
on different devices. `./setup.sh` writes a shared backend/plugin build
fingerprint. When the plugin checks `wiki plugin version`, it compares the
backend fingerprint with the fingerprint bundled into the installed plugin.
If the generated backend manifest is missing, `wiki plugin version` still returns
a stable `build` object with backend/plugin version, git commit key, and schema
metadata so the update check does not crash on an empty object.

If the fingerprints are missing or do not match, the chat window shows a
setup/rebuild banner — but only when a repo path is available to update from.
The plugin resolves the repo path in this order: the optional
`incuratorRepoPath` override → the path the backend reports in
`wiki plugin version` (`repo_path`) → none. When the backend is a regular
(non-editable) install with no repo, `repo_path` is `null` and the banner is
hidden so there is no dead update button.

Clicking the update button copies the freshly built `main.js`, `manifest.json`,
and `styles.css` from `<repo>/plugin/` into the **currently open vault's**
plugin directory. It does **not** run `git pull` or `./setup.sh` — building the
backend and plugin is the job of `./setup.sh`, which you run manually after
pulling updates. Other vaults update themselves the next time they are opened.
After all required plugin artifacts copy successfully, the button becomes
**Reload Obsidian** and performs the renderer reload needed to activate the new
bundle.

If plugin files are replaced by `./setup.sh`, Syncthing, or another external
deployment while Obsidian remains open, the old bundle is still running in
memory. Before starting an AI provider, the plugin compares the active bundled
build identity with the installed bundle on disk. A mismatch blocks the request
and asks you to reload instead of silently running stale code. This activation
gate is why a security or provider hotfix cannot appear installed while the old
runtime continues answering questions.

`Use Incurator backend` controls whether the plugin uses local Incurator backend
commands. When enabled, the plugin discovers the `wiki` binary, reads backend
runtime snapshots, and calls hidden `wiki plugin ...` JSON commands for source,
PDF, query, promotion, and Zotero operations. The generic MCP Servers section
remains available for other MCP servers; the plugin does not auto-start
Incurator MCP for same-device backend access.

### PDF → Curator registration flow

When Incurator integration is on and you reference a PDF:

```text
Cmd+Shift+L (or Cmd+Shift+X) captures PDF content
      │
      │ backend source registration command
      ▼
Source registered in Curator backend
      │
      │ L1 → L2 → L3 processing (background)
      ▼
Shared L4 Synthesis is available after build
      │
      ▼
Searchable via query/search tools
```

The purple PDF chip is the refinement control. Clicking **Add source** does not
wait for the whole DAG to finish; it registers the source, creates L1, and queues
L2/L3. Use **Dashboard > Jobs > Run queued** when you want to actively drain the
queued build work, or leave the queue for a backend worker to process. Once the
source is tracked, the chip shows the inert **Added** badge described above.
If backend registration succeeds but a non-fatal maintenance step such as the
search-index refresh is skipped, the backend returns the warning in the
`warnings` array instead of failing the registration.

Images embedded in an added PDF (figures, diagrams) are extracted during the
instant L1 step and saved into the vault so the generated L1 context page can
embed them with `![[...]]` links. Where they land (v0.5.6):

- **Zotero-backed PDFs** reuse the asset folder of the matching Zotero import
  profile (the same base folder + per-item subfolder the annotation images use),
  so a paper's extracted figures sit next to its annotation assets.
- **Other PDFs** go to a sanitized source-name subfolder under the
  `incuratorPdfAssetFolder` base folder if you set one.
- **Fallback** (setting empty, or the resolved folder is unsafe, cannot be
  resolved, or escapes the vault): the backend default
  `05_Assets/<source-name>/`.

The L1 page always links the folder the images were actually written to, so the
embeds resolve either way. Note that text-layer extraction of mathematical
notation from PDFs is approximate; improving math fidelity (VLM-assisted
extraction) is tracked separately by the RAG & Knowledge Quality Stabilization
program, not by this asset-routing feature.

For ordinary workspace/domain questions with no primary selected text, line
range, PDF page, or crop image attached to the latest user turn, sidechat calls
`wiki plugin context fetch` by default. The returned ContextService pack is
inserted into provider context as evidence items, with `pack_id`, snapshot,
budget, omissions, locators, expansion handles, and verification handles
available to Sources & Trace. Sidechat does not inject the backend synthesized
answer by default. `wiki plugin query` remains available for explicit backend
synthesis and still returns additive trace/provenance fields for compatibility.
If the latest turn is focused on a selected crop or editable Markdown region,
sidechat skips the workspace pack and answers from that selected context instead.

For PDFs opened from Zotero or another external location, **Add to Incurator**
uses Reference Mode by default. The backend leaves the PDF in place, creates a
small markdown reference stub under `04_Resources/`, and stores the real PDF
path as device-local backend source metadata. The generated stub does not embed
the absolute PDF path by default, so it can sync to another device where Zotero
or external PDFs live elsewhere. For Zotero PDFs, the stub includes portable
Zotero identity and a `zotero://open-pdf/library/items/<key>` link so it is
clearly a Zotero-backed reference. Copying a PDF into the vault is an explicit
exception, not the default.

Zotero setup and repair are backend-owned. The plugin asks hidden backend JSON
commands for Zotero status, initialization, metadata, annotations, and PDF
attachment resolution, then presents any required user choice or repair action.

The dashboard **Reset** action asks for two confirmations before clearing the
local database and generated L1-L4 content.

Dashboard status comes from backend-owned local snapshots under
repo-cache `runtime/`, not from plugin-owned state. The backend is the only writer
for those JSON files; the plugin asks the local backend to refresh them before
rendering source counts, job state, index health, and backend version. Missing
or stale snapshots are treated as waiting or unknown state, not as an empty
backend. Runtime `status.json` and `sources.json` do not export absolute local
paths. Machine-local paths such as model GGUF files, Zotero roots, and external
reference locations remain in the repository-local `.cache/config/config.yml`
and are consulted through backend commands when the plugin needs live local
resolution.

Dashboard buttons run backend commands for mutations; the plugin does not
directly edit backend-owned `.curator` state for those actions. The primary
Overview action is **Update** (the one-shot `wiki update`: add → build → embed →
sync); the granular **Add / Build / Sync / Lint / Reindex / Reset** steps live
under an **Advanced** disclosure. For exact CLI behavior and flags, use the
canonical [CLI Reference](USER_GUIDE.md#cli-reference). LLM Apply and Persona
Save persist config.

Backend commands are bounded so a hung subprocess cannot wait forever or grow
memory without limit. Normal metadata/search/config operations allow up to 2
minutes and 16 MiB of combined output; pipeline, import, model-download, and job
operations allow up to 60 minutes and 64 MiB. Reaching a bound stops the process
and reports a visible failure; long operations keep their larger policy instead
of being truncated by the normal-command limits.

### Dashboard tabs (v0.3.3)

- **Overview → System** card shows the DB-native search engine plus the live
  **Embed model** and **Reranker** rows (identity + health, from the backend
  `search_models` status). Click either row to re-provision the local search
  models (`wiki plugin models refresh` → downloads the Qwen3 GGUFs / installs
  `llama-cpp-python` / starts Ollama as needed). A `· not downloaded` /
  `· runtime missing` suffix flags an unhealthy model.
- **Traces** tab lists durable `QTR-` query traces from the current Obsidian
  vault via the vault-local backend command runner (`wiki plugin trace list`).
  Selecting one loads a separate backend detail view with route (and its reason),
  latency, mode/**expansion cue**, **derivation status**,
  degradation/`fallbackMode`, warnings, evidence, and available RRF/rerank
  contribution data (`wiki plugin trace show`).

  The **Derivation** row says whether a search-query derivation ran for that
  query, and what it produced — `derived — no search terms, intent=synthesis`,
  or `not run — routed on the raw question`. *A derivation ran and found no
  search terms* (normal for a whole-corpus question) and *no derivation ran*
  both leave an empty search query, so only this row tells them apart.

  The cue row is labelled **expansion cue**, not "intent": that value
  (`definition` / `comparison` / `procedure` / `default`) steers query expansion
  and is a different mechanism from the routing intent
  (`lookup` / `synthesis` / `discovery`) shown on the Derivation row.
- **Synthesis** tab lists recent L4 `SYN-` nodes from the current vault
  (`wiki plugin synthesis list`). Selecting one loads the read-only L4-to-L1
  audit chain (`wiki plugin synthesis show`) with community reports, graph
  entities/relations, source spans, prompt traces, and grounding/staleness
  warnings.
- **Sources** tab lists recent sources with per-layer L1–L4 status badges. If a
  build stopped on an error (for example *"Antigravity capacity exhausted
  (429)"*), the tab shows a **Retry errored sources** button at the top. After
  switching to a working model (Settings → LLM Provider, or the Overview LLM
  Provider card), click it to resume: it runs `wiki build`, which re-attempts
  every source whose L2/L3 is still `pending` or `error` with the now-current
  provider, continuing the knowledge-refinement graph from where it stopped. An
  L4 **Skipped** badge is terminal and non-error: global L3/L4 finished, but no
  eligible shared synthesis exists for the current community-report corpus.
  Watch progress in the **Jobs** tab.
- **Insights** tab lists pending derived insight candidates
  from the current Obsidian vault (`wiki plugin insight list`). Selecting one
  loads the backend detail payload (`wiki plugin insight show`) before exposing
  **Promote** (`insight promote`, writes to `02_Wiki/`) and **Reject**
  (`insight reject`) actions. Promotion/rejection are always explicit user
  actions; the backend never auto-promotes.

Zotero search, metadata refresh, PDF path resolution, annotation loading, source
status/import/rebind, PDF context/search, query, and promotion use the hidden
plugin-local backend API (`wiki plugin ...`). This keeps durable backend state
and local filesystem/database resolution in backend code without requiring the
plugin to discover or call Incurator MCP tools, and without exposing plugin
plumbing as normal human-facing `wiki` commands.

---

## 10. Sync Notes

### Cross-device knowledge auto-sync (Syncthing)

When the **Auto-sync knowledge DB** setting is on (default), the plugin keeps your
knowledge base in step across every device that shares the vault through Syncthing —
no manual export/import.

- **Triggers**: one pass when Obsidian opens (Auto-sync on open), live detection when
  Syncthing delivers a peer file (Watch for incoming sync data — desktop only), a
  60-second safety poll, and a manual **Sync Knowledge DB** ribbon button. After
  the backend identifies this device's exported snapshot filename, the watcher
  ignores that self file instead of treating it as incoming peer data. If the
  watched directory is deleted, renamed, or becomes inaccessible, the plugin
  logs the watcher error instead of raising an unhandled Electron exception;
  the 60-second poll continues to provide fallback coverage.
- **What a pass does**: runs `wiki db autosync` in the backend — imports every other
  device's snapshot (`.curator/sync/dev-<id>.jsonl`), merges any Syncthing
  `*.sync-conflict-*` files, then writes this device's own snapshot if anything changed.
  All heavy work runs in the backend subprocess, so the Obsidian UI never freezes.
- **Refused rows are always reported (v0.50.0)**: if a peer's snapshot is
  truncated or malformed, the database refuses those rows. They are counted
  separately and never as "new", and the plugin raises a notice naming the
  count — **even when sync notifications are turned off**, because this is data
  that did not arrive rather than routine progress. The rest of the file still
  imports, so one bad row cannot wedge syncing on that device; re-export from
  the other device to resolve it.
- **Merge safety**: portable source keys remap replica-local numeric ids;
  row-level monotonic Last-Write-Wins + tombstones preserve concurrent reads and
  disjoint-source edits. Composite primary keys are compared as complete keys,
  and composite tombstones encode every key field in validated canonical JSON;
  source-scoped tombstones carry a portable source key rather than a local id.
  An equal/newer tombstone blocks a stale row, while a strictly newer mutable row
  clears its older tombstone and proceeds. Equivalent rows are skipped even when
  a peer sends a fresh full-snapshot
  `export_id`, so unchanged snapshots cannot trigger re-export ping-pong. Deletes
  propagate. No whole-file overwrite.
- **Feedback**: a status-bar `⟳ Sync` while running, and a toast only when a sync actually
  applied changes (Notify on sync changes).

If local sync bookkeeping is corrupt, a peer import fails, or a conflict cannot
be archived, the backend returns a failed pass. The plugin shows **Sync Failed**
and does not show a “Merged conflict” toast for that file. After correcting the
reported state/file/permission problem, the next coalesced poll or manual sync
retries safely; a failed pass never resets the device identity.

All devices must use the same JSONL schema version. After the v13 upgrade, each
device publishes a new snapshot; v12 snapshots are skipped rather than partially
applied. An unsupported raw composite tombstone fails the pass visibly and is
preserved for operator review.

Source layer statuses use the source row's dedicated `updated_at` revision, so
L1-L4 status-only changes participate in LWW sync. Dashboard Knowledge Graph
counts come from serving DB records, never stale Collection projection files.
Machine-local backend settings (`llm`, `search`, and `external` roots/model
paths) are loaded only from the current device's repo-local
`.cache/config/config.yml`; if those blocks are present in synced
`.curator/settings.yml`, the backend ignores them so Linux and macOS paths do
not overwrite each other.
Zotero profile saves are serialized and merge the canonical text supplied at
the atomic commit boundary, so a stale device cannot erase peer-only profiles
during an unrelated settings save. If a partially damaged decoded payload is
missing `profiles` or `recentItems`, the merge treats that property as an empty
array rather than crashing.

| Setting | Default | Effect |
| --- | --- | --- |
| Auto-sync knowledge DB | On | Master switch for all auto-sync behavior |
| Auto-sync on Obsidian open | On | Run one sync pass at vault load |
| Watch for incoming sync data | On | `fs.watch` peer snapshots in `.curator/sync/`; ignore the known self snapshot (desktop) |
| Notify on sync changes | On | Toast only when a sync applied changes |

> [!WARNING]
> Disabling the plugin's **Enable Incurator** master switch also disables every
> plugin-side auto-sync trigger on that device. On a CLI-primary device this is
> fine — since v0.30.0 the backend exports the device's snapshot after every
> mutating CLI command (`wiki add`/`build`/`sync`/`update`, `auto_sync.enabled`
> default-on) — but a device that neither runs the plugin nor mutates via the
> CLI will simply never publish new knowledge to its peers.

> [!NOTE]
> The local DB/runtime/staging/temp tree lives under repo
> `.cache/vaults/<vault-key>/`. Device id and peer high-water marks live under
> `.cache/config/sync_state/<vault-root-hash>.json`; only the `.curator/sync/`
> JSONL snapshots travel between devices. See the User Guide
> "Cross-Device Knowledge Sync" and the Sync Ignore Guide.

### Session history (`sessions.json`)

Plugin data is split across these files.

| File | Contents | Cross-device sync |
| --- | --- | --- |
| `data.json` | Settings such as provider, model, and MCP servers | Recommended only when paths match |
| `.curator/sessions.json` | Chat conversation history | Supported |
| `.curator/zotero_profiles.json` | Zotero import profiles + recent-item LRU (v0.30.0) | Supported |
| `<repo>/.cache/vaults/<vault-key>/runtime/*.json` | Backend dashboard/status snapshots | Local only |

In v0.2.1, the plugin re-reads the latest on-disk `sessions.json` before saving and merges by session id. This preserves distinct sessions created on Linux and macOS. Deleted sessions are recorded in `deletedSessionIds` tombstones so an older synced file does not resurrect them later. If the same session is edited on both devices concurrently, the copy with the newer `updatedAt` timestamp wins.

Since v0.40.0, session loading distinguishes a genuinely missing canonical
file from corrupt or unreadable state. Legacy/default migration is allowed only
when `.curator/sessions.json` is missing. If it exists but cannot be parsed or
read, the original bytes stay untouched, the session store is read-only for the
current plugin run, and a notice asks you to repair or restore the file and
reload Obsidian. A file that becomes corrupt between load and save also blocks
that save instead of being replaced. For an existing valid session or
Zotero-profile file, the serialized save parses and merges the exact canonical
text supplied by Obsidian's atomic process callback, including a peer update or
deletion tombstone that arrived just before commit. The plugin adopts in-memory
state only after that commit succeeds. A transient process failure rejects that
save without falsely marking valid data corrupt. Initial creation may use a
temporary sibling and rename; partial temp-write and rename failures clean the
sibling and never publish partial JSON. Obsidian's portable adapter has no
simultaneous create-if-absent guarantee, so conflict-free first creation is not
claimed.

Session sync does not make absolute PDF/Zotero paths portable. Context attached
to chat messages may preserve portable identity such as a Zotero attachment key,
file hash, vault-relative path, and page number, but device-local absolute paths
from macOS or Linux are verified or re-resolved on the current device before
being used. The plugin sanitizes session data immediately before every
`sessions.json` write, including first-write and legacy-migration paths, so
captured absolute source paths do not become synced chat history. Runtime
backend `status.json` and `sources.json` snapshots are also path-sanitized before
write. If a synced session references a Zotero PDF, the current device's local
Zotero database and linked-attachment roots are used to recover the real PDF
path.

The sidebar conversation list derives each chat title from the first assistant
answer after the first user question. Reasoning-model `<think>…</think>` blocks
are stripped first so the title summarizes the actual answer rather than showing
literal `<think>`/`<thinking>` text (an unclosed reasoning block is dropped
entirely). While that answer is still pending, it uses the first user question
as the temporary title. Each row also shows relative last activity from
`updatedAt`, such as `12m ago` or `3h ago`.

Deleting a chat session from the sidebar trash action is immediate. The delete
is still recorded as a tombstone in `deletedSessionIds` so synced devices do not
restore the removed session.

If the backend executable path differs per device, or one device does not have
Incurator installed, `.cache/config/devices.json` is the local override for the
current device. A synced `data.json` may still contain an `incuratorRepoPath`,
but on startup the plugin replaces it in memory with the current device's
`backend.repo_path` from `.cache/config/devices.json` when that value exists. If you
want to avoid syncing any plugin-local settings at all, add `data.json` to
`.stignore`, not `sessions.json`.

```text
.obsidian/plugins/incurator-obsidian-agent/data.json
```

When `Backend command` is left as `wiki`, the plugin resolves the backend from
the repository path as `<repo>/.venv/bin/wiki`. It does not run a global PATH
`wiki`. If the repository is a sibling of the vault workspace, for example
`Workspace/Incurator` next to `Workspace/second_brain`, the desktop plugin can
use that path as a memory-only local hint without writing it to plugin
`data.json`. Otherwise configure **Settings > AI Agent > PDF & Incurator** like
this on each device:

| Setting | Value |
| --- | --- |
| `Repository path (override)` | `/Users/<you>/Workspace/Incurator` |
| `Backend command` | `wiki` |
| `Backend arguments` | `[]` |

On startup and after settings saves, the Obsidian plugin automatically records
Syncthing device names and the current device's backend launcher/repository hint
in `.cache/config/devices.json`. This registry lets Linux/macOS path differences be
visible without letting a synced `data.json` path clobber the active machine's
runtime path. The dashboard Overview lists every device in the active
Syncthing shared-folder registry, including remote devices that have no backend
launcher configured on the current machine, and shows whether each device syncs
the Vault and/or Zotero folders. The current machine is marked as **This
device** using Syncthing's local REST `myID` when available, then the per-device
repository path/backend launcher hint as a fallback. There is no standalone
Devices tab. Unknown platform fields are shown as unknown instead of guessed.
`wiki devices sync` is a manual repair command when the automatic refresh is
unavailable; `wiki devices` inspects the current registry.

See [SYNC_IGNORE_GUIDE.md](SYNC_IGNORE_GUIDE.md) for the full synchronization setup.

### External PDF restart behavior

An open external PDF keeps its resolved absolute path only in memory. Persisted
plugin/view/session state does not use that device-specific path as durable
identity. Zotero-backed tabs persist `zoteroAttachmentKey` and resolve it through
the current device's backend/Zotero configuration after restart; generic
external tabs persist a portable `externalRef` under a machine-local named root.
If the current device has not configured that named root, or the referenced file
was moved outside it, the tab cannot reopen the file until the root or reference
is repaired. The plugin does not fall back to a synced absolute `doc.path`.

---

## 11. Zotero Integration

When a Zotero data directory is configured, clicking a `zotero://open-pdf/library/items/<KEY>?page=X` link in a Markdown note opens the PDF directly in the built-in viewer — no Zotero app required.
- If the link contains a `?page=X` parameter, the viewer will automatically scroll to that page.
- If the link contains `annotation=<KEY>&viewer=obsidian`, the existing PDF view is reused and navigated to that page and annotation location; the annotation area is shown as an empty outline box so the PDF content remains visible.
- If the link contains `viewer=zotero`, the plugin lets the link open in Zotero instead.
- Clicking multiple Zotero links for the same PDF will re-use the existing split view rather than opening new ones.

### Setup

Go to **Settings > AI Agent > Zotero Integration > Backend Zotero status > Open setup** to inspect what the backend can actually read on this device. The setup dialog is the single Zotero data-directory entry point, defaults to `~/Zotero`, displays home-directory paths with `~` instead of an absolute `/Users/...` prefix, and can save the data directory plus an optional linked attachment root to the backend for future status checks, searches, PDF resolution, annotations, and Add-to-Incurator registration.
> **Note**: If you use the default Zotero profile location (`~/Zotero`), the backend automatically parses your `prefs.js` to auto-discover the Linked attachment root and ZotMoov destination directory. Therefore, you typically do not need to manually enter the linked attachment root in the settings dialog. It is only provided as an override for custom environments where auto-discovery fails.
When backend resolution returns checked roots or checked PDF paths, the setup
dialog shows them as candidate roots with a **Use** action so you can populate
the data-directory or linked-root field without retyping long paths.

| OS | Default path |
| --- | --- |
| macOS | `~/Zotero` |
| Linux | `~/Zotero` |
| Windows | `C:\Users\<username>\Zotero` |

The directory should contain `zotero.sqlite`; attachment PDFs may be in Zotero
`storage/` or a linked/base attachment directory. The linked attachment root is
only for Zotero DB `attachments:` paths; ordinary `storage/<KEY>/...`
attachments do not need it. If the directory moved or the database is missing,
the backend status command reports a structured state instead of making Zotero
search look like an empty library.
When a Zotero link or Add-to-Incurator action cannot resolve a PDF, the backend
returns a structured state: `db_missing`, `attachment_key_missing`, or
`attachment_file_missing`. This keeps "Zotero is unavailable", "the item key is
not in this database", and "the linked PDF file is missing from configured
roots" separate in plugin UI. The plugin opens the same Zotero setup dialog from
Settings, Dashboard, Zotero link failures, and sidechat Add-to-Incurator
failures so repair logic stays in one UI path.
 From v0.61.0 there is a fourth: `attachment_file_denied`, meaning the PDF is
 there and this app is not permitted to read it. It is shown as a permission
 problem naming the folder to grant, not as a missing file.

### Import Zotero Item

Leaving the `Import Zotero Item` search box blank shows recently modified Zotero items ordered by `dateModified`. The Zotero directory setting may contain multiple comma-separated data directories; the plugin checks each path's `zotero.sqlite` in order.

Editing a saved profile in **Settings → Zotero Import Profiles** has no Save
button: fields save as you type and again when you leave the field, so changing
a value and clicking away is enough. (Before v0.42.1 only the first typed
character was actually persisted — a template path edited from
`book_template.md` to `paper_template.md` could be stored as `boo_template.md`.
If you edited a profile on an earlier version, re-check its values.)

When the import wizard opens and saved profiles exist, the **most recently used
profile is loaded automatically** and the Import Profile dropdown lists profiles
most-recently-used first (v0.21.0), so the profile you are actively working with
sits at the top instead of being buried under older ones. A profile's recency is
updated whenever you import an item with it (or create it). Successfully imported items are remembered
in a `recentItems` LRU list so they appear before other matches in
later Zotero searches. Created or updated Zotero notes also store the originating
profile name in frontmatter as `zotero_profile`, so reload can use the same
template and asset folder even when multiple profiles exist.

**Profiles sync across devices (v0.30.0).** Import profiles and the
recent-item LRU are stored in `.curator/zotero_profiles.json` inside the vault —
the same synced location as `sessions.json` — so a profile created on one
device appears on your other devices after Syncthing sync. (Before v0.30.0 they
lived in the plugin's `data.json`, which is typically excluded from sync, so
each device saw a different profile list.) On first load after upgrading, the
plugin migrates existing profiles out of `data.json` automatically and
non-destructively; profiles contain only vault-relative paths, so they are safe
to share between Linux and macOS. Serialized saves merge peer-only profiles,
recent-item keys, and deletion tombstones from the canonical commit-time value.
Same-name concurrent edits remain last-write-wins according to the stored
profile timestamps.

If `.curator/zotero_profiles.json` ever becomes corrupted (invalid JSON or an
unrecognizable structure — e.g. an interrupted sync or a bad hand-edit), the
plugin does **not** overwrite it: profiles go read-only for the session and a
notice asks you to repair or delete the file, after which a reload restores
normal behavior. Your profile data stays recoverable on disk. Damage to
individual entries inside an otherwise-valid file is repaired in place
(unusable entries are dropped, missing text fields become empty) without
touching the rest.

Output subfolders, filenames, and asset subfolders use the same Nunjucks
templating engine as Zotero note templates. Examples:

```text
{{ date | format("YYYY") }}/{{ creators | firstAuthorLast | pathSafe }}
{{ creators | firstAuthorLast }}_{{ title | pathSafe }}
{{ tags | joinTags("; ") }}
```

Rendered path segments are sanitized before files are created in the vault.

Import is also the explicit repair path after a Zotero item has been recreated
or moved by an attachment manager such as ZotMoov. If the selected item's
rendered filename differs from an existing note only by letter case, the wizard
updates that existing note instead of failing with `File already exists`. It
keeps the existing filename and persisted template regions, while refreshing
the note from the selected item's current metadata, including its current
parent-item and PDF-attachment links. Other filesystem creation errors are
reported normally.

### Reload Zotero Item / PDF (`Cmd+Shift+R`)

With a Zotero note (it has a `citekey` or `zotero_app_url` in frontmatter) or an
external PDF view active, **`Cmd+Shift+R`** reloads it — the same action as the
PDF viewer's toolbar Reload button:

- **Zotero note**: re-fetches the item's metadata and re-renders the note from its
  stamped `zotero_profile` template when present, falling back to the first saved
  profile only for older notes without that stamp. Annotation region images are
  localized into the vault asset folder using the **same** path resolution as the
  selected import profile (`assetFolder` / `assetSubfolder`, e.g.
  `05_Assets/.../{{citekey}}`), so reload writes
  **vault-relative** embeds (`![[05_Assets/...]]`) — never absolute
  `![[/Users/.../Zotero/cache/...]]` paths. If an annotation region changed in
  Zotero, its asset file is **overwritten** so the note shows the current image.
  If the item cannot be resolved — for example a note that has only a `citekey`
  and no `zotero_app_url` (a citekey is not a Zotero item key) — reload **aborts
  with a clear error and leaves the note unchanged** instead of rewriting it with
  empty metadata. Re-import the note from the Zotero wizard so it records a
  `zotero_app_url`.
- **External PDF view**: drops the cached document and re-reads the PDF from disk.

### Annotation links and parent-item resolution

A `zotero://select/library/items/<KEY>` link (as stored in `zotero_app_url`)
carries the **parent item** key. Backend PDF resolution now resolves that parent
key to its **child PDF attachment**, so the link still opens the PDF, and an
annotation link (`...?annotation=<KEY>`) jumps to and highlights the annotation —
annotation lookups use the resolved child attachment key.

When a Zotero PDF is opened in the plugin viewer and registered from the
sidechat/purple-pin flow, Incurator registers the original file in Reference
Mode instead of copying it into the vault. The generated reference stub records
the Zotero attachment key and a Zotero open-pdf link, while the resolved local
PDF path stays in backend source metadata. The plugin shows a completion notice
when registration succeeds and an error notice when the backend cannot resolve
or register the file path. The Zotero path setting may point either to a Zotero
data directory or directly to `zotero.sqlite`; backend PDF resolution normalizes
the latter to its parent directory before checking `storage/<attachmentKey>/`.
For linked Zotero attachments, backend resolution also checks configured linked
attachment roots for `attachments:` paths.
When the plugin has a Zotero attachment key, Add-to-Incurator can pass that key
to backend source import directly; the backend resolves the PDF and records a
stable `zotero:<attachmentKey>` logical source id for the local reference row.
If the viewer has already resolved the PDF, the plugin may pass both the local
path and attachment key. The backend still uses the key as the portable
identity and treats the path only as a current-device read hint; Zotero
registration must not require that path to appear in generic
`external.path_roots`.
Repeated registration of the same Zotero attachment reuses that logical source
id instead of creating `-02` reference stubs. PDF crop/snipping context is
temporary chat context; it is sent to the selected model when possible and must
not leave durable generated images under `05_Assets`. Temporary crop files and
CLI image/cache byproducts live under repo `.cache/` and are removed after the
request. If the repo cannot be resolved, the plugin fails visibly instead of
writing temporary files into the vault.
Zotero setup and repair are backend-owned: the plugin should call hidden JSON
commands such as `wiki plugin zotero status`, `wiki plugin zotero init`,
`wiki plugin zotero search`, and `wiki plugin zotero resolve-pdf` instead of
treating plugin settings as canonical. PDF context requests should pass the
richest identity available, such as a source id, file hash, vault relpath,
absolute path, or Zotero attachment key, so the backend can resolve moved or
reference-mode files consistently. Absolute paths are per-device hints used for
the current backend call; they must not be written into synced `04_Resources`
reference stubs.

For chat answers, the plugin-selected provider/model writes the final sidechat
answer. Backend/Incurator calls supply retrieved context, PDF windows, source
status, or backend synthesis only when the plugin explicitly calls them. The
plugin uses a structured language bridge for every latest request: detect input
language, use English for internal search/reasoning/tool arguments, then answer
in the detected latest input language unless that latest request asks for
another output language. Previous turns, Korean Markdown context, and saved
saved metadata does not set a persistent answer language; English latest
questions receive English final answers unless the latest request asks
otherwise. When `curator_query` runs, the chat transcript keeps compact parseable
trace fields so the Sources & Trace panel can show the supporting evidence, but
stale `final_output_language` is not reused as sidechat language state.

Input-language detection is deterministic and runs fresh on every chat turn.
The plugin classifies the latest request by Unicode script — for example Korean
(한글), Chinese (汉字), Japanese (かな), Russian (Кириллица), Arabic, and others,
falling back to English for Latin script — and the same canonical detector is
used whether the turn triggers a backend curator query or a plain provider chat.
So a chat session that receives an English question answers in English, a Korean
question answers in Korean, and a Chinese question answers in Chinese, each
decided independently per message regardless of what language earlier turns used.
The detected language is the answer language directly; the model does not first
produce English and then translate in a separate pass. The three language fields
(`input_language`, `english_query`, `final_output_language`) live only in the
query JSON/trace and are never written into generated node frontmatter. A plain
chat whose active note is not inside a workspace folder is treated as outside a
workspace and resolves to `default`, never to an unrelated project workspace you
did not open.

### Zotero link flow

```text
Click zotero:// link in a Markdown note
      │
      │ (Zotero data directory is configured)
      ▼
Plugin intercepts click and tries the built-in viewer first
      │
      │ Scans storage/<ATTACHMENTKEY>/*.pdf
      ▼
Resolves PDF path → opens in built-in viewer (split view)
      │
      │ If the PDF cannot be resolved locally
      ▼
Falls through to the Zotero app
      │
      ▼
Use Cmd+Shift+L to add to chat context or trigger Incurator ingest
```

The global `window.open` / Electron `openExternal` fallbacks are only restored on
plugin unload if Incurator still owns those patches, so another plugin that
patches the same openers later is preserved.

### Generating Zotero links

Right-click an item in Zotero → **Copy Item Link**, or use the [Zotero Integration](https://github.com/mgmeyers/obsidian-zotero-integration) plugin to auto-generate notes that include `zotero://` links.

> **Note**: If no Zotero data directory is set, the click falls through to default behavior (browser or Zotero app).

---

## 11. Keyboard Shortcuts Summary

| Shortcut | Action |
|----------|--------|
| `Cmd+Shift+K` | Quick query on the selected text (In-line Copilot) |
| `Cmd+Shift+L` | Add current content to chat context (Markdown or PDF) |
| `Cmd+Shift+X` | Snip PDF region → attach to chat (Incurator PDF viewer only) |
| `Cmd+Shift+;` | Toggle chat sidebar |

> On macOS, `Cmd` = `⌘`. On Linux/Windows, use `Ctrl`.

---

## 12. v0.3.2 Curation-Native Interfaces

The plugin talks to the backend's v0.3.2 curation-native features through hidden
local JSON commands (never via MCP for same-device flows). The client
(`IncuratorClient`) exposes:

| Client method | Backend command | Returns |
|---|---|---|
| `getCuratePlan(workspacePath)` | `wiki plugin curate plan` | `IncuratorCuratePlan` (route, selected/excluded sources, allowed modes, validation errors) |
| `getPromptTrace(traceId)` | `wiki plugin prompt trace` | `IncuratorPromptTrace` (prompt id/version, validator status, model) |
| `listInsightCandidates(workspacePath)` | `wiki plugin insight list` | `IncuratorInsightCandidate[]` |
| `getInsightCandidate(insightId, workspacePath)` | `wiki plugin insight show` | `IncuratorInsightCandidate` with evidence/source event details |
| `promoteInsight(insightId, workspacePath)` | `wiki plugin insight promote` | `{ promotedTo }` (writes only `02_Wiki/`) |
| `rejectInsight(insightId, workspacePath, reason)` | `wiki plugin insight reject` | `{ ok, status }` |
| `listQueryTraces(workspacePath, limit)` | `wiki plugin trace list` | Recent `QTR-` trace summaries |
| `getQueryTrace(traceId, workspacePath)` | `wiki plugin trace show` | Query route, evidence ids, retrieval trace, warnings |
| `listSynthesisNodes(workspacePath, limit)` | `wiki plugin synthesis list` | Recent L4 `SYN-` summaries |
| `getSynthesisAudit(synthesisId, workspacePath)` | `wiki plugin synthesis show` | Read-only L4-to-L1 synthesis audit report |
| `proposeCorrection(nodeId, correction, previous, workspacePath)` | `wiki plugin correction propose` | Classification/recommended action/review flag |

## 13. Git Sidechat Integration

The plugin exposes local Git repository workflows through sidechat without
adding manual Commit/Push dashboard buttons. It uses your existing local `git`
only — there is **no GitHub CLI (`gh`) dependency** and the plugin never stores
GitHub tokens. (Authentication for pushing over HTTPS, if you use it, is handled
by your normal git credential helper, outside the plugin.)

Repository operations use hidden backend JSON commands:

| Client method | Backend command | Purpose |
|---|---|---|
| `getGitStatus()` | `wiki plugin git status` | Branch, upstream, ahead/behind, dirty counts, `.curator/` ignore warning |
| `getGitLog(limit)` | `wiki plugin git log` | Recent vault commits |
| `getGitDiffStat()` | `wiki plugin git diff --stat` | Capped working-tree diff summary |
| `getGitHistory(filePath, queryText, limit)` | `wiki plugin git history` | Active Markdown file or selected-text history |
| `pushGitChanges()` | `wiki plugin git push` | Push current branch when upstream is safe |
| `commitGitChanges(message)` | `wiki plugin git commit` | Guarded fallback for explicit commit requests |

The default workflow assumes the vault may already use scheduled commits. For
requests like `push해줘`, sidechat should push existing commits rather than
creating a new commit first. For selected Markdown history questions such as
"이 내용 예전에 어떻게 바뀌었는지 히스토리 찾아줘", sidechat should pass the
selected text or a normalized excerpt plus the active Markdown file path to
`getGitHistory`.

Git commands must be deterministic backend calls through `IncuratorClient`, not
provider-native shell/tool guesses. If the backend reports no git repository, no
upstream, or a behind/diverged branch, sidechat reports the structured blocker
instead of attempting a merge, rebase, or unsafe push.

Query results (`CuratorQueryResult`) and the Sources & Trace panel carry the
v0.3.2 fields additively: `route`, `trace_id` (`QTR-`), `prompt_trace_ids`
(`PTR-`), `source_span_ids` (`SPAN-`), `community_report_ids` (`REP-`),
`memory_path_ids` (`MPATH-`), `insight_candidate_ids` (`INS-`), `pack_id`,
`snapshot`, and `budget`. The hidden `wiki plugin query` command returns these
fields both at the additive result level and inside `trace` for L3-complete
ContextService-backed answers. Older/partial backend responses simply omit them,
so the panel degrades gracefully.

When explicit backend synthesis fails at the provider boundary, the hidden
`wiki plugin query` command still emits one parseable result with `ok=false`,
`error`, and every available QTR/PTR/provenance/warning field, then exits 1.
The plugin consumes that JSON even on the non-zero exit. Sources & Trace shows
the failure reason with the retained trace; it must not mix diagnostic process
text into the answer or treat the failure as an empty success.

Plan F adds normalized context packs to this flow. The plugin calculates the
provider's remaining context budget after local selected/pinned/open-note/PDF/
image context, requests a backend pack within that budget, and grounds the
provider with the pack evidence items. Sources & Trace renders the exact
`pack_id`, snapshot, budget, coverage/degraded state, evidence item summaries,
locators, expansion handles, verification handles, and omitted expansion handles
used for the turn. The fetched pack is retained on the trace payload as
`context_pack`; locators are clickable and resolve their target by source kind.
External Reference Mode sources (with an `external_uri`) open the real external
file rather than the in-vault stub: reference PDFs open in the plugin's external
PDF viewer at the cited page, while other external references open through the
system handler (local files use the desktop shell opener on desktop). Vault
Zotero PDF tabs persist only the effective attachment key and view position.
On restore, the plugin asks the backend to resolve that key through the current
device's Zotero database. The returned absolute path is memory-only: it is not
written to plugin localStorage, Obsidian view state, `data.json`, sessions, or
the backend DB. Generic external tabs persist a portable `externalRef`. Vault
sources open their relpath; a registered/vault PDF jumps to
the cited page via Obsidian's viewer (`#page=N`) and other notes use their
heading/block anchor when present. Expansion and verification buttons use
`wiki plugin context expand` and `wiki plugin context verify` with the displayed
pack id and snapshot id. Successful verification updates the displayed evidence
item in place. If the backend reports `snapshot_conflict`, the panel
marks the displayed pack as stale, shows the expected/current snapshot ids, and
offers **Refetch**; refetch runs `wiki plugin context fetch` for the original
question and replaces the displayed pack instead of merging evidence across
snapshots. A backend synthesized answer is not injected by default.

Each evidence item in Sources & Trace carries a feedback affordance: 👍
(relevant) / 👎 (irrelevant) plus a **Report…** menu for incorrect, stale,
insufficient, or duplicate. Choosing one appends an event through
`wiki plugin context feedback` against the displayed trace id and pack id. The
backend looks up the root `QTR-*` directly, verifies that the `PACK-*` belongs to
that trace, records an append-only `FBK-*` event tied to the pack/snapshot, and
returns `ranking_or_truth_mutated: false`: feedback never edits source files,
generated records, ranking, or truth state, and stays quarantined until a
separately reviewed policy applies it. A `new_insight` event enqueues a
provisional insight candidate for later human review rather than changing
anything immediately.

The Sources & Trace panel also has a **💾 Save to 02_Wiki** button. Clicking it is
an explicit promotion of that answer into a durable `02_Wiki/` page, and it passes
the trace's `source_span_ids` so the page gets a `## Sources` section linking the
original source documents — those then appear in Obsidian's Graph view and
Backlinks. The plugin never promotes automatically; only this button (or the
equivalent backend command) writes the page. The button is bound to that answer's
own trace; when promoting a historical answer and the trace has no explicit
question, the plugin falls back to the user message immediately preceding that
answer, not the newest user message in the chat. Historical trace panels remain
navigable and promotable, but mutating context-pack actions (expand, verify,
refetch, and feedback) are shown only for the latest active answer so old panels
cannot mutate the live query state.

Rules:
- Insight-candidate promotion is an explicit user action; the plugin must confirm
  before calling `promoteInsight`, which writes only to `02_Wiki/`.
- These local commands return JSON and must not be routed through Incurator MCP
  tools (MCP is for external agents). See
  [Plugin Schema spec](../specs/plugin_schema/PLUGIN_SCHEMA.md) §9–12.
- Dashboard Trace and Insights tabs are click-to-use surfaces over these commands.
  They may list/show traces and insight candidates, promote/reject candidates, and
  propose corrections, but they must never write repo-cache `state.sqlite`,
  `.curator/Collections/`, `03_Notes/`, `04_Resources/`, or `06_Archives`
  directly.

---

## Debug logging

By default the plugin keeps the developer console quiet: only warnings and errors
(prefixed `[Incurator]`) are printed. To see verbose diagnostic logs (e.g. when
filing a bug report), open the developer console (**Ctrl/Cmd+Shift+I**) and run:

```js
localStorage.setItem("incurator-debug", "1")
```

then reload Obsidian (the flag is read once at plugin load). Set it back to `"0"`
(or remove it) and reload to silence verbose logs again. This is a developer
affordance, not a plugin setting — it is per-device and never synced.

## Troubleshooting

### Chat, popover, and context pins all stop working at once

If the purple context pins disappear, **Send** does nothing, and the Quick Query
popover sits on "Thinking", open the developer console
(**Ctrl/Cmd+Shift+I**) and look for a single underlying error — these three
surfaces share one context-building path, so one exception takes all of them
down together.

`TypeError: getRuntimePath is not a function` was the v0.41.0 form of this and
is fixed in v0.41.1. It came from restored (deferred) PDF tabs, so restarting
Obsidian made it *more* likely rather than less. If you are still on v0.41.0,
update; closing PDF tabs before restarting is a temporary workaround.

### Which `wiki` the plugin actually runs

The plugin runs the backend command configured in its settings. If that setting
is the bare name `wiki`, it is resolved against the PATH of the Obsidian
application process, which is **not** your shell's PATH — shell aliases and
`.zshrc` exports do not apply. If another Incurator install exists on that PATH
(for example an old `pip install -e` inside an Anaconda environment), the plugin
may silently use it.

Set the backend command to the absolute path of the launcher in this
repository's runtime environment, for example
`/path/to/Incurator/.venv/bin/wiki`. To confirm which install answers, compare:

```bash
wiki version
/path/to/Incurator/.venv/bin/wiki version
```

An editable install keeps running current repository code while reporting the
version recorded when it was first installed, so a stale version string does
**not** mean stale behavior — but it does mean the plugin's version check cannot
be trusted until the path is corrected.

## Related Docs

- [Full Workflow](WORKFLOW_GUIDE.md) — How the entire system fits together
- [MCP User Guide](MCP_USER_GUIDE.md) — Connecting AI agents via MCP
- [User Guide](USER_GUIDE.md) — wiki CLI command reference
