"""`wiki lint` must not report errors the user cannot act on.

Two ways the `invalid_source_path` check lied, both observed on a real 37-source
vault that scored 70 errors / 0 warnings:

1. It compared a filesystem-derived path against a stored path with byte-exact
   equality. macOS stores filenames decomposed, so a source named
   ``…Plücker…`` walks as ``Plu`` + U+0308 while the atom frontmatter holds the
   precomposed ``ü`` — the same file, never equal in a ``set`` lookup.
2. It advertised `wiki lint --fix` for atoms whose parent source row points at a
   path that no longer exists. The "repair" copies that same dead path back, so
   the error survives every fix run.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

from curator import config as cfg
from curator import db, lint

# "Plücker" written the way macOS stores it: base letter + combining diaeresis.
_DECOMPOSED_STEM = unicodedata.normalize(
    "NFD", "Camera Pose Estimation from Lines using Plücker Coordinates"
)
_PRECOMPOSED_STEM = unicodedata.normalize("NFC", _DECOMPOSED_STEM)


def _vault(tmp_path: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(tmp_path)
    for layer_dir in (paths.contexts, paths.atoms, paths.concepts, paths.synthesis):
        layer_dir.mkdir(parents=True, exist_ok=True)
    for raw_dir in paths.raw_dirs:
        raw_dir.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    return paths


def _write_context(paths: cfg.WikiPaths, context_id: str, source_relpath: str) -> None:
    (paths.contexts / f"{context_id}.md").write_text(
        f"""---
id: {context_id}
type: context
source_path: '[[{source_relpath.removesuffix(".md")}]]'
last_updated: '2026-08-06T00:00:00Z'
---

# Context
""",
        encoding="utf-8",
    )


def _write_atom(
    paths: cfg.WikiPaths, atom_id: str, context_id: str, source_relpath: str
) -> None:
    (paths.atoms / f"{atom_id}.md").write_text(
        f"""---
id: {atom_id}
type: atom
parent_source: 01_Contexts/{context_id}
source_path: '[[{source_relpath.removesuffix(".md")}]]'
claim_type: fact
last_updated: '2026-08-06T00:00:00Z'
---

# Atom

A claim.
""",
        encoding="utf-8",
    )


def _register(paths: cfg.WikiPaths, context_id: str, relpath: str) -> None:
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources "
            "(relpath, content_hash, file_type, bytes, added_at, status, context_id) "
            "VALUES (?, ?, 'md', 0, '2026-08-06T00:00:00Z', 'curated', ?)",
            (relpath, f"hash-{context_id}", context_id),
        )


def _source_path_errors(paths: cfg.WikiPaths) -> list[lint.LintIssue]:
    report = lint.run_lint(paths, deep=False, client=None)
    return [
        issue
        for issue in report.issues
        if issue.check == lint.CheckId.INVALID_SOURCE_PATH
    ]


def test_decomposed_filename_is_not_reported_as_a_missing_source(
    tmp_path: Path,
) -> None:
    """The file is right there; only the two Unicode forms differed."""
    paths = _vault(tmp_path)

    # On disk exactly as macOS stores it.
    disk_relpath = f"04_Resources/{_DECOMPOSED_STEM}.md"
    disk_file = tmp_path / disk_relpath
    disk_file.parent.mkdir(parents=True, exist_ok=True)
    disk_file.write_text("# Paper\n", encoding="utf-8")

    # Everything the backend stores is precomposed.
    stored_relpath = f"04_Resources/{_PRECOMPOSED_STEM}.md"
    assert stored_relpath != disk_relpath, "the two forms must differ byte-wise"

    _register(paths, "CTX-uni00001", stored_relpath)
    _write_context(paths, "CTX-uni00001", stored_relpath)
    _write_atom(paths, "ATM-uni00001", "CTX-uni00001", stored_relpath)

    assert _source_path_errors(paths) == []


def test_unrepairable_source_row_is_not_advertised_as_fixable(
    tmp_path: Path,
) -> None:
    """A renamed source leaves a row naming a file that no longer exists.

    `--fix` restores `source_path` from that row, so it would write the dead
    path back and the error would return on the next run. The check must say so
    rather than sending the user round a loop it cannot exit.
    """
    paths = _vault(tmp_path)

    dead_relpath = "04_Resources/renamed-away-ref-5.md"
    _register(paths, "CTX-dead0001", dead_relpath)
    _write_context(paths, "CTX-dead0001", dead_relpath)
    _write_atom(paths, "ATM-dead0001", "CTX-dead0001", dead_relpath)

    errors = _source_path_errors(paths)
    assert len(errors) == 1
    issue = errors[0]
    assert issue.fixable is False
    assert "does not exist on disk either" in issue.suggestion
    assert "wiki sources rm" in issue.suggestion


def test_a_genuinely_wrong_atom_path_is_still_fixable(
    tmp_path: Path,
) -> None:
    """The repairable case must keep working — this is the check's whole point."""
    paths = _vault(tmp_path)

    real_relpath = "04_Resources/real-paper.md"
    real_file = tmp_path / real_relpath
    real_file.parent.mkdir(parents=True, exist_ok=True)
    real_file.write_text("# Paper\n", encoding="utf-8")

    _register(paths, "CTX-good0001", real_relpath)
    _write_context(paths, "CTX-good0001", real_relpath)
    # The atom points somewhere that was never a source.
    _write_atom(paths, "ATM-good0001", "CTX-good0001", "04_Resources/typo.md")

    errors = _source_path_errors(paths)
    assert len(errors) == 1
    issue = errors[0]
    assert issue.fixable is True
    assert "wiki lint --fix" in issue.suggestion

    assert lint.apply_fixes(paths, errors) == 1
    assert _source_path_errors(paths) == []


