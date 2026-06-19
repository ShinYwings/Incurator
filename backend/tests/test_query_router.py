"""Phase 6 (v0.3.1): deterministic query routing."""

from __future__ import annotations

from curator.curate_yml import CurateReasoning, CurateSpec, compile_curate_policy
from curator.retrieval import choose_route
from curator.retrieval.models import GraphStatus, QueryRequest


def _policy(allowed=None, default="auto", exploration=True):
    spec = CurateSpec(
        project="lab",
        reasoning=CurateReasoning(
            default_mode=default,
            allowed_modes=allowed or ["local", "global", "explore", "source-section"],
            exploration_enabled=exploration,
        ),
    )
    return compile_curate_policy(spec)


FULL = GraphStatus(has_entities=True, has_relations=True, has_reports=True)


def test_explicit_mode_wins() -> None:
    route, _ = choose_route(QueryRequest(question="x", mode="global"), _policy(), FULL)
    assert route == "global"


def test_explicit_mode_disallowed_degrades_to_local() -> None:
    route, _ = choose_route(
        QueryRequest(question="x", mode="global"), _policy(allowed=["local"]), FULL
    )
    assert route == "local"


def test_source_key_routes_source_section() -> None:
    route, _ = choose_route(QueryRequest(question="x", source_key="3"), _policy(), FULL)
    assert route == "source-section"


def test_explore_signal_routes_explore() -> None:
    route, _ = choose_route(
        QueryRequest(question="what else connects to residual learning?"), _policy(), FULL
    )
    assert route == "explore"


def test_explore_disabled_falls_back_to_local() -> None:
    route, _ = choose_route(
        QueryRequest(question="find connections between X and Y"),
        _policy(exploration=False), FULL,
    )
    assert route == "local"


def test_global_signal_routes_global() -> None:
    route, _ = choose_route(
        QueryRequest(question="give an overall summary of the themes"), _policy(), FULL
    )
    assert route == "global"


def test_global_signal_without_reports_falls_back_local() -> None:
    status = GraphStatus(has_entities=True, has_relations=True, has_reports=False)
    route, _ = choose_route(QueryRequest(question="overall summary"), _policy(), status)
    assert route == "local"


def test_default_is_local() -> None:
    route, _ = choose_route(QueryRequest(question="what is a residual block?"), _policy(), FULL)
    assert route == "local"


def test_incomplete_graph_routes_local_with_warning() -> None:
    empty = GraphStatus()
    route, reason = choose_route(QueryRequest(question="anything"), _policy(), empty)
    assert route == "local"
    assert "DB-native retrieval" in reason
