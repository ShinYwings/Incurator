# Defense / Revision of Plugin Retention Proposal
Date: 2026-09-11 | Agent Persona: Plugin and Session Retention Reviewer

## 1. Vulnerabilities & Flaws

The independent cache proposal changes the correct release order: the existing collector can mutate candidate databases during planning and delete source-less retained history. These are concrete preservation failures and precede a new Dashboard surface. My initial proposal identified the missing GC tab but did not imply that UI should outrank those defects. The completed cross-critique is `02_critique_plugin_on_safety.md`; its guard precision, empty-cache capability, WAL-awareness and bounded revalidation requirements remain applicable.

No critique of the plugin proposal was available when this revision was written. This revision follows the parent synthesis direction and the independent findings, rather than claiming an absent critique was resolved.

## 2. Suggested Alternatives / Final Recommendation

**First release: cache-only prerequisite patch.** Repair the existing cache eligibility predicate with read-only, WAL-aware inspection and preservation of durable application rows, unknown content and unrecognized layouts; revalidate identity and eligibility immediately before deletion. Preserve collection of a recognized genuinely empty temporary cache. Do not claim the final check excludes every uncooperative writer. The separately confirmed prompt-run transaction gap deserves its own tracked correctness patch rather than broadening this cache-only release by implication.

**Subsequent milestone: complete backend-driven GC Dashboard with writer coordination.** The GC tab is an explicitly requested missing feature. It must render backend-normalized effective policy, use explicit project-local CLI config writes, and distinguish saving policy from executing deletion. Existing session windows and opt-in prompt-run caps require no new user policy choice. Before exposing Run, resolve the shared backend/plugin session write boundary and reconcile sidebar messages/selection after pruning; test concurrent saves, tombstones, drafts, generation and failures. A JavaScript button-disable flag or a backend-only lock is not a complete root-cause fix. If that work changes session storage or the persistence API, give it a dedicated contract plan and migration rehearsal before the UI release.

Keep full active-session replay, visible thumbnails, all session tombstones and current history defaults. There is no user decision needed to fix data-preservation defects or implement the already requested controls. Ask only for an actual product tradeoff, such as removing useful historical images or adopting new job/query/compiler history windows. Run no live GC or migration during implementation validation. B1/B2 remains active after the prerequisite patch, with the session writer and full Dashboard milestones named explicitly.
