"""Phase 4 (v0.3.1): LLM knowledge-unit extraction into the DB."""

from __future__ import annotations

import dataclasses
import json
import tempfile
from pathlib import Path

import pytest

from curator import db, prompting
from curator.llm import ChatMessage
from curator.pipeline import knowledge_units as ku
from curator.pipeline import source_spans as ss


class FakeClient:
    def __init__(
        self,
        responses: list[str | Exception],
        model: str = "fake",
        optimal_chars: int = 60000,
    ) -> None:
        self._responses = list(responses)
        self._optimal_chars = optimal_chars
        self.model = model
        self.calls = 0

    def optimal_chunk_chars(self) -> int:
        return self._optimal_chars

    def chat(self, messages: list[ChatMessage], *, json_mode=False, temperature=0.3) -> str:
        self.calls += 1
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        dbp = Path(t) / "state.sqlite"
        db.init_db(dbp)
        with db.connect(dbp) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                ("04_Resources/resnet.md", "h", "md", 1),
            )
        spans = ss.spans_from_sections(
            [{
                "id": "s1",
                "title": "Intro",
                "page": 1,
                "text": "Residual connections ease optimization and enable very deep nets.",
            }]
        )
        ids = ss.store_source_spans(dbp, 1, "04_Resources/resnet.md", spans)
        # Pair stored ids with full text for the extractor.
        span_inputs = [
            {"id": ids[i], "text": spans[i].text, "section_title": spans[i].section_title}
            for i in range(len(ids))
        ]
        yield dbp, span_inputs


def _units_json(span_id: str) -> str:
    return json.dumps(
        {
            "units": [
                {
                    "canonical_name": "Residual learning eases optimization",
                    "unit_type": "claim",
                    "statement": "Residual connections make deep nets easier to optimize.",
                    "source_span_ids": [span_id],
                    "confidence": 0.9,
                    "truth_status": "source_supported",
                }
            ]
        }
    )


def _add_span(dbp: Path, text: str, title: str) -> dict:
    spans = ss.spans_from_sections(
        [{"id": title.lower(), "title": title, "page": 1, "text": text}]
    )
    ids = ss.store_source_spans(dbp, 1, "04_Resources/resnet.md", spans)
    return {"id": ids[0], "text": spans[0].text, "section_title": spans[0].section_title}


def test_extract_persists_units(vault) -> None:
    dbp, spans = vault
    client = FakeClient([_units_json(spans[0]["id"])])
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert result.ok
    assert len(result.unit_ids) == 1
    units = db.list_knowledge_units_for_source(dbp, 1)
    assert len(units) == 1
    assert units[0]["truth_status"] == "source_supported"
    assert units[0]["source_span_ids"] == [spans[0]["id"]]
    assert units[0]["prompt_run_id"] == result.trace_id
    supports = db.list_claim_supports(dbp, units[0]["id"])
    assert len(supports) == 1
    assert supports[0]["source_span_id"] == spans[0]["id"]
    assert supports[0]["support_role"] == "primary"
    assert supports[0]["support_status"] == "unchecked"


def test_invented_span_rejected_and_not_persisted(vault) -> None:
    dbp, spans = vault
    bad = _units_json("SPAN-invented")
    client = FakeClient([bad, bad])  # repair also bad
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert not result.ok
    assert result.errors
    # No partial artifact written.
    assert db.list_knowledge_units_for_source(dbp, 1) == []


def test_failed_late_batch_publishes_nothing(vault) -> None:
    """A late failure publishes nothing. Since v0.62.0 the earlier batches are
    still *persisted* — unpublished, `generation_id IS NULL` — so a re-run can
    adopt them. The guarantee that matters is that none of them is authoritative.
    """
    dbp, spans = vault
    spans.append(_add_span(dbp, "Batch two content is intentionally unrecoverable.", "Second"))
    client = FakeClient(
        [_units_json(spans[0]["id"]), "not json", "still not json"],
        optimal_chars=160,
    )
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert not result.ok
    assert result.errors
    units = db.list_knowledge_units_for_source(dbp, 1)
    assert units, "the batch that succeeded should have been kept for a resume"
    assert all(u["generation_id"] is None for u in units), (
        "a failed extraction published units"
    )


