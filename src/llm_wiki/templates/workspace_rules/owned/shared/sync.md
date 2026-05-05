# LLM-Wiki Rule Synchronization

The source of truth for llm-wiki workspace behavior is:

- `.agents/llm_wiki/shared/rules.md`

Runtime entrypoints should point to that file and the selected runtime file
under `.agents/llm_wiki/runtime/`.

Run from the workspace root:

```bash
python .agents/llm_wiki/shared/check_rule_sync.py
```
