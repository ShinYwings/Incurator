"""D2: the curation lens reaches retrieval but is invisible in the result.

The roadmap carried an audit finding that `curate.yml`'s KRS and the vault
persona "never reach the chat surface". Re-verified before planning, as that
entry asked: **half of it is stale.** `ChatSidebarView` resolves the real
workspace from the note in focus and passes it, `context_fetch` resolves the
policy from it, and on the reference vault that policy genuinely differs from the
default in six fields — `source_include`, `allowed_routes`, `prompt_profile`,
`avoid_merges`, and the two ids.

What is still true is the half the roadmap flagged as adjacent: **the context
pack does not say what the lens did.** It carries `workspace_id` and nothing
else about the policy, so a lens that applied nothing is indistinguishable from
one that applied everything, and the vault persona — which shapes how an answer
should read — never reaches the surface that writes the answer at all.

That is the failure this repo keeps naming: not a wrong result, an unverifiable
one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from curator import config as cfg
from curator import db


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / "01_Workspaces" / "proj").mkdir(parents=True)
    (root / "01_Workspaces" / "proj" / "curate.yml").write_text(
        "workspace_id: proj\n"
        "project: proj\n"
        "sources:\n  include: ['03_Notes/**']\n"
        "prompts:\n  profile: technical-research\n",
        encoding="utf-8",
    )
    paths = cfg.paths_from_config(root)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)
    db.init_db(paths.state_db)
    return root


def _pack(root: Path, workspace: str) -> dict:
    from curator.context_service import ContextService
    from curator.retrieval import QueryRequest

    paths = cfg.paths_from_config(root)
    return ContextService(paths, None).context_fetch(
        QueryRequest(question="what is a residual connection?",
                     workspace_path=workspace, mode="local")
    )


def test_the_pack_lists_the_filters_the_lens_actually_applied(vault: Path) -> None:
    """The shape is the one the spec already documented, not a new one.

    `policy.applied_filters` / `excluded` is what the Plan F fixture and
    `PLUGIN_SCHEMA.md` §15.1 have described all along, and what this roadmap
    entry named. A first pass here invented a parallel `policy` shape, which
    would have put two incompatible meanings on the same key.
    """
    pack = _pack(vault, str(vault / "01_Workspaces" / "proj"))
    assert "policy" in pack, "the context pack does not report the curation lens at all"
    policy = pack["policy"]
    assert policy["workspace_id"] == "proj"
    filters = {f["filter"]: f["value"] for f in policy["applied_filters"]}
    assert "source_include" in filters, (
        f"a workspace that narrows to 03_Notes reported no filter: {policy}"
    )
    assert "03_Notes/**" in filters["source_include"]


def test_an_inert_lens_reports_an_empty_filter_set(vault: Path) -> None:
    """Outside a workspace the lens runs and narrows nothing. The spec's own
    words: an inert lens must be "visible as an empty filter set rather than
    something that has to be inferred"."""
    pack = _pack(vault, "")
    policy = pack["policy"]
    assert policy["workspace_id"] == "default"
    assert policy["applied_filters"] == []
    assert policy["excluded"] == []


def test_a_field_that_changes_routing_counts_as_a_filter(vault: Path) -> None:
    """`exploration_enabled` is read by `router.choose_route`, so turning it off
    makes the explore route unreachable.

    The first version of this compared eight fields chosen by hand and this was
    not among them, so a workspace that disabled exploration reported that it had
    narrowed nothing — while demonstrably changing where questions route.
    """
    ws = vault / "01_Workspaces" / "explore_off"
    ws.mkdir()
    (ws / "curate.yml").write_text(
        "workspace_id: explore_off\nproject: explore_off\n"
        "reasoning:\n  exploration_enabled: false\n",
        encoding="utf-8",
    )
    policy = _pack(vault, str(ws))["policy"]
    filters = {f["filter"]: f["value"] for f in policy["applied_filters"]}
    assert "exploration_enabled" in filters, (
        f"disabling exploration changes routing but reported no filter: {policy}"
    )
    assert "explore" in policy["excluded"]


def test_a_field_that_changes_nothing_is_declared_but_not_claimed_as_applied(
    vault: Path,
) -> None:
    """The mirror error, and the one that is easier to miss.

    `output_language` is compiled into the policy and read nowhere on the
    answering path. Listing it as an applied filter would tell the user the
    system acted on a knob they turned when it did not — the same false
    visibility this feature exists to remove, pointing the other way.
    """
    ws = vault / "01_Workspaces" / "lang"
    ws.mkdir()
    (ws / "curate.yml").write_text(
        "workspace_id: lang\nproject: lang\noutput:\n  language: Korean\n",
        encoding="utf-8",
    )
    policy = _pack(vault, str(ws))["policy"]
    assert policy["applied_filters"] == [], (
        f"an inert field was reported as an applied filter: {policy}"
    )
    assert "output_language" in policy["declared"]


def test_the_pack_carries_the_vault_persona(vault: Path) -> None:
    """The plugin's chat model writes the answer, and the backend only hands it
    the pack. A persona the pack does not carry cannot shape anything the user
    reads."""
    pack = _pack(vault, str(vault / "01_Workspaces" / "proj"))
    persona = pack.get("persona")
    assert isinstance(persona, dict) and persona, (
        "the pack carries no persona, so the surface that writes the answer "
        "never sees it"
    )
