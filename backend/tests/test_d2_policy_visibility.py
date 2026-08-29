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


def test_the_pack_says_which_lens_it_applied(vault: Path) -> None:
    """A pack that does not name its policy cannot be checked against one."""
    pack = _pack(vault, str(vault / "01_Workspaces" / "proj"))
    assert "policy" in pack, "the context pack does not report the curation lens at all"
    policy = pack["policy"]
    assert policy.get("workspace_id") == "proj"
    assert policy.get("prompt_profile") == "technical-research"
    assert "03_Notes/**" in (policy.get("source_include") or [])


def test_an_inert_lens_is_visible_as_such(vault: Path) -> None:
    """Outside a workspace the policy is the default. That is correct behaviour,
    and it must be legible as "nothing was narrowed" rather than inferred."""
    pack = _pack(vault, "")
    policy = pack["policy"]
    assert policy.get("workspace_id") == "default"
    assert policy.get("source_include") == []
    assert policy.get("applied") is False, (
        "a default policy must announce that it narrowed nothing"
    )


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
