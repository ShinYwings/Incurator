# Briefing: PDF Convert-to-LaTeX Copies Antigravity Work Logs

Date: 2026-07-30

## User report

The PDF viewer's **Convert to LaTeX** action sometimes copies Antigravity agent
progress text such as:

> I will start by checking the permissions...
> I will list the contents of the scratch directory...
> I will read `find_mvg_text.py`...

The expected clipboard value is the selected prose preserved faithfully, with
rendered mathematics converted to Markdown LaTeX delimiters.

The user reports that the feature worked when first introduced and became
unreliable after model selection was added.

## Reproduction

With local config:

```yaml
llm:
  primary: antigravity-cli::gemini-3.6-flash
  primary_effort: medium
  vision_model: antigravity-cli::gemini-3.6-flash
  latex_extract_model: antigravity-cli::gemini-3.6-flash
```

the command:

```text
VAULT_ROOT=testbed wiki plugin pdf transcribe \
  --text "The reconstruction loss is L = sum_i (x_i - y_i)^2." \
  --workspace-path testbed
```

returned `ok: true` with seven lines of scratch-directory investigation rather
than a transcription.

## Verified cause

`AntigravityCliClient._run()` invokes:

```text
agy --print "Follow the instructions in the provided input."
```

and sends the actual prompt through `subprocess.run(input=...)`. Installed
`agy 1.1.8` treats the `--print` argument as the prompt and does not use stdin as
that “provided input.” The same client still treats model/effort as a prompt hint
even though the installed CLI exposes `--model` and `--effort`.

A direct call with the full prompt as the `--print` argument and explicit
`--model gemini-3.6-flash --effort medium` returned:

```xml
<transcription>
The reconstruction loss is $L = \sum_i (x_i - y_i)^2$.
</transcription>
```

## Success criteria

1. Backend Antigravity calls pass the actual prompt as the `--print` value.
2. The chosen model is passed through `--model`.
3. Explicit effort is preserved; when an Antigravity catalogue model requires
   effort and the dedicated extraction slot has no effort field, its catalogue
   default is passed.
4. `wiki plugin pdf transcribe` returns the selected prose plus LaTeX math and
   the plugin copies only that normalized transcription.
5. Tests reproduce the old command construction and fail before implementation.
6. Docs, EN/KR guides, version manifests, changelog, full CI, and testbed smoke
   remain synchronized.
