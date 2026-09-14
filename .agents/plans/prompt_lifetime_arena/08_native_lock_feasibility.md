# Native session lock feasibility gate

Date: 2026-09-14. Read-only package/source audit; no dependency installed in the
repository, no production files accessed, no application code changed.

## Selected implementable path

Use exact `fs-native-extensions@1.4.0`, with its shipped Node-API binaries and
an explicitly matching Python adapter. Do not write a new native addon and do
not use the latest package's Node-API 9 binaries. This amends the session
consensus's Linux primitive: Linux uses open-file-description record locks,
macOS uses `flock`, Windows uses `LockFileEx`. The primitive must match between
Python and Node on each platform. A Linux Python `flock` paired with this
package's `F_OFD_SETLK` does not provide the required exclusion.

Pin the package exactly, lock its dependency graph, preserve its Apache-2.0
license, and distribute the platform artifacts as part of the plugin. Package
1.4.0 is a concrete compatibility candidate, not a claim of completed runtime
qualification. Its native runtime and cross-language tests remain release gates.

## Published artifact evidence

Downloaded npm registry tarballs into `/tmp/incurator-native-lock.VAY8g2` with
`npm pack --pack-destination`; no install scripts ran. Inspected tar inventories,
package source and macOS arm64 binary symbols/disassembly using `nm` and `otool`.

| Sampled release | Node binary evidence | Shipped desktop Node prebuilds |
| --- | --- | --- |
| 1.0.0 | Source uses Node-API, no explicit API version; includes `napi_get_uv_event_loop` and libuv calls | None in published tarball |
| 1.2.0 | Legacy `napi_module_register` registration, no exported requested-API function; cannot infer full runtime minimum from the module registration integer | Darwin x64/arm64, Linux x64/arm64, Windows x64 |
| 1.3.0 | Actual Darwin arm64 `node_api_module_get_api_version_v1` returns 8 | Darwin, Linux, Windows, each x64/arm64 |
| 1.4.0 | Actual Darwin arm64 `node_api_module_get_api_version_v1` returns 8 | Darwin, Linux, Windows, each x64/arm64 |
| 1.5.1 | Published CMake explicitly defines `NAPI_VERSION=9` | Darwin, Linux, Windows, each x64/arm64 |

