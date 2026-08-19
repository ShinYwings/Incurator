# Briefing: the system cannot tell a missing file from a forbidden one

Date: 2026-08-20 | Author: main agent (measured on the live vault and this machine)

## 1. What happened

Ingesting a Zotero-referenced PDF failed with:

```
parse failed: Cannot parse PDF MultipleViewGeometryHartley - .pdf:
Failed to open file '/Users/…/Mobile Documents/…/MultipleViewGeometryHartley - .pdf'
```

The file is fine. 21 MB, materialised on disk (`st_blocks=41592`), not an iCloud
placeholder, and it opens instantly in Finder. The process was denied.

The user is sent to look for a corrupt PDF that does not exist.

## 2. The measurement that decides this plan's shape

**`os.access(path, R_OK)` returns True for a file that cannot be opened.**

```
exists()       : True
is_file()      : True
os.access R_OK : True
open()         : PermissionError errno=1 Operation not permitted
```

This kills the obvious fix. The audit in `USER_REPORT.md` proposed "add a
readability check" and counted `os.access`/`R_OK` usage as the missing piece —
**that proposal does not work.** `access()` consults POSIX permission bits;
macOS TCC denies at a layer below, so the bits say yes and the kernel says no.

Any design in this Arena that relies on a predicate cheaper than an actual
`open()` is wrong, and this is the measurement that proves it.

## 3. The systemic shape

Swept the external-file surface:

| module | `exists()` / `is_file()` | readability check |
|---|---|---|
| `zotero.py` | 8 | 0 |
| `source_tools.py` | 5 | 0 |
| `zotero_integration.py` | 4 | 0 |
| `asset_identity.py` | 3 | 0 |
| `zotero_tools.py` | 1 | 0 |
| `path_refs.py` | 0 | 0 |

`PermissionError` appears **once** in the whole backend (`commands/core.py:121`,
redundantly — it is an `OSError` subclass beside `OSError`). The plugin has one
`accessSync` against 41 `existsSync`/`statSync`.

The deciding helper names the assumption out loud:

```python
def _first_existing_pdf(candidates: list[str]) -> str:   # zotero_tools.py:294
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
```

It picks a file, `resolve_pdf` declares `ok: True`, and the parser
(`parsers/pdf.py:156`) wraps the resulting `PermissionError` as
`Cannot parse PDF`.

## 4. The root is the contract, not the code

`SYSTEM_BEHAVIOR.md:963-966` mandates three failure states — `db_missing`,
`attachment_key_missing`, `attachment_file_missing` — and the code implements
**all three faithfully** (`zotero_tools.py:84, 226, 241, 310, 340`).

This is not drift. **The taxonomy has no state for "present but not readable"**,
so `attachment_file_missing` is the only thing the code can honestly return for
a 21 MB file sitting on disk. Fixing this in code alone would put the
implementation ahead of its spec, which this project treats as both being wrong.

## 5. A second confusion the same area carries

`zotero_root_candidates()` returns one list mixing two different kinds of root:

- the **data directory** (`~/Zotero`) — holds `zotero.sqlite`; the index that
  resolves `zotero:<key>` and records where attachments live.
- the **attachment directory** — from `extensions.zotero.baseAttachmentPath` /
  `extensions.zotmoov.dst_dir`; holds the bytes. Often iCloud, Dropbox, external.

Visible at `zotero_tools.py:30-35`, where `_db_candidates` probes every entry —
including attachment directories — for `zotero.sqlite`.

They are **separate macOS grants**. The data directory being readable says
nothing about the attachment directory, and that split is exactly this failure:
discovery succeeded, so the precise path was known, and `open()` was denied.

## 6. What is protected, measured on this machine

| Folder | Reachable without a grant? |
|---|---|
| `~/Zotero` | yes |
| `~/Library/CloudStorage` | yes |
| `/Volumes` | yes (top level) |
| `~/Documents`, `~/Desktop`, `~/Downloads` | **no** |
| `~/Library/Mobile Documents` (iCloud) | **no** |

Not a cloud question: an attachment directory under `~/Documents/Zotero` is
denied with no cloud involved.

## 7. Questions for the Arena

1. Given `os.access` is useless here, what is the cheapest reliable probe, and
   what does it cost on a path that is fine? An ingest resolves many files.
2. Where does the new state live — a fourth value in the existing taxonomy, or a
   dimension beside it? Whichever, the spec changes first.
3. How far does the state have to travel? `resolve_pdf` → `_resolve_reference_source`
   → the parser → the job error → the plugin. Every hop currently flattens it.
4. What does the user see, and where? A job error is the worst place to learn
   this; the dashboard knows which sources are unreadable.
5. Do the two Zotero root kinds get split now, or is that a separate change?

Constraint: this is one release. It fixes the ability to *say* "denied". It does
not add a folder picker, does not grant anything, and does not change what the
backend is permitted to read (ROADMAP 8).
