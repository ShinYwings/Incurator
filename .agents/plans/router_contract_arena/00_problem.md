# Briefing: `curator.query_router` is pinned in two specs and has zero call sites

ROADMAP **A6**. The contract is registered (`prompting/families/query.py:294`),
required by `test_prompt_registry.py`, listed in `SYSTEM_BEHAVIOR.md` §15, and
promised by §17: *"an LLM router (`curator.query_router`) is used only when
deterministic signals are ambiguous."*

It has **no production caller**. Per CLAUDE.md — *"any divergence means both are
wrong until reconciled"* — either the contract gets implemented or the spec
drops it.

v0.65.0 complicates the question rather than settling it: routing now reads a
derived **intent** from `curator.query_search_terms@v2`, which is the job §17
imagined for the router, done without a second round trip. That is an argument
for deletion, but it is the *author of v0.65.0* making it, which is exactly the
kind of self-agreement the Arena exists to prevent.

## The question put to the Arena

Three agents ran in parallel, with genuinely opposed briefs:

| agent | brief |
|---|---|
| `router_advocate` | the strongest honest case that the LLM router still earns its place |
| `deletion_advocate` | the strongest honest case for deleting it, with the full blast radius |
| `adversarial_verifier` | take no side; try to **refute** "zero call sites, nothing stored, safe to remove" |

Each was required to end with **WHERE MY POSITION FAILS**. An Arena that cannot
lose is worthless.
