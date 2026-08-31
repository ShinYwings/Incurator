# Prompt Contract Proposal: Provider-Conditional `boundaryConstraints`
Date: 2026-08-31 | Agent Persona: `prompt_architect`

## 0. Framing

The bug is not "a permission is missing" — the permission and the server are
both present (measured facts #1–#3 in `00_problem.md`). The bug is that
`promptRegistry.ts` makes ONE unconditional claim — *"You have NO filesystem
access and NO MCP tools"* — that is true for API providers and for the claude
CLI's ephemeral branch (`--tools ""`, which measurement in `LLMClient.ts`
confirms empties the whole tool surface), and **false** for the antigravity
CLI branch, where `syncAgyMcpConfig()` runs unconditionally
(`LLMClient.ts:2658`) and registers `fetch_url` (plus every other configured
MCP server) in ONE GLOBAL file that the popover and the sidechat both read.
The `ephemeral` flag computed in `buildCliCommand` never reaches that global
file — it only empties `--add-dir` (visibility roots), which the CLI's own
`--sandbox` doesn't even gate for reads (PLUGIN_SCHEMA §13.6: "reads bypass
[`--add-dir`]"). So on antigravity, the popover's "NO MCP tools" claim was
never true to begin with, and the model — told it had nothing, needing a
URL — reached for its own built-in `read_url`, which auto-denies (no
permission rule names it, and per this plan's constraints, none ever will)
and produces an empty turn.

My angle is the prompt contract: make `boundaryConstraints` (and the
`buildRecencyAnchor` wrapper that re-emits it at the highest-attention
position) say something that is **actually true for the provider that will
run the call**, without touching `ToolPolicy`, `shouldInjectMcpTools`,
`isEphemeralToolPolicy`, or any enforcement code path. Nothing about
enforcement changes in this proposal — the plugin still injects zero MCP
tools into any request body, on every provider, unconditionally. What
changes is only what the popover's own system prompt is permitted to *say*
about a fact the plugin does not and cannot control per-call: antigravity's
own independent, global MCP registry.

## 1. Core Logic & Implementation

### 1.1 A new, narrowly-scoped exhaustive union — NOT a `ToolPolicy` value

```ts
// context/promptRegistry.ts — the ONLY new import in this file, and it is
// type-only, so the file's "import-free at runtime" contract (see its own
// header comment) is unbroken. types.ts has zero imports of its own, so this
// cannot create a cycle back into context/ or agent/.
import type { LLMProvider } from "../types";

/**
 * What the popover's OWN prompt text may truthfully claim about network-fetch
 * tools on THIS call, given the provider that will actually run it.
 *
 * - "none"          => no fetch tool exists on this call. True for every API
 *                       provider (ollama, deepseek — no CLI at all) and for
 *                       any CLI provider whose ephemeral branch genuinely
 *                       empties its tool surface (claude's `--tools ""`,
 *                       measured to disable MCP along with everything else).
 * - "guarded-fetch"  => the spawned CLI process loads its OWN persistent,
 *                       global MCP registry that this call cannot scope out
 *                       (antigravity/`agy` — see syncAgyMcpConfig,
 *                       LLMClient.ts:3020, ONE file, no per-spawn variant,
 *                       because scoping it per-spawn would race the sidebar
 *                       reading/writing the same file — 00_problem.md's
 *                       explicit constraint). The guarded `fetch_url` tool is
 *                       therefore LIVE on this call whether the prompt admits
 *                       it or not, so the prompt MUST admit it and steer the
 *                       model at that ONE tool instead of leaving it to guess
 *                       (and reach for its own built-in `read_url`, which is
 *                       not on any permission allow-list and auto-denies).
 *
 * Deliberately NOT folded into `ToolPolicy`. See §1.4 for why.
 *
 * Exhaustive for the same reason `ToolPolicy` is (see messageUtils.ts):
 * consumers switch on it with a `never`-typed default, so a third state is a
 * compile error, not a silent wording gap.
 */
export type NetworkToolTruth = "none" | "guarded-fetch";

/**
 * Maps the ACTIVE provider to the network-tool truth the popover's prompt may
 * claim. Pure, total over `LLMProvider` (5 cases, matching `types.ts`), and
 * deliberately does NOT take a "provider unknown" branch — the caller decides
 * what to do with an absent provider (see quickQueryContext.ts §1.2), because
 * that is a call-site availability question, not a fact about any provider.
 *
 * codex (`openai`) is "none" here NOT because it has been measured safe, but
 * because it has NOT been measured at all — see §3 Open Questions. A false
 * "none" costs the model a tool it could have used; a false "guarded-fetch"
 * tells the model to call a tool that might not exist. The asymmetry decides
 * the default, exactly as messageUtils.ts's QUOTA_PHRASES comment argues for
 * its own asymmetric default.
 */
export function networkToolTruthForProvider(
  provider: LLMProvider
): NetworkToolTruth {
  switch (provider) {
    case "antigravity":
      return "guarded-fetch";
    case "claude":
    case "openai":
    case "ollama":
    case "deepseek":
      return "none";
    default: {
      const exhaustive: never = provider;
      return exhaustive;
    }
  }
}
```

### 1.2 `boundaryConstraints` signature change

```ts
// context/promptRegistry.ts
export function boundaryConstraints(
  profile: SurfaceProfile,
  networkTools: NetworkToolTruth = "none"   // safe default: the OLD, truthful-
                                              // for-most-providers claim. Never
                                              // silently over-claims.
): string {
  let rules = "";
  switch (profile.toolPolicy) {
    case "none":
      rules = /* UNCHANGED — this proposal touches nothing here */;
      break;
    case "local-only": {
      // networkTools is read ONLY inside this branch. "none" and "auto"
      // ignore the parameter entirely — it has zero effect on them, by
      // construction (see the test in §1.5 that pins this).
      if (networkTools === "guarded-fetch") {
        rules =
          "You have NO filesystem access. Your tools here are: fetching a " +
          "page of the PDF the user already has open by number instead of " +
          "telling the user to navigate there; reading a page as an image " +
          "where `read_pdf_page_image` is among the tools you were given, " +
          "for when what you were asked about is not in that page's text " +
          "(a typeset paper draws many of its equations and figures as " +
          "pictures, so the text can read as complete prose while the " +
          "formula itself is simply absent); and fetching a URL — a DOI, a " +
          "reference-list entry, a linked resource the passage points to — " +
          "with `fetch_url`. Use nothing else, even if another tool is " +
          "listed as available to you: never list, browse, create, or " +
          "execute files, scripts, or shell commands, never invent folder, " +
          "file, or directory names, and never call `read_url` or any " +
          "other browsing/fetch tool for a URL — `fetch_url` is the only " +
          "one that works here, the rest auto-deny and will produce " +
          "nothing. Answer from the provided context and anything you " +
          "fetch or read first; where those do not cover the question, " +
          "answer it from your general knowledge of the field rather than " +
          "stopping. Explain the subject — the reader wants the answer, " +
          "not an account of which sentence came from where.";
      } else {
        rules = /* UNCHANGED — byte-for-byte the current "local-only" string */;
      }
      break;
    }
    case "auto":
      rules = /* UNCHANGED */;
      break;
    default: {
      const exhaustive: never = profile.toolPolicy;
      return exhaustive;
    }
  }
  return rules;
}
```

The exact **variant-A** (`networkTools: "none"`) literal string — pinned
byte-for-byte in §1.5 — is copied verbatim from the current file, unchanged:

> "You have NO filesystem access and NO MCP tools. Never list, browse, create,
> or execute files, scripts, or shell commands, and never invent folder, file,
> or directory names. Your only tools read the PDF the user already has open,
> and nothing else: you may fetch a page of that document by number to follow
> a reference instead of telling the user to navigate there, and — where
> `read_pdf_page_image` is among the tools you were given — you may read a
> page as an image when what you were asked about is not in that page's text;
> a typeset paper draws many of its equations and figures as pictures, so the
> text can read as complete prose while the formula itself is simply absent.
> Answer from the provided context and any page you fetch or read first;
> where those do not cover the question, answer it from your general
> knowledge of the field rather than stopping. Explain the subject — the
> reader wants the answer, not an account of which sentence came from where."

The exact **variant-B** (`networkTools: "guarded-fetch"`) literal string —
the exact string in the code block above, restated for Question 2's
requirement to write it literally:

> "You have NO filesystem access. Your tools here are: fetching a page of the
> PDF the user already has open by number instead of telling the user to
> navigate there; reading a page as an image where `read_pdf_page_image` is
> among the tools you were given, for when what you were asked about is not
> in that page's text (a typeset paper draws many of its equations and
> figures as pictures, so the text can read as complete prose while the
> formula itself is simply absent); and fetching a URL — a DOI, a
> reference-list entry, a linked resource the passage points to — with
> `fetch_url`. Use nothing else, even if another tool is listed as available
> to you: never list, browse, create, or execute files, scripts, or shell
> commands, never invent folder, file, or directory names, and never call
> `read_url` or any other browsing/fetch tool for a URL — `fetch_url` is the
> only one that works here, the rest auto-deny and will produce nothing.
> Answer from the provided context and anything you fetch or read first;
> where those do not cover the question, answer it from your general
> knowledge of the field rather than stopping. Explain the subject — the
> reader wants the answer, not an account of which sentence came from where."

