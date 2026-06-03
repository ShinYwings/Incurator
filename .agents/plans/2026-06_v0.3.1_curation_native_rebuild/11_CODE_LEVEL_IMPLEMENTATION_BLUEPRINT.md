# Code-Level Implementation Blueprint

## 1. Purpose

This document is intentionally close to code level. It describes which files
should be added or changed, what public functions/classes should exist, how
current functions should be wrapped or replaced, and which tests should prove
the behavior.

It is still a plan. Do not implement code in the planning phase. Future
implementation should follow this blueprint after v0.3.1 specs and guides are
approved.

## 2. Current Code Anchors

The future implementation should be anchored to the current codebase instead of
inventing an unrelated product.

| Area | Current file | Current role | v0.3.1 action |
| --- | --- | --- | --- |
| Prompt strings | `backend/src/curator/prompts.py` | Large module containing Curator system prompt, L1/L2/L3/L4 prompts, verification, backprop, persona prompts | Convert to compatibility wrapper; move prompt families into `backend/src/curator/prompting/`. |
| Query orchestration | `backend/src/curator/query.py` | qmd search, synthesis prompt, save-back Exhibition | Keep `run_query()` API but delegate to `QueryOrchestrator`. |
| Search | `backend/src/curator/search.py` | qmd wrapper and source-page lexical search | Keep qmd wrapper; add higher-level retrievers that call qmd as one backend. |
| DB schema | `backend/src/curator/db.py` | v0.2.x state, sources, jobs, DAG edges | Add v0.3.1 tables and idempotent migrations. |
| LLM ingest | `backend/src/curator/ingest_llm.py` | SummaryData, Atoms, Concepts, Exhibitions | Insert source spans, typed knowledge units, entities, relations, reports. |
| `curate.yml` | `backend/src/curator/curate_yml.py` | basic KRS loader plus boost terms | Add v0.3.1 dataclasses and `compile_curate_policy()`. |
| CLI | `backend/src/curator/cli.py` | Typer commands for add/build/curate/query/sync/plugin/MCP | Add `wiki prompt`, `wiki curate plan`, richer `wiki query --mode`. |
| Plugin API | `backend/src/curator/plugin_api.py` | hidden JSON commands for Obsidian | Add curation plan, prompt trace, insight list/promote commands. |
| MCP | `backend/src/curator/mcp_server.py` | external-agent tools | Add external-agent-safe trace/explore/insight tools via shared services. |
| Plugin client | `plugin/src/agent/incuratorClient.ts` | shells out to backend hidden commands | Add TypeScript payload types and client methods. |
| Plugin trace UI | `plugin/src/ui/incuratorQueryTrace.ts` | shallow query trace panel | Render route, source spans, prompt traces, community reports, memory paths. |

## 3. Phase 0: Specs And Guides Before Code

Before implementing any file below:

1. Create:
   - `docs/specs/curator_schema/SCHEMA_v0.3.1.md`
   - `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.3.1.md`
   - `docs/specs/plugin_schema/PLUGIN_SCHEMA_v0.3.1.md`
2. Archive root v0.2.2 spec files.
3. Update English guides, then Korean guides.
4. Add plan/spec version guard tests if practical.

No code implementation should begin before this step.

## 4. Phase 1: Prompt Subsystem

### 4.1 Add New Package

Add:

```text
backend/src/curator/prompting/__init__.py
backend/src/curator/prompting/contracts.py
backend/src/curator/prompting/registry.py
backend/src/curator/prompting/render.py
backend/src/curator/prompting/trace.py
backend/src/curator/prompting/validators.py
backend/src/curator/prompting/evals.py
backend/src/curator/prompting/families/__init__.py
backend/src/curator/prompting/families/source_map.py
backend/src/curator/prompting/families/knowledge_units.py
backend/src/curator/prompting/families/entities.py
backend/src/curator/prompting/families/community_reports.py
backend/src/curator/prompting/families/curation_plan.py
backend/src/curator/prompting/families/exhibition.py
backend/src/curator/prompting/families/query.py
backend/src/curator/prompting/families/explore.py
backend/src/curator/prompting/families/backprop.py
backend/src/curator/prompting/families/note_writing.py
```

### 4.2 Define Contract Types

In `contracts.py`:

```python
from dataclasses import dataclass, field
from typing import Callable, Type
from pydantic import BaseModel

@dataclass(frozen=True)
class PromptContract:
    prompt_id: str
    version: str
    family: str
    purpose: str
    input_model: type[BaseModel]
    output_model: type[BaseModel] | None
    system_template: str
    user_template: str
    validators: list[str] = field(default_factory=list)
    retry_policy: str = "json_repair_once"
    trace_fields: list[str] = field(default_factory=list)
```

In `registry.py`:

```python
class PromptRegistry:
    def register(self, contract: PromptContract) -> None: ...
    def get(self, prompt_id: str, version: str | None = None) -> PromptContract: ...
    def list(self, family: str | None = None) -> list[PromptContract]: ...
    def assert_unique(self) -> None: ...
```

### 4.3 Define Prompt Trace

In `trace.py`:

```python
@dataclass
class PromptRunTrace:
    trace_id: str
    prompt_id: str
    prompt_version: str
    family: str
    model_provider: str
    model_name: str
    input_hash: str
    output_hash: str
    validator_status: str
    validator_errors: list[str]
    source_ids: list[int]
    source_span_ids: list[str]
    curate_spec_hash: str
    created_at: str
```

Add functions:

```python
def start_prompt_run(...) -> PromptRunTrace: ...
def finish_prompt_run(...) -> PromptRunTrace: ...
def hash_prompt_input(messages: list[ChatMessage]) -> str: ...
def hash_prompt_output(output: str) -> str: ...
```

### 4.4 Move Existing Prompt Families

Do not delete `prompts.py` immediately. Instead:

1. Move `SUMMARY_INSTRUCTIONS` and `build_summary_messages()` into
   `families/source_map.py`.
2. Leave wrapper in `prompts.py`:

```python
def build_summary_messages(...):
    from .prompting.families.source_map import build_summary_messages
    return build_summary_messages(...)
```

3. Move `FRAGMENT_PAGE_TEMPLATE` and atom builders into
   `families/knowledge_units.py`.
4. Move concept clustering/page prompts into `families/entities.py` or
   `families/community_reports.py` depending on final schema.
5. Move `CURATION_PAGE_TEMPLATE`, `build_curation_page_messages()`, and
   `build_curation_planning_messages()` into `families/exhibition.py` and
   `families/curation_plan.py`.
6. Move `SYNTHESIS_SYSTEM_PROMPT` from `query.py` into `families/query.py`.
7. Move backprop prompts from `prompts.py`, `backprop_agents.py`, and sync
   helpers into `families/backprop.py`.

### 4.5 Required Prompt IDs

Register at minimum:

```text
curator.source_map.v1
curator.knowledge_unit_extract.v1
curator.entity_relation_extract.v1
curator.community_report_write.v1
curator.curation_plan.v1
curator.exhibition_write.v1
curator.query_router.v1
curator.query_local_answer.v1
curator.query_global_reduce.v1
curator.query_explore_expand.v1
curator.backprop_classify.v1
curator.backprop_patch_plan.v1
curator.note_context_pack.v1
```

### 4.6 Validators

In `validators.py`, add:

```python
def validate_json_model(raw: str, model: type[BaseModel]) -> ValidationResult: ...
def validate_source_span_ids(output: BaseModel, valid_span_ids: set[str]) -> ValidationResult: ...
def validate_no_unknown_wikilinks(markdown: str, allowed_targets: set[str]) -> ValidationResult: ...
def validate_no_source_truth_pollution(output: BaseModel) -> ValidationResult: ...
def validate_language_policy(output: str, expected_language: str) -> ValidationResult: ...
def validate_exhibition_frontmatter(frontmatter: dict) -> ValidationResult: ...
```

### 4.7 Tests

Add:

```text
backend/tests/test_v031_prompt_registry.py
backend/tests/test_v031_prompt_trace.py
backend/tests/test_v031_prompt_validators.py
backend/tests/test_v031_prompt_family_contracts.py
backend/tests/test_v031_prompt_eval_fixtures.py
```

Minimum assertions:

- every prompt id is unique;
- every prompt has version, family, input model, validators;
- all JSON prompt families declare output model;
- prompt run trace persists prompt id/version/input hash/output hash;
- source-span validator rejects invented ids;
- old `prompts.py` wrappers still work during migration.