def test_property_chunk_budget_is_respected(vault) -> None:
    dbp, spans = vault
    spans.append(_add_span(dbp, "Batch two content should be extracted separately.", "Second"))

    class PropertyChunkClient(FakeClient):
        @property
        def optimal_chunk_chars(self) -> int:
            return 160

    client = PropertyChunkClient([_units_json(spans[0]["id"]), _units_json(spans[1]["id"])])
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )

    assert result.ok, result.errors
    assert client.calls == 2
    assert len(db.list_knowledge_units_for_source(dbp, 1)) == 2


def test_provider_exception_leaves_no_partial_units(vault) -> None:
    dbp, spans = vault
    spans.append(_add_span(dbp, "The provider fails on the second batch.", "Second"))
    spans.append(_add_span(dbp, "This later batch must not be called.", "Third"))
    client = FakeClient(
        [
            _units_json(spans[0]["id"]),
            RuntimeError("capacity exhausted"),
            _units_json(spans[2]["id"]),
        ],
        optimal_chars=160,
    )
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert not result.ok
    assert "capacity exhausted" in result.errors[0]
    assert client.calls == 2
    # The first batch survives for a resume; nothing is published (v0.62.0).
    assert all(
        u["generation_id"] is None for u in db.list_knowledge_units_for_source(dbp, 1)
    )
    with db.connect(dbp) as conn:
        statuses = [
            row[0]
            for row in conn.execute(
                "SELECT validator_status FROM prompt_runs ORDER BY created_at"
            )
        ]
    assert statuses == ["ok", "failed"]


def test_extraction_discards_previous_unpublished_units(vault) -> None:
    dbp, spans = vault
    stale_id = db.upsert_knowledge_unit(
        dbp,
        unit_type="claim",
        canonical_name="Stale failed-run unit",
        statement="A failed extraction previously wrote this unpublished unit.",
        source_span_ids=[spans[0]["id"]],
        source_id=1,
        confidence=0.1,
        truth_status="source_supported",
    )
    assert db.list_knowledge_units_for_source(dbp, 1)[0]["id"] == stale_id

    client = FakeClient([_units_json(spans[0]["id"])])
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert result.ok
    units = db.list_knowledge_units_for_source(dbp, 1)
    assert [unit["id"] for unit in units] == result.unit_ids
    assert stale_id not in result.unit_ids


def test_extraction_preserves_retired_unpublished_units(vault) -> None:
    dbp, spans = vault
    retired_id = db.upsert_knowledge_unit(
        dbp,
        unit_type="claim",
        canonical_name="Retired unpublished unit",
        statement="A retired generation-less unit remains audit history.",
        source_span_ids=[spans[0]["id"]],
        source_id=1,
        confidence=0.1,
        truth_status="source_supported",
    )
    db.retire_knowledge_unit(dbp, retired_id)

    client = FakeClient([_units_json(spans[0]["id"])])
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert result.ok
    units = db.list_knowledge_units_for_source(dbp, 1)
    assert retired_id in {unit["id"] for unit in units}
    assert retired_id not in result.unit_ids


def test_failed_combined_batch_retries_smaller_batches(vault) -> None:
    dbp, spans = vault
    spans.append(_add_span(dbp, "Residual blocks can be stacked deeply.", "Depth"))
    client = FakeClient(
        [
            "not json",
            "still not json",
            _units_json(spans[0]["id"]),
            _units_json(spans[1]["id"]),
        ],
        optimal_chars=60000,
    )
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert result.ok, result.errors
    assert client.calls == 4
    units = db.list_knowledge_units_for_source(dbp, 1)
    assert len(units) == 2
    assert {tuple(unit["source_span_ids"]) for unit in units} == {
        (spans[0]["id"],),
        (spans[1]["id"],),
    }


def test_failed_left_retry_slice_skips_right_slice(vault) -> None:
    dbp, spans = vault
    spans.append(_add_span(dbp, "Right slice would succeed but should not run.", "Depth"))
    client = FakeClient(
        ["not json", "still not json", "left not json", "left still not json"],
        optimal_chars=60000,
    )
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert not result.ok
    assert result.errors
    assert client.calls == 4
    assert db.list_knowledge_units_for_source(dbp, 1) == []


def test_split_batch_for_retry_empty_batch_is_noop() -> None:
    assert ku._split_batch_for_retry([]) is None


def test_empty_spans_is_noop(vault) -> None:
    dbp, _ = vault
    client = FakeClient([])
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=[]
    )
    assert result.ok
    assert result.unit_ids == []