This is a sampled release audit, not a claim to have tested every patch release
or binary. 1.4.0's tarball SHA-256 is
`def5e911aa60cc3215e77e93ca9d6124cf4bad52d50ccb09e8a5c84f75ca8280`.
Tarball source: [npm 1.4.0 artifact](https://registry.npmjs.org/fs-native-extensions/-/fs-native-extensions-1.4.0.tgz).
Current source explains the later API increase:
[upstream CMake](https://github.com/holepunchto/fs-native-extensions/blob/main/CMakeLists.txt).

The manifest remains desktop-only and `minAppVersion: 1.1.0`. Node-API 8 is
supported by Node 16 and by designated earlier Node releases; Node-API 9 starts
at Node 18.17/20.3. Electron 18 shipped Node 16.13.2. Obsidian's 1.1.9 installer
upgrade to Electron 21 required a separate installer download, so app version
alone is not proof of runtime version. Sources:
[Node API matrix](https://nodejs.org/api/n-api.html#node-api-version-matrix),
[Electron 18](https://www.electronjs.org/blog/electron-18-0),
[Obsidian installer note](https://obsidian.md/changelog/2022-12-23-desktop-v1.1.9/).

Therefore API 8 avoids the known Node 16 incompatibility, but the exact oldest
supported Obsidian installer still needs a real load/lock smoke test. Check
`process.versions.napi` and actual load success before canonical writes; do not
silently raise minAppVersion or label all 1.1 installations verified. The addon
also imports libuv symbols, so Node-API version alone is not a complete ABI proof.

## Exact lock contract

1.4.0 `index.js` exposes synchronous `tryLock(fd, offset=0, length=0, opts={})`.
Default is exclusive. It returns false only for native `EAGAIN`; other errors
throw. `unlock(fd, offset=0, length=0)` releases the same range. Poll tryLock
asynchronously; never call its blocking wait API on the plugin UI path.

- macOS `src/mac.c`: offset and length must both be zero. Uses
  `flock(fd, LOCK_EX | LOCK_NB)` and `flock(fd, LOCK_UN)`.
- Linux `src/linux.c`: `fcntl(fd, F_OFD_SETLK, &flock)` with `l_start=0`,
  `l_len=0`, `l_pid=0`, `l_whence=SEEK_SET`, and F_WRLCK/F_UNLCK. The zero length
  means through EOF/future extension; ownership follows the open file description.
- Windows `src/win.c`: `LockFileEx`, FAIL_IMMEDIATELY plus EXCLUSIVE_LOCK,
  offset zero; zero length expands to SIZE_MAX. For these 64-bit builds use
  low/high length words both `0xffffffff`. UnlockFileEx receives identical range.

Python macOS uses `fcntl.flock`. Python Windows uses `msvcrt.get_osfhandle` on
its own open file descriptor and ctypes LockFileEx/UnlockFileEx with the stated
range. Python Linux uses `fcntl.F_OFD_SETLK` with a ctypes-defined native
`struct flock`, converted to bytes for `fcntl.fcntl`. On supported Linux x64
and arm64 LP64, assert offsets type=0, whence=2, start=8, len=16, pid=24 and
size=32. Use native alignment and signed 64-bit offsets, zero-initialize padding,
and verify against a tiny C sizeof/offsetof fixture in platform CI. Do not use a
guessed packed Python format or silently fall back to flock when OFD is missing.
Nonblocking contention EACCES/EAGAIN returns busy; unexpected errors fail closed.
Obtain the F_OFD_SETLK constant from the Python platform, never a cross-platform
literal. Close-on-exec and explicit descriptor lifetime prevent inherited locks.

This adapter is local session locking; it need not replace any independent
producer-lifetime locking primitive provided each lock's participants agree.

## Smallest complete packaging change

The following four real delivery paths currently copy only three plugin files:

| Path | Required change |
| --- | --- |
| `plugin/esbuild.config.mjs` | Produce and deploy a native artifact directory/manifest alongside main.js; handle configured output directory and watch builds |
| `setup.sh:62` | Validate and copy the native artifact set with the plugin files |
| `backend/src/curator/commands/core.py:171` (`wiki init`) | Same artifact validation/copy; missing required artifact cannot report successful installation |
| `plugin/main.ts:1423` self-update | Prevalidate full set, stage binaries first, activate matching JS/manifest only after verification |

Keep the package's runtime loader external to esbuild in a self-contained
installed directory containing its JS, package.json, required transitive loader
dependencies and selected prebuilds. Resolve it relative to the installed plugin
directory, not the repository's node_modules or process.cwd. A deterministic
artifact manifest records relative paths, platform/architecture, required API
level and SHA-256. The build may select host artifacts for local installation;
release distribution must contain every supported target. Avoid bundling
`require-addon` while changing its `__filename` assumptions. Test installed
artifact resolution from a temporary unrelated working directory.

Native DLLs may remain loaded on Windows during self-update. Use a versioned or
content-addressed artifact directory so an update never overwrites a loaded
binary; keep the prior directory until no loaded plugin uses it. Verify new
artifacts before replacing entry files. Runtime activation checks must cover
the selected native manifest/digest in addition to existing main.js version/hash.
Digest mismatch or unloadable native code blocks session mutation visibly.

## Qualification that remains before release

Run shipped 1.4.0 binaries under the oldest supported Electron runtime and a
current runtime on Darwin/Linux/Windows x64 and arm64. The native dependency
source audit is not that test. Every platform test starts Node and Python actors,
proves contention in both directions, kills each owner in turn, and proves
release without lease timeouts. Include unlocked malformed descriptor errors,
unsupported primitive failure, installed-directory load, digest mismatch,
updating while the old native module is loaded, and full session commit tests.

No architectural uncertainty remains in the primitive choice. The concrete
remaining obstacle is executing the supported-platform runtime matrix and
confirming the oldest permitted Obsidian installer, rather than inventing another
storage authority or reducing offline save/CLI prune capability.

## Executed local qualification (2026-09-14)

Installed exactly `fs-native-extensions@1.4.0` using `npm install --ignore-scripts
--save-exact --prefix /tmp/incurator-lock-smoke.C8k7x3`. This isolated directory
contains its six installed packages and lockfile; repository dependencies were
not modified. The test uses the published prebuild, not a local compilation.

Executed `/tmp/incurator-lock-smoke.C8k7x3/smoke.py` with Python 3.14.7. Node
reported v22.14.0, Node-API 10, Darwin arm64. Every Node process ran with `/`
as its working directory and loaded the isolated package by absolute path.

| Actual subprocess check | Result |
| --- | --- |
| Isolated package/addon loads from unrelated working directory | PASS |
| Python holds flock; Node `tryLock` returns false | PASS |
| Kill Python owner; fresh Node acquires and explicitly unlocks | PASS |
| Node holds `tryLock`; Python nonblocking flock raises BlockingIOError | PASS |
| Kill Node owner; Python acquires and explicitly unlocks | PASS |

Both holders were real independent processes, forcibly terminated only after
the contender had observed contention; readiness used pipe output, not an
assumed startup delay. The final run exited zero. An initial harness syntax typo
was corrected before this successful run; it failed before addon loading and
did not exercise a lock. The only lock file created was the disposable probe
file under the stated temporary directory. No vault or session file was used.

This proves current macOS arm64 Node/Python exclusion and kernel release with
the published artifact and its isolated loader. It does not establish oldest
Electron compatibility, Windows/Linux behavior, six-target ABI compatibility,
or correctness of the not-yet-implemented production artifact copier.
