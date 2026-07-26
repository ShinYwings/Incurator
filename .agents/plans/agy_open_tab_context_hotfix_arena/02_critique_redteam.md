# Critique on Frontend And Security Proposal
Date: 2026-07-26 | Agent Persona: Security Auditor / Red Teamer

## 1. Vulnerabilities & Flaws

- Automatically including all hidden tabs would expose unrelated private note
  content and exhaust context windows; discovery and transmission must not share
  one boolean.
- Reading only `manifest.json.version` can miss a rebuilt bundle at the same
  version. The guard should prefer the existing build fingerprint and use
  version only when no fingerprint exists.
- A copy loop that succeeds for only one artifact must not offer reload as if
  deployment were complete.
- Programmatic self-disable/re-enable may leave the update callback executing on
  an unloaded plugin instance. A supported whole-renderer reload command is safer
  than manipulating internal plugin manager state.
- An identity-only hidden PDF chip must not be treated as prompt-ready with
  placeholder text; eye-on must materialize it or report an actionable capture
  failure.
- Existing file-path dedupe can merge different PDF pages. Conversely, leaf-only
  keys can duplicate identical content. The key contract must be explicit.
- Settings merge tests alone do not validate the live bundle lifecycle. A
  regression test must fail when disk and runtime identities differ.

## 2. Suggested Alternatives

- Use `{runtimeBuild, installedBuild}` comparison through a pure helper and block
  generation before credential/provider startup.
- Require all three plugin artifacts to copy before enabling reload.
- Use exact `(view type, portable source/file identity, page)` context keys.
- Keep hidden contexts eye-off; materialize only upon inclusion.
- Preserve the existing `$read_file$()` allow rule and explicit tests forbidding
  blanket bypasses.

