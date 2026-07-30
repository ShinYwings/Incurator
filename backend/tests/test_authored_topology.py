"""v0.39 authored-note topology contracts (Failure Atlas F9).

These tests pin deterministic parsing/resolution, production publication,
edge-class lifecycle, source reconciliation, replica identity, and the boundary
between structural topology and extracted factual report support.
"""

from __future__ import annotations

import importlib
import json
import unicodedata
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db
from curator import ingest_raw
from curator.db_sync import (
    _reconcile_authoritative_generations,
    _timestamp_key,
    export_knowledge,
    import_knowledge,
)
from curator.llm import ChatMessage
from curator.pipeline import compile as compile_mod
from curator.pipeline import memory_paths
from curator.pipeline.claim_support import run_compiler_audit
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
[[Alternate Name#Alias Heading]]
#Body/Tag

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
    _write_target(
        paths,
        "03_Notes/AliasTarget.md",
        "---\naliases: [Alternate Name]\n---\n# Alias Target\n",
    )
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
        ("links_to", "vault_note", "03_Notes/AliasTarget.md"),
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
    _write_target(paths, "Hidden.md")
    _write_target(paths, "outside.md")

    topology = _extractor_module().extract_authored_topology(
        paths.root, source_relpath, source_text
    )
    assert topology.relations == ()


def test_masking_escapes_and_tags_do_not_invent_authored_topology(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_relpath = "03_Notes/Source.md"
    source_text = """\
[[Tar<!-- hidden -->get]]
#to%% hidden %%pic
\\[[Escaped]]
#123

~~~
[[InsideFence]]
~~~~
[[Visible]]
"""
    _write_target(paths, source_relpath, source_text)
    for name in ("Target", "Escaped", "InsideFence", "Visible"):
        _write_target(paths, f"03_Notes/{name}.md")

    topology = _extractor_module().extract_authored_topology(
        paths.root, source_relpath, source_text
    )

    assert {
        (relation.relation_type, relation.target.canonical_key)
        for relation in topology.relations
    } == {
        ("links_to", "03_Notes/Visible.md"),
        ("tagged_with", "to"),
    }


def test_unclosed_fence_masks_through_end_of_file(tmp_path: Path) -> None:
    paths = _init_paths(tmp_path)
    source_relpath = "03_Notes/Source.md"
    source_text = "~~~md\n[[InsideFence]]\n"
    _write_target(paths, source_relpath, source_text)
    _write_target(paths, "03_Notes/InsideFence.md")

    topology = _extractor_module().extract_authored_topology(
        paths.root, source_relpath, source_text
    )

    assert topology.relations == ()


def test_comment_backticks_do_not_mask_following_visible_syntax(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_relpath = "03_Notes/Source.md"
    source_text = "<!-- ` --> [[Visible]] `\n"
    _write_target(paths, source_relpath, source_text)
    _write_target(paths, "03_Notes/Visible.md")

    topology = _extractor_module().extract_authored_topology(
        paths.root, source_relpath, source_text
    )

    assert [relation.target.canonical_key for relation in topology.relations] == [
        "03_Notes/Visible.md"
    ]


def test_comment_and_fence_precedence_preserves_following_visible_syntax(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_relpath = "03_Notes/Source.md"
    source_text = "<!--\n~~~\n-->\n[[Visible]]\n"
    _write_target(paths, source_relpath, source_text)
    _write_target(paths, "03_Notes/Visible.md")

    topology = _extractor_module().extract_authored_topology(
        paths.root, source_relpath, source_text
    )

    assert [relation.target.canonical_key for relation in topology.relations] == [
        "03_Notes/Visible.md"
    ]


def test_quoted_numeric_frontmatter_tag_is_not_topology(tmp_path: Path) -> None:
    paths = _init_paths(tmp_path)
    source_relpath = "03_Notes/Source.md"
    source_text = "---\ntags: ['123', valid123]\n---\n# Source\n"
    _write_target(paths, source_relpath, source_text)

    topology = _extractor_module().extract_authored_topology(
        paths.root, source_relpath, source_text
    )

    assert [relation.target.canonical_key for relation in topology.relations] == [
        "valid123"
    ]


def test_balanced_parent_relative_markdown_links_and_ambiguity_are_exact(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_relpath = "Folder/Child/Source.markdown"
    source_text = """\
[Balanced](Target_(v2).md)
[EscapedParen](Target_\\(v3\\).md)
[Parent](../Target.md)
[[Dupe]]
"""
    _write_target(paths, source_relpath, source_text)
    _write_target(paths, "Folder/Child/Target_(v2).md")
    _write_target(paths, "Folder/Child/Target_(v3).md")
    _write_target(paths, "Folder/Target.md")
    _write_target(paths, "a/Dupe.md")
    _write_target(paths, "b/Dupe.md")
    _write_target(
        paths,
        "AliasTarget.md",
        "---\naliases: [Dupe]\n---\n# Alias Target\n",
    )

    topology = _extractor_module().extract_authored_topology(
        paths.root, source_relpath, source_text
    )

    assert {
        relation.target.canonical_key for relation in topology.relations
    } == {
        "Folder/Child/Target_(v2).md",
        "Folder/Child/Target_(v3).md",
        "Folder/Target.md",
    }


def test_markdown_link_labels_allow_bounded_balanced_nesting(tmp_path: Path) -> None:
    paths = _init_paths(tmp_path)
    source_relpath = "03_Notes/Source.md"
    source_text = "[see [nested [detail]]](Target.md)\n"
    _write_target(paths, source_relpath, source_text)
    _write_target(paths, "03_Notes/Target.md")

    topology = _extractor_module().extract_authored_topology(
        paths.root, source_relpath, source_text
    )

    assert [relation.target.canonical_key for relation in topology.relations] == [
        "03_Notes/Target.md"
    ]


def test_markdown_targets_are_percent_decoded_exactly_once(tmp_path: Path) -> None:
    paths = _init_paths(tmp_path)
    source_relpath = "03_Notes/Source.md"
    source_text = (
        "[encoded space](A%2520B.md)\n"
        "[encoded slash](%252FFolder%252FTarget.md)\n"
    )
    _write_target(paths, source_relpath, source_text)
    _write_target(paths, "03_Notes/A%20B.md")
    _write_target(paths, "03_Notes/%2FFolder%2FTarget.md")

    topology = _extractor_module().extract_authored_topology(
        paths.root, source_relpath, source_text
    )

    assert {
        relation.target.canonical_key for relation in topology.relations
    } == {
        "03_Notes/A%20B.md",
        "03_Notes/%2FFolder%2FTarget.md",
    }


def test_markdown_suffix_compiles_note_to_note_topology(tmp_path: Path) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(
        paths,
        "# Source\n\n[[Target]]\n",
        relpath="03_Notes/Source.markdown",
    )
    _write_target(paths, "03_Notes/Target.markdown")

    result = compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id)

    assert result.ok, result.error
    rows = _authored_rows(paths, include_retired=False)
    assert len(rows) == 1
    assert db.get_graph_entity(paths.state_db, rows[0]["source_entity_id"])[
        "entity_type"
    ] == "vault_note"
    assert db.get_graph_entity(paths.state_db, rows[0]["target_entity_id"])[
        "canonical_name"
    ] == "03_Notes/Target.markdown"


def test_real_compile_publishes_active_authored_edges_without_factual_support(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(paths, "# Source\n\n[[Target]] [[Source]] #topic\n")
    _write_target(paths, "03_Notes/Target.md")

    result = compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id)
    assert result.ok, result.error
    rows = _authored_rows(paths, include_retired=False)
    assert {(row["relation_type"], row["lifecycle_status"]) for row in rows} == {
        ("links_to", "active"),
        ("links_to", "quarantined"),
        ("tagged_with", "active"),
    }
    self_link = next(
        row for row in rows
        if row["source_entity_id"] == row["target_entity_id"]
    )
    assert self_link["quarantine_reason"] == "self_loop"
    assert self_link["reeval_trigger"] == "endpoints_distinct"
    assert all(row["assertion_source"] == "source_states" for row in rows)
    assert all(row["generation_id"] for row in rows)
    assert all(float(row["topology_weight"]) == 1.0 for row in rows)

    with db.connect(paths.state_db) as conn:
        support_count = conn.execute(
            "SELECT COUNT(*) FROM graph_relation_supports"
        ).fetchone()[0]
    assert support_count == 0
    assert db.graph_audit(paths.state_db) == []


def test_generation_audit_owns_authored_membership_across_db_only_republish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(paths, "# Source\n\n[[Target]]\n")
    _write_target(paths, "03_Notes/Target.md")
    assert compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id).ok
    relation_id = _authored_rows(paths, include_retired=False)[0]["id"]
    prior = db.get_authoritative_generation(paths.state_db, source_id)
    assert prior is not None
    assert json.loads(prior["audit_json"])["authored_relation_ids"] == [relation_id]

    monkeypatch.setattr(
        compile_mod,
        "PROMPT_CONTRACT_VERSION",
        f"{compile_mod.PROMPT_CONTRACT_VERSION}-review",
    )
    compile_mod.recompile_source(paths.state_db, source_id)

    current = db.get_authoritative_generation(paths.state_db, source_id)
    assert current is not None
    assert current["id"] != prior["id"]
    assert json.loads(current["audit_json"])["authored_relation_ids"] == [relation_id]
    row = _authored_rows(paths, include_retired=False)[0]
    assert row["generation_id"] == current["id"]
    assert row["lifecycle_status"] == "active"


def test_non_markdown_transition_retires_prior_authored_membership(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(paths, "# Source\n\n[[Target]]\n")
    _write_target(paths, "03_Notes/Target.md")
    assert compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id).ok
    relation_id = _authored_rows(paths, include_retired=False)[0]["id"]

    old_path = paths.root / "03_Notes/Source.md"
    new_path = paths.root / "03_Notes/Source.txt"
    old_path.rename(new_path)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET relpath = ?, file_type = 'txt', "
            "content_hash = 'source-text-v2' WHERE id = ?",
            ("03_Notes/Source.txt", source_id),
        )

    result = compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id)

    assert result.ok, result.error
    assert _authored_rows(paths, include_retired=False) == []
    with db.connect(paths.state_db) as conn:
        row = conn.execute(
            "SELECT lifecycle_status FROM graph_relations WHERE id = ?",
            (relation_id,),
        ).fetchone()
        current = conn.execute(
            "SELECT audit_json FROM compiler_generations "
            "WHERE source_id = ? AND status = 'authoritative'",
            (source_id,),
        ).fetchone()
    assert row["lifecycle_status"] == "retired"
    assert json.loads(current["audit_json"])["authored_relation_ids"] == []


def test_db_only_changed_fingerprint_fails_closed_and_refreshes_search(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(paths, "# Source\n\n[[Target]]\n")
    _write_target(paths, "03_Notes/Target.md")
    assert compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id).ok
    relation_id = _authored_rows(paths, include_retired=False)[0]["id"]

    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET content_hash = 'db-only-content-change' WHERE id = ?",
            (source_id,),
        )
    compile_mod.recompile_source(paths.state_db, source_id)

    assert _authored_rows(paths, include_retired=False) == []
    assert relation_id not in {
        doc["record_id"] for doc in db.list_search_documents(paths.state_db)
    }


def test_rebuild_edit_failure_rename_and_delete_reconcile_source_owned_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    with monkeypatch.context() as patcher:
        patcher.setattr(
            compile_mod.db,
            "publish_compiler_generation",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("generation flip failed")
            ),
        )
        failed = compile_mod.compile_source_l2(paths, client, source_id)
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
    assert not any(
        doc["record_type"] in {"graph_relation", "graph_entity"}
        and doc["record_id"] in {
            after_rename[0]["id"],
            after_rename[0]["source_entity_id"],
            after_rename[0]["target_entity_id"],
        }
        for doc in db.list_search_documents(paths.state_db)
    )


