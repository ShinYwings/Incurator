# Core Proposal: one probe that opens, one state that travels

Date: 2026-08-20 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### 1.1 The probe must open, because nothing cheaper is honest

`os.access` is out (briefing §2). The only predicate that agrees with reality is
the one reality uses:

```python
# backend/src/curator/file_access.py  (new)

class Reachability(str, Enum):
    OK      = "ok"        # opened, bytes readable
    MISSING = "missing"   # not there
    DENIED  = "denied"    # there, and this process may not read it


def probe(path: Path) -> Reachability:
    """Answer by doing what the caller will do: open it and read one byte.

    `os.access(R_OK)` returns True for a TCC-denied file (measured), so a
    permission-bit check would report OK and let the caller fail later with a
    message about something else.
    """
    try:
        with open(path, "rb") as f:
            f.read(1)
        return Reachability.OK
    except FileNotFoundError:
        return Reachability.MISSING
    except PermissionError:
        return Reachability.DENIED
    except OSError:
        return Reachability.MISSING   # a broken symlink, a dead mount
```

One byte, not zero: an empty successful `open()` on a directory or a dataless
placeholder can succeed where the first read fails.

### 1.2 Replace the predicate, keep the shape

`_first_existing_pdf` becomes `_first_readable_pdf` and returns *why* it failed:

```python
def _first_readable_pdf(candidates: list[str]) -> tuple[str, Reachability]:
    denied: str | None = None
    for candidate in candidates:
        match probe(Path(candidate)):
            case Reachability.OK:      return candidate, Reachability.OK
            case Reachability.DENIED:  denied = denied or candidate
            case _:                    continue
    # A denied candidate outranks "nothing found": it is a real file we were
    # refused, and saying "missing" about it is what sent the user hunting.
    return (denied, Reachability.DENIED) if denied else ("", Reachability.MISSING)
```

### 1.3 A fourth state in the taxonomy, and the spec goes first

`SYSTEM_BEHAVIOR.md:963-966` gains `attachment_file_denied` beside
`attachment_file_missing`. `resolve_pdf` returns it, with the path and the
folder that needs the grant:

```python
return {
    "ok": False,
    "state": "attachment_file_denied",
    "error": f"Not permitted to read {path}",
    "path": str(path),
    "grant_folder": str(_grant_root(path)),   # the folder the user must allow
}
```

`_grant_root` walks up to the first TCC-relevant ancestor (`~/Documents`,
`~/Desktop`, `~/Downloads`, `~/Library/Mobile Documents`, a `/Volumes/<vol>`),
because telling a user to grant access to one PDF is useless.

### 1.4 The parser stops relabelling

`parsers/pdf.py:156` wraps every exception as `Cannot parse PDF`. Let
`PermissionError` through unwrapped so the job error says what happened:

```python
except PermissionError:
    raise                      # a denial is not a parse failure
except Exception as e:
    raise ParserError(f"Cannot parse PDF {path.name}: {e}") from e
```

### 1.5 Where the user meets it

The job error is the worst place to learn this. `wiki status` and the plugin
dashboard already enumerate sources; a source whose file probes DENIED is
reported there with its `grant_folder` and the fix, once, rather than as a
recurring ingest failure.

## 2. Pros & Cons

**Pros.**

- One predicate, used everywhere, that cannot disagree with what the caller
  then does.
- The state is additive: `attachment_file_denied` beside the existing three,
  so no reader that switches on the old values breaks.
- The parser change is three lines and removes the actively misleading message.
- `grant_folder` makes the error actionable instead of merely accurate.

**Cons / limits.**

- **`probe` does I/O.** `exists()` is a stat; this opens and reads. On a resolve
  path that walks many candidates that is a real cost and it is unmeasured.
- It changes `_first_existing_pdf`'s selection: today the first *existing*
  candidate wins even if unreadable; after this a readable later candidate wins.
  That is intended, but it is a behavior change in resolution order.
- Only the Zotero path is covered. `source_tools.py`, `asset_identity.py` and
  the plugin's 41 `existsSync` sites keep the old assumption.
- Nothing here splits the two Zotero root kinds (briefing §5).
