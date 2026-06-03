# PDF Source Registration UX Plan

## Goal

Fix the Obsidian sidechat PDF source-registration flow so it works for Zotero
PDFs, non-Zotero external PDFs, and vault-local PDFs with clear user feedback.
Remove user-facing "ingest" wording from the plugin because the product concept
is "Add/Register as Incurator source", while backend internals may still use
`ingest_jobs` for pipeline execution.

## Current Behavior

Plugin sidechat:

- Renders a small source-status badge for `pdf-page` context refs.
- For `untracked`, the badge label is currently `ingest`.
- Clicking the badge calls `onIncuratorStatusClick`.
- Zotero-managed PDFs skip the modal and call `IncuratorClient.ingestPdf(...)`
  with `importMode: "reference"`.
- Non-Zotero PDFs open `IngestDestinationModal`.
- The modal title is `Ingest Non-Zotero PDF` and the CTA is `Ingest`.
- Success/failure feedback is mostly transient `Notice` messages, and the chip
  does not always show an immediate in-progress state.
- The intended Reference Mode design is that external PDFs are not copied into
  the vault. Instead, `04_Resources` should contain a lightweight markdown
  reference/link stub and backend state should point through that stub to the
  original file.

Backend:

- `wiki plugin source import` imports or references the source.
- `wiki plugin source register` creates instant L1 and queues L2/L3.
- `wiki plugin pdf context --file-path` returns page-window context if a
  readable filesystem path is available.
- Current backend `policy=reference` avoids copying the PDF, but stores the
  absolute external path as `sources.relpath` and does not create the intended
  `04_Resources/*.md` reference stub. That needs to be fixed.

Docs/spec:

- `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.2.2.md` says untracked PDFs
  should show an explicit `"Add to Incurator"` action.
- `docs/guides/WORKFLOW_GUIDE.md` says plugin UI should show
  `"+ Add to Incurator"`.

## Product Language

Use "source" language in UI:

- `Add to Incurator`
- `Add as source`
- `Reference external file`
- `Copy into vault`
- `Building source...`
- `Queued`
- `L1 ready`, `L2 ready`, `L3 ready`, `L4 ready`

Avoid user-facing:

- `ingest`
- `ingesting`
- `import` unless specifically describing file copy/import policy

Backend internals can retain:

- `ingest_jobs`
- `ingest_raw.py`
- `IngestWorker`

Those are implementation names, not user-facing labels.

## Ownership Boundary

Backend owns:

- Source registration.
- `04_Resources` markdown reference/link stub creation for external PDFs.
- Copy/reference policy execution.
- Hashing.
- L1 generation.
- L2/L3 queueing.
- Source status and rebind.

Plugin owns:

- Current viewer context.
- User approval.
- Choosing between copy/reference when backend cannot infer safely.
- Showing progress/errors in the sidechat chip and modal.

## Required UX Changes

### Source Badge

State labels:

- `untracked` -> `Add source`
- `unknown` -> `Check source`
- `queued` -> `Queued`
- `running` -> `Building...`
- `l1_ready` -> `L1 ready`
- `l2_ready` -> `L2 ready`
- `l3_ready` -> `L3 ready`
- `l4_ready` -> `L4 ready`
- `missing` -> `Find file`
- `moved` -> `Rebind`
- `hash_drift` -> `Update source`
- `error` -> `Error`

Badge click behavior:

- `untracked`: open source-registration modal or auto-reference for known Zotero
  PDFs after a visible confirmation path.
- `unknown`: force-refresh backend status and update chip.
- `queued`/`running`: show current status and keep polling.
- `missing`/`moved`: show rebind proposal if backend has a candidate.
- `error`: show backend error and offer retry if applicable.

### Modal

Rename `IngestDestinationModal` user-facing text:

- Title: `Add PDF to Incurator`
- Description: explain that the backend will register the PDF as a source and
  create searchable context.
