"""The folder a user must grant survives from the exception to the surface.

`ParserAccessDenied` carries `.grant_folder` — the exact folder to grant,
computed by walking upward from the file. Traced across the ingest paths, it was
flattened into a prose `message` and the structured answer discarded, because
`AddOutcome` had nowhere to put it.

That is why the plugin cannot say which folder to open: there is no folder in
what it receives. `ZoteroRepairModal` still sends users to System Settings
without naming one — the exact mistake `grant_root`'s own docstring records this
repo already paying for once, when a guessed location sent someone to change a
setting that was never the problem.

A prompt with a button is only possible if this field arrives.
"""

from __future__ import annotations

import stat

import pytest

from curator import ingest_raw


@pytest.fixture
def denied_source(tmp_path):
    """A readable vault holding a file inside a folder this process cannot open."""
    vault = tmp_path / "vault"
    (vault / "04_Resources").mkdir(parents=True)
    locked = tmp_path / "locked"
    locked.mkdir()
    pdf = locked / "paper.pdf"
    pdf.write_text("%PDF-1.4 stub")
    locked.chmod(0o000)
    yield vault, locked, pdf
    locked.chmod(stat.S_IRWXU)


def test_the_outcome_carries_the_folder_to_grant(denied_source) -> None:
    """The whole point: a caller can name the folder without re-deriving it."""
    _vault, locked, pdf = denied_source

    outcome = ingest_raw.AddOutcome(
        result=ingest_raw.AddResult.ERROR,
        source_path=pdf,
        relpath=str(pdf),
        message="denied",
        grant_folder=str(locked),
    )
    assert outcome.grant_folder == str(locked)


def test_the_field_defaults_to_empty_for_every_other_failure() -> None:
    """An unrelated parse error must not look like a permission problem.

    Offering a folder to grant for a corrupt PDF would send the user to change a
    setting that has nothing to do with it.
    """
    outcome = ingest_raw.AddOutcome(
        result=ingest_raw.AddResult.ERROR,
        source_path=None,
        relpath="x.pdf",
        message="Unsupported file type",
    )
    assert outcome.grant_folder == ""


def test_a_denial_during_add_fills_it_in(denied_source, monkeypatch) -> None:
    """End to end through the real `add_file`, not a hand-built outcome."""
    vault, locked, pdf = denied_source

    from curator import config as cfg

    paths = cfg.WikiPaths(vault)
    outcome = ingest_raw.add_file(paths, pdf)

    assert outcome.result is ingest_raw.AddResult.ERROR
    assert outcome.grant_folder == str(locked), (
        "the folder was computed and then thrown away, which is why the plugin "
        "cannot name it"
    )
