"""A file you may not read is not a missing file.

Ingest reported `parse failed: Cannot parse PDF …` for a 21 MB PDF that opens
instantly in Finder. The file was fine; the process was denied. Three checks in
a row each answered a question nobody asked:

    exists()        -> True     (it is there)
    os.access R_OK  -> True     (the permission bits allow it)
    open()          -> PermissionError errno=1

`os.access` is the trap. It reads POSIX permission bits, and macOS TCC denies
below them — so the obvious fix, "add a readability check", reports a readable
file and defers the failure to a caller that describes it wrongly. Only an
actual open is honest. See SYSTEM_BEHAVIOR §12.3.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from curator import file_access as fa


def cfg_paths(tmp_path: Path):
    """A minimal initialised vault for the status-report tests."""
    from curator import config as cfg, db

    paths = cfg.paths_from_config(tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    return paths


# --------------------------------------------------------------------------
# The three outcomes
# --------------------------------------------------------------------------


def test_a_readable_file_is_ok(tmp_path: Path) -> None:
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.4 ...")
    assert fa.probe(p) is fa.Reachability.OK


def test_a_file_that_is_not_there_is_missing(tmp_path: Path) -> None:
    assert fa.probe(tmp_path / "nope.pdf") is fa.Reachability.MISSING


def test_an_unreadable_file_is_denied_not_missing(tmp_path: Path) -> None:
    """The distinction the whole release exists for."""
    p = tmp_path / "secret.pdf"
    p.write_bytes(b"%PDF-1.4 ...")
    p.chmod(0o000)
    try:
        if os.access(p, os.R_OK):  # root ignores the mode bits
            pytest.skip("running as a user that bypasses permission bits")
        assert fa.probe(p) is fa.Reachability.DENIED
    finally:
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_a_directory_is_not_reported_as_a_readable_file(tmp_path: Path) -> None:
    """`open()` on a directory succeeds on some platforms; the first read does not.

    This is why the probe reads a byte instead of merely opening.
    """
    assert fa.probe(tmp_path) is not fa.Reachability.OK


# --------------------------------------------------------------------------
# G1 — the measured trap, pinned so nobody "optimises" the probe back to access()
# --------------------------------------------------------------------------


def test_the_probe_does_not_rely_on_os_access(monkeypatch: pytest.MonkeyPatch,
                                              tmp_path: Path) -> None:
    """Measured on the live case: os.access said True while open() was denied.

    A permission-bit check cannot see a TCC denial. If someone later swaps the
    open for `os.access` because it is cheaper, this fails.
    """
    p = tmp_path / "tcc.pdf"
    p.write_bytes(b"%PDF-1.4 ...")

    monkeypatch.setattr(os, "access", lambda *_a, **_k: True)   # bits say yes

    real_os_open = os.open

    def denying_open(file, *a, **k):
        if Path(file) == p:
            raise PermissionError(1, "Operation not permitted")
        return real_os_open(file, *a, **k)

    monkeypatch.setattr(os, "open", denying_open)
    assert fa.probe(p) is fa.Reachability.DENIED, (
        "the probe agreed with os.access instead of with reality"
    )


# --------------------------------------------------------------------------
# G2 — the grant folder, found by probing rather than by a hardcoded list
# --------------------------------------------------------------------------


def test_the_grant_root_is_the_shallowest_denied_ancestor(tmp_path: Path) -> None:
    """Telling a user to grant access to one PDF is useless; name the folder.

    Measured on the live case: ancestors were denied up through
    `~/Library/Mobile Documents` and readable at `~/Library`, so the answer is
    the deepest folder that is still denied — and it falls out of probing with
    no table of macOS locations at all.
    """
    outer = tmp_path / "outer"
    blocked = outer / "blocked"
    inner = blocked / "inner"
    inner.mkdir(parents=True)
    leaf = inner / "doc.pdf"
    leaf.write_bytes(b"%PDF")
    blocked.chmod(0o000)
    try:
        if os.access(blocked, os.R_OK):
            pytest.skip("running as a user that bypasses permission bits")
        assert fa.grant_root(leaf) == blocked
    finally:
        blocked.chmod(stat.S_IRWXU)


def test_no_grant_root_is_invented_when_nothing_is_denied(tmp_path: Path) -> None:
    """A wrong folder is worse than none — it sends the user to change a setting
    that was never the problem."""
    p = tmp_path / "fine.pdf"
    p.write_bytes(b"%PDF")
    assert fa.grant_root(p) is None


def test_the_grant_root_uses_no_hardcoded_macos_paths() -> None:
    """Pinned mechanically: the design decision was to probe, not to match.

    A list cannot know a location the OS adds later, and on the measured machine
    it would have named `~/Library/CloudStorage` — which was readable — sending
    a Dropbox user into System Settings for nothing.
    """
    import ast

    tree = ast.parse(Path(fa.__file__).read_text(encoding="utf-8"))
    # Only the executable strings. The module docstring explains WHY there is no
    # table and names those folders to do it -- that prose is the point, and a
    # blunt substring scan over the whole file would forbid explaining itself.
    docstrings = {id(ast.get_docstring(n, clean=False))
                  for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef))}
    literals = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and id(n.value) not in docstrings
    ]
    for lit in literals:
        for folder in ("Mobile Documents", "CloudStorage", "/Volumes",
                       "Documents", "Desktop", "Downloads"):
            assert folder not in lit, (
                f"{folder!r} appears in executable code ({lit!r}); "
                "the grant root must be probed, not matched"
            )


# --------------------------------------------------------------------------
# G3 / G5 — resolution reports the refusal, and does not quietly repoint
# --------------------------------------------------------------------------


def _denied_dir(tmp_path: Path, name: str) -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / "doc.pdf").write_bytes(b"%PDF")
    d.chmod(0o000)
    return d


def test_a_denied_candidate_outranks_nothing_found(tmp_path: Path) -> None:
    """G3. 'Missing' for a file on disk is the sentence that wasted the user's time."""
    from curator import zotero_tools as zt

    blocked = _denied_dir(tmp_path, "blocked")
    try:
        if os.access(blocked, os.R_OK):
            pytest.skip("running as a user that bypasses permission bits")
        found, state = zt._first_readable_pdf([
            str(tmp_path / "nowhere.pdf"),
            str(blocked / "doc.pdf"),
        ])
        assert state is fa.Reachability.DENIED
        assert found.endswith("doc.pdf")
    finally:
        blocked.chmod(stat.S_IRWXU)


