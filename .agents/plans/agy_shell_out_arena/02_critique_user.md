# Critique: B' would let the model brute-force what we already indexed

Date: 2026-08-21 | Raised by: the user, mid-implementation | Persona: red_teamer

> *"근데 우리가 옵시디언에서 external link를 통해 pdf를 불러와서 렌더링까지
> 하잖아. 그 때 불러와진 정보들을 사용하면 안되나…?"*

## 1. The objection lands, and it demotes B'

The user's report has the model running:

```python
pdf_path = ".../Zotero/[Project] .../MultipleViewGeometryHartley - .pdf"
reader = PyPDF2.PdfReader(f)
for i in range(len(reader.pages)):
    if re.search(r"Pl[uü]cker", text) and re.search(r"epipolar", text): ...
```

That is a brute-force scan of 673 PDF pages for two terms. **The vault has
already indexed exactly that**, measured just now on the live DB:

| | |
|---|---|
| Hartley spans indexed | **8,905** |
| vision pages transcribed and cached | 104 |
| FTS5 documents matching `plucker OR plücker` | **240** |
| FTS5 documents matching `epipolar` | **406** |

(A first pass at this used `LIKE` against `source_spans.text_preview` and
reported 0 for Plücker. That was the query being wrong — `text_preview` is a
truncated preview, not the text. The FTS corpus is the real surface.)

So the model was not doing something clever we failed to permit. It was slowly
and worse re-deriving — via PyPDF2's text layer rather than our parse plus vision
transcription — something the system could have answered instantly.

## 2. Why it reached for a shell: we hand it nothing

Measured:

```
$ agy mcp list
No MCP servers configured.
```

and `AntigravityCliClient` (`llm.py:1063`) builds
`[agy, --log-file, --model, --effort, (--json-schema …), --print, <prompt>]` —
**no MCP server, no tool wiring, no `--add-dir` except on the vision path.**

A CLI-routed model therefore receives **zero** tools from us. Asked to find two
terms in a book, its only options are to answer from the prompt or to use its own
built-in shell. It used the shell. That is not misbehaviour to be contained; it
is the absence of an alternative.

## 3. What this changes

**B' stops being the fix and becomes a backstop.** Containment is still worth
having — §3 of `01_measured_options.md` shows the model will read and echo a
secret file on request when uncontained — but shipping B' *as the answer to 5b*
would mean paying a real security cost to make a brute-force PDF scan succeed,
while the indexed answer sits unused.

The surfaces split, and they need different fixes:

| surface | why the model shells out | right fix |
|---|---|---|
| query / chat (2026-08-21 report, 2026-08-09 P0) | it has no tool and no content | **give it the content or a tool** — the FTS corpus already holds the answer |
| compile — `entity_relation_extract` | it is trying to recover *its own prompt input* from agy's transcript log | no tool helps; needs C (non-fatal retry) and/or B' containment |

## 4. Revised direction

1. **Supply what we already have** to CLI-routed calls — the query surface's root
   cause, and per CLAUDE.md ("Fix the disease, not the symptoms") the only one of
   the four candidates that is not a workaround.
2. **C — make a denial non-fatal** in `extract_graph_data`, so one refusal stops
   killing an 87-batch compile.
3. **B' — containment** kept as a backstop for whatever still reaches for a
   shell, and because the uncontained exfiltration demonstrated in
   `01_measured_options.md` §3 should not be possible regardless of this item.

Ordering matters: (1) removes the reason, (2) removes the fatality, (3) bounds
the damage. Shipping (3) alone would have been the workaround the repo rules
specifically prohibit.
