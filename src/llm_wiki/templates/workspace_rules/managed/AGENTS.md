## LLM-Wiki Workspace Rules

This workspace is connected to llm-wiki for `{{agent_runtime}}`.

Read and follow:

1. `.agents/llm_wiki/shared/rules.md`
2. `.agents/llm_wiki/runtime/{{agent_runtime}}.md`
3. `.agents/llm_wiki/workflows/research_pipeline.md`

Knowledge Isolation: Do not use cross-workspace paths or mix results with
external projects. Restrict knowledge extraction, graph search, and insertion
commands strictly to this workspace's local DAG.
