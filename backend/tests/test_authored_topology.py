"""v0.39 authored-note topology contracts (Failure Atlas F9).

These tests pin deterministic parsing/resolution, production publication,
edge-class lifecycle, source reconciliation, replica identity, and the boundary
between structural topology and extracted factual report support.
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db
from curator import ingest_raw
from curator.llm import ChatMessage
from curator.pipeline import compile as compile_mod
from curator.pipeline import memory_paths
from curator.retrieval.router import graph_status


class _EmptyUnitsClient:
    model = "fake"

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        return json.dumps({"units": []})


class _GraphFailClient:
    """Create one valid staged claim, then fail graph extraction."""

    model = "fake"

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        text = "\n".join(message.content for message in messages)
        span_ids = re.findall(r"SPAN-[0-9a-f]{8}", text)
        first = span_ids[0] if span_ids else "SPAN-00000000"
        if "Extract the knowledge units" in text:
            return json.dumps(
                {
                    "units": [
                        {
                            "canonical_name": "A staged claim",
                            "unit_type": "claim",
                            "statement": "A staged claim is grounded.",
                            "source_span_ids": [first],
                            "confidence": 0.9,
                            "truth_status": "source_supported",
                        }
                    ]
                }
            )
        if "Extract entities and relations" in text:
            return "not valid graph json"
        return "{}"


def _init_paths(root: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(root)
    paths.internal.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    return paths


def _seed_source(
    paths: cfg.WikiPaths,
    text: str,
    *,
    relpath: str = "03_Notes/Source.md",
    content_hash: str = "source-v1",
) -> int:
    path = paths.root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    with db.connect(paths.state_db) as conn:
        cur = conn.execute(
            "INSERT INTO sources "
            "(relpath, content_hash, file_type, bytes, added_at, l1_status) "
            "VALUES (?, ?, 'md', ?, datetime('now'), 'done')",
            (relpath, content_hash, len(text.encode("utf-8"))),
        )
        return int(cur.lastrowid)


def _write_target(paths: cfg.WikiPaths, relpath: str, text: str = "# Target\n") -> None:
    path = paths.root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _authored_rows(paths: cfg.WikiPaths, *, include_retired: bool = True) -> list[dict]:
    where = "edge_class = 'authored'"
    if not include_retired:
        where += " AND lifecycle_status != 'retired'"
    with db.connect(paths.state_db) as conn:
        return [
            dict(row)
            for row in conn.execute(
                f"SELECT * FROM graph_relations WHERE {where} ORDER BY id"
            ).fetchall()
        ]


def _extractor_module():
    return importlib.import_module("curator.pipeline.authored_topology")


def test_extracts_closed_obsidian_syntax_without_presentation_fragments(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_text = """\
---
tags: [ml, nested/topic]
aliases: [Source Alias]
related:
  - "[[03_Notes/Target#Section|Displayed]]"
---
# Source