## 5. Phase 2: Database Schema

### 5.1 Bump Schema Version

In `backend/src/curator/db.py`:

```python
SCHEMA_VERSION = 4
```

Do not remove old tables.

### 5.2 Add Tables

Add to `SCHEMA_SQL`:

```sql
CREATE TABLE IF NOT EXISTS source_spans (
    id TEXT PRIMARY KEY,
    source_id INTEGER NOT NULL,
    relpath TEXT NOT NULL,
    span_type TEXT NOT NULL,
    page_number INTEGER,
    section_title TEXT,
    start_char INTEGER,
    end_char INTEGER,
    content_hash TEXT NOT NULL,
    text_preview TEXT NOT NULL DEFAULT '',
    metadata TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_units (
    id TEXT PRIMARY KEY,
    unit_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    statement TEXT NOT NULL,
    source_span_ids TEXT NOT NULL,
    source_id INTEGER,
    confidence REAL NOT NULL DEFAULT 0.0,
    truth_status TEXT NOT NULL DEFAULT 'source_supported',
    prompt_run_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_entities (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    prompt_run_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_relations (
    id TEXT PRIMARY KEY,
    source_entity_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.0,
    prompt_run_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS community_reports (
    id TEXT PRIMARY KEY,
    community_key TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    full_content TEXT NOT NULL,
    finding_json TEXT NOT NULL DEFAULT '[]',
    entity_ids TEXT NOT NULL DEFAULT '[]',
    relation_ids TEXT NOT NULL DEFAULT '[]',
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    rank REAL NOT NULL DEFAULT 0.0,
    prompt_run_id TEXT,
    dependency_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_runs (
    trace_id TEXT PRIMARY KEY,
    prompt_id TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    family TEXT NOT NULL,
    model_provider TEXT NOT NULL DEFAULT '',
    model_name TEXT NOT NULL DEFAULT '',
    input_hash TEXT NOT NULL,
    output_hash TEXT NOT NULL DEFAULT '',
    validator_status TEXT NOT NULL DEFAULT 'pending',
    validator_errors TEXT NOT NULL DEFAULT '[]',
    source_ids TEXT NOT NULL DEFAULT '[]',
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    curate_spec_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS curation_plans (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    workspace_path TEXT NOT NULL DEFAULT '',
    project TEXT NOT NULL DEFAULT '',
    curate_spec_hash TEXT NOT NULL,
    route TEXT NOT NULL,
    source_policy_json TEXT NOT NULL,
    retrieval_policy_json TEXT NOT NULL,
    prompt_profile TEXT NOT NULL DEFAULT '',
    evidence_plan_json TEXT NOT NULL DEFAULT '{}',
    prompt_run_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_paths (
    id TEXT PRIMARY KEY,
    query_hash TEXT NOT NULL,
    route TEXT NOT NULL,
    start_node_id TEXT NOT NULL DEFAULT '',
    path_json TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0.0,
    source_span_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS insight_candidates (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT '',
    source_event_id TEXT NOT NULL DEFAULT '',
    classification TEXT NOT NULL,
    statement TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    affected_node_ids TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending',
    prompt_run_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_dependencies (
    artifact_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    depends_on_id TEXT NOT NULL,
    depends_on_type TEXT NOT NULL,
    dependency_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (artifact_id, depends_on_id, depends_on_type)
);
```

Add indexes for source id, ids, route, prompt id, and workspace id.

### 5.3 Add DB Functions

Add functions to `db.py`:

```python
def upsert_source_span(...): ...
def list_source_spans(db_path: Path, source_id: int) -> list[dict]: ...
def upsert_knowledge_unit(...): ...
def list_knowledge_units_for_source(...): ...
def upsert_graph_entity(...): ...
def upsert_graph_relation(...): ...
def upsert_community_report(...): ...
def record_prompt_run(...): ...
def finish_prompt_run(...): ...
def get_prompt_run(db_path: Path, trace_id: str) -> dict | None: ...
def record_curation_plan(...): ...
def get_curation_plan(...): ...
def record_memory_path(...): ...
def create_insight_candidate(...): ...
def update_insight_candidate_status(...): ...
def record_artifact_dependency(...): ...
def invalidate_artifacts_for_dependency(...): ...
```

### 5.4 Tests

Add:

```text
backend/tests/test_v031_db_schema.py
backend/tests/test_v031_source_spans.py
backend/tests/test_v031_artifact_dependencies.py
backend/tests/test_v031_prompt_run_db.py
backend/tests/test_v031_insight_candidates.py
```

## 6. Phase 3: `curate.yml` KRS Parser

### 6.1 Extend Dataclasses

In `backend/src/curator/curate_yml.py`, add:

```python
@dataclass
class CurateGoal:
    primary: str = ""
    audience: str = ""
    deliverables: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)

@dataclass
class CurateKnowledge:
    domains: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    disambiguation_keywords: list[str] = field(default_factory=list)
    avoid_merges: list[str] = field(default_factory=list)

@dataclass
class CurateOutput:
    format: str = "exhibition"
    style: str = "dense-technical"
    citation_style: str = "curator-source-spans"
    include_sections: list[str] = field(default_factory=list)

@dataclass
class CurateReasoning:
    default_mode: str = "auto"
    allowed_modes: list[str] = field(default_factory=lambda: ["local", "global", "explore", "exhibition"])
    exploration_enabled: bool = True
    max_followups: int = 5
    require_insight_candidates: bool = False

@dataclass
class CurateVerification:
    min_confidence: float = 0.60
    high_threshold: float = 0.85
    require_source_spans: bool = True
    allow_general_knowledge: bool = False
    contradiction_policy: str = "surface-and-flag"

@dataclass
class CurateBackprop:
    enabled: bool = True
    source_truth_policy: str = "never_rewrite_original_source"
    derived_insight_policy: str = "record_then_promote_or_patch_generated"
    ambiguous_merge_policy: str = "needs_review"

@dataclass
class CuratePrompts:
    profile: str = "default"
    output_language: str = "same_as_latest_request"
    prompt_overrides: dict[str, str] = field(default_factory=dict)
```

Extend `CurateSpec` with these fields while preserving old `persona`.

### 6.2 Add Runtime Policy

Add:

```python
@dataclass(frozen=True)
class CurationPolicy:
    workspace_id: str
    project: str
    source_include: tuple[str, ...]
    source_exclude: tuple[str, ...]
    allowed_routes: frozenset[str]
    default_route: str
    prompt_profile: str
    require_source_spans: bool
    allow_general_knowledge: bool
    contradiction_policy: str
    backprop_enabled: bool
    max_explore_followups: int
```

Add:

```python
def compile_curate_policy(spec: CurateSpec, workspace_path: Path | None = None) -> CurationPolicy: ...
def validate_curate_spec(spec: CurateSpec) -> list[str]: ...
def curate_spec_hash(workspace_path: Path) -> str: ...
```

### 6.3 Backward Compatibility

Rules:

- existing `persona.domain` maps to `knowledge.domains[0]` if new
  `knowledge.domains` absent;
- existing `persona.subdomain` maps to `knowledge.topics`;
- existing `persona.goal` maps to `goal.primary`;
- existing `min_confidence` maps to `verification.min_confidence`;
- existing `persona.confidence.high_threshold` maps to
  `verification.high_threshold`;
- existing `persona.disambiguation_keywords` maps to
  `knowledge.disambiguation_keywords`.

### 6.4 Tests

Add:

```text
backend/tests/test_v031_curate_yml_krs.py
backend/tests/test_v031_curation_policy.py
backend/tests/test_v031_curate_yml_backward_compat.py
```

## 7. Phase 4: Source Spans And Knowledge Units

### 7.1 Add Models

Add:

```text
backend/src/curator/knowledge_models.py
```

With Pydantic models:

```python
class SourceSpan(BaseModel):
    id: str
    source_id: int
    relpath: str
    span_type: str
    page_number: int | None = None
    section_title: str = ""
    start_char: int | None = None
    end_char: int | None = None
    content_hash: str
    text_preview: str = ""

class KnowledgeUnit(BaseModel):
    id: str
    unit_type: Literal["claim", "definition", "equation", "procedure", "entity", "relationship", "constraint"]
    canonical_name: str
    statement: str
    source_span_ids: list[str]
    confidence: float
    truth_status: Literal["source_supported", "derived_insight", "contradiction", "promoted_human_truth"]
```

### 7.2 Modify L1 Generation

Current `plugin_api.register_source()` calls:

```python
ingest_raw.generate_l1_structural_context(...)
```

Future change:

1. `generate_l1_structural_context()` should also call a new source-span
   builder.
2. Add `ingest_raw.extract_source_spans(paths, source_id, relpath)`.
3. For Markdown:
   - split by headings and paragraphs;
   - preserve char offsets;
   - classify equations/code blocks as specialized spans.
4. For PDF:
   - reuse `source_pdf_pages`;
   - create page spans and optional section spans if headings are detected.
5. Write spans to `source_spans`.

### 7.3 Modify L2 Extraction

Current `ingest_llm.SummaryData.atom_candidates` has no source span id.

Future output model:

```python
class KnowledgeUnitCandidate(BaseModel):
    canonical_name: str
    unit_type: str
    statement: str
    source_span_ids: list[str]
    confidence: float
```

Future change:

- replace or extend `AtomCandidate`;
- prompt must receive valid span ids;
- validator rejects invented span ids;
- each generated Atom page frontmatter should include:

```yaml
source_span_ids:
  - SPAN-...
knowledge_unit_ids:
  - KNU-...
prompt_trace_ids:
  - PTR-...
```

### 7.4 Tests

Add:

```text
backend/tests/test_v031_markdown_source_spans.py
backend/tests/test_v031_pdf_source_spans.py
backend/tests/test_v031_knowledge_unit_extraction.py
backend/tests/test_v031_atom_frontmatter_source_spans.py
```

## 8. Phase 5: Graph Entities, Relations, Communities

### 8.1 Add Modules

Add:

```text
backend/src/curator/graph_index.py
backend/src/curator/community_reports.py
backend/src/curator/memory_paths.py
```

### 8.2 Entity/Relation Extraction

In `graph_index.py`:

```python
def extract_entities_and_relations(paths, source_id: int, knowledge_unit_ids: list[str], client) -> GraphExtractionResult: ...
def upsert_graph_records(paths, result: GraphExtractionResult) -> None: ...
def entity_seed_search(paths, query: str, limit: int = 12) -> list[GraphEntity]: ...
def relation_neighborhood(paths, entity_ids: list[str], depth: int = 1) -> list[GraphRelation]: ...
```

Prompt contract:

```text
curator.entity_relation_extract.v1
```

Required validator:

- relation endpoints must be declared entities;
- source_span_ids must exist;
- relation confidence must be 0.0-1.0.

### 8.3 Community Reports

In `community_reports.py`:

```python
def detect_communities(paths, policy: CurationPolicy | None = None) -> list[CommunityPlan]: ...
def generate_community_report(paths, community: CommunityPlan, client) -> CommunityReport: ...
def refresh_stale_community_reports(paths) -> list[str]: ...
```

Initial v0.3.1 can use simple grouping:

- by domain/topic from `knowledge_units`;
- by connected components over `graph_relations`;
- by source/project boundaries;
- later replace with Leiden or another graph algorithm if needed.

Community report frontmatter/page optional:

- do not force every report into `.curator/Collections`;
- SQL record is required;
- markdown page can be added later if useful for Obsidian inspection.

### 8.4 Memory Paths

In `memory_paths.py`:

```python
def build_memory_paths(paths, query: str, seed_entities: list[str], policy: CurationPolicy) -> list[MemoryPath]: ...
def score_memory_path(path: MemoryPath, policy: CurationPolicy) -> float: ...
def record_memory_paths(paths, paths_: list[MemoryPath], query_hash: str) -> None: ...
```

Initial scoring:

```text
score =
  0.35 * lexical/entity seed score
+ 0.25 * relation confidence
+ 0.20 * source-span support
+ 0.10 * recency/promoted status
+ 0.10 * curate.yml domain fit
```

Do not implement full PPR in the first patch unless tests already prove path
trace fidelity.

### 8.5 Tests

Add:

```text
backend/tests/test_v031_entity_relation_extraction.py
backend/tests/test_v031_graph_neighborhood.py
backend/tests/test_v031_community_reports.py
backend/tests/test_v031_memory_paths.py
backend/tests/test_v031_report_invalidation.py
```

## 9. Phase 6: Query Orchestration

### 9.1 Add Retrieval Package

Add:

```text
backend/src/curator/retrieval/__init__.py
backend/src/curator/retrieval/models.py
backend/src/curator/retrieval/router.py
backend/src/curator/retrieval/evidence_pack.py
backend/src/curator/retrieval/local.py
backend/src/curator/retrieval/global_.py
backend/src/curator/retrieval/explore.py
backend/src/curator/retrieval/exhibition.py
backend/src/curator/retrieval/source_section.py
backend/src/curator/retrieval/orchestrator.py
```

### 9.2 Define Models

In `retrieval/models.py`:

```python
@dataclass
class QueryRequest:
    question: str
    english_query: str
    input_language: str
    final_output_language: str
    workspace_path: str = ""
    mode: str = "auto"
    session_id: str | None = None

@dataclass
class EvidenceItem:
    id: str
    kind: str
    title: str
    text: str
    score: float
    source_ids: list[int]
    source_span_ids: list[str]
    curator_node_id: str = ""
    community_report_id: str = ""
    memory_path_id: str = ""

@dataclass
class EvidencePack:
    route: str
    items: list[EvidenceItem]
    source_span_ids: list[str]
    community_report_ids: list[str]
    memory_path_ids: list[str]
    warnings: list[str]
```

### 9.3 Router

In `retrieval/router.py`:

```python
def choose_route(request: QueryRequest, policy: CurationPolicy, graph_status: GraphStatus) -> RetrievalRoute:
    ...
```

Rules:

- explicit `--mode local/global/explore/exhibition/source-section` wins if
  allowed by policy;
- source-specific question with known source id -> `source-section`;
- active workspace Exhibition and question asks for project context ->
  `exhibition`;
- broad synthesis terms -> `global`;
- "what else", "find connections", "new insight" -> `explore`;
- entity/fact question -> `local`;
- if graph incomplete -> qmd fallback with warning.

### 9.4 Orchestrator

In `retrieval/orchestrator.py`:

```python
class QueryOrchestrator:
    def run(self, request: QueryRequest, callbacks: QueryCallbacks) -> QueryResult:
        policy = resolve_policy(...)
        route = choose_route(...)
        evidence = build_evidence_pack(...)
        prompt = registry.get(prompt_for_route(route, evidence))
        answer, prompt_trace = run_prompt(...)
        query_trace = record_query_trace(...)
        maybe_save_exhibition(...)
        return QueryResult(...)
```

### 9.5 Modify `query.py`

Keep `QueryResult` and `QueryCallbacks` initially.

Add fields to `QueryResult`:

```python
route: str = ""
trace_id: str = ""
prompt_trace_ids: list[str] = field(default_factory=list)
source_span_ids: list[str] = field(default_factory=list)
community_report_ids: list[str] = field(default_factory=list)
memory_path_ids: list[str] = field(default_factory=list)
warnings: list[str] = field(default_factory=list)
```

Change `run_query()`:

```python
def run_query(...):
    from .retrieval.orchestrator import QueryOrchestrator, QueryRequest
    request = QueryRequest(...)
    return QueryOrchestrator(paths, client).run(request, callbacks)
```

Keep old code temporarily behind:

```python
def run_legacy_query(...): ...
```

for migration tests and fallback.

### 9.6 Tests

Add:

```text
backend/tests/test_v031_query_router.py
backend/tests/test_v031_query_local_route.py
backend/tests/test_v031_query_global_route.py
backend/tests/test_v031_query_explore_route.py
backend/tests/test_v031_query_exhibition_route.py
backend/tests/test_v031_query_trace_payload.py
backend/tests/test_v031_query_legacy_fallback.py
```

## 10. Phase 7: Backprop And Insight Lifecycle

### 10.1 Add Modules

Add:

```text
backend/src/curator/insight_lifecycle.py
backend/src/curator/backprop_classifier.py
```

### 10.2 Classifier

In `backprop_classifier.py`:

```python
def classify_feedback(paths, event: BackpropEvent, client) -> BackpropClassification:
    ...
```

Output classes:

```text
correction
contradiction
derived_insight
style_only
promotion_request
ambiguous
```

Rules:

- correction can patch generated ATM/CON/EXH;
- contradiction flags both sides and creates candidate;
- derived insight creates `insight_candidates`;
- style-only does not trigger graph rebuild;
- promotion request requires explicit human approval;
- L1 source context is never rewritten to include later derived insight.