- CTA:
  - `Add as reference` when mode is reference.
  - `Copy and add` when mode is copy.

The TypeScript class/file may be renamed later, but user-facing strings should
change first to minimize churn.

### Progress Feedback

When the user clicks the action:

1. Immediately set local badge state to `running` with message
   `Adding source...`.
2. Disable modal CTA while backend command is running.
3. On success, set status from backend response.
4. If backend returns no usable status, show `error` in the badge, not only a
   transient notice.
5. Poll while `queued` or `running`.

### External PDF Categories

Zotero PDF:

- Prefer backend-owned Zotero resolution by attachment key.
- Register as reference.
- Create a lightweight `04_Resources` markdown reference/link stub, not a copied
  PDF.
- Do not copy into vault by default.

Other external PDF:

- Default should be `reference` if the path is stable and readable.
- Create a lightweight `04_Resources` markdown reference/link stub pointing to
  the original file.
- Offer `copy` only as an explicit exception when the file is in a
  temporary/download location or user wants vault-local durability.

Vault-local PDF:

- Register in place as a source.
- No copy modal needed unless backend proposes a different policy.

Pathless Obsidian PDF viewer:

- Do not show `Add source` as if it will work.
- Show `Viewer-only`/`No file path` state.
- Continue answering from PDF.js captured context.
- Future enhancement: support passing PDF bytes/temp-file to backend.

## Functional Bug To Verify

The user reports that clicking the current sidechat action appears to do
nothing. Likely causes to test:

- `sourcePath` missing from the context ref.
- Backend command fails but the failure is swallowed into `unknown`.
- Modal closes before status is visibly updated.
- `IncuratorClient.ingestPdf()` normalizes backend `ok=false` into an unclear
  state.
- Zotero auto-reference path calls backend without setting a local `running`
  state first.

## Implementation Steps

1. Update docs/spec first:
   - System behavior: source-registration UI language and states.
   - Plugin schema: badge labels and click behavior.
   - Workflow guide EN/KR: replace ingest UI wording with source registration.

2. Add tests:
   - `IncuratorClient.ingestPdf()` returns clear error status when import or
     register fails.
   - `registerSource()` uses reference policy and preserves source path.
   - Chat sidebar status label maps `untracked` to `Add source`, not `ingest`.
   - Modal CTA disables while submit is pending and displays source language.

3. Plugin UI changes:
   - Replace user-facing `ingest` wording.
   - Add local pending/running state before backend calls.
   - Keep modal open on failure and show error text.
   - Refresh chip after backend response.

4. Backend command improvements if needed:
   - Ensure `plugin source import` and `plugin source register` always return
     structured JSON with `ok`, `state`, `message`, and `source_path`.
   - Change `policy=reference` for external PDFs to create a markdown reference
     stub under `04_Resources` and store that stub relpath in `sources.relpath`.
     Store the real PDF path in `sources.external_path`.
   - Keep the stub frontmatter compatible with the schema:
     `type: reference` and optional portable identity fields such as
     `zotero_key`/`logical_source_id`.
   - Do not write absolute `target_path` into automatically generated stubs by
     default. `04_Resources` may sync across devices while Zotero/external PDF
     roots differ per device. Store absolute paths in device-local backend
     source metadata (`sources.external_path`) and resolve/rebind per device.
   - Add identity-based PDF context/source registration later:
     `--zotero-attachment-key`, `--vault-relpath`, `--source-id`, `--file-hash`.

5. Validation:
   - Plugin Vitest for labels/modal/client.
   - Backend pytest for structured failure JSON.
   - Manual Obsidian smoke:
     - vault-local PDF,
     - Zotero external PDF,
     - non-Zotero external PDF,
     - pathless/failure case.

## Recommendation

Treat this as "source registration UX", not "ingest". Backend still performs the
pipeline; plugin should expose a small, clear control that tells the user what
will happen and immediately reflects progress.
