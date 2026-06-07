## incurator Workspace Rules

This workspace is connected to incurator for `{{agent_runtime}}`.

Read and follow:

1. `.agents/curator/shared/rules.md`
2. `.agents/curator/runtime/{{agent_runtime}}.md`
3. `.agents/curator/workflows/research_pipeline.md`

Knowledge Isolation: Do not use cross-workspace paths or mix results with
external projects. Restrict knowledge extraction, graph search, and insertion
commands strictly to this workspace's local DAG.