def test_same_structure_uses_same_ids_on_independent_replicas(tmp_path: Path) -> None:
    snapshots: list[tuple[list[str], list[str]]] = []
    db_paths: list[Path] = []
    for replica in ("one", "two"):
        paths = _init_paths(tmp_path / replica)
        db_paths.append(paths.state_db)
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

    exported = tmp_path / "replica-one.jsonl"
    export_knowledge(db_paths[0], exported)
    import_knowledge(db_paths[1], exported)
    with db.connect(db_paths[1]) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM graph_entities "
            "WHERE entity_type IN ('vault_note', 'vault_asset', 'tag')"
        ).fetchone()[0] == len(snapshots[0][0])
        assert conn.execute(
            "SELECT COUNT(*) FROM graph_relations WHERE edge_class = 'authored'"
        ).fetchone()[0] == len(snapshots[0][1])
        assert conn.execute(
            "SELECT COUNT(*) FROM graph_relations "
            "WHERE edge_class = 'authored' AND lifecycle_status = 'active'"
        ).fetchone()[0] == len(snapshots[0][1])
    assert run_compiler_audit(db_paths[1]).ok
    assert db.graph_audit(db_paths[1]) == []


def test_single_generation_is_retired_when_its_source_was_tombstoned(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(paths, "# Source\n\n[[Target]]\n")
    _write_target(paths, "03_Notes/Target.md")
    assert compile_mod.compile_source_l2(
        paths, _EmptyUnitsClient(), source_id
    ).ok
    relation_id = _authored_rows(paths, include_retired=False)[0]["id"]
    generation = db.get_authoritative_generation(paths.state_db, source_id)
    assert generation is not None
    future = "2040-01-01T00:00:00Z"

    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE compiler_generations SET updated_at = ? WHERE id = ?",
            (future, generation["id"]),
        )
        conn.execute(
            "UPDATE graph_relations SET updated_at = ? WHERE id = ?",
            (future, relation_id),
        )
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))

        _reconcile_authoritative_generations(conn)

        repaired_generation = conn.execute(
            "SELECT status, updated_at FROM compiler_generations WHERE id = ?",
            (generation["id"],),
        ).fetchone()
        repaired_relation = conn.execute(
            "SELECT lifecycle_status, updated_at FROM graph_relations WHERE id = ?",
            (relation_id,),
        ).fetchone()

    assert repaired_generation["status"] == "discarded"
    assert repaired_relation["lifecycle_status"] == "retired"
    assert _timestamp_key(repaired_generation["updated_at"]) > _timestamp_key(future)
    assert _timestamp_key(repaired_relation["updated_at"]) > _timestamp_key(future)


