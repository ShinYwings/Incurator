"""v0.65.0 (ROADMAP A1, Arena proposal A): route on the derived INTENT.

`derive_search_query` can legitimately return an EMPTY search query for a
knowledge question: "내 볼트 전체의 주제를 정리해줘" has no search terms because its
target is the corpus. `working_query`'s `(english_query or question)` then
substitutes the raw question, so the router sees Korean, matches nothing, and
defaults to `local`.

Measured on the live vault for exactly that question:

| route | result |
|---|---|
| `local` | 8 items, all raw-Korean FTS5 hits, **0 entities, 0 of 417 reports** |
| `global` | 10 community reports, no warnings |

`global` is not a better guess — it is the route built to work without a query
(`evidence.py:341` falls back to rank when there are no query terms;
`_synthesis_items` takes no query at all), while `local` seeds entities from
`seed_terms(query)`, which returns `[]` for both an empty string and Korean text.
"""

from __future__ import annotations

import pytest

from curator.curate_yml import CurationPolicy
from curator.retrieval.models import GraphStatus, QueryRequest
from curator.retrieval.router import choose_route


def _policy(**over) -> CurationPolicy:
    base = dict(
        workspace_id="w", project="p", source_include=[], source_exclude=[],
        allowed_routes={"local", "global", "explore"}, default_route="local",
        prompt_profile="", output_language="English", require_source_spans=True,
        allow_general_knowledge=False, contradiction_policy="report",
        backprop_enabled=False, exploration_enabled=True, max_explore_followups=2,
        min_confidence=0.0, high_threshold=0.8, avoid_merges=False,
    )
    base.update(over)
    return CurationPolicy(**base)


FULL = GraphStatus(has_entities=True, has_relations=True, has_reports=True)


def test_a_synthesis_intent_reaches_global() -> None:
    """The measured bug, from the side that actually fires.

    `english_query` here deliberately contains NO `_GLOBAL_SIGNALS` token, so
    this passes only through the derived intent — never by accident through the
    regex. That is the whole point: the regex outcome was a coin flip on which
    synonym the extractor sampled."""
    route, reason = choose_route(
        QueryRequest(
            question="내 볼트 전체의 주제를 정리해줘",
            english_query="vault topics overview",
            intent="synthesis",
        ),
        policy=_policy(), status=FULL,
    )
    assert route == "global", reason
    assert "intent" in reason


def test_a_policy_that_forbids_global_degrades_and_says_so() -> None:
    """The model proposes; the deterministic policy disposes. A workspace whose
    curate.yml excludes `global` must not silently get it, and must record why
    it did not."""
    route, reason = choose_route(
        QueryRequest(question="내 볼트 전체의 주제를 정리해줘",
                     english_query="vault topics overview", intent="synthesis"),
        policy=_policy(allowed_routes={"local"}), status=FULL,
    )
    assert route == "local"
    assert "global" in reason.lower()


def test_no_reports_means_no_global() -> None:
    """A gate that is not satisfied falls through to today's path, not to an
    error: routing to a layer the vault does not have is worse than local."""
    route, _ = choose_route(
        QueryRequest(question="내 볼트 전체의 주제를 정리해줘",
                     english_query="vault topics overview", intent="synthesis"),
        policy=_policy(), status=GraphStatus(has_entities=True, has_relations=True,
                                             has_reports=False),
    )
    assert route == "local"


def test_the_other_measured_question_now_reaches_global_too() -> None:
    """The case a keyword regex can never catch.

    `advantages of 2D GS over 3D` contains no `_GLOBAL_SIGNALS` token and never
    will — the extractor correctly dropped "여러 논문을 종합해서" as a search term,
    because it is not one. Only a stated intent recovers it.
    """
    route, _ = choose_route(
        QueryRequest(
            question="2D GS가 3D보다 나은 점을 여러 논문을 종합해서 설명해줘",
            english_query="advantages of 2D GS over 3D",
            intent="synthesis",
        ),
        policy=_policy(), status=FULL,
    )
    assert route == "global"


def test_a_rogue_intent_string_is_inert() -> None:
    """An out-of-vocabulary value from a model matches no branch and falls
    through to today's signals — degraded, never harmful."""
    route, _ = choose_route(
        QueryRequest(question="what is a Plücker coordinate?",
                     english_query="Plücker coordinate definition", intent="banana"),
        policy=_policy(), status=FULL,
    )
    assert route == "local"


def test_a_lookup_intent_does_not_get_dragged_global_by_a_stray_keyword() -> None:
    """The lottery, from the other direction: a narrow fact question whose
    paraphrase happens to contain `summary` used to route `global`."""
    route, reason = choose_route(
        QueryRequest(question="Plücker 좌표가 뭐야?",
                     english_query="Plücker coordinate summary", intent="lookup"),
        policy=_policy(), status=FULL,
    )
    assert route == "local", reason


def test_an_underived_request_behaves_exactly_as_before() -> None:
    """`unset` is the default, so every existing caller — CLI, MCP, ~70 tests —
    keeps today's behaviour byte for byte."""
    for q, expected in (
        ("what are the overall themes in my vault?", "global"),
        ("what else have I written about Plücker coordinates?", "explore"),
        ("what is a Plücker coordinate?", "local"),
    ):
        route, _ = choose_route(QueryRequest(question=q), policy=_policy(), status=FULL)
        assert route == expected, q