def _write_compiler_atom(
    paths: cfg.WikiPaths, atom_id: str, span_id: str, source_path: str
) -> None:
    """An Atom in the shape the compiler actually emits: spans, no parent_source."""
    (paths.atoms / f"{atom_id}.md").write_text(
        f"""---
id: {atom_id}
type: atom
unit_type: method
source_span_ids:
- {span_id}
truth_status: source_supported
source_path: {source_path}
---

# Atom

A claim.
""",
        encoding="utf-8",
    )


def test_compiler_emitted_atom_resolves_its_source_through_spans(
    tmp_path: Path,
) -> None:
    """No compiler-emitted Atom carries `parent_source` any more.

    Measured on a real vault: 0 of 1098 atoms had the field, while 1098 had
    `source_span_ids`. Resolving the repair only through `parent_source` meant
    `fixable` was False for every modern atom, so `--fix` was advertised and
    then silently did nothing. The repair must come from the provenance the
    page actually carries.
    """
    paths = _vault(tmp_path)

    real_relpath = "04_Resources/paper.md"
    real_file = tmp_path / real_relpath
    real_file.parent.mkdir(parents=True, exist_ok=True)
    real_file.write_text("# Paper\n", encoding="utf-8")

    _register(paths, "CTX-span0001", real_relpath)
    _write_context(paths, "CTX-span0001", real_relpath)
    with db.connect(paths.state_db) as conn:
        source_id = conn.execute(
            "SELECT id FROM sources WHERE relpath = ?", (real_relpath,)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO source_spans "
            "(id, source_id, relpath, span_type, content_hash, text_preview, created_at) "
            "VALUES ('SPAN-abc12345', ?, ?, 'paragraph', 'spanhash', 'text', "
            "'2026-08-06T00:00:00Z')",
            (source_id, real_relpath),
        )

    _write_compiler_atom(paths, "ATM-span0001", "SPAN-abc12345", "04_Resources/wrong.md")

    errors = _source_path_errors(paths)
    assert len(errors) == 1
    issue = errors[0]
    assert issue.fixable is True, (
        "an atom whose spans resolve to a real source must be repairable "
        f"(suggestion was: {issue.suggestion})"
    )
    assert issue.context["new_target"] == "[[04_Resources/paper]]"

    assert lint.apply_fixes(paths, errors) == 1
    assert _source_path_errors(paths) == []