def test_chunking_large_span_is_split(vault) -> None:
    dbp, spans = vault
    huge_text = "A" * 60000
    spans[0]["text"] = huge_text
    span_id = spans[0]["id"]

    class SmallChunkClient:
        def optimal_chunk_chars(self) -> int:
            return 20000

        def chat(self, messages, **kwargs):
            return _units_json(span_id)

    client = SmallChunkClient()
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=spans
    )
    assert result.ok, result.errors

    units = db.list_knowledge_units_for_source(dbp, 1)
    assert len(units) > 1
    for u in units:
        assert u["source_span_ids"] == [span_id]



def test_a_batch_that_never_succeeded_persists_nothing(vault) -> None:
    """Only a *validated* batch is persisted. This fixture has one batch and it
    raises, so there is nothing to keep — resumability does not mean storing
    output that never passed validation.
    """
    dbp, spans = vault

    # One response, because a raised exception is not retried — retry/split
    # applies to validation failures, not to a provider that errors out.
    failing = FakeClient([RuntimeError("provider died")])
    first = ku.extract_knowledge_units(
        dbp, failing, source_id=1, source_title="ResNet", spans=spans
    )
    assert first.ok is False
    assert failing.calls == 1
    with db.connect(dbp) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM knowledge_units WHERE source_id = 1"
        ).fetchone()[0] == 0, "a failed extraction left units behind"


def test_a_late_batch_failure_keeps_the_earlier_batches(vault) -> None:
    """The scenario resumable L2 exists for: batch N of many fails.

    This test used to assert the opposite — that batches 1..N-1 were discarded —
    and said so explicitly: "pins it so a future per-batch persistence change has
    to face the guarantee it breaks". v0.62.0 is that change. The guarantee it
    actually protected was that nothing partial is *published*, and that is what
    the assertion now checks; the earlier batches are kept, unpublished.
    """
    dbp, spans = vault
    extra = _add_span(dbp, "Bottleneck blocks cut compute per layer.", "Design")
    both = [*spans, extra]

    # Small chunk budget forces more than one batch.
    client = FakeClient(
        [_units_json(spans[0]["id"]), RuntimeError("died on the second batch")],
        optimal_chars=80,
    )
    result = ku.extract_knowledge_units(
        dbp, client, source_id=1, source_title="ResNet", spans=both
    )

    assert result.ok is False
    assert client.calls >= 2, "the fixture did not actually produce two batches"
    with db.connect(dbp) as conn:
        kept, published = conn.execute(
            "SELECT COUNT(*), COUNT(generation_id) FROM knowledge_units "
            "WHERE source_id = 1"
        ).fetchone()
    assert kept > 0, "the successful batch was discarded; a resume has nothing to adopt"
    assert published == 0, "a failed extraction published units"


# --- v0.62.0: resumable L2 extraction (SYSTEM_BEHAVIOR L2 item 4) -------------


def _published(dbp: Path, source_id: int = 1) -> list[dict]:
    return [
        u for u in db.list_knowledge_units_for_source(dbp, source_id)
        if u["generation_id"] is not None
    ]


def _stamp_generation(dbp: Path, unit_ids: list[str], gen_id: str = "GEN-test") -> None:
    """Stand in for what compile.py does immediately after extraction returns."""
    with db.connect(dbp) as conn:
        for uid in unit_ids:
            conn.execute(
                "UPDATE knowledge_units SET generation_id = ? WHERE id = ?", (gen_id, uid)
            )


def _two_batch_fixture(dbp: Path, spans: list[dict]) -> list[dict]:
    return [*spans, _add_span(dbp, "Bottleneck blocks cut compute per layer.", "Design")]


class InterruptingClient(FakeClient):
    """Raises KeyboardInterrupt on the Nth call.

    KeyboardInterrupt, not Exception, and deliberately: `_run_batch_with_retry`
    catches `Exception`, so an ordinary error is absorbed into an error result
    and the run finishes tidily. A resume test built on that would pass against
    code that never resumes — which is exactly how an earlier vision-resume test
    passed against unfixed code.
    """

    def __init__(self, responses, *, interrupt_on: int, **kw) -> None:
        super().__init__(responses, **kw)
        self._interrupt_on = interrupt_on

    def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
        if self.calls + 1 == self._interrupt_on:
            self.calls += 1
            raise KeyboardInterrupt("user stopped the build")
        return super().chat(messages, json_mode=json_mode, temperature=temperature)


