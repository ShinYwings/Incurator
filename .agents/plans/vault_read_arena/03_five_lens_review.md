# PR #210 Five-Lens Substitute Review
Date: 2026-09-21 | Reviewer: CLI Runtime Engineer

Reviewed commit: `a44962fbd5841016669259f4a00583b30bc5cf81`, against
`f184c99d`. PR: https://github.com/ShinYwings/Incurator/pull/210.

The required `/code-review:code-review 210` skill was attempted by the executor
but could not run because Claude OAuth was expired. This document is an explicit
substitute, not a successful skill invocation. RELAY records the user's standing
authorization to proceed with available independent agents after the same OAuth
blocker. A separate independent reviewer covers containment adversarially.

Confidence rubric applied to candidate findings: 0 = false or pre-existing;
25 = tentative; 50 = real minor; 75 = highly likely important; 100 = confirmed
frequent. Only verified introduced findings scoring at least 80 are reportable.

## Result

No verified introduced findings at confidence 80 or above.

This review does not waive the remaining release gates: complete local checks,
green remote CI, final release commit, completed-plan removal, deployment and
cleanup. The original incident's raw failing provider trace remains unavailable;
the matching nested Seatbelt failure mechanism and the corrected native launch
have been reproduced independently.

## 1. CLAUDE.md Compliance

Read the relevant repository workflow, testbed, storage, documentation and review
requirements. The AGENTS.md and CLAUDE.md shared body is byte-identical; their
provider-specific introductory headings differ as intended and were not changed.

The patch uses a hotfix branch from master, records actual independent Arena
proposals and cross-critique, preserves the original unrelated timeout report
verbatim in ROADMAP, and leaves the separate lifetime implementation untouched.
Runtime changes are narrowly limited to the Codex command-construction branch.
English and Korean plugin guides both changed; plugin and system specs reflect
the native-only command path. All five version fields agree at 0.82.9, and the
CHANGELOG has the matching Fixed entry. The minor line is unchanged, so spec-title
line updates are not required. Unit tests exercise actual command construction.

Plans remain in this intermediate commit for review; removal belongs to release
cleanup already enumerated in the master plan. No production data migration,
deletion, reindex, or global Codex configuration change is part of this diff.

## 2. Shallow Bug Scan

Inspected both streaming and non-streaming callers. Each still obtains the
canonical CLI cwd before spawning and passes `getAugmentedEnv`, which pins
TMPDIR/TEMP/TMP into that cache. Returning the Codex base command early preserves
stdin, effort arguments, JSON output, and output-last-message handling. No
provider-specific case below it is skipped: openai, deepseek and ollama all use
this exact Codex branch; other providers still reach the wrapper.

The previous shared addDirs list included Zotero. The new list correctly calls
sandboxWriteRoots, includes the scoped image run only on non-ephemeral calls,
and has no additional roots for either `none` or `local-only`. Approval never,
empty inherited writable_roots, and exclude_slash_tmp are invocation overrides,
not global configuration edits. No dangerous bypass or unsandboxed retry exists.

Independently inspected the parent's private `prepare.ts` and native JSON event
logs under `.cache/vault-read-live`. The fixture uses the imported application
LLMClient to generate argv and spawn environment, stubbing only profile writes.
The actual auto run read both random markers absent from the prompt, accepted
the fake-vault write, and denied reference/sibling writes. The none run read both
markers and denied all three writes. The inherited-root run again accepted only
the intended vault write and denied the external destinations. These results
were present in command_execution aggregated_output, not merely model claims.
No permission request or nested sandbox_apply failure appeared in those runs.

## 3. Git-History Context

Read the original wrapper history, including `62d71bad`, `2dfd194a`, provider
scope changes `a0f12b66`/`8e8042af`, and later CLI-policy changes. The original
outer layer addressed AGY's ineffective sandbox and excessive filesystem writes.
This patch does not alter that provider's containment, its headless sandbox flag,
the inline Seatbelt profile, Linux bwrap arguments, or provider state directories.

The historical split between read roots and write roots exists specifically to
protect Zotero. The patch preserves that purpose and corrects Codex's mistaken
interpretation of add-dir as mere visibility. The existing canonical-path helper
remains in use rather than introducing raw path interpolation or shell quoting.
The known operational cache and temp paths are retained.

## 4. Prior-PR Guidance

Read PR #46, including its review and validation gaps; PR #53 and its
provider-directory finding; and PR #157's owner review and live-permission
evidence. Also inspected the current PR description, comments and reviews.

PR #46 explicitly called for vault writes, external/Zotero refusal, canonical
paths, inline profiles, and live confirmation that Codex read-only still emits
its answer. Current actual exec logs demonstrate these relevant permission and
answer results for the changed path; other providers' profile machinery is
untouched. PR #53's unknown-provider fallback issue is not reintroduced.

PR #157 warns that writing or preserving a permission string does not prove
authorization. This patch's unit assertions alone would not satisfy that lesson;
the actual model-backed fixture reads and write failures do. The private helper
retains repeatable construction evidence. Cross-platform native execution and
every possible future Codex permission-profile format are not established by the
macOS run and should not be described as live-tested.

## 5. Contradictions With Code Comments

The changed core comments now accurately describe Codex add-dir as a WRITE grant,
the native-only launch, and the remaining wrapper's use by AGY/Claude. The base
commit's unchanged unavailable-wrapper comment still mentioned Codex fallback;
the executor's current worktree already corrects it to state Codex never enters
that method. This is a minor documentation nit below the reporting threshold,
not a runtime defect.

The pre-existing description of ephemeral policies as having no native tools is
broader than the actual Codex read-only behavior, but this patch does not create
that mismatch. It retains the existing read-only distinction and explicitly
documents direct reads. Likewise, a Zotero directory physically inside a writable
vault has always overlapped the vault grant; the updated spec now states that
qualification instead of claiming an impossible external-root carve-out.

No changed implementation contradicts a load-bearing comment in a way that
produces an introduced bug at the reportable confidence threshold.