def test_replica_generation_winner_preserves_shared_edge_despite_row_clock(
    tmp_path: Path,
) -> None:
    replicas: list[tuple[cfg.WikiPaths, int, str, str]] = []
    for name in ("local", "remote"):
        paths = _init_paths(tmp_path / name)
        source_id = _seed_source(paths, "# Source\n\n[[Target]]\n")
        _write_target(paths, "03_Notes/Target.md")
        assert compile_mod.compile_source_l2(
            paths, _EmptyUnitsClient(), source_id
        ).ok
        generation = db.get_authoritative_generation(paths.state_db, source_id)
        assert generation is not None
        relation_id = _authored_rows(paths, include_retired=False)[0]["id"]
        replicas.append((paths, source_id, str(generation["id"]), relation_id))

    local, _local_source, local_generation, relation_id = replicas[0]
    remote, _remote_source, remote_generation, remote_relation_id = replicas[1]
    assert relation_id == remote_relation_id
    with db.connect(local.state_db) as conn:
        conn.execute(
            "UPDATE compiler_generations SET published_at = ?, updated_at = ? "
            "WHERE id = ?",
            ("2026-07-30T01:00:00Z", "2040-01-01T00:00:00Z", local_generation),
        )
        conn.execute(
            "UPDATE graph_relations SET updated_at = ? WHERE id = ?",
            ("2040-01-01T00:00:00Z", relation_id),
        )
    with db.connect(remote.state_db) as conn:
        conn.execute(
            "UPDATE compiler_generations SET published_at = ?, updated_at = ? "
            "WHERE id = ?",
            ("2030-01-01T00:00:00Z", "2030-01-01T00:00:00Z", remote_generation),
        )
        conn.execute(
            "UPDATE graph_relations SET updated_at = ? WHERE id = ?",
            ("2030-01-01T00:00:00Z", relation_id),
        )

    exported = tmp_path / "remote.jsonl"
    export_knowledge(remote.state_db, exported)
    import_knowledge(local.state_db, exported)

    with db.connect(local.state_db) as conn:
        authoritative = conn.execute(
            "SELECT id FROM compiler_generations "
            "WHERE status = 'authoritative'"
        ).fetchall()
        relation = conn.execute(
            "SELECT generation_id, lifecycle_status, updated_at FROM graph_relations "
            "WHERE id = ?",
            (relation_id,),
        ).fetchone()
        discarded = conn.execute(
            "SELECT status, updated_at FROM compiler_generations WHERE id = ?",
            (local_generation,),
        ).fetchone()
    assert [str(row["id"]) for row in authoritative] == [remote_generation]
    assert relation["generation_id"] == remote_generation
    assert relation["lifecycle_status"] == "active"
    assert _timestamp_key(relation["updated_at"]) > _timestamp_key(
        "2040-01-01T00:00:00Z"
    )
    assert discarded["status"] == "discarded"
    assert _timestamp_key(discarded["updated_at"]) > _timestamp_key(
        "2040-01-01T00:00:00Z"
    )


