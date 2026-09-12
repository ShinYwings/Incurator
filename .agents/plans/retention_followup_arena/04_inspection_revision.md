# Cache Inspection Revision: Isolate SQLite Reader Side Effects
Date: 2026-09-12 | Agent Persona: Independent Data Preservation Reviewer

## 1. Vulnerabilities & Flaws

The initial mode=ro design does not fully implement the promised non-mutating
candidate inspection. SQLite can create `-wal` and `-shm` beside a read-only
connection to a WAL-mode main database. Those files make the next inspection
reject a cache that the first inspection itself changed. Removing those files
from the original afterwards is unacceptable: their presence could belong to
another process, and GC has no authority to repair or checkpoint the candidate.

This is documented behavior, not a reason to suppress the sidecar guard.
SQLite's [WAL documentation, sections 4 and 5](https://sqlite.org/wal.html)
explains that read-only WAL access can create coordination files in a writable
directory, and that a WAL file may carry committed database state. Therefore
neither ignoring source sidecars nor switching the original to immutable=1
establishes the required preservation property.

Independent isolated verification used a db.init_db-created, closed database
under TemporaryDirectory, copied it to a separate TemporaryDirectory, then
called the current `_database_is_empty` on the copy. Results:

```text
copied_empty_database_recognized True
scratch_members ['state.sqlite', 'state.sqlite-shm', 'state.sqlite-wal']
original_member_names_unchanged True
original_database_bytes_unchanged True
```

No application code, live cache, vault, or production configuration was changed.
The parent reports 41 focused tests passing and two existing empty-collection
cases failing before this revision. That count is parent evidence, not a second
independent test run.

## 2. Suggested Alternatives

### Decision: accept private-copy inspection with strengthened source checks

A private temporary copy is a sound bounded correction to the inspection
boundary. The original remains the authority being evaluated; SQLite receives
only the copied bytes. Any WAL/SHM coordination belongs to the temporary
inspection workspace, which the process owns and can remove in full.

The revision must retain all of these conditions:

1. Inspect the original namespace before copying. It must still have a real
   directory, regular marker, canonical absent temporary root, and only marker
   plus optional state.sqlite. Any source WAL, SHM, rollback journal, unknown
   member, symlink, unreadable state, or existing root prevents inspection.
2. Capture the complete member-name set and relevant lstat metadata. Include
   device, inode, size, mtime_ns, and preferably ctime_ns, plus directory
   metadata. Directory change timestamps detect sidecars or other files that
   appeared and disappeared during copying. Do not compare atime: reading the
   candidate may legitimately update access time.
3. Copy the main-file bytes into a private TemporaryDirectory outside the
   candidate namespace. Do not call SQLite on the original, use backup APIs
   that first open the original, change its journal mode, or remove its
   sidecars. Normal read-only SQLite on the copy may create scratch sidecars.
4. Apply the already approved schema signature/version/logical-table emptiness
   check to that copy. Preserve failures, partial schemas and occupied rows.
   No immutable shortcut is needed on either path.
5. After copy inspection, re-read the original member set and metadata, marker
   contents, namespace identity and root absence. Compare them with the
   pre-copy observation. Any mismatch means retain, even if the copied view
   appeared empty. Ensure each current member remains regular; an inode check
   is not a substitute for rejecting a changed file type.
6. The approved Reclaimable authority must record these original observations.
   Before sweep, rerun the same inspection and compare it to the approved
   observation. Recheck source members/metadata/root immediately after the
   last copied inspection before rmtree. Count only actual removals.
7. Close the SQLite copy connection before temporary-directory cleanup. Failed
   copying, unavailable scratch storage, SQLite errors or cleanup/inspection
   errors must never fall through to deletion permission.

Why copying is legitimate here: source sidecars are rejected both before and
after the read, so the collector is not deliberately detaching a known WAL
from its main database. A normal writer beginning during copying leaves either
sidecars, modified main-file metadata, or changed directory metadata, causing
retention. A torn copy that does not parse is also retained. This is stronger
than reading only original main-file bytes and claiming they form an immutable
database.

### Limits and cost

These checks do not create an atomic lifetime reservation. A process can start
writing after the final observation and before recursive deletion. The master
plan already excludes a general shared writer-lock protocol; preserve that
limitation in implementation comments and release wording. Likewise, metadata
comparison does not defend against an adversarial actor deliberately restoring
filesystem timestamps and contents; do not market it as such.

The copy costs temporary disk space and I/O proportional to the candidate main
file. That is acceptable for this narrowly eligible class and preferable to
mutating an unknown original. An allocation/copy failure retains the candidate.
Do not add an arbitrary size cutoff or new user configuration in this patch.

### Regression additions required for this revision

- Inspect the same closed initialized WAL cache twice. Both results must be
  reclaimable, the original database bytes unchanged, and the original member
  names exactly marker plus state.sqlite. Sweeping the resulting plan must
  still collect it.
- During the controlled copy hook, create a sidecar or unknown file on the
  original. Inspection must retain it and leave that file untouched.
- During that hook, commit a durable source-independent row through an original
  database writer that then closes. The original may have no sidecars by the
  time inspection resumes; metadata revalidation must still reject the stale
  empty copy.
- Replace the original database/marker/directory while copying, or recreate the
  root, and require retention. These complement the existing post-plan cases.
- Existing committed-WAL, partial-schema unchanged, unknown-file and symlink
  regressions continue to pass. A copy exception must retain without modifying
  the original or leaking a temporary SQLite connection.

This revision changes no retention policy, schema, API or default. Update the
master plan and English/Korean descriptions of inspection before implementing
it. It is a correction to the SQLite boundary itself, not a workaround that
cleans up reader side effects after they already affected the original.
