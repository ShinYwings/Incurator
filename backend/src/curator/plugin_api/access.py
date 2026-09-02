"""Which folders Incurator can read, and which folder to grant when it cannot.

`file_access` has been able to answer this since it existed — `probe` classifies
a path, `grant_root` names the shallowest folder the user must grant. Nothing
ever asked it on the user's behalf: a `grep` of `plugin/src` for either name
returned zero hits, so a vault whose PDFs moved into a cloud folder failed with
no way for anyone to learn why.

That is the incident this release came from. Ten thousand spans failed to
hydrate, the cause was a folder permission, and finding it took an agent reading
a database by hand.

**The decision lives here, not in the plugin.** The plugin renders rows. A second
implementation of "what is a root" or "is it readable" in TypeScript is a second
thing to drift, and this repo has paid for that shape four times.
"""

from __future__ import annotations

import logging

from pathlib import Path
from typing import Any

from .. import config as cfg
from .. import file_access, path_refs

_log = logging.getLogger(__name__)


def _state_of(path: Path) -> str:
    """The verdict, with the directory trap handled once.

    `probe` opens a path as a FILE — it is built for source files — so a
    perfectly readable DIRECTORY comes back MISSING. A report built on the raw
    verdict would mark every healthy root missing and send the user hunting for
    folders that are right where they left them.

    A denial is NOT affected: opening a directory you may not read raises
    PermissionError exactly as a file does, so DENIED arrives correctly and only
    the OK case needs disambiguating.
    """
    verdict = file_access.probe(path)
    if verdict is file_access.Reachability.MISSING and path.is_dir():
        return "ok"
    return verdict.value


def access_report(
    paths: cfg.WikiPaths,
    *,
    config: dict | None = None,
    extra_roots: dict[str, Path] | None = None,
) -> list[dict[str, Any]]:
    """One row per root worth telling the user about.

    A root the user never configured is OMITTED rather than reported missing. A
    tab that lists absent things as problems is a tab of noise, and noise is what
    stops someone reading the one row that matters.
    """
    if config is None:
        try:
            config = cfg.load_config(paths)
        except Exception:  # noqa: BLE001 - a broken config is `wiki lint`'s to report
            config = {}

    candidates: list[tuple[str, Path]] = [("Vault", paths.root)]

    resources = paths.root / "04_Resources"
    if resources.exists():
        candidates.append(("References (04_Resources)", resources))

    # Zotero keeps its index and its bytes in DIFFERENT directories, granted
    # separately. Showing one and calling it done is a mistake this repo has
    # already made; both get a row when both are configured.
    for key, root in path_refs.configured_roots(config or {}).items():
        candidates.append((f"Configured root: {key}", root))

    # Zotero's ATTACHMENT directory is discovered from its prefs, not from our
    # config, and on this machine it is the iCloud folder that caused the
    # incident. Listing only `path_roots` showed the DATA dir and left the one
    # that was actually denied off the report entirely — the exact conflation
    # this repo has made before.
    try:
        from .. import zotero_tools

        for raw_root in zotero_tools.zotero_root_candidates("", config or {}):
            candidates.append(("Zotero", Path(raw_root)))
    except Exception:  # noqa: BLE001 - a broken Zotero setup is `wiki lint`'s to report
        # Logged, not swallowed: this report exists to explain why a file could
        # not be read, so a discovery failure inside it is exactly the thing that
        # would otherwise hide the answer.
        _log.debug("could not enumerate Zotero roots for the access report", exc_info=True)

    for label, root in (extra_roots or {}).items():
        candidates.append((label, root))

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label, root in candidates:
        try:
            resolved = root.expanduser().resolve()
        except OSError:
            resolved = root
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        state = _state_of(resolved)
        # A root that is not there is not a permission problem, and a row saying
        # "missing" about a folder the user never set up is noise. Noise is what
        # stops someone reading the one row that matters. The vault itself is the
        # exception: if THAT is missing, the user needs to know.
        if state == "missing" and resolved != paths.root.resolve():
            continue
        grant = file_access.grant_root(resolved) if state == "denied" else None
        rows.append(
            {
                "label": label,
                "path": key,
                "state": state,
                "grant_folder": str(grant) if grant else "",
                "detail": file_access.describe(resolved) if state != "ok" else "",
            }
        )
    return rows