def test_the_warning_seed_terms_has_always_promised_now_exists(tmp_path) -> None:
    """`seed_terms`' docstring says `context_fetch` warns when a non-English
    question reaches seeding. It never did — nothing inspected `english_query`.

    This test fails against the code as it stood before v0.65.0, which is the
    point: a documented invariant with no implementation is why A1 took three
    diagnoses.
    """
    from curator import config as cfg, db
    from curator.retrieval.evidence import build_evidence

    root = tmp_path / "vault"
    paths = cfg.WikiPaths(root)
    paths.internal.mkdir(parents=True)
    db.init_db(paths.state_db)

    pack = build_evidence(
        paths,
        QueryRequest(question="내 볼트 전체의 주제를 정리해줘"),  # status defaults to "unset"
        "local",
    )
    assert any("was not derived" in w for w in pack.warnings), pack.warnings


def test_a_routed_empty_derivation_does_not_get_that_warning(tmp_path) -> None:
    """A derived-but-empty query is a whole-corpus question, which `intent`
    routes to `global`, and `global` does not seed entities. Warning there would
    fire on a path working exactly as designed — and a warning that fires when
    nothing is wrong is one the user learns to skip."""
    from curator import config as cfg, db
    from curator.retrieval.evidence import build_evidence

    root = tmp_path / "vault"
    paths = cfg.WikiPaths(root)
    paths.internal.mkdir(parents=True)
    db.init_db(paths.state_db)

    pack = build_evidence(
        paths,
        QueryRequest(question="내 볼트 전체의 주제를 정리해줘",
                     english_query="", english_query_status="derived"),
        "global",
    )
    assert not any("was not derived" in w for w in pack.warnings), pack.warnings


def test_the_intent_vocabulary_matches_the_prompt_literal() -> None:
    """Two declarations, one asserted-equal pair.

    `QUERY_INTENTS` lives in retrieval, the `Intent` Literal lives in the prompt
    family, and they cannot import each other without a cycle (the prompt
    registry imports families as a side effect, and retrieval imports the
    registry). The repo already duplicates `ROUTES`/`Route` for the same reason —
    without this guard, which that pair does not have.
    """
    from typing import get_args

    from curator.prompting.families.query import Intent
    from curator.retrieval.models import QUERY_INTENTS

    assert set(QUERY_INTENTS) == set(get_args(Intent))


def test_v1_of_the_prompt_stays_registered() -> None:
    """`prompt_runs` stores prompt_id + version, so retiring v1 would make every
    historical trace unresolvable. v2 is additive; a bare get() picks it up."""
    from curator import prompting

    assert prompting.REGISTRY.get("curator.query_search_terms").version == "v2"
    assert prompting.REGISTRY.get("curator.query_search_terms", "v1").version == "v1"


def test_v2_carries_every_rule_v1_had() -> None:
    """v2 is v1 plus the intent, never a rewrite. The v1 rules are load-bearing —
    the pasted-body case, notation preservation, the 20-word cap — and a rewrite
    is how you lose one without noticing."""
    from curator.prompting.families.query import (
        SEARCH_QUERY_SYSTEM,
        SEARCH_QUERY_SYSTEM_V2,
    )

    rules = [ln for ln in SEARCH_QUERY_SYSTEM.split("\n") if ln.strip().startswith("- ")]
    assert len(rules) >= 6
    for rule in rules:
        assert rule in SEARCH_QUERY_SYSTEM_V2, rule
    assert "INTENT" in SEARCH_QUERY_SYSTEM_V2
    assert "INTENT" not in SEARCH_QUERY_SYSTEM


def test_a_provider_outage_yields_no_intent_rather_than_a_guessed_one() -> None:
    """When the step that would judge the intent never ran, "" routes on today's
    signals. Guessing here would be the worst of both designs."""
    import tempfile
    from pathlib import Path

    from curator import db
    from curator.query import derive_search_query

    class _DeadClient:
        model = "dead"

        def chat(self, *a, **k):
            raise RuntimeError("provider unavailable")

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "state.sqlite"
        db.init_db(p)
        derived = derive_search_query(p, _DeadClient(), "ellipsoid 형태의 quadric")

    assert derived.intent == ""
    assert "unavailable" in derived.reason
    assert "ellipsoid" in derived.search_query


def test_the_intent_survives_the_boundary(tmp_path, monkeypatch) -> None:
    """The anti-drop test, and the one this file was missing.

    Every routing test above passes even if `plugin_api/context.py` never sets
    `intent` on the request — verified by mutation. That is not a hypothetical
    gap: it is exactly how the ORIGINAL defect worked. `router.py:32-34` records
    that `english_query` existed as a field while the ContextService path never
    populated it, so `working_query` silently fell back to the raw question for
    releases on end.

    So pin the wiring, not just the consumer.
    """
    from curator import config as cfg, db
    from curator.plugin_api import context as ctx
    from curator.retrieval.models import DerivedQuery

    root = tmp_path / "vault"
    paths = cfg.WikiPaths(root)
    paths.internal.mkdir(parents=True)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)
    db.init_db(paths.state_db)

    monkeypatch.setattr(
        "curator.query.derive_search_query",
        lambda *a, **k: DerivedQuery("vault topics overview", True, "synthesis", "ok"),
    )
    # imported inside the function, so patch at the source module

    seen = {}

    class _Service:
        def __init__(self, *a, **k) -> None:
            pass

        def context_fetch(self, request, limit_tokens=0):
            seen["request"] = request
            return {"ok": True, "operation": "context_fetch", "items": []}

    monkeypatch.setattr("curator.context_service.ContextService", _Service)

    class _Client:
        model = "stub"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("curator.llm.build_client", lambda *a, **k: _Client())

    ctx.fetch_context(paths, query_text="내 볼트 전체의 주제를 정리해줘", workspace_path="")

    request = seen.get("request")
    assert request is not None, "context_fetch was never reached"
    assert request.intent == "synthesis", (
        "the boundary dropped the derived intent — the router will never see it, "
        "which is the v0.47.0 defect repeated"
    )
