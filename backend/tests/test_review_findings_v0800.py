"""Regressions for the defects the v0.80.0 code review found.

Each of these was code that computed the right answer and then discarded it —
the shape this repo calls half-wiring. The tests pin the wiring, not the helper.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from curator import file_access, ingest_raw, zotero_tools
from curator.parsers import ParserNotDownloaded
from curator.plugin_api import access


def test_resolve_pdf_reports_an_evicted_attachment_as_evicted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`_first_readable_pdf` computed NOT_DOWNLOADED and `resolve_pdf` dropped it.

    Every consumer then described an online-only iCloud PDF as "Zotero
    attachment file not found", sending the user to look for a file that was
    never deleted. Three review lenses caught it independently.
    """
    pdf = tmp_path / "storage" / "KEY1" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_text("placeholder")

    monkeypatch.setattr(
        zotero_tools,
        "_first_readable_pdf",
        lambda _paths: (str(pdf), file_access.Reachability.NOT_DOWNLOADED),
    )
    monkeypatch.setattr(
        zotero_tools, "_first_existing_zotero_db", lambda *a, **k: str(tmp_path / "z.sqlite")
    )
    monkeypatch.setattr(zotero_tools, "zotero_root_candidates", lambda *a, **k: [str(tmp_path)])
    monkeypatch.setattr(
        zotero_tools.zotero_backend,
        "resolve_pdf_attachment_for_key",
        lambda *a, **k: ("KEY1", str(pdf)),
    )
    monkeypatch.setattr(zotero_tools.cfg, "load_config", lambda *a, **k: {})
    monkeypatch.setattr(file_access, "describe", lambda p: f"{p} is not downloaded to this machine")

    from curator import config as cfg

    result = zotero_tools.resolve_pdf("KEY1", cfg.WikiPaths(root=tmp_path))

    assert result["state"] == "attachment_file_not_downloaded"
    assert "not found" not in result["error"]
    # Nothing is denied, so there is no folder whose granting would help.
    assert result["grant_folder"] == ""


def test_an_evicted_attachment_does_not_silently_ingest_the_stub(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The sibling of the denial guard.

    Degrading here would ingest the reference note's frontmatter and report
    success — the source silently becomes a few lines of metadata instead of the
    book it points at. The broad `except Exception` below the guard would have
    swallowed the new exception straight back into that path.
    """
    stub = tmp_path / "ref.md"
    stub.write_text("---\ntype: reference\nzotero_key: KEY1\n---\n\nnotes\n")

    monkeypatch.setattr(
        zotero_tools,
        "resolve_pdf",
        lambda *a, **k: {
            "ok": False,
            "state": "attachment_file_not_downloaded",
            "path": str(tmp_path / "cloud.pdf"),
            "error": "cloud.pdf is not downloaded to this machine",
        },
    )
    from curator import config as cfg

    with pytest.raises(ParserNotDownloaded):
        ingest_raw._resolve_reference_source(cfg.WikiPaths(root=tmp_path), stub)


def test_import_source_carries_the_folder_to_grant(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`AddOutcome.grant_folder` was computed and dropped at the plugin boundary.

    That is the loss PR #163 was reviewed for, on a second call path.
    """
    from curator import config as cfg
    from curator.plugin_api import sources as sources_api

    outcome = ingest_raw.AddOutcome(
        result=ingest_raw.AddResult.ERROR,
        source_path=tmp_path / "p.pdf",
        relpath="p.pdf",
        message="cannot be read",
        grant_folder="/Users/x/Library/Mobile Documents",
    )
    monkeypatch.setattr(ingest_raw, "import_source_file", lambda *a, **k: outcome)

    payload: dict[str, Any] = sources_api.import_source(
        cfg.WikiPaths(root=tmp_path), file_path=str(tmp_path / "p.pdf")
    )
    assert payload["grant_folder"] == "/Users/x/Library/Mobile Documents"


def test_a_configured_root_that_went_missing_is_still_reported(tmp_path: Path) -> None:
    """Omitting absent roots was meant to hide folders the user never set up.

    A configured root that has been renamed or unmounted is the opposite: it is
    exactly what this tab exists to surface, and dropping the row makes it
    vanish with no reason given.
    """
    from curator import config as cfg

    vault = tmp_path / "vault"
    vault.mkdir()
    rows = access.access_report(
        cfg.WikiPaths(root=vault),
        config={"external": {"path_roots": {"papers": str(tmp_path / "gone")}}},
    )
    by_label = {r["label"]: r for r in rows}
    assert "Configured root: papers" in by_label
    assert by_label["Configured root: papers"]["state"] == "missing"


def test_a_discovered_root_that_is_absent_is_still_omitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The other half: a Zotero location Zotero merely might use is not noise
    worth a row when it is not there."""
    from curator import config as cfg
    from curator import zotero_tools as zt

    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(zt, "zotero_root_candidates", lambda *a, **k: [str(tmp_path / "nope")])
    rows = access.access_report(cfg.WikiPaths(root=vault), config={})
    assert [r["label"] for r in rows if r["label"] == "Zotero"] == []
