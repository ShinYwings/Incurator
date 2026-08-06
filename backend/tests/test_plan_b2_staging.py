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

def test_successful_compile_persists_graph_with_live_span_refs(vault) -> None:
    # The compile path anchors graph entities to L1 SPANS (knowledge_unit_ids is
    # always [] there), so verify the real invariant: every graph source_span_ids
    # ref points at a live span — not the vacuous knowledge_unit_ids loop.
    result = compile_mod.compile_source_l2(vault, _UnitsClient(), 1)
    assert result.ok, result.error
    assert db.get_authoritative_generation(vault.state_db, 1) is not None
    assert db.list_serving_units(vault.state_db)  # verified units served
    with db.connect(vault.state_db) as conn:
        n_ent = conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
        live_spans = {r[0] for r in conn.execute("SELECT id FROM source_spans").fetchall()}
        refs = [
            s
            for (j,) in (
                conn.execute("SELECT source_span_ids FROM graph_entities").fetchall()
                + conn.execute("SELECT source_span_ids FROM graph_relations").fetchall()
            )
            for s in json.loads(j or "[]")
        ]
    assert n_ent > 0  # graph persisted at publish
    assert refs       # graph actually cites spans (non-vacuous, unlike knowledge_unit_ids)
    assert all(s in live_spans for s in refs), "graph cites a dropped/dangling span"


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


class _NoCallClient:
    model = "must-not-run"

    def chat(self, *args, **kwargs):
        raise AssertionError("projection recovery must not call the LLM")


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


def test_emptied_source_recompile_retires_prior(vault) -> None:
    # A GENUINELY emptied/changed source (its spans disappear) makes the prior
    # claims lose their basis → retire (§26.4); the zero-unit generation still
    # publishes (no zero-unit guard). NB: the spans must actually change — an LLM
    # omission on UNCHANGED spans is handled by the carry-forward test below.
    assert compile_mod.compile_source_l2(vault, _UnitsClient(units=True), 1).ok
    prior_units = db.list_serving_units(vault.state_db)
    assert prior_units
    prior_atom_id = str(prior_units[0]["atom_node_id"])
    (vault.root / "04_Resources" / "resnet.md").write_text(
        "# Unrelated\n\nEntirely different prose with no prior claims.\n", encoding="utf-8")
    with db.connect(vault.state_db) as conn:
        conn.execute("UPDATE sources SET content_hash = 'emptied' WHERE id = 1")
    result = compile_mod.compile_source_l2(vault, _UnitsClient(units=False), 1)
    assert result.ok, result.error  # zero-unit publish is valid
    assert db.list_serving_units(vault.state_db) == []  # prior retired, not served forever
    assert db.get_authoritative_generation(vault.state_db, 1) is not None
    assert not (vault.atoms / f"{prior_atom_id}.md").exists()
    with db.connect(vault.state_db) as conn:
        assert conn.execute(
            "SELECT 1 FROM dag_edges WHERE source_id = 1"
        ).fetchone() is None


def test_llm_omission_on_unchanged_span_carries_claim_forward(vault) -> None:
    # §26.4: a claim whose SPAN basis is unchanged is KEPT even when a re-extraction
    # omits it (LLM non-determinism) — it must not be lost, and keeps its stable id.
    assert compile_mod.compile_source_l2(vault, _UnitsClient(units=True), 1).ok
    before = {u["id"] for u in db.list_serving_units(vault.state_db)}
    assert len(before) == 1
    # Same file (spans unchanged), but the LLM returns zero units this time.
    with db.connect(vault.state_db) as conn:
        conn.execute("UPDATE sources SET content_hash = 'omit-v2' WHERE id = 1")
    assert compile_mod.compile_source_l2(vault, _UnitsClient(units=False), 1).ok
    after = {u["id"] for u in db.list_serving_units(vault.state_db)}
    assert after == before, "unchanged-span claim must survive an LLM omission with its id"