def _unit_content(dbp: Path, source_id: int = 1) -> list[tuple[str, str]]:
    return sorted(
        (u["canonical_name"], u["statement"])
        for u in db.list_knowledge_units_for_source(dbp, source_id)
    )


def _clean_vault(root: Path, model_spans: list[dict]) -> tuple[Path, list[dict]]:
    """A second vault holding the same span TEXTS as `model_spans`."""
    dbp = root / "state.sqlite"
    db.init_db(dbp)
    with db.connect(dbp) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("04_Resources/resnet.md", "h", "md", 1),
        )
    out: list[dict] = []
    for s in model_spans:
        recs = ss.spans_from_sections(
            [{"id": s["section_title"].lower(), "title": s["section_title"],
              "page": 1, "text": s["text"]}]
        )
        ids = ss.store_source_spans(dbp, 1, "04_Resources/resnet.md", recs)
        out.append({"id": ids[0], "text": recs[0].text,
                    "section_title": recs[0].section_title})
    return dbp, out


def _relabel(responses: list[str], old_spans: list[dict], new_spans: list[dict]) -> list[str]:
    """Point canned responses at the second vault's span ids."""
    mapping = {o["id"]: n["id"] for o, n in zip(old_spans, new_spans)}
    out = []
    for r in responses:
        for old_id, new_id in mapping.items():
            r = r.replace(old_id, new_id)
        out.append(r)
    return out


def test_a_resumed_run_only_calls_for_the_batch_that_did_not_finish(vault) -> None:
    """The whole point: batch 1 is not re-paid."""
    dbp, spans = vault
    both = _two_batch_fixture(dbp, spans)

    first = InterruptingClient(
        [_units_json(both[0]["id"])], interrupt_on=2, optimal_chars=160
    )
    with pytest.raises(KeyboardInterrupt):
        ku.extract_knowledge_units(
            dbp, first, source_id=1, source_title="ResNet", spans=both
        )
    assert first.calls == 2
    kept = db.list_knowledge_units_for_source(dbp, 1)
    assert kept, "batch 1 was lost, so there is nothing to resume from"

    second = FakeClient([_units_json(both[1]["id"])], optimal_chars=160)
    result = ku.extract_knowledge_units(
        dbp, second, source_id=1, source_title="ResNet", spans=both
    )
    assert result.ok, result.errors
    assert second.calls == 1, (
        f"the resumed run made {second.calls} calls; batch 1 should have been adopted"
    )
    assert len(result.unit_ids) == 2, "the adopted batch is missing from the result"


def test_a_resumed_run_yields_the_same_units_as_an_uninterrupted_one(vault) -> None:
    dbp, spans = vault
    both = _two_batch_fixture(dbp, spans)
    responses = [_units_json(both[0]["id"]), _units_json(both[1]["id"])]

    interrupted = InterruptingClient(list(responses), interrupt_on=2, optimal_chars=160)
    with pytest.raises(KeyboardInterrupt):
        ku.extract_knowledge_units(
            dbp, interrupted, source_id=1, source_title="ResNet", spans=both
        )
    resumed = ku.extract_knowledge_units(
        dbp, FakeClient([responses[1]], optimal_chars=160),
        source_id=1, source_title="ResNet", spans=both,
    )
    assert resumed.ok, resumed.errors
    resumed_units = _unit_content(dbp)

    # A clean vault, same span texts, same responses, no interruption. Span ids
    # are minted per (source_id, content_hash) row, so the second vault's ids
    # differ; the units are compared by content, which is what "the same units"
    # means here. Span linkage is pinned by test_extract_persists_units.
    with tempfile.TemporaryDirectory() as tmp:
        clean_dbp, clean_spans = _clean_vault(Path(tmp), both)
        clean = ku.extract_knowledge_units(
            clean_dbp, FakeClient(_relabel(responses, both, clean_spans), optimal_chars=160),
            source_id=1, source_title="ResNet", spans=clean_spans,
        )
        assert clean.ok, clean.errors
        clean_units = _unit_content(clean_dbp)
        assert len(resumed.unit_ids) == len(clean.unit_ids)
    assert resumed_units == clean_units


