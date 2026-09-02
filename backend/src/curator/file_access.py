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
import errno
import os
import stat
import sys
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
    #: The file is registered and present as a placeholder, but its bytes are not
    #: on this machine — macOS has evicted it to iCloud-only. Deliberately NOT
    #: `DENIED`: no permission was revoked, so there is no folder to grant and a
    #: picker would be a no-op. Deliberately NOT `MISSING` either, because the
    #: file has not been deleted and telling the user it is gone is wrong.
    NOT_DOWNLOADED = "not_downloaded"


#: How a dataless iCloud placeholder fails when it cannot be materialised. The
#: File Provider surfaces these rather than a permission error, which is why they
#: were landing in the catch-all and being reported as a missing file.
_EVICTED_ERRNOS = frozenset(
    e for e in (
        getattr(errno, "ENODATA", None),
        getattr(errno, "EDEADLK", None),
        getattr(errno, "ETIMEDOUT", None),
    ) if e is not None
)


def describe(path: Path) -> str:
    """One sentence a user can act on, matched to why the path is unusable.

    The wording differs because the ACTION differs: a denial is fixed by granting
    a folder, an eviction by downloading the file, and neither fix helps the
    other. Conflating them is what sends someone to System Settings for a file
    that was never blocked.
    """
    verdict = probe(path)
    if verdict is Reachability.OK:
        return f"{path} is readable."
    if verdict is Reachability.DENIED:
        folder = grant_root(path)
        if not folder:
            return f"{path} cannot be read: this process is not permitted to."
        # The FIX differs by platform, so the sentence has to. On macOS a denial
        # is usually TCC and the user grants a folder in System Settings. On
        # Linux there is no such grant: the same denial is filesystem
        # permissions, and telling someone to "grant access to a folder" sends
        # them looking for a dialog their OS does not have.
        if sys.platform == "darwin":
            return (
                f"{path} cannot be read: this process is not permitted to. "
                f"Grant access to {folder}."
            )
        return (
            f"{path} cannot be read: this process is not permitted to. Check the "
            f"permissions on {folder} — it must be readable by the user running "
            "Incurator."
        )
    if verdict is Reachability.NOT_DOWNLOADED:
        if sys.platform == "darwin":
            return (
                f"{path} is not downloaded to this machine — iCloud is keeping it "
                "online-only. Open it once in Finder, or turn off Optimise Storage "
                "for that folder, then retry."
            )
        return (
            f"{path} is not downloaded to this machine — the cloud client is "
            "keeping it online-only. Open it once so the client fetches it, "
            "then retry."
        )
    return f"{path} is not there."


def probe(path: Path) -> Reachability:
    """Answer by doing what the caller is about to do: open it and read a byte.

    One byte rather than zero. Opening a directory succeeds on some platforms
    and a dataless placeholder can open without materialising, so the read is
    what makes the answer true.
    """
    try:
        # O_NONBLOCK so a FIFO with no writer cannot block the process. A plain
        # `open()` on one waits for a writer, and this runs on the ingest path
        # and on every `wiki status` -- a stray named pipe at a source path
        # would hang the CLI with no way out but a kill. `os.path.exists`, which
        # this replaced, never had that failure mode, so guarding it is not
        # optional politeness.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                # A directory, FIFO, socket or device is not a source we could
                # read anyway; MISSING keeps it out of the denial report rather
                # than inventing a permission problem.
                return Reachability.MISSING
            os.read(fd, 1)
        finally:
            os.close(fd)
        return Reachability.OK
    except PermissionError:
        return Reachability.DENIED
    except FileNotFoundError:
        return Reachability.MISSING
    except IsADirectoryError:
        return Reachability.MISSING
    except OSError as e:
        if e.errno in _EVICTED_ERRNOS:
            # A dataless placeholder that could not materialise. `stat` says the
            # file is there and the read says it is not, which is why a
            # metadata-based check calls it present and this one used to call it
            # gone. Naming a folder to grant here would be the failure this
            # module was written about: the permission is fine, the bytes are in
            # iCloud.
            return Reachability.NOT_DOWNLOADED
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

    Every ancestor is checked rather than stopping at the first readable one.
    Listing a directory and reading a file are DIFFERENT macOS permission
    checks, so a folder can enumerate fine while the bytes beneath it are
    refused; breaking early on the first successful listing would return None
    for exactly the case this exists to describe. The walk is bounded by path
    depth and runs only on the denial path.

    Deliberately not a lookup table of macOS locations. A table cannot know a
    directory the OS adds later, and on the machine this was measured against it
    would have named `~/Library/CloudStorage` — readable there — sending the
    user to change a setting that was never the problem. Probing asks the
    machine in front of us.
    """
    if probe(path) is not Reachability.DENIED:
        return None

    # Resolve first. `probe` follows symlinks — `os.open` does — while
    # `Path.parents` does not, so without this the two disagree about what they
    # are looking at: probe reports the TARGET's denial and the walk climbs the
    # LINK's parents, which are readable, and answers None.
    try:
        path = path.resolve(strict=False)
    except OSError:
        pass

    shallowest_denied: Path | None = None

    # The path ITSELF may be the denied node, and for a root it usually is.
    # Walking only `parents` answered None for `~/Downloads` and for
    # `~/Library/Mobile Documents` — both measured DENIED at the same moment —
    # so the grant button on a Dashboard row would have had nothing to open, on
    # exactly the rows it exists for. A file inside a denied folder still
    # resolves to the folder, which is the shape production depends on.
    for candidate in (path, *path.parents):
        try:
            with os.scandir(candidate) as it:
                next(iter(it), None)
        except PermissionError:
            shallowest_denied = candidate
        except NotADirectoryError:
            # A denied FILE: its bytes are refused but it is not a folder, so it
            # is never the thing to grant. Its parent is.
            continue
        except OSError:
            continue
    return shallowest_denied