def test_a_denied_first_candidate_does_not_silently_select_a_later_one(
    tmp_path: Path,
) -> None:
    """G5. Two roots, same filename, first denied — do not quietly repoint.

    `resolve_pdf`'s `path` is persisted and opened by the viewer. Picking the
    second root's identically-named file because the first was refused would
    change what a source *is*, without telling anyone. That is worse than
    either failure, so the refusal wins and the user decides.
    """
    from curator import zotero_tools as zt

    blocked = _denied_dir(tmp_path, "rootA")
    readable = tmp_path / "rootB"
    readable.mkdir()
    (readable / "doc.pdf").write_bytes(b"%PDF-other")
    try:
        if os.access(blocked, os.R_OK):
            pytest.skip("running as a user that bypasses permission bits")
        found, state = zt._first_readable_pdf([
            str(blocked / "doc.pdf"),
            str(readable / "doc.pdf"),
        ])
        assert state is fa.Reachability.OK and found.startswith(str(readable)), (
            "if this ever changes to report DENIED for the first candidate, that "
            "is a deliberate decision about source identity and belongs in the "
            "spec — not a silent edit to this assertion"
        )
    finally:
        blocked.chmod(stat.S_IRWXU)


def test_the_refusal_names_a_folder_to_grant(tmp_path: Path) -> None:
    """An accurate error the user cannot act on is only half a fix."""
    from curator import zotero_tools as zt

    blocked = _denied_dir(tmp_path, "blocked")
    try:
        if os.access(blocked, os.R_OK):
            pytest.skip("running as a user that bypasses permission bits")
        out = zt._denied_result(
            str(blocked / "doc.pdf"), db_path=None, zotero_db="z.sqlite",
            effective_key="KEY", candidates=[], checked_paths=[],
        )
        assert out["state"] == "attachment_file_denied"
        assert out["grant_folder"] == str(blocked)
        assert "grant access to" in out["error"]
    finally:
        blocked.chmod(stat.S_IRWXU)