**Why "even if another tool is listed as available to you" and not "the
only MCP tool available to you is `fetch_url`":** I checked this claim
against the actual enforcement mechanics before writing it, and the stronger
claim is FALSE. `mcp(*)` (`AGY_MCP_PERMISSION`, `LLMClient.ts:119`) is a
**class-wide** wildcard — per its own comment, "It authorises headless calls
into EVERY server in agy's registry" — and `syncAgyMcpConfig` registers the
`incurator` server (curator_query, curator_check_workspace, etc.) and any
user-added servers in the SAME global file as `incurator_fetch`, with no
per-spawn distinction between popover and sidechat. So on antigravity, the
popover's `agy` process can almost certainly see (and, at the permission
layer, call) the full curator tool surface too, not only `fetch_url`.
Claiming "`fetch_url` is the only MCP tool available" would be a second false
capability claim of exactly the shape this whole plan exists to fix. The
wording above instead makes a **behavioral** commitment ("use nothing else,
even if another tool is listed") rather than a **capability** claim about
what exists — mirroring how the existing `"auto"` case already handles this
("Any tool... access must stay within the allowed roots" — a boundary on
*use*, not an inventory of what's technically reachable). Restricting what
the popover's `agy` process can actually SEE, not just what it's told to
ignore, is explicitly out of scope here — see §3.

### 1.3 Threading the parameter through both call sites

**Both** places that call `boundaryConstraints(POPOVER_PROFILE)` today must
change together, or the fix regresses at the worst possible position:

```
quickQueryContext.ts:208  systemText = ... + boundaryConstraints(POPOVER_PROFILE) + ...
quickQueryContext.ts:225  buildRecencyAnchor(POPOVER_PROFILE, { hasPrimarySelection: true })
  -> promptRegistry.ts:169   lines.push(boundaryConstraints(profile));
```

`buildRecencyAnchor` emits its copy of the boundary text **last**, inside
`<critical_invariants>`, at the position of strongest LLM attention (the
function's own doc comment: "emitted LAST in the payload"). If only the
line-208 call site is fixed, the line-225→169 call site re-emits the STALE
"NO MCP tools" claim at the position most likely to win — reintroducing
the exact bug this plan fixes, at the worst possible spot in the prompt.
This is the single most important correctness constraint in this proposal.

```ts
// context/promptRegistry.ts
export interface RecencyAnchorOptions {
  hasPrimarySelection: boolean;
  /** Same meaning as boundaryConstraints's parameter; optional, defaults to
   *  "none" so every existing caller (ChatSidebarView.ts, which never passes
   *  it and always uses SIDECHAT_PROFILE where the parameter has no effect
   *  anyway) needs zero changes. */
  networkTools?: NetworkToolTruth;
}

export function buildRecencyAnchor(
  profile: SurfaceProfile,
  opts: RecencyAnchorOptions
): string {
  const lines: string[] = ["<critical_invariants>"];
  if (opts.hasPrimarySelection) { /* unchanged */ }
  if (!profile.allowEdits) { /* unchanged */ }
  lines.push(boundaryConstraints(profile, opts.networkTools ?? "none"));
  lines.push("</critical_invariants>");
  return lines.join("\n");
}
```

```ts
// context/quickQueryContext.ts
import {
  boundaryConstraints,
  buildRecencyAnchor,
  networkToolTruthForProvider,
  POPOVER_PROFILE,
  type NetworkToolTruth,
} from "./promptRegistry";
import type { ActiveContext, ContextRef, LLMMessage, LLMProvider } from "../types";

export interface QuickQueryMessageArgs {
  selectedText: string;
  question: string;
  activeContext?: ActiveContext;
  previousTurns?: QuickQueryTurn[];
  maxBackgroundLength?: number;
  resolvedReferencesBlock?: string;
  pinnedContextRefs?: ContextRef[];
  vaultEvidenceBlock?: string;
  /**
   * Active provider for THIS call (v0.77.0). Determines whether the
   * popover's boundary text may advertise the guarded `fetch_url` tool.
   * OPTIONAL and fail-CLOSED: omitting it falls back to "none" — the OLD,
   * zero-MCP claim — never the reverse. The real production call site
   * (quickQueryPopover.ts) MUST pass it; that requirement is pinned by a
   * source-grep test (§1.6) rather than the type system, because a thin
   * test-only wrapper (`quickQueryPopover.ts`'s exported
   * `buildQuickQueryMessages(selectedText, question)`) also constructs a
   * `QuickQueryMessageArgs` and has no business knowing about providers —
   * see §1.4's discussion of why this is NOT made a required field.
   */
  provider?: LLMProvider;
}

export function buildQuickQueryMessages(args: QuickQueryMessageArgs): LLMMessage[] {
  const networkTools: NetworkToolTruth = args.provider
    ? networkToolTruthForProvider(args.provider)
    : "none";

  // ... existing background/followups/resolvedReferencesBlock/pinnedBlock ...

  const systemText =
    "You are a reading assistant embedded in Obsidian. ..." /* unchanged prefix */ +
    boundaryConstraints(POPOVER_PROFILE, networkTools) +
    " When asked about a region of the document, ..." /* unchanged suffix */;

  const content = [
    /* ... unchanged blocks ... */
    buildRecencyAnchor(POPOVER_PROFILE, { hasPrimarySelection: true, networkTools }),
  ].filter(Boolean).join("\n\n");

  return [
    { role: "system", content: systemText },
    { role: "user", content },
  ];
}
```

```ts
// ui/quickQueryPopover.ts — the ONE real production call site, ~line 580
const messages = buildQuickQueryContextMessages({
  selectedText: this.capturedSelection,
  question,
  activeContext,
  previousTurns: this.turns,
  resolvedReferencesBlock,
  pinnedContextRefs: this.plugin.getPinnedContextRefs(),
  vaultEvidenceBlock,
  provider: this.plugin.settings.provider,   // <-- the ONE line this proposal
                                              //     adds to production code
});
```

`this.plugin.settings.provider` is the SAME field `LLMClient` reads moments
later, inside the same synchronous submit handler, to decide CLI routing
(`this.settings.provider` in `complete`/`streamChat`/`shouldUseCli` — and
`this.settings` there is a reference to the same plugin settings object, not
a copy). A provider switch mid-flight between message-build and CLI-spawn is
a pre-existing, unrelated hazard shared by `model`, `toolPolicy`, and every
other setting read at both points — not something this proposal introduces
or worsens.

### 1.4 Why this is a NEW parameter, not a new `ToolPolicy` value (Question 4)

**Keep the `ToolPolicy` union exactly as it is: `"auto" | "none" |
"local-only"`.** Add an independent, separately-exhaustive parameter
(`NetworkToolTruth`) instead of a fourth `ToolPolicy` value (e.g.
`"local-only-with-fetch"`). Three reasons, in order of how much they'd
actually break if ignored:

1. **`ToolPolicy` has real enforcement consequences; `NetworkToolTruth` has
   none.** `ToolPolicy` is read by `shouldInjectMcpTools`,
   `shouldInjectLocalTools`, and `isEphemeralToolPolicy` — three functions
   that gate actual code behavior (whether the plugin injects MCP tools into
   a request body, whether it injects the local PDF reader, and whether
   `buildCliCommand` treats the call as ephemeral for `--add-dir`/
   `--tools`/`--sandbox` purposes). A fourth `ToolPolicy` value would force
   a considered decision in all three switches — and the honest answer for
   all three is "unchanged": the plugin still injects zero MCP tools into
   the request body on antigravity (nothing about `shouldInjectMcpTools`'s
   behavior changes), the local PDF reader's injection is unaffected, and
   `buildCliCommand`'s ephemeral gate correctly still empties `--add-dir`.
   Adding a `ToolPolicy` value to represent a fact that changes NONE of
   those three decisions would be actively misleading — it would look like
   a new enforcement lever when it isn't one.
2. **The fact `NetworkToolTruth` encodes is not something the plugin
   controls per-call at all.** `ToolPolicy` answers "what should THIS
   plugin call do." `NetworkToolTruth` answers "what does the CLI's OWN,
   independent, already-existing global state make true regardless of what
   this call does" — a fact about `agy`'s persistent registry, not a
   decision the popover's `toolPolicy` was ever able to express. Folding an
   external, uncontrollable fact into the same union as a set of controlled,
   enforced policies conflates two different kinds of thing the codebase
   currently keeps cleanly separate (`ToolPolicy` = code behavior;
   `boundaryConstraints`'s prose = what the prompt honestly says about the
   result).
3. **It keeps the blast radius contained to the one file that owns
   wording.** `messageUtils.ts`'s three `ToolPolicy`-exhaustive functions,
   and every one of their existing tests (`llmClient.test.ts` — the
   `shouldInjectMcpTools`, `shouldInjectLocalTools`, and
   `isEphemeralToolPolicy` describe blocks), need ZERO changes under this
   proposal. Code that isn't touched can't regress. A fourth `ToolPolicy`
   value would touch all of it for a purely textual fix.

`NetworkToolTruth` is still exhaustive in the same spirit `ToolPolicy` is —
a `never`-typed default inside `boundaryConstraints`'s `"local-only"` branch
— it's just a narrower-scoped union describing a narrower-scoped decision
(prompt wording only, not tool injection).

**Not a `SurfaceProfile` field either.** `POPOVER_PROFILE`/`SIDECHAT_PROFILE`
are static, exported, shared singleton objects describing properties of a
*surface* (popover vs. sidechat) that do not vary per request — a user can
switch LLM providers in settings while the popover remains "the popover."
Baking provider-dependent truth into a nominally-static profile would force
either (a) mutating the shared exported singleton per call — a genuine race
the moment two calls interleave (sidebar + popover concurrently), the exact
failure class `syncAgyMcpConfig`'s own global-file design already has to
guard against — or (b) spreading a fresh `{ ...POPOVER_PROFILE, networkTools
}` at every call site, with no type-level force function preventing a call
site from forgetting the override and silently reusing the exported
constant's stale default. A plain function parameter with a safe default is
simpler and the failure mode (a forgotten override) is caught by the
source-grep test in §1.6 rather than by a subtler "did anyone forget to
spread correctly" bug.

### 1.5 Tests — `context/promptRegistry.test.ts` (Question 5)

Existing tests in this file call `boundaryConstraints(POPOVER_PROFILE)` and
`buildRecencyAnchor(POPOVER_PROFILE, { hasPrimarySelection: ... })` with NO
second argument. Because the new parameter defaults to `"none"`, every one
of those existing assertions (lines 11–19, 21–32, 34–38, 51–59, 90–117,
120–125, 127–174) continues to pass completely unmodified — this is the
direct payoff of choosing a safe default over a required field.

New assertions to add:

```ts
describe("boundaryConstraints — networkTools (v0.77.0)", () => {
  const NONE_TEXT =
    "You have NO filesystem access and NO MCP tools. Never list, browse, " +
    "create, or execute files, scripts, or shell commands, and never invent " +
    "folder, file, or directory names. Your only tools read the PDF the " +
    "user already has open, and nothing else: you may fetch a page of that " +
    "document by number to follow a reference instead of telling the user " +
    "to navigate there, and — where `read_pdf_page_image` is among the " +
    "tools you were given — you may read a page as an image when what you " +
    "were asked about is not in that page's text; a typeset paper draws " +
    "many of its equations and figures as pictures, so the text can read " +
    "as complete prose while the formula itself is simply absent. Answer " +
    "from the provided context and any page you fetch or read first; " +
    "where those do not cover the question, answer it from your general " +
    "knowledge of the field rather than stopping. Explain the subject — " +
    "the reader wants the answer, not an account of which sentence came " +
    "from where.";

  it("pins the exact API-provider ('none') text byte-for-byte — Question 3's guarantee", () => {
    // toBe, not toContain: the CURRENT suite only checks substrings, which
    // would let an unrelated future edit silently drift this string. An
    // exact-equality pin forces any change through a conscious, reviewed
    // edit to this constant.
    expect(boundaryConstraints(POPOVER_PROFILE, "none")).toBe(NONE_TEXT);
    expect(boundaryConstraints(POPOVER_PROFILE)).toBe(NONE_TEXT); // default == explicit "none"
  });

  it("advertises fetch_url and drops the blanket claim for guarded-fetch", () => {
    const text = boundaryConstraints(POPOVER_PROFILE, "guarded-fetch");
    expect(text).toContain("fetch_url");
    expect(text).toContain("You have NO filesystem access");
    // The OLD blanket sentence must not survive verbatim.
    expect(text).not.toContain("NO filesystem access and NO MCP tools.");
    // no-shell / no-invented-paths rules stay intact
    expect(text).toContain("never list, browse, create, or execute files");
    expect(text).toContain("scripts, or shell commands");
    expect(text).toContain("never invent folder, file, or directory names");
  });

  it("names read_url only inside a forbidding clause, never inviting its use", () => {
    const text = boundaryConstraints(POPOVER_PROFILE, "guarded-fetch");
    const idx = text.indexOf("read_url");
    expect(idx).toBeGreaterThan(-1);
    expect(text.slice(Math.max(0, idx - 30), idx)).toMatch(/never call/);
    expect(text.slice(idx, idx + 60)).toMatch(/auto-deny|will produce nothing|not available/);
  });

  it("guarded-fetch keeps every shared clause the none/local-only branch already had", () => {
    const text = boundaryConstraints(POPOVER_PROFILE, "guarded-fetch");
    expect(text).toContain("PDF the user already has open");
    expect(text).toContain("read_pdf_page_image");
    expect(text).toContain("general knowledge");
    expect(text).toContain("Answer from the provided context");
  });

  it("networkTools has no effect outside the local-only policy", () => {
    expect(boundaryConstraints(SIDECHAT_PROFILE, "guarded-fetch")).toEqual(
      boundaryConstraints(SIDECHAT_PROFILE, "none")
    );
    const toolFree = boundaryConstraints({ ...POPOVER_PROFILE, toolPolicy: "none" }, "guarded-fetch");
    expect(toolFree).toContain("NO tools and NO filesystem access");
    expect(toolFree).not.toContain("fetch_url");
  });

  it("covers every NetworkToolTruth value with distinct text for local-only", () => {
    const truths: NetworkToolTruth[] = ["none", "guarded-fetch"];
    const texts = truths.map((t) => boundaryConstraints(POPOVER_PROFILE, t));
    expect(new Set(texts).size).toBe(truths.length);
  });
});

describe("buildRecencyAnchor — networkTools threading (v0.77.0)", () => {
  it("defaults to the zero-MCP boundary text when networkTools is omitted", () => {
    const text = buildRecencyAnchor(POPOVER_PROFILE, { hasPrimarySelection: false });
    expect(text).toContain(boundaryConstraints(POPOVER_PROFILE, "none"));
    expect(text).not.toContain("fetch_url");
  });

  it("threads networkTools through to the embedded boundary rule — regression guard for the two-call-site trap", () => {
    const text = buildRecencyAnchor(POPOVER_PROFILE, {
      hasPrimarySelection: false,
      networkTools: "guarded-fetch",
    });
    expect(text).toContain(boundaryConstraints(POPOVER_PROFILE, "guarded-fetch"));
    expect(text).toContain("fetch_url");
  });

  it("networkTools has no effect on a profile whose policy is not local-only", () => {
    const text = buildRecencyAnchor(SIDECHAT_PROFILE, {
      hasPrimarySelection: false,
      networkTools: "guarded-fetch",
    });
    expect(text).not.toContain("fetch_url");
  });
});
```

### 1.6 Tests — `context/quickQueryContext.test.ts` and `ui/quickQueryPopover.test.ts`

`quickQueryContext.test.ts` exercises the FULL assembled message array (both
call sites at once), which the unit tests above on `boundaryConstraints`
alone cannot: they prove the function is correct in isolation but not that
BOTH call sites inside `buildQuickQueryMessages` were actually updated to
pass the same value.

```ts
describe("quick query: provider-conditional network tool truth (v0.77.0)", () => {
  const baseArgs = { selectedText: "See [12] for details.", question: "What is reference 12?" };

  it("advertises fetch_url and drops the blanket NO-MCP claim for antigravity", () => {
    const messages = buildQuickQueryMessages({ ...baseArgs, provider: "antigravity" });
    const system = String(messages[0].content);
    expect(system).toContain("fetch_url");
    expect(system).not.toContain("NO filesystem access and NO MCP tools.");
  });

  it("keeps the zero-MCP claim for every non-antigravity provider", () => {
    for (const provider of ["claude", "openai", "ollama", "deepseek"] as const) {
      const messages = buildQuickQueryMessages({ ...baseArgs, provider });
      const system = String(messages[0].content);
      expect(system).toContain("NO filesystem access and NO MCP tools.");
      expect(system).not.toContain("fetch_url");
    }
  });

  it("defaults to the zero-MCP claim when provider is omitted (fail-closed)", () => {
    const messages = buildQuickQueryMessages({ ...baseArgs });
    expect(String(messages[0].content)).toContain("NO filesystem access and NO MCP tools.");
  });

  it("the recency anchor (highest-attention, end of payload) carries the SAME truth as the system prompt", () => {
    const messages = buildQuickQueryMessages({ ...baseArgs, provider: "antigravity" });
    const system = String(messages[0].content);
    const user = String(messages[1].content);
    expect(system).toContain("fetch_url");
    expect(user).toContain("<critical_invariants>");
    expect(user).toContain("fetch_url"); // would fail today if only line 208 were fixed
  });
});
```

`quickQueryPopover.test.ts` already reads its own source file into `source`
(line 16) to pin call-site shape — e.g. the existing "sources its tool
policy from POPOVER_PROFILE rather than a literal" test. Add one more in the
same style, because a passing unit test on the pure builder does NOT prove
the real production call site was updated — that's exactly the class of gap
`00_problem.md` itself documents (item 6: a flag computed but not threaded
to where it mattered):

```ts
it("threads the active provider into the popover's prompt truth (v0.77.0)", () => {
  expect(source).toMatch(
    /buildQuickQueryContextMessages\(\{[\s\S]{0,400}provider:\s*this\.plugin\.settings\.provider/
  );
});
```

### 1.7 Documentation impact (not performed here — flagged for the Master Plan's P1)

`docs/specs/plugin_schema/PLUGIN_SCHEMA.md` §13.5 currently states, as a
spec-level invariant: *"for `local-only` it declares zero MCP tools"*
(line ~2330). That sentence becomes conditionally true under this proposal
and MUST be updated to describe `NetworkToolTruth` and the antigravity
exception. §13.6's CLI section should gain a cross-reference from its
`syncAgyMcpConfig` discussion to the new prompt-truth mechanism. By
contrast, §13.7's *"Enforcement is behavioral, not textual... The popover's
zero-MCP guarantee MUST be locked by tests"* (line ~2764) does **NOT** need
to change — that guarantee is about `shouldInjectMcpTools` refusing to put
MCP entries in the request body, a mechanism this proposal does not touch
and which remains unconditionally true on every provider. Conflating those
two guarantees in the docs update would be a mistake worth flagging to
whichever persona does P1.

## 2. Pros & Cons

### Pros

- **Minimal, contained blast radius.** Two files gain real changes
  (`promptRegistry.ts`, `quickQueryContext.ts`) plus a one-line addition to
  one production call site (`quickQueryPopover.ts`). `LLMClient.ts`,
  `messageUtils.ts`, `ToolPolicy`, and every existing `ToolPolicy`-exhaustive
  function are untouched — nothing that currently works can regress from
  this change, because nothing that currently works is edited.
- **Fail-closed defaults everywhere.** `boundaryConstraints`'s new parameter
  defaults to `"none"`; `RecencyAnchorOptions.networkTools` defaults to
  `"none"`; `QuickQueryMessageArgs.provider` is optional and maps absence to
  `"none"`. Every possible way to forget the new plumbing reproduces
  TODAY's behavior (the "NO MCP tools" claim), never a new false "you have
  fetch_url" claim on a provider that doesn't. The only way to get the wrong
  (stale) text is to under-claim, which is an answer-quality regression, not
  a correctness/security one.
- **Closes the exact two-call-site trap the bug itself exemplifies.**
  `boundaryConstraints` is called from two places in the popover's prompt
  assembly, and the second (inside `buildRecencyAnchor`, at the
  highest-attention position) is easy to miss — which is structurally the
  same class of miss as `00_problem.md` item 6 (a flag computed in one place
  that never reached where it mattered). §1.3 and its regression test in
  §1.6 make that specific failure mode impossible to reintroduce silently.
- **Does not overclaim in the other direction.** I checked whether
  "`fetch_url` is the only MCP tool available" would be true and found it
  is not — `mcp(*)` is class-wide, so the curator server's tools and any
  user-added servers are also technically reachable on antigravity. §1.2's
  wording makes a behavioral commitment ("use nothing else") instead of a
  false inventory claim, so this proposal does not trade one false claim for
  a narrower but still-false one.
- **Strengthens the existing test suite's guarantee, not just meets it.**
  The current `promptRegistry.test.ts` only asserts substrings
  (`toContain`). §1.5 adds an exact byte-for-byte (`toBe`) pin for the
  "none" branch specifically because Question 3 demands a guarantee against
  silent drift, which substring checks do not provide.

### Cons — what this proposal does NOT solve

- **Does not close the underlying registry-scoping gap.** The popover's
  `agy` process can, at the `mcp(*)` permission layer, actually call
  `curator_query`, `curator_check_workspace`, and any user-added MCP server
  — not only `fetch_url` — because `syncAgyMcpConfig` writes one global
  registry shared with the sidechat. This proposal's wording tells the model
  not to use anything but `fetch_url` and the PDF tools; it does NOT prevent
  the model from calling something else if it chooses to ignore that
  instruction. That is a prompt-level guard, not a permission-level one — a
  genuinely weaker guarantee than the popover had **when its zero-MCP claim
  was actually true** (on every provider except antigravity, it still is).
  Scoping the registry per-spawn is explicitly ruled out by this plan's own
  constraints (it would race the sidebar); a real fix would need a
  different mechanism entirely (e.g., a distinct config profile / env var
  per spawn) and is out of scope here.
- **codex (`openai`) is unmeasured, not verified-safe.** I mapped it to
  `"none"` conservatively because nothing in this codebase or its docs
  establishes whether `codex exec --sandbox read-only` still loads MCP tools
  from `obsidian.config.toml` (`syncCodexMcpConfig` also writes
  unconditionally, the same pattern as `syncAgyMcpConfig`). If it turns out
  codex's read-only sandbox does NOT block MCP calls, the popover has the
  identical bug on codex today, unfixed by this proposal, silently, because
  nobody has measured it. This needs a P0 measurement step before the
  master plan can claim the fix is complete rather than "complete for the
  one provider that was reported."
- **Does not fix (and is not asked to fix) the standing filesystem-read
  claim.** PLUGIN_SCHEMA §13.6 documents that `read_file(*)` is a global,
  standing grant that "reads bypass [`--add-dir`]" — meaning the popover's
  separate claim of "NO filesystem access" may have the exact same shape of
  problem on antigravity that this plan fixes for MCP tools. `00_problem.md`
  explicitly scopes this milestone to the network tool only ("Only the
  network tool changes"), so I have left that sentence untouched in both
  variants — but it is worth flagging by name so a future briefing doesn't
  have to rediscover it from scratch.
- **`provider` is optional, not required — a deliberate but real
  trade-off.** Making it required on `QuickQueryMessageArgs` would be a
  stronger, type-checked guarantee that the real call site can never forget
  to pass it. I chose optional specifically because a required field would
  ripple into `quickQueryPopover.ts`'s exported, test-only convenience
  wrapper `buildQuickQueryMessages(selectedText, question)` (used only by
  `quickQueryPopover.test.ts:21,31`), which has no legitimate provider to
  supply and no reason to know about one. The gap is covered by a
  source-grep test (§1.6) instead of the type system, which is a weaker
  guarantee — a reviewer who disagrees with this trade should say so; making
  it required and threading a third `provider` parameter through the thin
  wrapper is a completely viable alternative if the Arena decides the
  stronger compile-time guarantee is worth the extra parameter.
- **Answer-quality risk if the model over-relies on `fetch_url`.**
  `fetch_url`'s own tool description (`LLMClient.ts:156-162`) states that a
  binary response (PDF, image) is saved to disk and the reply gives a path
  — but the popover has no filesystem tool to read that path back. A model
  that fetches a URL pointing at a PDF will get a path it cannot use. This
  proposal does not add guidance for that case (it would be scope creep
  beyond "advertise fetch_url, stop reaching for read_url" and the reported
  failure was about a text/HTML reference, not a PDF link) — flagging it
  here so the red_teamer critique can decide if it needs a one-line
  addendum before this ships.

## 3. Open Questions For The Arena

1. Should codex's ephemeral MCP behavior be measured as a P0 step before
   this plan is approved, or is "conservatively `none`, flagged as unmeasured"
   an acceptable state to ship v0.77.0 with, given the reported bug is
   antigravity-specific and codex has never been reported broken this way?
2. Is the `provider`-optional / source-grep-test trade-off in §1.2 and the
   Cons section acceptable, or should the Arena prefer the required-field
   design and accept threading a third parameter through the test-only
   convenience wrapper?
3. Does the "use nothing else, even if another tool is listed" behavioral
   wording in variant B need to be stronger (e.g., explicitly name
   `curator_query` and other known tool names) given that `mcp(*)` makes them
   genuinely reachable, or would naming them risk drawing the model's
   attention to them the same way the old "NO MCP tools" claim's own
   falseness drew attention to `read_url`?