def test_replica_topology_addition_retires_endpoint_report(tmp_path: Path) -> None:
    local = _init_paths(tmp_path / "local")
    local_source = _seed_source(local, "# Source\n\n[[Target]]\n")
    _write_target(local, "03_Notes/Target.md")
    _write_target(local, "03_Notes/Other.md")
    assert compile_mod.compile_source_l2(
        local, _EmptyUnitsClient(), local_source
    ).ok
    authored = _authored_rows(local, include_retired=False)[0]
    extracted_target = db.upsert_graph_entity(
        local.state_db,
        canonical_name="Extracted",
        entity_type="concept",
    )
    extracted = db.upsert_graph_relation(
        local.state_db,
        source_entity_id=authored["target_entity_id"],
        target_entity_id=extracted_target,
        relation_type="supports",
        confidence=0.9,
    )
    with db.connect(local.state_db) as conn:
        for index in (1, 2):
            conn.execute(
                "INSERT INTO graph_relation_supports "
                "(relation_id, knowledge_unit_id, source_span_ids, assertion_source, "
                "confidence, support_status, support_hash, source_lineage_hash, "
                "created_at, updated_at) "
                "VALUES (?, ?, '[]', 'source_states', 0.9, 'verified', ?, ?, 't', 't')",
                (
                    extracted,
                    f"KNU-sync-{index}",
                    f"sync-support-{index}",
                    f"sync-lineage-{index}",
                ),
            )
    db.rebuild_graph_generation(local.state_db)
    report = db.list_community_reports(local.state_db)[0]

    remote = _init_paths(tmp_path / "remote")
    remote_source = _seed_source(
        remote,
        "# Source\n\n[[Target]] [[Other]]\n",
        content_hash="source-v2",
    )
    _write_target(remote, "03_Notes/Target.md")
    _write_target(remote, "03_Notes/Other.md")
    assert compile_mod.compile_source_l2(
        remote, _EmptyUnitsClient(), remote_source
    ).ok
    with db.connect(remote.state_db) as conn:
        conn.execute(
            "UPDATE sources SET updated_at = '2030-01-01T00:00:00Z' "
            "WHERE id = ?",
            (remote_source,),
        )
        conn.execute(
            "UPDATE compiler_generations SET published_at = ?, updated_at = ? "
            "WHERE source_id = ?",
            (
                "2030-01-01T00:00:00Z",
                "2030-01-01T00:00:00Z",
                remote_source,
            ),
        )

    exported = tmp_path / "remote-addition.jsonl"
    export_knowledge(remote.state_db, exported)
    import_knowledge(local.state_db, exported)

    stale = db.get_community_report(local.state_db, report["id"])
    assert stale is not None
    assert stale["retired_at"] is not None