def test_edit_recompile_preserves_stable_id_and_live_graph_refs(vault) -> None:
    # §26.4: an unchanged claim keeps its STABLE ID across a re-compile (the early
    # exit used to lose it → publish gate retired it → new id won); and the graph
    # cites only live spans after stale-span cleanup.
    assert compile_mod.compile_source_l2(vault, _UnitsClient(), 1).ok
    before = {u["id"] for u in db.list_serving_units(vault.state_db)}
    assert len(before) == 1
    with db.connect(vault.state_db) as conn:
        conn.execute("UPDATE sources SET content_hash = 'edited-v2' WHERE id = 1")
    assert compile_mod.compile_source_l2(vault, _UnitsClient(), 1).ok
    after = {u["id"] for u in db.list_serving_units(vault.state_db)}
    assert after == before, "unchanged claim must keep its stable id (§26.4)"
    with db.connect(vault.state_db) as conn:
        live_spans = {r[0] for r in conn.execute("SELECT id FROM source_spans").fetchall()}
        refs = [
            s for (j,) in conn.execute("SELECT source_span_ids FROM graph_entities").fetchall()
            for s in json.loads(j or "[]")
        ]
    assert all(s in live_spans for s in refs), "dangling graph span ref after edit"


def test_publish_failure_rolls_back_persisted_graph(vault, monkeypatch) -> None:
    # The graph is persisted INSIDE the publish transaction, so a flip failure
    # rolls the graph back too — no leaked graph from a failed compile.
    def _boom(*a, **k):
        raise RuntimeError("flip failed")

    monkeypatch.setattr(compile_mod.db, "publish_compiler_generation", _boom)
    result = compile_mod.compile_source_l2(vault, _UnitsClient(), 1)  # first compile, no prior
    assert not result.ok
    with db.connect(vault.state_db) as conn:
        n_ent = conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
    assert n_ent == 0  # graph rolled back with the failed publish (no leak)


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


def test_post_publish_projection_failure_recovers_without_new_generation_or_llm(
    vault,
    monkeypatch,
) -> None:
    original_write_text = Path.write_text
    failed = False

    def _fail_first_atom_write(path, *args, **kwargs):
        nonlocal failed
        if path.parent == vault.atoms and not failed:
            failed = True
            raise OSError("projection write failed")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _fail_first_atom_write)
    first = compile_mod.compile_source_l2(vault, _UnitsClient(), 1)
    assert not first.ok
    generation = db.get_authoritative_generation(vault.state_db, 1)
    assert generation is not None
    with db.connect(vault.state_db) as conn:
        source = conn.execute(
            "SELECT l2_status, layer_error FROM sources WHERE id = 1"
        ).fetchone()
        atom_id = conn.execute(
            "SELECT atom_node_id FROM knowledge_units WHERE generation_id = ?",
            (generation["id"],),
        ).fetchone()[0]
    assert source["l2_status"] == "error"
    assert str(source["layer_error"]).startswith("post-publish projection failed:")
    assert atom_id

    second = compile_mod.compile_source_l2(vault, _NoCallClient(), 1)

    assert second.ok, second.error
    assert db.get_authoritative_generation(vault.state_db, 1)["id"] == generation["id"]
    assert (vault.atoms / f"{atom_id}.md").exists()
    assert db.get_search_document(
        vault.state_db,
        f"DOC-knowledge_unit-{second.knowledge_unit_ids[0]}",
    )


