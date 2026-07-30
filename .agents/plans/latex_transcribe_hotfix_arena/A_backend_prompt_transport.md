# Backend Proposal: Restore the Antigravity Print Contract

Date: 2026-07-30 | Agent Persona: Backend / Provider Integration

## 1. Design constraints from codebase

- `plugin/src/ui/pdf/ExternalPdfView.ts` already routes selected text through
  `IncuratorClient.transcribePdfRegion()` and copies only the returned `latex`.
- `backend/src/curator/commands/plugin.py` already owns the output-only
  transcription prompt and interactive normalizer.
- `backend/src/curator/ingest_raw.py` already resolves
  `latex_extract_model → vision_model → main-if-vision`.
- `backend/src/curator/models.py` already provides catalogue-backed
  `get_default_effort(provider, model)`.
- `backend/src/curator/llm.py::AntigravityCliClient._run()` is the divergent
  transport boundary. It predates the installed `agy` model/effort flags.

## 2. Alternatives and trade-offs

### A. Strip lines beginning with “I will”

Reject. This treats one symptom as model noise, can delete legitimate selected
prose, and still leaves the actual prompt undispatched.

### B. Special-case only `plugin pdf transcribe`

Reject. The defect is in the shared backend Antigravity transport; routing around
it would preserve broken prompt delivery for other backend calls.

### C. Update the shared Antigravity command builder

Selected. Pass the exact full prompt as the `--print` argument, pass `--model`,
and pass explicit effort or the selected model's catalogue default. Preserve
existing timeout, log-file, quota detection, and error behavior.

## 3. Final decision

Change only `AntigravityCliClient._run()` plus its focused tests. Do not alter the
plugin-to-backend JSON contract, model slot schema, clipboard code, or PDF
selection capture.

## 4. Implementation pseudocode

```python
effective_effort = self.effort or get_default_effort("antigravity", self.model)
cmd = ["agy"]
append log flag when available
append ["--model", self.model] when selected
append ["--effort", effective_effort] when catalogue/setting supplies one
append ["--print", prompt, "--print-timeout", "15m"]
subprocess.run(cmd, capture_output=True, ...)
```

Tests assert:

```text
--print is followed by the exact transcription prompt
no subprocess input= prompt fallback exists
--model is followed by gemini-3.6-flash
missing explicit effort resolves to catalogue default medium
explicit effort is preserved
models without an effort dimension omit --effort
```