def test_replica_topology_addition_is_compared_with_every_loser(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(paths, "# Source\n\n[[Target]]\n")
    _write_target(paths, "03_Notes/Target.md")
    _write_target(paths, "03_Notes/Other.md")
    assert compile_mod.compile_source_l2(
        paths, _EmptyUnitsClient(), source_id
    ).ok
    original = _authored_rows(paths, include_retired=False)[0]

    extracted_target = db.upsert_graph_entity(
        paths.state_db,
        canonical_name="Extracted",
        entity_type="concept",
    )
    extracted = db.upsert_graph_relation(
        paths.state_db,
        source_entity_id=original["target_entity_id"],
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
                    f"KNU-three-way-{index}",
                    f"three-way-support-{index}",
                    f"three-way-lineage-{index}",
                ),
            )
    db.rebuild_graph_generation(paths.state_db)
    report = db.list_community_reports(paths.state_db)[0]

    other_entity = db.upsert_graph_entity(
        paths.state_db,
        canonical_name="03_Notes/Other.md",
        entity_type="vault_note",
    )
    with db.connect(paths.state_db) as conn:
        original_generation = conn.execute(
            "SELECT id FROM compiler_generations "
            "WHERE source_id = ? AND status = 'authoritative'",
            (source_id,),
        ).fetchone()[0]
        for generation_id, published_at in (
            ("GEN-three-way-middle", "2030-01-01T00:00:00Z"),
            ("GEN-three-way-winner", "2040-01-01T00:00:00Z"),
        ):
            conn.execute(
                "INSERT INTO compiler_generations "
                "(id, source_id, status, prompt_contract_version, created_at, "
                "published_at, audit_json, updated_at) "
                "VALUES (?, ?, 'authoritative', 'test', ?, ?, '{}', ?)",
                (
                    generation_id,
                    source_id,
                    published_at,
                    published_at,
                    published_at,
                ),
            )
        added_relation = db.upsert_graph_relation(
            paths.state_db,
            source_entity_id=original["source_entity_id"],
            target_entity_id=other_entity,
            relation_type="links_to",
            assertion_source="source_states",
            confidence=1.0,
            edge_class="authored",
            lifecycle_status="active",
            topology_weight=1.0,
            generation_id="GEN-three-way-winner",
            conn=conn,
        )
        middle_and_winner = json.dumps(
            {
                "authored_relation_ids": sorted([original["id"], added_relation]),
                "content_hash": "source-v1",
                "unit_count": 0,
                "unit_ids": [],
            },
            sort_keys=True,
        )
        conn.execute(
            "UPDATE compiler_generations SET audit_json = ? "
            "WHERE id IN ('GEN-three-way-middle', 'GEN-three-way-winner')",
            (middle_and_winner,),
        )
        conn.execute(
            "UPDATE compiler_generations SET published_at = ?, updated_at = ? "
            "WHERE id = ?",
            (
                "2020-01-01T00:00:00Z",
                "2020-01-01T00:00:00Z",
                original_generation,
            ),
        )

        _reconcile_authoritative_generations(conn)

    stale = db.get_community_report(paths.state_db, report["id"])
    assert stale is not None
    assert stale["retired_at"] is not None