def test_a_changed_prompt_template_re_runs_every_batch(vault, monkeypatch) -> None:
    """`input_hash` covers the rendered prompt, so a template edit invalidates
    every batch by construction — no separate configuration key exists."""
    dbp, spans = vault
    both = _two_batch_fixture(dbp, spans)
    responses = [_units_json(both[0]["id"]), _units_json(both[1]["id"])]

    first = InterruptingClient(list(responses), interrupt_on=2, optimal_chars=160)
    with pytest.raises(KeyboardInterrupt):
        ku.extract_knowledge_units(
            dbp, first, source_id=1, source_title="ResNet", spans=both
        )
    assert db.list_knowledge_units_for_source(dbp, 1)

    # PromptContract is frozen, so the edited contract is swapped in at the
    # registry rather than mutated in place.
    contract = prompting.REGISTRY.get("curator.knowledge_unit_extract")
    edited = dataclasses.replace(
        contract, system_template=contract.system_template + "\n\nAn added instruction."
    )
    monkeypatch.setattr(
        prompting.REGISTRY, "get",
        lambda pid: edited if pid == "curator.knowledge_unit_extract" else contract,
    )

    second = FakeClient(list(responses), optimal_chars=160)
    result = ku.extract_knowledge_units(
        dbp, second, source_id=1, source_title="ResNet", spans=both
    )
    assert result.ok, result.errors
    assert second.calls == 2, "a changed template must not adopt the old batch"


def test_an_already_published_source_is_not_resumed(vault) -> None:
    """Published units belong to the authoritative generation. Adopting them into
    a new one would attribute another generation's rows to this run.

    This is a GUARD, not a feature test: before resume exists it passes
    vacuously, because nothing is ever adopted. Mutation-checked at P3, with a
    result worth recording — dropping the `generation_id IS NULL` clause from
    `_adoptable_unit_ids` OR from `_adopt_existing_batch` leaves this test green,
    because each gate masks the other. Removing BOTH turns it red. So the test
    pins the property (a published unit is never adopted) but cannot localise
    which gate enforces it; do not read a green run here as either clause being
    individually covered.
    """
    dbp, spans = vault
    both = _two_batch_fixture(dbp, spans)
    responses = [_units_json(both[0]["id"]), _units_json(both[1]["id"])]

    done = ku.extract_knowledge_units(
        dbp, FakeClient(list(responses), optimal_chars=160),
        source_id=1, source_title="ResNet", spans=both,
    )
    assert done.ok, done.errors
    _stamp_generation(dbp, done.unit_ids)
    assert len(_published(dbp)) == len(done.unit_ids)

    again = FakeClient(list(responses), optimal_chars=160)
    result = ku.extract_knowledge_units(
        dbp, again, source_id=1, source_title="ResNet", spans=both
    )
    assert result.ok, result.errors
    assert again.calls == 2, "a published source must be re-extracted in full"
    assert set(result.unit_ids).isdisjoint(set(done.unit_ids)), (
        "the new run adopted the authoritative generation's rows"
    )


def test_discard_keeps_adoptable_units_and_deletes_the_rest(vault) -> None:
    """Conditional discard: rows citing spans that are gone cannot be adopted."""
    dbp, spans = vault
    both = _two_batch_fixture(dbp, spans)

    first = InterruptingClient(
        [_units_json(both[0]["id"])], interrupt_on=2, optimal_chars=160
    )
    with pytest.raises(KeyboardInterrupt):
        ku.extract_knowledge_units(
            dbp, first, source_id=1, source_title="ResNet", spans=both
        )
    kept = db.list_knowledge_units_for_source(dbp, 1)
    assert kept

    # The span basis disappears — the partial can no longer be adopted.
    with db.connect(dbp) as conn:
        conn.execute("DELETE FROM source_spans WHERE id = ?", (both[0]["id"],))

    second = FakeClient(
        [_units_json(both[0]["id"]), _units_json(both[1]["id"])], optimal_chars=160
    )
    result = ku.extract_knowledge_units(
        dbp, second, source_id=1, source_title="ResNet", spans=both
    )
    assert result.ok, result.errors
    assert second.calls == 2, "an unadoptable partial must not be reused"
    stale = [u for u in db.list_knowledge_units_for_source(dbp, 1) if u["id"] in
             {k["id"] for k in kept}]
    assert stale == [], "the unadoptable partial was left behind"
