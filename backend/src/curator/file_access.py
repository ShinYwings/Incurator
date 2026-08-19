"""Can this process actually read that file?

Three checks in a row answered a question nobody asked, and the user was sent
to look for a corrupt PDF that opens fine in Finder:

    exists()        -> True     it is there
    os.access R_OK  -> True     the permission bits allow it
    open()          -> PermissionError errno=1

`os.access` is the trap, and it is why this module exists rather than a one-line
helper. It consults POSIX permission bits; macOS TCC denies below them. So the
obvious fix — "add a readability check" — reports a readable file and defers the
failure to a caller that will describe it as something else entirely.

Only an actual open is honest. See SYSTEM_BEHAVIOR §12.3, which is normative.

Cost, measured over 200 iterations on real paths:

    ok       0.016 ms
    missing  0.001 ms
    denied   0.722 ms    <- two orders of magnitude dearer than a stat

The denial is expensive because a TCC refusal is not a cheap filesystem EACCES.
That is affordable only because the caller's candidate list is short (2 on the
measured vault). If resolution ever walks many roots, re-measure before assuming
this is still free.
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

_log = logging.getLogger(__name__)

__all__ = ["Reachability", "probe", "grant_root"]


class Reachability(str, Enum):
    """Why a path is or is not usable. Never collapse this to a bool.

    A bool is what left the previous resolution helper unable to say anything:
    it picked a file it could not read, reported success, and the parser failed
    citing an unrelated cause.
    """

    OK = "ok"
    MISSING = "missing"
    DENIED = "denied"


def probe(path: Path) -> Reachability:
    """Answer by doing what the caller is about to do: open it and read a byte.

    One byte rather than zero. Opening a directory succeeds on some platforms
    and a dataless placeholder can open without materialising, so the read is
    what makes the answer true.
    """
    try:
        with open(path, "rb") as handle:
            handle.read(1)
        return Reachability.OK
    except PermissionError:
        return Reachability.DENIED
    except FileNotFoundError:
        return Reachability.MISSING
    except IsADirectoryError:
        return Reachability.MISSING
    except OSError as e:
        # A broken symlink, a dead mount, a name too long. MISSING is the safe
        # direction: it is the state every caller already handles, and claiming
        # DENIED would send the user to grant a permission that is not the
        # problem. Logged because an exotic denial landing here is precisely
        # what this module would otherwise hide.
        _log.debug("probe(%s) inconclusive: %s", path, e)
        return Reachability.MISSING


def grant_root(path: Path) -> Path | None:
    """The folder a user must grant, or None if nothing is denied.

    Telling someone they cannot read one PDF is useless — permission is granted
    per folder. The answer is the SHALLOWEST ancestor that is itself denied,
    found by walking upward and probing.

    Deliberately not a lookup table of macOS locations. A table cannot know a
    directory the OS adds later, and on the machine this was measured against it
    would have named `~/Library/CloudStorage` — readable there — sending the
    user to change a setting that was never the problem. Probing asks the
    machine in front of us.
    """
    if probe(path) is not Reachability.DENIED:
        return None

    deepest_denied: Path | None = None
    for ancestor in path.parents:
        try:
            with __import__("os").scandir(ancestor) as it:
                next(iter(it), None)
        except PermissionError:
            deepest_denied = ancestor
            continue
        except OSError:
            continue
        # First readable ancestor: the one below it is the boundary.
        break
    return deepest_denied