def test_portable_entity_ids_normalize_unicode_paths() -> None:
    endpoint_type = _extractor_module().AuthoredEndpoint
    nfc_path = unicodedata.normalize("NFC", "03_Notes/Café.md")
    nfd_path = unicodedata.normalize("NFD", nfc_path)

    nfc = endpoint_type(entity_type="vault_note", canonical_key=nfc_path)
    nfd = endpoint_type(entity_type="vault_note", canonical_key=nfd_path)

    assert nfc.canonical_key == nfd.canonical_key == nfc_path
    assert nfc.entity_id == nfd.entity_id


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


def test_authored_lifecycle_rejects_generation_owned_by_another_source(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_a = _seed_source(
        paths,
        "# Source A\n\n[[Target]]\n",
        relpath="03_Notes/Source A.md",
        content_hash="source-a",
    )
    source_b = _seed_source(
        paths,
        "# Source B\n\n[[Target]]\n",
        relpath="03_Notes/Source B.md",
        content_hash="source-b",
    )
    _write_target(paths, "03_Notes/Target.md")
    assert compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_a).ok
    assert compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_b).ok

    rows = _authored_rows(paths, include_retired=False)
    source_a_entity = next(
        row["source_entity_id"]
        for row in rows
        if db.get_graph_entity(paths.state_db, row["source_entity_id"])[
            "canonical_name"
        ] == "03_Notes/Source A.md"
    )
    with db.connect(paths.state_db) as conn:
        source_b_generation = conn.execute(
            "SELECT id FROM compiler_generations "
            "WHERE source_id = ? AND status = 'authoritative'",
            (source_b,),
        ).fetchone()[0]
    wrong_target = db.upsert_graph_entity(
        paths.state_db,
        canonical_name="wrong-owner",
        entity_type="tag",
    )
    wrong_relation = db.upsert_graph_relation(
        paths.state_db,
        source_entity_id=source_a_entity,
        target_entity_id=wrong_target,
        relation_type="tagged_with",
        edge_class="authored",
        lifecycle_status="active",
        topology_weight=1.0,
        generation_id=source_b_generation,
    )

    violations = db.graph_audit(paths.state_db)
    assert {
        (violation["code"], violation["subject_id"])
        for violation in violations
    } >= {("active_authored_relation_stale_generation", wrong_relation)}
    assert db.compile_relation_lifecycle(
        paths.state_db,
        relation_id=wrong_relation,
    ) == "quarantined"