[[Target#Section|Alias]]
![[assets/plot.png|300]]
[Other](other.md#part)
![Plot](assets/plot.png)
#body/tag

`[[Ignored]]`
%% [[Ignored]] %%
```md
[[Ignored]]
```
"""
    source_relpath = "03_Notes/Source.md"
    _write_target(paths, source_relpath, source_text)
    _write_target(paths, "03_Notes/Target.md")
    _write_target(paths, "03_Notes/other.md")
    _write_target(paths, "03_Notes/Ignored.md")
    _write_target(paths, "03_Notes/assets/plot.png", "PNG")

    topology = _extractor_module().extract_authored_topology(
        paths.root, source_relpath, source_text
    )
    observed = {
        (relation.relation_type, relation.target.entity_type, relation.target.canonical_key)
        for relation in topology.relations
    }

    assert observed == {
        ("links_to", "vault_note", "03_Notes/Target.md"),
        ("links_to", "vault_note", "03_Notes/other.md"),
        ("embeds", "vault_asset", "03_Notes/assets/plot.png"),
        ("tagged_with", "tag", "ml"),
        ("tagged_with", "tag", "nested/topic"),
        ("tagged_with", "tag", "body/tag"),
        ("property_ref", "vault_note", "03_Notes/Target.md"),
    }
    assert all("Ignored" not in relation.target.canonical_key for relation in topology.relations)


def test_resolution_fails_closed_for_ambiguity_external_hidden_and_traversal(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_relpath = "03_Notes/Source.md"
    source_text = """\
# Source

[[Dupe]]
[[../../outside]]
[[.secret/Hidden]]
[[.curator/Collections/X]]
[Web](https://example.com)
"""
    _write_target(paths, source_relpath, source_text)
    _write_target(paths, "a/Dupe.md")
    _write_target(paths, "b/Dupe.md")
    _write_target(paths, ".secret/Hidden.md")
    _write_target(paths, ".curator/Collections/X.md")

    topology = _extractor_module().extract_authored_topology(
        paths.root, source_relpath, source_text
    )
    assert topology.relations == ()


def test_real_compile_publishes_active_authored_edges_without_factual_support(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(paths, "# Source\n\n[[Target]] #topic\n")
    _write_target(paths, "03_Notes/Target.md")

    result = compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id)
    assert result.ok, result.error
    rows = _authored_rows(paths, include_retired=False)
    assert {(row["relation_type"], row["lifecycle_status"]) for row in rows} == {
        ("links_to", "active"),
        ("tagged_with", "active"),
    }
    assert all(row["assertion_source"] == "source_states" for row in rows)
    assert all(row["generation_id"] for row in rows)
    assert all(float(row["topology_weight"]) == 1.0 for row in rows)

    with db.connect(paths.state_db) as conn:
        support_count = conn.execute(
            "SELECT COUNT(*) FROM graph_relation_supports"
        ).fetchone()[0]
    assert support_count == 0
    assert db.graph_audit(paths.state_db) == []


def test_rebuild_edit_failure_rename_and_delete_reconcile_source_owned_edges(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(paths, "# Source\n\n[[Target]]\n")
    _write_target(paths, "03_Notes/Target.md")
    _write_target(paths, "03_Notes/Other.md")
    client = _EmptyUnitsClient()

    assert compile_mod.compile_source_l2(paths, client, source_id).ok
    first = _authored_rows(paths, include_retired=False)
    assert len(first) == 1
    first_id = first[0]["id"]

    assert compile_mod.compile_source_l2(paths, client, source_id).ok
    unchanged = _authored_rows(paths, include_retired=False)
    assert [row["id"] for row in unchanged] == [first_id]

    source_path = paths.root / "03_Notes/Source.md"
    source_path.write_text("# Source\n\n[[Other]]\n", encoding="utf-8")
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET content_hash = 'source-v2' WHERE id = ?",
            (source_id,),
        )
    assert compile_mod.compile_source_l2(paths, client, source_id).ok
    active_after_edit = _authored_rows(paths, include_retired=False)
    assert len(active_after_edit) == 1
    assert active_after_edit[0]["id"] != first_id
    with db.connect(paths.state_db) as conn:
        assert conn.execute(
            "SELECT lifecycle_status FROM graph_relations WHERE id = ?",
            (first_id,),
        ).fetchone()[0] == "retired"

    prior_id = active_after_edit[0]["id"]
    source_path.write_text("# Source\n\n[[Target]]\n", encoding="utf-8")
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET content_hash = 'source-v3' WHERE id = ?",
            (source_id,),
        )
    failed = compile_mod.compile_source_l2(paths, _GraphFailClient(), source_id)
    assert not failed.ok
    assert [row["id"] for row in _authored_rows(paths, include_retired=False)] == [
        prior_id
    ]

    renamed_relpath = "03_Notes/Renamed.md"
    renamed_path = paths.root / renamed_relpath
    source_path.rename(renamed_path)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET relpath = ?, content_hash = 'source-v4' WHERE id = ?",
            (renamed_relpath, source_id),
        )
    assert compile_mod.compile_source_l2(paths, client, source_id).ok
    after_rename = _authored_rows(paths, include_retired=False)
    assert len(after_rename) == 1
    assert after_rename[0]["id"] not in {first_id, prior_id}

    removed, _message = ingest_raw.remove_source(paths, source_id)
    assert removed
    assert _authored_rows(paths, include_retired=False) == []
    assert all(
        row["lifecycle_status"] == "retired"
        for row in _authored_rows(paths, include_retired=True)
    )


def test_same_structure_uses_same_ids_on_independent_replicas(tmp_path: Path) -> None:
    snapshots: list[tuple[list[str], list[str]]] = []
    for replica in ("one", "two"):
        paths = _init_paths(tmp_path / replica)
        source_id = _seed_source(paths, "# Source\n\n[[Target]] #topic\n")
        _write_target(paths, "03_Notes/Target.md")
        assert compile_mod.compile_source_l2(
            paths, _EmptyUnitsClient(), source_id
        ).ok
        with db.connect(paths.state_db) as conn:
            entity_ids = [
                str(row[0])
                for row in conn.execute(
                    "SELECT id FROM graph_entities "
                    "WHERE entity_type IN ('vault_note', 'vault_asset', 'tag') "
                    "ORDER BY id"
                ).fetchall()
            ]
            relation_ids = [
                str(row[0])
                for row in conn.execute(
                    "SELECT id FROM graph_relations "
                    "WHERE edge_class = 'authored' ORDER BY id"
                ).fetchall()
            ]
        assert entity_ids
        assert relation_ids
        snapshots.append((entity_ids, relation_ids))
    assert snapshots[0] == snapshots[1]


def test_authoritative_traversal_uses_active_relations_only(tmp_path: Path) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(paths, "# Source\n\n[[Target]]\n")
    _write_target(paths, "03_Notes/Target.md")
    assert compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id).ok
    authored = _authored_rows(paths, include_retired=False)[0]

    extra = db.upsert_graph_entity(
        paths.state_db, canonical_name="Extra", entity_type="concept"
    )
    provisional = db.upsert_graph_relation(
        paths.state_db,
        source_entity_id=authored["source_entity_id"],
        target_entity_id=extra,
        relation_type="provisional",
    )

    active = db.relation_neighborhood(
        paths.state_db,
        [authored["source_entity_id"]],
        lifecycle_status="active",
    )
    assert {row["id"] for row in active} == {authored["id"]}
    inspected = db.relation_neighborhood(
        paths.state_db,
        [authored["source_entity_id"]],
        lifecycle_status=None,
    )
    assert {row["id"] for row in inspected} == {authored["id"], provisional}

    paths_found = memory_paths.build_memory_paths(
        paths.state_db,
        seed_entity_ids=[authored["source_entity_id"]],
        max_depth=1,
    )
    assert {hop["relation_id"] for path in paths_found for hop in path.hops} == {
        authored["id"]
    }
    assert graph_status(paths.state_db).has_relations

    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE graph_relations SET lifecycle_status = 'retired' "
            "WHERE edge_class = 'authored'"
        )
    assert not graph_status(paths.state_db).has_relations


def test_authored_edges_shape_membership_but_not_report_factual_support(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(paths, "# Source\n\n[[Target]]\n")
    _write_target(paths, "03_Notes/Target.md")
    assert compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id).ok
    authored = _authored_rows(paths, include_retired=False)[0]

    target_id = authored["target_entity_id"]
    extracted_target = db.upsert_graph_entity(
        paths.state_db, canonical_name="Extracted", entity_type="concept"
    )
    extracted = db.upsert_graph_relation(
        paths.state_db,
        source_entity_id=target_id,
        target_entity_id=extracted_target,
        relation_type="supports",
        confidence=0.9,
    )
    with db.connect(paths.state_db) as conn:
        for index in (1, 2):
            conn.execute(
                "INSERT INTO graph_relation_supports "
                "(relation_id, knowledge_unit_id, source_span_ids, assertion_source, "
                "confidence, support_status, support_hash, source_lineage_hash, "
                "created_at, updated_at) "
                "VALUES (?, ?, '[]', 'source_states', 0.9, 'verified', ?, ?, 't', 't')",
                (
                    extracted,
                    f"KNU-support-{index}",
                    f"support-{index}",
                    f"lineage-{index}",
                ),
            )

    db.rebuild_graph_generation(paths.state_db)
    reports = [
        report
        for report in db.list_community_reports(paths.state_db)
        if not report.get("retired_at")
    ]
    assert len(reports) == 1
    assert reports[0]["relation_ids"] == [extracted]
    assert set(reports[0]["entity_ids"]) == {
        authored["source_entity_id"],
        target_id,
        extracted_target,
    }
    assert authored["id"] not in reports[0]["relation_ids"]

    with db.connect(paths.state_db) as conn:
        dependency_ids = {
            str(row[0])
            for row in conn.execute(
                "SELECT depends_on_id FROM artifact_dependencies "
                "WHERE artifact_id = ? AND depends_on_type = 'relation'",
                (reports[0]["id"],),
            ).fetchall()
        }
    assert dependency_ids == {authored["id"], extracted}
