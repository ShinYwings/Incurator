"""ROADMAP A7: a query trace must say whether a derivation ran, and what it found.

This exists because the same fact was measured wrong twice. Two separate
single-run observations of one question produced an empty derived search query,
and a routing design was built on the premise that empty was a deliberate,
stable signal. Running that question eight times gave 0/8 empty and a 6-in-8
route flip instead — a completely different bug. One sample was mistaken for a
property, twice, because nothing stored enough to check afterwards.

The distinguishing case is `test_derived_but_empty_is_distinguishable_from_never_derived`.
"Nothing was derived" and "a derivation ran and legitimately found no search
terms" are the two readings that were confused, and until this change they were
byte-identical in storage: `english_query == ""` either way.
"""

from __future__ import annotations

from pathlib import Path

from curator import config as cfg
from curator import db
from curator.retrieval.models import QueryRequest


def _seed_context_vault(tmp_path: Path) -> cfg.WikiPaths:
    """Smallest vault ContextService will serve a local route from.

    A local copy, matching this repo's test convention -- no test module imports
    another.
    """
    paths = cfg.WikiPaths(tmp_path / "vault")
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES ('04_Resources/context.md', 'source-hash', 'md', 1, datetime('now'))"
        )
    span_id = db.upsert_source_span(
        paths.state_db,
        source_id=1,
        relpath="04_Resources/context.md",
        span_type="paragraph",
        content_hash="span-hash",
        section_title="Context",
        text_preview="Residual connections stabilize optimization.",
    )
    db.upsert_graph_entity(
        paths.state_db,
        canonical_name="residual connection",
        entity_type="concept",
        source_span_ids=[span_id],
    )
    return paths


def _derivation_for(paths, request: QueryRequest) -> dict:
    """Read the block back through the production write path, not a rebuild."""
    from curator import context_service as cs

    response = cs.ContextService(paths).context_fetch(request)
    trace = db.get_query_trace(paths.state_db, response["trace_id"])
    assert trace is not None
    return trace["retrieval_trace"]["context_service"]["derivation"]


def test_records_what_the_derivation_produced(tmp_path: Path) -> None:
    block = _derivation_for(
        _seed_context_vault(tmp_path),
        QueryRequest(
            question="내 볼트 전체의 주제를 정리해줘",
            english_query="themes across the vault",
            english_query_status="derived",
            intent="synthesis",
            mode="auto",
        ),
    )
    assert block["status"] == "derived"
    assert block["search_query_empty"] is False
    assert block["routing_intent"] == "synthesis"


def test_records_that_no_derivation_ran(tmp_path: Path) -> None:
    """The CLI and both MCP paths never derive (ROADMAP A8). That must be legible
    in the trace rather than looking like a derivation that returned nothing."""
    paths = _seed_context_vault(tmp_path)
    block = _derivation_for(paths, QueryRequest(question="residual connection", mode="auto"))
    assert block["status"] == "unset"
    assert block["routing_intent"] == ""


def test_derived_but_empty_is_distinguishable_from_never_derived(tmp_path: Path) -> None:
    """THE case this whole item exists for.

    A whole-corpus question legitimately has no search terms, so an empty
    `english_query` from a derivation that RAN is a real result — not a failure,
    and not the same thing as no derivation at all. Before this block, both
    stored `english_query == ""` and were indistinguishable after the fact.
    """
    paths_a = _seed_context_vault(tmp_path / "a")
    paths_b = _seed_context_vault(tmp_path / "b")

    ran = _derivation_for(
        paths_a,
        QueryRequest(
            question="summarise everything",
            english_query="",
            english_query_status="derived",
            intent="synthesis",
            mode="auto",
        ),
    )
    never = _derivation_for(
        paths_b,
        QueryRequest(question="summarise everything", english_query="", mode="auto"),
    )

    # Both have an empty search query...
    assert ran["search_query_empty"] is True
    assert never["search_query_empty"] is True
    # ...and that is precisely why `status` has to carry the difference.
    assert ran["status"] != never["status"]
    assert (ran["status"], never["status"]) == ("derived", "unset")


def test_status_is_read_from_the_request_not_assumed(tmp_path: Path) -> None:
    """Mutation guard. Hardcoding either value passes every test above that
    happens to use the other one, so pin both against the same code path."""
    paths_a = _seed_context_vault(tmp_path / "a")
    paths_b = _seed_context_vault(tmp_path / "b")
    q = "residual connection"
    derived = _derivation_for(
        paths_a,
        QueryRequest(question=q, english_query=q, english_query_status="derived", mode="auto"),
    )
    unset = _derivation_for(paths_b, QueryRequest(question=q, mode="auto"))
    assert {derived["status"], unset["status"]} == {"derived", "unset"}


def test_routing_intent_is_not_the_expansion_intent(tmp_path: Path) -> None:
    """`retrieval_trace["intent"]` is `ExpandedQuery.intent` — a keyword-cue
    detector for query EXPANSION whose vocabulary is
    definition/comparison/procedure/default. The routing intent is a different
    mechanism with a different vocabulary. They must not collide on one key."""
    from curator.retrieval.expansion import ExpandedQuery
    from curator.retrieval.models import QUERY_INTENTS

    assert ExpandedQuery(raw="x").intent == "default"
    assert "default" not in QUERY_INTENTS

    paths = _seed_context_vault(tmp_path)
    block = _derivation_for(
        paths,
        QueryRequest(
            question="what is a residual connection",
            english_query="residual connection",
            english_query_status="derived",
            intent="lookup",
            mode="auto",
        ),
    )
    assert block["routing_intent"] == "lookup"
    assert "intent" not in block, (
        "a bare `intent` key here would sit in the same JSON document as the "
        "expansion intent and leave the next reader to guess which is which"
    )


def test_wiki_inspect_answer_prints_the_derivation(tmp_path: Path, monkeypatch) -> None:
    """Storing it is half the item. Phase A is *make failure visible*, and the
    human summary prints only `route=` today — not even `routeReason`. A datum
    that needs `--json | jq` to reach is not visible."""
    import os

    from typer.testing import CliRunner

    from curator import config as cfg
    from curator import context_service as cs
    from curator.cli import app

    paths = _seed_context_vault(tmp_path)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)
    response = cs.ContextService(paths).context_fetch(
        QueryRequest(
            question="summarise everything",
            english_query="",
            english_query_status="derived",
            intent="synthesis",
            mode="auto",
        )
    )
    monkeypatch.setenv("VAULT_ROOT", str(paths.root))
    assert os.environ["VAULT_ROOT"]

    result = CliRunner().invoke(app, ["inspect", "answer", response["trace_id"]])
    assert result.exit_code == 0, result.stdout
    out = result.stdout
    assert "derived" in out, out
    assert "synthesis" in out, out
    # The empty search query is the fact that was misread twice. It has to be on
    # screen, not inferable.
    assert "no search terms" in out, out
