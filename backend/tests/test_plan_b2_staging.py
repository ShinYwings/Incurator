"""Plan B2 — copy-on-stage generation isolation (SYSTEM_BEHAVIOR §26.3).

Oracles for the staged/authoritative row separation: staged-generation units are
stored but never served (no ATM/graph/search), publish persists the graph
against final stable ids and materializes from the authoritative DB, discard
leaves no orphan downstream artifact, the temp→stable id rewrite keeps all
references consistent, and a successful zero-unit compile publishes (retiring the
prior units).

New eligibility APIs are resolved lazily so collection never breaks before P3/P4
land them; each oracle asserts the API exists, then the behavior.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db
from curator.llm import ChatMessage
from curator.pipeline import compile as compile_mod

SOURCE_MD = """\
# Residual Learning

Residual connections make very deep networks easier to optimize.

# Euler Discretization

A residual block resembles one Euler step of an ODE.
"""


class _UnitsClient:
    """Dynamic fake LLM: cites real span ids; configurable unit set."""

    model = "fake"

    def __init__(self, *, units: bool = True) -> None:
        self._units = units

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        text = "\n".join(m.content for m in messages)
        span_ids = re.findall(r"SPAN-[0-9a-f]{8}", text)
        first = span_ids[0] if span_ids else "SPAN-00000000"
        if "Extract the knowledge units" in text:
            if not self._units:
                return json.dumps({"units": []})
            return json.dumps({"units": [{
                "canonical_name": "Residual learning eases optimization",
                "unit_type": "claim",
                "statement": "Residual connections make deep nets easier to optimize.",
                "source_span_ids": [first], "confidence": 0.9,
                "truth_status": "source_supported",
            }]})
        if "Extract entities and relations" in text:
            return json.dumps({
                "entities": [
                    {"canonical_name": "ResNet", "entity_type": "method",
                     "source_span_ids": [first]},
                    {"canonical_name": "degradation problem", "entity_type": "concept",
                     "source_span_ids": [first]},
                ],
                "relations": [{"source": "ResNet", "target": "degradation problem",
                               "relation_type": "addresses", "assertion_source": "source_states",
                               "source_span_ids": [first], "confidence": 0.9}],
            })
        return "{}"


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        paths = cfg.WikiPaths(root)
        db.init_db(paths.state_db)
        src = root / "04_Resources" / "resnet.md"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(SOURCE_MD, encoding="utf-8")
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, "
                "context_id, l1_status) VALUES (?, ?, ?, ?, datetime('now'), ?, 'done')",
                ("04_Resources/resnet.md", "h", "md", len(SOURCE_MD), "CTX-test1234"),
            )
        yield paths


def _serving(db_path):
    fn = getattr(db, "list_serving_units", None)
    assert fn is not None, "B2 list_serving_units not implemented"
    return fn


def _gen_units(db_path):
    fn = getattr(db, "list_generation_units", None)
    assert fn is not None, "B2 list_generation_units not implemented"
    return fn


# --- Eligibility split (P3) -------------------------------------------------

def test_staged_generation_units_are_not_served(vault) -> None:
    serving, gen_units = _serving(vault.state_db), _gen_units(vault.state_db)
    gen = db.create_compiler_generation(
        vault.state_db, prompt_contract_version="v2", source_id=1)  # status='staged'
    uid = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="x",
        statement="Some claim.", source_span_ids=["SPAN-a"], source_id=1)
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "UPDATE knowledge_units SET generation_id = ?, support_status = 'verified' "
            "WHERE id = ?", (gen, uid))
    assert uid not in [u["id"] for u in serving(vault.state_db)]    # staged → invisible
    assert uid in [u["id"] for u in gen_units(vault.state_db, gen)]  # compiler-visible


def test_authoritative_gen_with_unchecked_unit_is_stored_not_served(vault) -> None:
    serving = _serving(vault.state_db)
    gen = db.create_compiler_generation(
        vault.state_db, prompt_contract_version="v2", source_id=1)
    db.publish_compiler_generation(vault.state_db, gen)  # authoritative
    uid = db.upsert_knowledge_unit(
        vault.state_db, unit_type="atom", canonical_name="x",
        statement="Unverified claim.", source_span_ids=["SPAN-a"], source_id=1)
    with db.connect(vault.state_db) as conn:
        conn.execute(  # authoritative generation, but still unchecked
            "UPDATE knowledge_units SET generation_id = ? WHERE id = ?", (gen, uid))
    assert uid not in [u["id"] for u in serving(vault.state_db)]  # unchecked → not served
    with db.connect(vault.state_db) as conn:  # but it is stored + auditable
        assert conn.execute(
            "SELECT COUNT(*) FROM knowledge_units WHERE id = ?", (uid,)).fetchone()[0] == 1


# --- Copy-on-stage compile (P4) ---------------------------------------------

def test_successful_compile_persists_graph_and_serves_units(vault) -> None:
    serving = _serving(vault.state_db)
    result = compile_mod.compile_source_l2(vault, _UnitsClient(), 1)
    assert result.ok, result.error
    gen = db.get_authoritative_generation(vault.state_db, 1)
    assert gen is not None
    served = serving(vault.state_db)
    assert served, "verified units must be served after publish"
    served_ids = {u["id"] for u in served}
    with db.connect(vault.state_db) as conn:
        n_ent = conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
        ent_rows = conn.execute("SELECT knowledge_unit_ids FROM graph_entities").fetchall()
    assert n_ent > 0  # graph persisted at publish
    for (kus_json,) in ent_rows:  # every graph entity references only served units
        for ku in json.loads(kus_json or "[]"):
            assert ku in served_ids, "graph references a non-served unit (leak/dangling)"


def test_failed_staged_compile_leaves_no_orphan_graph(vault) -> None:
    # Plant a publish-gate violation (ghost dangling support) so the staged
    # compile is blocked at publish; NO graph entity/relation may be persisted
    # (they are upserted only inside the publish txn).
    db.upsert_claim_support(
        vault.state_db, knowledge_unit_id="KNU-ghost000", source_span_id="SPAN-missing",
        support_role="primary", support_status="verified", evidence_hash="x")
    result = compile_mod.compile_source_l2(vault, _UnitsClient(), 1)
    assert not result.ok  # publish gate blocked the compile
    with db.connect(vault.state_db) as conn:
        n_ent = conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
        n_rel = conn.execute("SELECT COUNT(*) FROM graph_relations").fetchone()[0]
        n_auth = conn.execute(
            "SELECT COUNT(*) FROM compiler_generations WHERE status = 'authoritative'"
        ).fetchone()[0]
    assert n_ent == 0 and n_rel == 0  # no leaked graph (currently upserted pre-gate → red)
    assert n_auth == 0               # nothing published


class _GraphFailClient(_UnitsClient):
    """Units extract fine, but the graph LLM call fails — the atomicity vector
    the post-publish design missed."""

    def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
        text = "\n".join(m.content for m in messages)
        if "Extract entities and relations" in text:
            return "not valid json — graph extraction failure"
        return super().chat(messages, json_mode=json_mode, temperature=temperature)


def test_graph_extraction_failure_leaves_no_partial_publish(vault) -> None:
    # The LLM graph extraction must run BEHIND the publish gate: if it fails, the
    # staged units are discarded and NO generation is published (§26.3). A prior
    # design that published first and extracted the graph after would leave a
    # published generation with no graph.
    result = compile_mod.compile_source_l2(vault, _GraphFailClient(), 1)
    assert not result.ok  # graph failure aborts the compile
    with db.connect(vault.state_db) as conn:
        n_ent = conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
        n_auth = conn.execute(
            "SELECT COUNT(*) FROM compiler_generations WHERE status = 'authoritative'"
        ).fetchone()[0]
        n_units = conn.execute(
            "SELECT COUNT(*) FROM knowledge_units WHERE retired_at IS NULL"
        ).fetchone()[0]
    assert n_ent == 0       # no graph
    assert n_auth == 0      # nothing published
    assert n_units == 0     # staged units discarded — no partial state
    assert db.list_serving_units(vault.state_db) == []


def test_graph_extraction_failure_preserves_prior_authoritative(vault) -> None:
    # A graph failure on a RE-compile must leave the prior authoritative
    # generation (and its served units + graph) byte-untouched.
    assert compile_mod.compile_source_l2(vault, _UnitsClient(), 1).ok
    before = {u["id"] for u in db.list_serving_units(vault.state_db)}
    with db.connect(vault.state_db) as conn:
        ent_before = conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
        conn.execute("UPDATE sources SET content_hash = 'edited-gf' WHERE id = 1")
    result = compile_mod.compile_source_l2(vault, _GraphFailClient(), 1)
    assert not result.ok
    after = {u["id"] for u in db.list_serving_units(vault.state_db)}
    with db.connect(vault.state_db) as conn:
        ent_after = conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
    assert after == before and after  # prior served set untouched
    assert ent_after == ent_before    # prior graph untouched


def test_zero_unit_recompile_publishes_and_retires_prior(vault) -> None:
    serving = _serving(vault.state_db)
    assert compile_mod.compile_source_l2(vault, _UnitsClient(units=True), 1).ok
    assert serving(vault.state_db)  # units served
    # Source emptied of claims → extraction returns zero units → must publish + retire.
    with db.connect(vault.state_db) as conn:
        conn.execute("UPDATE sources SET content_hash = 'emptied' WHERE id = 1")
    result = compile_mod.compile_source_l2(vault, _UnitsClient(units=False), 1)
    assert result.ok, result.error  # zero-unit publish is valid
    assert serving(vault.state_db) == []  # prior claims retired, not served forever
    assert db.get_authoritative_generation(vault.state_db, 1) is not None


def test_edit_recompile_keeps_graph_refs_consistent(vault) -> None:
    # temp→stable id rewrite at publish: no graph ref dangles after an edit.
    serving = _serving(vault.state_db)
    assert compile_mod.compile_source_l2(vault, _UnitsClient(), 1).ok
    with db.connect(vault.state_db) as conn:
        conn.execute("UPDATE sources SET content_hash = 'edited-v2' WHERE id = 1")
    assert compile_mod.compile_source_l2(vault, _UnitsClient(), 1).ok
    served_ids = {u["id"] for u in serving(vault.state_db)}
    with db.connect(vault.state_db) as conn:
        ent_rows = conn.execute("SELECT knowledge_unit_ids FROM graph_entities").fetchall()
    for (kus_json,) in ent_rows:
        for ku in json.loads(kus_json or "[]"):
            assert ku in served_ids, f"dangling graph ref to non-served unit {ku}"


# --- Legacy NULL-generation backfill migration (P3) -------------------------

def test_init_db_backfills_legacy_verified_units_to_synthetic_generation(vault) -> None:
    # A legacy verified unit with NULL generation_id (pre-B2) is attributed to a
    # deterministic synthetic authoritative generation by init_db, so it becomes
    # served; an unchecked legacy unit is left NULL (not served).
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO knowledge_units (id, unit_type, canonical_name, statement, "
            "source_span_ids, source_id, support_status, formula_status, created_at, "
            "updated_at) VALUES ('KNU-legacyV', 'atom', 'V', 'Verified legacy.', "
            "'[\"SPAN-x\"]', 1, 'verified', 'not_applicable', '2026-01-01T00:00:00Z', "
            "'2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO knowledge_units (id, unit_type, canonical_name, statement, "
            "source_span_ids, source_id, support_status, formula_status, created_at, "
            "updated_at) VALUES ('KNU-legacyU', 'atom', 'U', 'Unchecked legacy.', "
            "'[\"SPAN-y\"]', 1, 'unchecked', 'not_applicable', '2026-01-01T00:00:00Z', "
            "'2026-01-01T00:00:00Z')"
        )
    db.init_db(vault.state_db)  # runs the one-time backfill
    with db.connect(vault.state_db) as conn:
        gen_v = conn.execute(
            "SELECT generation_id FROM knowledge_units WHERE id = 'KNU-legacyV'"
        ).fetchone()[0]
        gen_u = conn.execute(
            "SELECT generation_id FROM knowledge_units WHERE id = 'KNU-legacyU'"
        ).fetchone()[0]
        gen_status = conn.execute(
            "SELECT status FROM compiler_generations WHERE id = ?", (gen_v,)
        ).fetchone()
    assert gen_v == "GEN-mig-1"                 # deterministic id
    assert gen_status is not None and gen_status[0] == "authoritative"
    assert gen_u is None                        # unchecked legacy is NOT backfilled
    served_ids = {u["id"] for u in db.list_serving_units(vault.state_db)}
    assert "KNU-legacyV" in served_ids          # now served
    assert "KNU-legacyU" not in served_ids      # unchecked → not served
    # Idempotent: a second init_db creates no duplicate generation.
    db.init_db(vault.state_db)
    with db.connect(vault.state_db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM compiler_generations WHERE id = 'GEN-mig-1'"
        ).fetchone()[0] == 1


# --- Atomic publish: failures preserve the prior authoritative generation ----

def test_graph_persistence_failure_preserves_authoritative_state(vault, monkeypatch) -> None:
    # A persist_graph_data exception (after the gate, before reconcile) must
    # discard the staged generation cleanly and leave the prior authoritative
    # generation + its served units perfectly preserved (no catastrophic
    # discard-of-authoritative).
    assert compile_mod.compile_source_l2(vault, _UnitsClient(), 1).ok
    before = {u["id"] for u in db.list_serving_units(vault.state_db)}
    gen_before = db.get_authoritative_generation(vault.state_db, 1)["id"]
    with db.connect(vault.state_db) as conn:
        conn.execute("UPDATE sources SET content_hash = 'edited-pf' WHERE id = 1")

    def _boom(*a, **k):
        raise RuntimeError("persist_graph_data failed")

    monkeypatch.setattr(compile_mod.graph_index, "persist_graph_data", _boom)
    result = compile_mod.compile_source_l2(vault, _UnitsClient(), 1)
    assert not result.ok
    assert db.get_authoritative_generation(vault.state_db, 1)["id"] == gen_before
    assert {u["id"] for u in db.list_serving_units(vault.state_db)} == before and before


def test_publish_failure_rolls_back_reconcile_to_prior_authoritative(vault, monkeypatch) -> None:
    # A failure INSIDE the reconcile+publish transaction (here: the generation
    # flip) must roll back reconcile's prior-id re-tagging, leaving the prior
    # authoritative generation + served set byte-identical — no reused unit
    # stranded in a staged/discarded generation, no data loss.
    assert compile_mod.compile_source_l2(vault, _UnitsClient(), 1).ok
    before = {u["id"] for u in db.list_serving_units(vault.state_db)}
    gen_before = db.get_authoritative_generation(vault.state_db, 1)["id"]
    with db.connect(vault.state_db) as conn:
        conn.execute("UPDATE sources SET content_hash = 'edited-pf2' WHERE id = 1")

    def _boom(*a, **k):
        raise RuntimeError("generation flip failed")

    monkeypatch.setattr(compile_mod.db, "publish_compiler_generation", _boom)
    result = compile_mod.compile_source_l2(vault, _UnitsClient(), 1)
    assert not result.ok
    assert db.get_authoritative_generation(vault.state_db, 1)["id"] == gen_before
    assert {u["id"] for u in db.list_serving_units(vault.state_db)} == before and before