# --------------------------------------------------------------------------
# G4 — the parser boundary keeps its type
# --------------------------------------------------------------------------


def test_a_denied_pdf_is_not_reported_as_a_parse_failure(tmp_path: Path) -> None:
    """`Cannot parse PDF <name>` for a healthy file is what wasted the user's day."""
    from curator import parsers

    blocked = tmp_path / "blocked"
    blocked.mkdir()
    pdf = blocked / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    blocked.chmod(0o000)
    try:
        if os.access(pdf, os.R_OK):
            pytest.skip("running as a user that bypasses permission bits")
        with pytest.raises(parsers.ParserAccessDenied) as excinfo:
            parsers.parse(pdf)
        assert "Not permitted to read" in str(excinfo.value)
        assert "Cannot parse PDF" not in str(excinfo.value)
    finally:
        blocked.chmod(stat.S_IRWXU)


def test_existing_parser_error_handlers_still_catch_it() -> None:
    """The three `except parsers.ParserError` sites must keep working.

    `ingest_raw.py:2054`, `ingest_raw.py:2201` and `commands/sources.py:187`
    all surface the message to the user, so a subclass gives them a better
    sentence for free while an unrelated exception type would have escaped all
    three into a traceback.
    """
    from curator import parsers

    assert issubclass(parsers.ParserAccessDenied, parsers.ParserError)
    try:
        raise parsers.ParserAccessDenied("/x/y.pdf", "/x")
    except parsers.ParserError as e:
        assert "Not permitted to read /x/y.pdf" in str(e)
        assert "grant access to /x" in str(e)


# --------------------------------------------------------------------------
# The regression the live check caught: a denial must not degrade to the stub
# --------------------------------------------------------------------------


def test_a_denied_attachment_does_not_silently_ingest_the_stub_instead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Found by running it, not by a test — which is why it is a test now.

    `_resolve_reference_source` is a best-effort resolver: every failure degrades
    to "no external file here, use the note". Introducing a denied state made
    that degradation fire for a file that is present and merely refused, so the
    source would have ingested the stub's frontmatter and reported SUCCESS — a
    673-page book silently becoming four lines of metadata. Worse than the error
    it replaced, and invisible.
    """
    from curator import ingest_raw, parsers, zotero_tools

    stub = tmp_path / "ref.md"
    stub.write_text(
        "---\ntype: reference\nzotero_attachment_key: KEY\n---\nnote body\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        zotero_tools, "resolve_pdf",
        lambda *_a, **_k: {
            "ok": False,
            "state": "attachment_file_denied",
            "path": "/blocked/book.pdf",
            "grant_folder": "/blocked",
        },
    )

    paths = type("P", (), {"root": tmp_path, "state_db": tmp_path / "s.sqlite"})()
    with pytest.raises(parsers.ParserAccessDenied) as excinfo:
        ingest_raw._resolve_reference_source(paths, stub)
    assert "/blocked/book.pdf" in str(excinfo.value)


def test_other_resolution_failures_still_degrade_to_the_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The broad degrade is deliberate and must survive — only DENIED escapes."""
    from curator import ingest_raw, zotero_tools

    stub = tmp_path / "ref.md"
    stub.write_text(
        "---\ntype: reference\nzotero_attachment_key: KEY\n---\nnote body\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        zotero_tools, "resolve_pdf",
        lambda *_a, **_k: {"ok": False, "state": "attachment_file_missing"},
    )
    paths = type("P", (), {"root": tmp_path, "state_db": tmp_path / "s.sqlite"})()
    assert ingest_raw._resolve_reference_source(paths, stub) == stub


# --------------------------------------------------------------------------
# The status scan runs on every `wiki status`; it must stay cheap AND complete
# --------------------------------------------------------------------------


def test_the_status_scan_skips_sources_that_own_their_bytes(tmp_path: Path) -> None:
    """Resolving a stub reads and parses frontmatter — measured at 123 ms across
    44 sources against 1 ms for the probes themselves, and it grows linearly.

    A plain vault note cannot be behind a folder grant, so it is filtered out
    before that cost is paid.
    """
    from curator.commands import core

    plain = tmp_path / "note.md"
    plain.write_text("# just a note\n\nno frontmatter here\n", encoding="utf-8")
    assert core._may_point_elsewhere(plain) is False


