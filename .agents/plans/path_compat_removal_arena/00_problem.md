# Briefing: Remove Portable-Path Backward Compatibility

Date: 2026-07-04

`wiki status` on macOS fails before rendering because the device-local
`state.sqlite` still has pre-v0.29 absolute-path source columns. The backend
raises an instruction to run `wiki paths migrate --apply`. The intended product
contract has no user-facing path migration workflow: DB rows retain portable
identity and each backend resolves physical files from its own repo-local
`.cache/config/`.

The release must remove retired path-format adapters and commands while keeping
the current Zotero-key and named-root runtime resolvers. The current production
DB must be backed up and normalized once before deploying the new backend.