def test_authored_lifecycle_requires_exact_generation_audit_membership(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(paths, "# Source\n\n[[Target]]\n")
    _write_target(paths, "03_Notes/Target.md")
    assert compile_mod.compile_source_l2(
        paths, _EmptyUnitsClient(), source_id
    ).ok
    relation_id = _authored_rows(paths, include_retired=False)[0]["id"]
    generation = db.get_authoritative_generation(paths.state_db, source_id)
    assert generation is not None
    audit = json.loads(generation["audit_json"])
    audit["authored_relation_ids"] = []

    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE compiler_generations SET audit_json = ? WHERE id = ?",
            (json.dumps(audit, sort_keys=True), generation["id"]),
        )

    assert {
        (violation["code"], violation["subject_id"])
        for violation in db.graph_audit(paths.state_db)
    } >= {("active_authored_relation_stale_generation", relation_id)}
    assert db.compile_relation_lifecycle(
        paths.state_db,
        relation_id=relation_id,
    ) == "quarantined"


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

    source_path = paths.root / "03_Notes/Source.md"
    source_path.write_text("# Source\n\nNo authored link remains.\n", encoding="utf-8")
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET content_hash = 'source-without-link' WHERE id = ?",
            (source_id,),
        )
    assert compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id).ok
    retired_report = db.get_community_report(paths.state_db, reports[0]["id"])
    assert retired_report is not None
    assert retired_report["retired_at"] is not None


def test_new_authored_edge_retires_report_containing_either_endpoint(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(paths, "# Source\n\n[[Target]]\n")
    _write_target(paths, "03_Notes/Target.md")
    _write_target(paths, "03_Notes/Other.md")
    assert compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id).ok
    authored = _authored_rows(paths, include_retired=False)[0]

    extracted_target = db.upsert_graph_entity(
        paths.state_db, canonical_name="Extracted", entity_type="concept"
    )
    extracted = db.upsert_graph_relation(
        paths.state_db,
        source_entity_id=authored["target_entity_id"],
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
                    f"KNU-addition-{index}",
                    f"addition-support-{index}",
                    f"addition-lineage-{index}",
                ),
            )
    db.rebuild_graph_generation(paths.state_db)
    report = db.list_community_reports(paths.state_db)[0]
    assert authored["source_entity_id"] in report["entity_ids"]

    (paths.root / "03_Notes/Source.md").write_text(
        "# Source\n\n[[Target]] [[Other]]\n",
        encoding="utf-8",
    )
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET content_hash = 'source-added-link' WHERE id = ?",
            (source_id,),
        )
    assert compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id).ok

    stale = db.get_community_report(paths.state_db, report["id"])
    assert stale is not None
    assert stale["retired_at"] is not None


def test_relation_retirement_strictly_advances_relation_and_report_clocks(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source = db.upsert_graph_entity(
        paths.state_db,
        canonical_name="Retirement Source",
        entity_type="concept",
    )
    target = db.upsert_graph_entity(
        paths.state_db,
        canonical_name="Retirement Target",
        entity_type="concept",
    )
    relation_id = db.upsert_graph_relation(
        paths.state_db,
        source_entity_id=source,
        target_entity_id=target,
        relation_type="supports",
        lifecycle_status="active",
    )
    report_id = db.upsert_community_report(
        paths.state_db,
        community_key="retirement-clock",
        entity_ids=[source, target],
    )
    db.record_artifact_dependency(
        paths.state_db,
        artifact_id=report_id,
        artifact_type="community_report",
        depends_on_id=relation_id,
        depends_on_type="relation",
        dependency_hash="retirement-clock",
    )
    relation_future = "2040-01-01T00:00:00Z"
    report_future = "2050-01-01T00:00:00Z"

    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE graph_relations SET updated_at = ? WHERE id = ?",
            (relation_future, relation_id),
        )
        conn.execute(
            "UPDATE community_reports SET updated_at = ? WHERE id = ?",
            (report_future, report_id),
        )
        assert db.retire_graph_relations_on_connection(
            conn,
            [relation_id],
            now="2030-01-01T00:00:00Z",
        ) == 1
        relation = conn.execute(
            "SELECT lifecycle_status, updated_at FROM graph_relations WHERE id = ?",
            (relation_id,),
        ).fetchone()
        report = conn.execute(
            "SELECT retired_at, updated_at FROM community_reports WHERE id = ?",
            (report_id,),
        ).fetchone()

    assert relation["lifecycle_status"] == "retired"
    assert _timestamp_key(relation["updated_at"]) > _timestamp_key(relation_future)
    assert _timestamp_key(report["retired_at"]) > _timestamp_key(report_future)
    assert report["updated_at"] == report["retired_at"]