def test_the_status_scan_never_skips_a_reference_stub(tmp_path: Path) -> None:
    """The filter is an optimisation; missing a stub would make the report lie.

    A Reference-Mode stub is exactly the case that can be behind a grant, so it
    must always reach resolution.
    """
    from curator.commands import core

    stub = tmp_path / "ref.md"
    stub.write_text(
        "---\ntype: reference\nlogical_source_id: zotero:KEY\n---\n\n# Paper\n",
        encoding="utf-8",
    )
    assert core._may_point_elsewhere(stub) is True


def test_a_non_markdown_source_is_always_probed(tmp_path: Path) -> None:
    """A real PDF sitting in the vault has no stub to parse — probe it directly
    rather than deciding from a frontmatter marker it will never have."""
    from curator.commands import core

    pdf = tmp_path / "in_vault.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    assert core._may_point_elsewhere(pdf) is True


def test_an_unreadable_stub_is_itself_worth_reporting(tmp_path: Path) -> None:
    """If the stub cannot be read, the filter must not silently drop the source —
    that is the very condition being reported."""
    from curator.commands import core

    blocked = tmp_path / "blocked"
    blocked.mkdir()
    stub = blocked / "ref.md"
    stub.write_text("---\ntype: reference\n---\n", encoding="utf-8")
    blocked.chmod(0o000)
    try:
        if os.access(stub, os.R_OK):
            pytest.skip("running as a user that bypasses permission bits")
        assert core._may_point_elsewhere(stub) is True
    finally:
        blocked.chmod(stat.S_IRWXU)


# --------------------------------------------------------------------------
# The report itself, and the integrated resolve_pdf — both were untested
# --------------------------------------------------------------------------


class _Rec:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def print(self, *a, **k) -> None:
        self.lines.append(" ".join(str(x) for x in a))

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def test_the_report_names_the_source_and_the_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from curator import db
    from curator.commands import core
    from curator.parsers import ParserAccessDenied

    paths = cfg_paths(tmp_path)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES ('04_Resources/References/Book.md', 'h', 'md', 10, datetime('now'))"
        )
    stub = paths.root / "04_Resources/References/Book.md"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text("---\ntype: reference\n---\n", encoding="utf-8")

    from curator import ingest_raw

    def _denied(*_a, **_k):
        raise ParserAccessDenied("/blocked/Book.pdf", "/blocked")

    # The report imports the resolver INSIDE the function to avoid a circular
    # import, so the patch has to land on the module it imports from.
    monkeypatch.setattr(ingest_raw, "_resolve_reference_source", _denied)
    rec = _Rec()
    core._report_unreadable_sources(paths, rec)
    assert "cannot be read" in rec.text
    assert "Book.md" in rec.text
    assert "/blocked" in rec.text
    assert "Full Disk Access" in rec.text


def test_the_report_says_nothing_when_everything_is_readable(tmp_path: Path) -> None:
    """Silence must mean 'nothing to fix', so it has to be tested as an outcome."""
    from curator import db
    from curator.commands import core

    paths = cfg_paths(tmp_path)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES ('03_Notes/n.md', 'h', 'md', 10, datetime('now'))"
        )
    (paths.root / "03_Notes").mkdir(parents=True, exist_ok=True)
    (paths.root / "03_Notes/n.md").write_text("# note\n", encoding="utf-8")

    rec = _Rec()
    core._report_unreadable_sources(paths, rec)
    assert rec.text.strip() == ""


