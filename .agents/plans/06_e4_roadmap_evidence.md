# E4 Evidence Ledger

Date: 2026-09-11 | Anchor: ce854940 (v0.82.4)

- agy --version: 1.2.0. Current configured primary: antigravity-cli::gemini-3.8-flash; no fallback.
- Existing testbed: ResNet_Dynamics_Lab, testbed:true. No testbed initialization or production config mutation performed.
- Exact entity_relation_extract@v2 with synthetic ResNet unit under the real backend OS sandbox: 13.50 s, 4 entities, 3 relations, num_turns=2. No publication.
- Harmless forced printf command under unchanged sandbox, schema and agy permissions: 8.38 s, exit=0, status=SUCCESS, response empty, structured_output absent, denied_actions=[{action:command,display_name:RunCommand}], stderr states auto-denied. Previous adapter returns empty string, not exception.
- Current graph retries exceptions 30 times; invalid model output follows runner JSON repair then failed result. Thus denial bypasses intended retry.
- 52 existing graph/resume/storage/compile tests passed before changes.
- Two independent domain proposals and two live-evidence cross-critiques agree on boundary-only fix. Broad exception retry taxonomy deferred.
- No storage contract or migration, no user-vault mutation. Pre-existing .agents/drafts/e4_agy_shell_out.md preserved until closure bookkeeping.

Post-change validation: 7 new regressions failed before implementation, then passed. Full local backend: 1980 passed, 6 skipped, 4 xfailed; plugin: 1286 passed, 3 skipped. Ruff, mypy, TypeScript, production build passed. A testbed-scoped `wiki plugin version` smoke returned JSON (dev environment installed metadata is stale; not evidence of production deployment).

Review: exact code-review skill invoked for PR #205; Claude OAuth session expired before review, no authentication retry. Independent peer review found no high-confidence actionable issue but is not a substitute for the mandated skill. PR remains open until required review or explicit user waiver.

## User correction: no login-triggering tests
The new pytest live graph test inherited conftest's temporary HOME and triggered agy authentication despite a valid real login. It timed out at 60 seconds; no agy process remains. User requested deletion. Removed it, the prior backend opt-in agy live test, and the global INCURATOR_LIVE_AGY guard bypass. Further automated verification replays captured real envelopes; no more real agy invocations in this task. The earlier direct live probes used normal HOME and remain valid pre-change evidence. Post-change live validation is explicitly not claimed.
