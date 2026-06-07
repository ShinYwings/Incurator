# incurator Rule Synchronization

The source of truth for incurator workspace behavior is:

- `.agents/curator/shared/rules.md`

Runtime entrypoints should point to that file and the selected runtime file
under `.agents/curator/runtime/`.

Run from the workspace root:

```bash
python .agents/curator/shared/check_rule_sync.py
```