def test_interrupted_post_publish_projection_recovers_without_llm(
    vault,
    monkeypatch,
) -> None:
    original_finalize = compile_mod._finalize_published_source

    def _interrupt_after_publish(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        compile_mod,
        "_finalize_published_source",
        _interrupt_after_publish,
    )
    with pytest.raises(KeyboardInterrupt):
        compile_mod.compile_source_l2(vault, _UnitsClient(), 1)

    generation = db.get_authoritative_generation(vault.state_db, 1)
    assert generation is not None
    with db.connect(vault.state_db) as conn:
        source = conn.execute(
            "SELECT l2_status, layer_error FROM sources WHERE id = 1"
        ).fetchone()
    assert source["l2_status"] == "running"
    assert source["layer_error"] == "post-publish projection pending"

    monkeypatch.setattr(
        compile_mod,
        "_finalize_published_source",
        original_finalize,
    )
    recovered = compile_mod.compile_source_l2(vault, _NoCallClient(), 1)

    assert recovered.ok, recovered.error
    assert db.get_authoritative_generation(vault.state_db, 1)["id"] == generation["id"]
    assert recovered.atom_ids
    assert (vault.atoms / f"{recovered.atom_ids[0]}.md").exists()


def test_crash_recovery_between_interrupt_and_retry_preserves_the_projection_marker(
    vault,
    monkeypatch,
) -> None:
    """The B3 hard condition: `recover_stale_jobs` must run BETWEEN the two.

    A real crash does not politely leave the process alive to retry. The worker
    dies, something restarts it, and `recover_stale_jobs` runs first to return
    interrupted jobs to the queue. That reset used to `SET layer_error = NULL`
    unconditionally — erasing the post-publish projection marker that
    `compile_source_l2` reads to take the recovery path. With the marker gone,
    the retry re-runs the full LLM extraction against a generation that was
    already published.

    Asserted here: the generation id is unchanged and the LLM client is never
    called, with recovery interposed exactly where the crash would put it.
    """
    # The worker claims a job before compiling; `recover_stale_jobs` keys off
    # that row, so a faithful crash simulation has to create it.
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "INSERT INTO ingest_jobs (source_id, job_type, state, phase, created_at) "
            "VALUES (1, 'l2_atoms', 'running', 'extracting', '2026-08-06T00:00:00Z')"
        )

    original_finalize = compile_mod._finalize_published_source

    def _interrupt_after_publish(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        compile_mod, "_finalize_published_source", _interrupt_after_publish
    )
    with pytest.raises(KeyboardInterrupt):
        compile_mod.compile_source_l2(vault, _UnitsClient(), 1)

    generation = db.get_authoritative_generation(vault.state_db, 1)
    assert generation is not None

    # --- the restart: exactly what a supervisor does before the retry ---
    db.recover_stale_jobs(vault.state_db)

    with db.connect(vault.state_db) as conn:
        source = conn.execute(
            "SELECT l2_status, layer_error FROM sources WHERE id = 1"
        ).fetchone()
    # §4.1 still requires the running -> pending reset...
    assert source["l2_status"] == "pending"
    # ...but the control-flow marker must survive it.
    assert source["layer_error"] == "post-publish projection pending"

    monkeypatch.setattr(
        compile_mod, "_finalize_published_source", original_finalize
    )
    recovered = compile_mod.compile_source_l2(vault, _NoCallClient(), 1)

    assert recovered.ok, recovered.error
    assert db.get_authoritative_generation(vault.state_db, 1)["id"] == generation["id"]
    assert recovered.atom_ids


def test_crash_recovery_still_clears_an_ordinary_stale_error(vault) -> None:
    """The marker is preserved; a plain human error message is not.

    Without this the CASE expression could be written to preserve everything,
    which would leave a stale failure message attached to a source that is about
    to be recompiled from scratch.
    """
    with db.connect(vault.state_db) as conn:
        conn.execute(
            "UPDATE sources SET l2_status = 'running', layer_error = ? WHERE id = 1",
            ("provider timed out after 120s",),
        )
        conn.execute(
            "INSERT INTO ingest_jobs (source_id, job_type, state, phase, created_at) "
            "VALUES (1, 'l2_atoms', 'running', 'extracting', '2026-08-06T00:00:00Z')"
        )

    db.recover_stale_jobs(vault.state_db)

    with db.connect(vault.state_db) as conn:
        source = conn.execute(
            "SELECT l2_status, layer_error FROM sources WHERE id = 1"
        ).fetchone()
    assert source["l2_status"] == "pending"
    assert source["layer_error"] is None