def test_endpoint_invalidation_preserves_report_with_winner_relation_dependency(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source = db.upsert_graph_entity(
        paths.state_db,
        canonical_name="Winner Source",
        entity_type="concept",
    )
    target = db.upsert_graph_entity(
        paths.state_db,
        canonical_name="Winner Target",
        entity_type="concept",
    )
    relation_id = db.upsert_graph_relation(
        paths.state_db,
        source_entity_id=source,
        target_entity_id=target,
        relation_type="winner-topology",
        lifecycle_status="active",
    )
    report_id = db.upsert_community_report(
        paths.state_db,
        community_key="winner-report",
        entity_ids=[source, target],
    )
    db.record_artifact_dependency(
        paths.state_db,
        artifact_id=report_id,
        artifact_type="community_report",
        depends_on_id=relation_id,
        depends_on_type="relation",
        dependency_hash="winner-report",
    )

    with db.connect(paths.state_db) as conn:
        retired = db.retire_community_reports_for_relation_endpoints_on_connection(
            conn,
            [relation_id],
        )

    assert retired == 0
    report = db.get_community_report(paths.state_db, report_id)
    assert report is not None
    assert report["retired_at"] is None


def test_link_removal_drops_orphan_authored_entities_from_search(
    tmp_path: Path,
) -> None:
    paths = _init_paths(tmp_path)
    source_id = _seed_source(paths, "# Source\n\n[[Target]]\n")
    _write_target(paths, "03_Notes/Target.md")
    assert compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id).ok
    authored = _authored_rows(paths, include_retired=False)[0]
    authored_ids = {
        authored["id"],
        authored["source_entity_id"],
        authored["target_entity_id"],
    }
    assert authored_ids <= {
        doc["record_id"] for doc in db.list_search_documents(paths.state_db)
    }

    (paths.root / "03_Notes/Source.md").write_text(
        "# Source\n\nNo authored link remains.\n",
        encoding="utf-8",
    )
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET content_hash = 'source-without-topology' WHERE id = ?",
            (source_id,),
        )
    assert compile_mod.compile_source_l2(paths, _EmptyUnitsClient(), source_id).ok

    assert authored_ids.isdisjoint(
        {doc["record_id"] for doc in db.list_search_documents(paths.state_db)}
    )


def test_bulk_relation_retirement_chunks_sqlite_parameters(tmp_path: Path) -> None:
    paths = _init_paths(tmp_path)
    source = db.upsert_graph_entity(
        paths.state_db,
        canonical_name="Bulk Source",
        entity_type="concept",
    )
    target = db.upsert_graph_entity(
        paths.state_db,
        canonical_name="Bulk Target",
        entity_type="concept",
    )
    relation_ids = [f"REL-bulk-{index:04d}" for index in range(1_001)]
    with db.connect(paths.state_db) as conn:
        conn.executemany(
            "INSERT INTO graph_relations "
            "(id, source_entity_id, target_entity_id, relation_type, "
            "created_at, updated_at, lifecycle_status) "
            "VALUES (?, ?, ?, ?, 't', 't', 'active')",
            [
                (relation_id, source, target, f"bulk-{index}")
                for index, relation_id in enumerate(relation_ids)
            ],
        )
        assert db.retire_graph_relations_on_connection(conn, relation_ids) == len(
            relation_ids
        )
        active = conn.execute(
            "SELECT COUNT(*) FROM graph_relations "
            "WHERE lifecycle_status != 'retired'"
        ).fetchone()[0]
    assert active == 0