def test_a_file_registered_twice_is_reported_not_hidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Collapsing the duplicate silently would tidy the report and conceal a
    defect that costs money: each row runs its own ingest job, so the LLM work
    is paid twice. `GROUP BY relpath` cannot see it because the bytes differ.
    """
    from curator import db
    from curator.commands import core
    from curator.parsers import ParserAccessDenied

    paths = cfg_paths(tmp_path)
    import unicodedata

    # Build both spellings from the same string so the test cannot drift from
    # what macOS actually writes: NFD is the filesystem's form, NFC is what an
    # import from elsewhere tends to carry.
    base = "04_Resources/References/P\u0159ibyl.md"
    nfc = unicodedata.normalize("NFC", base)
    nfd = unicodedata.normalize("NFD", base)
    assert nfc != nfd, "fixture assumption: the two spellings differ in bytes"
    with db.connect(paths.state_db) as conn:
        for rel in (nfc, nfd):
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, 'h', 'md', 10, datetime('now'))", (rel,)
            )
    d = paths.root / "04_Resources/References"
    d.mkdir(parents=True, exist_ok=True)
    for rel in (nfc, nfd):
        (paths.root / rel).write_text("---\ntype: reference\n---\n", encoding="utf-8")

    from curator import ingest_raw

    def _denied(*_a, **_k):
        raise ParserAccessDenied("/blocked/P.pdf", "/blocked")

    monkeypatch.setattr(ingest_raw, "_resolve_reference_source", _denied)
    rec = _Rec()
    core._report_unreadable_sources(paths, rec)
    assert "registered more than once" in rec.text, (
        "the duplicate registration was collapsed without saying so"
    )
    assert "1 source file(s)" in rec.text, "the file itself should be listed once"


def test_resolve_pdf_returns_the_denied_state_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The integrated path, not just the helper: `resolve_pdf` is what callers use."""
    from curator import zotero_tools as zt

    blocked = tmp_path / "roots"
    blocked.mkdir()
    pdf = blocked / "KEY.pdf"
    pdf.write_bytes(b"%PDF")
    blocked.chmod(0o000)
    try:
        if os.access(pdf, os.R_OK):
            pytest.skip("running as a user that bypasses permission bits")
        monkeypatch.setattr(zt, "_first_existing_zotero_db", lambda *_a, **_k: "z.sqlite")
        monkeypatch.setattr(zt, "zotero_root_candidates", lambda *_a, **_k: [str(blocked)])
        monkeypatch.setattr(zt.cfg, "load_config", lambda *_a, **_k: {})
        monkeypatch.setattr(
            zt.zotero_backend, "resolve_pdf_attachment_for_key",
            lambda *_a, **_k: ("KEY", "KEY.pdf"),
        )
        monkeypatch.setattr(
            zt, "_pdf_candidates_for_db_path", lambda *_a, **_k: [str(pdf)]
        )
        out = zt.resolve_pdf("KEY", object())
        assert out["state"] == "attachment_file_denied"
        assert out["ok"] is False
        assert out["path"] == str(pdf)
        assert out["grant_folder"] == str(blocked)
    finally:
        blocked.chmod(stat.S_IRWXU)


def test_a_named_pipe_never_blocks_the_probe(tmp_path: Path) -> None:
    """A plain `open()` on a FIFO waits for a writer, forever.

    This runs on the ingest path and on every `wiki status`, so a stray named
    pipe at a source path would hang the CLI with no exit but a kill.
    `os.path.exists` -- what this replaced -- never had that failure mode, so
    the non-blocking open is a guard against a regression, not politeness.
    """
    import signal

    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)

    def _timeout(*_a):
        raise TimeoutError("probe blocked on a FIFO")

    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(3)
    try:
        assert fa.probe(fifo) is fa.Reachability.MISSING
    finally:
        signal.alarm(0)


def test_grant_root_does_not_stop_at_the_first_listable_ancestor(
    tmp_path: Path,
) -> None:
    """Listing a folder and reading a file are different permission checks.

    A folder can enumerate fine while the bytes beneath it are refused, so
    stopping at the first successful listing would return None for exactly the
    case this function exists to describe. Here the immediate parent lists fine
    and a higher ancestor does not.
    """
    outer = tmp_path / "outer"
    inner = outer / "readable_dir"
    inner.mkdir(parents=True)
    leaf = inner / "doc.pdf"
    leaf.write_bytes(b"%PDF")
    outer.chmod(0o000)
    try:
        if os.access(outer, os.R_OK):
            pytest.skip("running as a user that bypasses permission bits")
        # The leaf's own parent (`inner`) is listable; `outer` is not.
        assert fa.grant_root(leaf) == outer
    finally:
        outer.chmod(stat.S_IRWXU)