### 10.3 Modify `sync.py`

Where current sync/backprop flows call prompt functions directly, route them
through:

```python
classification = backprop_classifier.classify_feedback(...)
plan = insight_lifecycle.plan_action(classification)
```

### 10.4 Tests

Add:

```text
backend/tests/test_v031_backprop_classification.py
backend/tests/test_v031_derived_insight_lifecycle.py
backend/tests/test_v031_source_truth_immutable.py
backend/tests/test_v031_promotion_lifecycle.py
backend/tests/test_v031_backprop_trace.py
```

## 11. Phase 8: CLI, MCP, Plugin

### 11.1 CLI Changes

In `backend/src/curator/cli.py`, add:

```text
wiki prompt list
wiki prompt show PROMPT_ID
wiki prompt trace TRACE_ID
wiki prompt eval

wiki curate plan --workspace PATH --json
wiki curate validate --workspace PATH

wiki query "..." --mode auto|local|global|explore|exhibition|source-section
wiki query "..." --trace

wiki insight list --workspace PATH
wiki insight show INSIGHT_ID
wiki insight promote INSIGHT_ID
```

Implementation detail:

- add `prompt_app = typer.Typer(name="prompt", ...)`;
- add `insight_app = typer.Typer(name="insight", ...)`;
- add route mode option to existing `query()` command;
- add JSON output for `curate plan`.

### 11.2 Plugin API Changes

In `backend/src/curator/plugin_api.py`, add:

```python
def curate_plan(paths, *, workspace_path: str) -> dict[str, Any]: ...
def prompt_trace(paths, *, trace_id: str) -> dict[str, Any]: ...
def insight_list(paths, *, workspace_path: str = "", status: str = "pending") -> dict[str, Any]: ...
def insight_promote(paths, *, insight_id: str, workspace_path: str = "") -> dict[str, Any]: ...
```

Update `curator_query()` to return:

```json
{
  "ok": true,
  "answer": "...",
  "route": "local|global|explore|exhibition|source-section",
  "trace_id": "QTR-...",
  "prompt_trace_ids": ["PTR-..."],
  "source_span_ids": ["SPAN-..."],
  "community_report_ids": ["REP-..."],
  "memory_path_ids": ["MPATH-..."],
  "insight_candidate_ids": ["INS-..."],
  "trace": { "...": "..." }
}
```

### 11.3 CLI Hidden Plugin Commands

In `cli.py`, add:

```text
wiki plugin curate plan --workspace-path PATH --json
wiki plugin prompt trace --trace-id ID --json
wiki plugin insight list --workspace-path PATH --json
wiki plugin insight promote --insight-id ID --workspace-path PATH --json
```

### 11.4 MCP Changes

In `mcp_server.py`, add tools:

```python
curator_explore(query: str, workspace_path: str = "") -> dict
curator_get_prompt_trace(trace_id: str, workspace_path: str = "") -> dict
curator_get_curation_plan(workspace_path: str) -> dict
curator_list_insight_candidates(workspace_path: str = "", status: str = "pending") -> dict
curator_promote_insight(insight_id: str, workspace_path: str = "") -> dict
```

Implementation rule:

These tools should call `plugin_api` or a shared service layer, not duplicate
business logic inside `mcp_server.py`.

### 11.5 Plugin TypeScript Changes

In `plugin/src/types.ts`, add:

```ts
export interface IncuratorPromptTrace {
  traceId: string;
  promptId: string;
  promptVersion: string;
  family: string;
  validatorStatus: string;
  validatorErrors: string[];
}

export interface IncuratorEvidenceTrace {
  route: string;
  traceId: string;
  promptTraceIds: string[];
  sourceSpanIds: string[];
  communityReportIds: string[];
  memoryPathIds: string[];
  insightCandidateIds: string[];
}
```

In `plugin/src/agent/incuratorClient.ts`, add:

```ts
getCuratePlan(workspacePath: string): Promise<...>
getPromptTrace(traceId: string): Promise<IncuratorPromptTrace>
listInsightCandidates(workspacePath: string): Promise<...>
promoteInsight(insightId: string, workspacePath: string): Promise<...>
```

In `plugin/src/ui/incuratorQueryTrace.ts`, render:

- route badge;
- source spans;
- community reports;
- prompt trace links;
- memory path summary;
- insight candidates and promote actions.

### 11.6 Tests

Add:

```text
backend/tests/test_v031_cli_prompt_commands.py
backend/tests/test_v031_cli_curate_plan.py
backend/tests/test_v031_plugin_trace_commands.py
backend/tests/test_v031_mcp_prompt_trace.py
backend/tests/test_v031_mcp_explore.py

plugin/src/agent/incuratorClientV031.test.ts
plugin/src/ui/incuratorQueryTraceV031.test.ts
plugin/src/context/systemPromptV031.test.ts
```

## 12. Phase 9: Testbed Scenario

Add scenario:

```text
scripts/dev/complex_math_backprop/
```

Required files:

```text
MASTER_PLAN.md
03_Notes/ResNet Original.md
03_Notes/Neural ODE Followup.md
04_Resources/resnet-paper.pdf or markdown fixture
01_Workspaces/ResNet_Dynamics_Lab/curate.yml
```

Scenario must test:

- original ResNet source truth remains source-supported only;
- later Neural ODE interpretation becomes derived insight or promoted note;
- global query uses community report;
- explore query returns memory path between residual learning and Euler
  discretization;
- backprop classification does not rewrite original L1;
- prompt traces are visible.

Smoke commands:

```bash
wiki testbed init complex_math_backprop --force
VAULT_ROOT=testbed wiki status
VAULT_ROOT=testbed wiki add
VAULT_ROOT=testbed wiki build --wait
VAULT_ROOT=testbed wiki curate plan --workspace testbed/01_Workspaces/ResNet_Dynamics_Lab --json
VAULT_ROOT=testbed wiki curate --workspace testbed/01_Workspaces/ResNet_Dynamics_Lab
VAULT_ROOT=testbed wiki query "What is the dynamics interpretation of residual learning?" --workspace testbed/01_Workspaces/ResNet_Dynamics_Lab --mode explore --trace
VAULT_ROOT=testbed wiki insight list --workspace testbed/01_Workspaces/ResNet_Dynamics_Lab
VAULT_ROOT=testbed wiki sync --backward --target EXH-...
VAULT_ROOT=testbed wiki lint
```

## 13. Migration Strategy

### 13.1 Patch Sequence

Implement in these PR-sized steps:

1. Specs/guides v0.3.1.
2. DB schema tables plus no-op accessors.
3. Prompt registry/contracts/traces with existing prompt wrappers.
4. `curate.yml` KRS parser and compiled policy.
5. Source spans.
6. Knowledge units.
7. Entity/relation graph.
8. Community reports.
9. Query orchestrator with legacy fallback.
10. Explore/memory paths.
11. Backprop classifier and insight candidates.
12. CLI/MCP/plugin payloads.
13. Testbed scenario and prompt eval suite.

### 13.2 Backward Compatibility Rules

- Existing `wiki query` must still work.
- Existing `wiki curate --workspace` must still write an Exhibition.
- Existing plugin `plugin query` must still return `answer`, `exhibition_id`,
  and `trace`.
- New fields can be additive.
- Old `curate.yml` files must parse.
- Old L1-L4 markdown pages must remain readable.
- `qmd` remains the fallback retrieval engine.

### 13.3 What Must Not Happen

- Do not delete old prompt functions in the first migration patch.
- Do not require all old vaults to rebuild before query works.
- Do not make plugin depend on MCP for local commands.
- Do not write derived insight into source context.
- Do not treat community report confidence as human verification.
- Do not expose hidden plugin commands as the human CLI surface.

## 14. Completion Criteria For Future Implementation

v0.3.1 implementation is complete only when:

- synchronized v0.3.1 specs and guides exist;
- all prompt families are registered and traced;
- prompt evals run;
- source spans exist for markdown and PDF fixtures;
- knowledge units require source spans;
- entity/relation graph records exist;
- community reports can be generated and queried;
- explore mode returns memory paths and follow-up questions;
- `curate.yml` compiles into runtime policy;
- query trace includes route, evidence, prompt trace, reports, and memory paths;
- insight candidates distinguish correction, contradiction, derived insight,
  style-only, and promotion;
- backend pytest passes;
- plugin Vitest passes;
- complex math/backprop testbed smoke passes or exact LLM/qmd blockers are
  documented.
