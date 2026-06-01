# ResNet Dynamics DAG, Query, And Backprop Testbed Plan

## User Review Required

This is a plan-first artifact for the requested testbed validation. Per
`AGENTS.md`, implementation should stop here until the plan is approved because
the work creates a new multi-step scenario, touches testbed behavior, and
validates MCP mutation/backprop semantics.

If you want to refine the scenario interactively before implementation, use
`/grill-me`. The main decisions worth grilling are:

- whether the source ResNet PDF should be downloaded during scenario setup or
  committed as a small public PDF fixture;
- whether the dynamics insight should enter through `curator_update_node` only,
  or through `curator_add_knowledge` first and then an Exhibition correction;
- which LLM backend to use for the full run if Antigravity capacity is unstable.

## Objective

Create and run a `testbed/` validation scenario that proves Incurator can:

1. ingest the original ResNet paper PDF into L1-L3 while preserving mathematical
   expressions and source/page provenance;
2. synthesize and query L4 Exhibitions according to the system's intended
   workspace behavior;
3. answer all three documented retrieval use cases using the right prior
   knowledge:
   - persona/workspace `curator_query`;
   - `curator_traverse_evidence`;
   - source-aware PDF search/context;
4. accept a user-discovered correction/insight through MCP
   `curator_update_node`, then backpropagate the updated dynamics interpretation
   into the dependent DAG nodes without editing source truth.

## Multi-Agent Execution Model

The scenario is now monitored by four explicit sub-agent roles plus Codex as
orchestrator:

1. **Incurator PDF/DAG refinement sub-agent**
   - Owns ResNet PDF acquisition, `wiki testbed init`, `wiki add`,
     `wiki build --wait`, L1-L3 math/provenance checks, and `dag_edges`
     assertions.
   - Must prove the original ResNet PDF is parsed into source-grounded L1, L2,
     and L3 artifacts.
2. **Workspace discovery sub-agent**
   - Owns the workspace `curate.yml`, simulated multi-turn ResNet research
     dialogue, and the three retrieval use cases.
   - Must keep the "agent gradually discovers Neural ODE" story separate from
     PDF source truth.
3. **MCP backprop sub-agent**
   - Owns the EXH patch fixture and `curator_update_node` validation.
   - Must use MCP/tool behavior, not direct writes to generated Atoms/Concepts.
4. **Performance/usability diagnostics sub-agent**
   - Owns timing, artifact-count, and practical usability diagnosis.
   - Must report whether the scenario is realistic for an actual user and where
     the system is slow, brittle, or confusing.

Codex integrates their outputs and rejects any script that:

- edits `03_Notes/` during validation;
- edits `.curator/` generated nodes directly instead of using CLI/MCP;
- pretends a mocked source-aware search is a pass;
- marks LLM-blocked synthesis as success.

## System-Correct Knowledge Semantics

The user asked whether the Neural ODE insight should update L1-L4, perhaps by
adding the insight into L1. Based on the current docs and MCP implementation,
the correct interpretation is:

- The ResNet PDF-derived L1 Context is source truth for He et al. It should
  preserve the paper and should **not** be rewritten to claim that He et al.
  knew or stated the Neural ODE interpretation.
- A later Neural ODE/dynamics insight may enter the graph as:
  - an EXH correction via `curator_update_node`, which backpropagates to
    dependent CON/ATM nodes where supported;
  - a new promoted knowledge artifact via `curator_add_knowledge`, if the user
    wants the conversational insight to become durable human-facing knowledge;
  - a separate source/Context if we seed a research brief or follow-up paper as
    an additional source.
- Therefore the completion criterion is not "mutate the original ResNet L1 to
  include Neural ODE." The criterion is:
  - original ResNet L1 remains faithful;
  - generated L4/Concept/Atom knowledge can incorporate the later insight with
    clear provenance/status;
  - if an L1 exists for the insight, it must belong to a separate research
    brief/promoted insight source, not the original PDF CTX.

## Current State Assessment

The repository already contains an untracked draft:

- `.agents/plans/2026-06-01_Math_RAG_Backprop_Plan.md`
- `scripts/dev/complex_math_backprop/MASTER_PLAN.md`
- `scripts/dev/complex_math_backprop/stage/03_Notes/math_theory.md`
- `scripts/dev/complex_math_backprop/dialogues/*.sh|*.py`

That draft is not sufficient for this objective:

- it tests generic backpropagation math, not ResNet;
- it does not ingest the original ResNet PDF;
- it has no source-aware PDF fixture;
- it mocks the source-aware use case instead of validating it;
- it directly edits an Atom file in `03_verify_backprop.py`, which violates the
  MCP rule that agents update EXH nodes and let backprop repair L1-L3;
- it does not verify query-generated L4 creation, cache behavior, or
  `curator_traverse_evidence` output.

Implementation should replace this draft scenario rather than extending it as-is.

## Primary Sources To Seed The Scenario

Use only primary/near-primary research sources for scenario facts:

1. **Original ResNet paper**
   - Kaiming He, Xiangyu Zhang, Shaoqing Ren, Jian Sun,
     "Deep Residual Learning for Image Recognition"
   - arXiv: <https://arxiv.org/abs/1512.03385>
   - PDF: <https://www.cv-foundation.org/openaccess/content_cvpr_2016/papers/He_Deep_Residual_Learning_CVPR_2016_paper.pdf>
   - Facts to assert:
     - residual learning reformulates layers as residual functions with
       reference to layer inputs;
     - deeper networks are harder to train due to degradation, and residual
       networks ease optimization;
     - the paper evaluates up to 152 layers and reports 3.57% ImageNet test
       top-5 error for the ensemble.
2. **PDE/dynamical-systems interpretation**
   - Lars Ruthotto, Eldad Haber,
     "Deep Neural Networks Motivated by Partial Differential Equations"
   - arXiv: <https://arxiv.org/abs/1804.04272>
   - Facts to assert:
     - the paper explicitly includes convolutional ResNets in a PDE
       interpretation;
     - PDE theory motivates parabolic and hyperbolic CNN architectures;
     - this is a later interpretive/design lens, not the original claim of the
       2015 ResNet paper.
3. **Continuous-depth/Neural ODE interpretation**
   - Ricky T. Q. Chen, Yulia Rubanova, Jesse Bettencourt, David Duvenaud,
     "Neural Ordinary Differential Equations"
   - arXiv: <https://arxiv.org/abs/1806.07366>
   - Facts to assert:
     - hidden-state derivatives are parameterized by a neural network and the
       output is computed with an ODE solver;
     - the paper demonstrates continuous-depth residual networks;
     - the adjoint method supports backpropagation through ODE solvers.

## Scenario Design

Scenario name: `complex_math_backprop`

Replace the current generic math scenario with:

```text
scripts/dev/complex_math_backprop/
├── MASTER_PLAN.md
├── stage/
│   ├── 01_Workspaces/ResNet_Dynamics_Lab/curate.yml
│   ├── 03_Notes/ResNet_Dynamics_Research_Brief.md
│   └── 04_Resources/
│       ├── README.md
│       └── Deep_Residual_Learning_for_Image_Recognition.pdf
├── fixtures/
│   ├── dynamics_insight_exhibition_patch.md
│   └── expected_terms.json
└── dialogues/
    ├── 00_fetch_public_sources.sh
    ├── 01_ingest_resnet_pdf.sh
    ├── 02_verify_l1_l3_math_and_provenance.py
    ├── 03_verify_three_query_use_cases.py
    └── 04_verify_mcp_backprop_dynamics_update.py
```

### Stage Data

#### `04_Resources/Deep_Residual_Learning_for_Image_Recognition.pdf`

Preferred implementation: `00_fetch_public_sources.sh` downloads the CVF PDF
into `stage/04_Resources/` before `wiki testbed init`. This keeps the committed
repository small while making the test reproducible with network access.

Fallback implementation: commit the PDF only if network access makes the
scenario flaky. It is a public paper PDF, but the plan should still note the
license/source.

#### `03_Notes/ResNet_Dynamics_Research_Brief.md`

Human-authored note used only as workspace context for the simulated external
agent research. It must not pretend to be source truth for ResNet's original
claims. It should say:

- Original ResNet block: `y = F(x, {W_i}) + x`
- Discrete dynamical systems lens:

  ```latex
  h_{k+1} = h_k + F_k(h_k)
  ```

- Forward-Euler interpretation:

  ```latex
  h_{k+1} = h_k + \Delta t\, f(h_k, t_k, \theta_k)
  ```

- This dynamics/PDE interpretation comes from later work, especially
  Ruthotto-Haber and Neural ODEs; it should be attached as a new insight/correction
  to the ResNet Exhibition, not backfilled as if He et al. originally claimed it.

#### Workspace `curate.yml`

Workspace path:

```text
testbed/01_Workspaces/ResNet_Dynamics_Lab
```

Required intent:

- domain: `machine-learning`, `computer-vision`, `dynamical-systems`
- topics:
  - residual learning;
  - degradation problem;
  - skip/identity connections;
  - ResNet as Euler/PDE/ODE discretization;
  - evidence provenance and math preservation.
- persona should prefer mathematically explicit answers and cite source layer
  IDs when possible.

## Validation Requirements

### Phase 1: Ingest ResNet PDF And Build L1-L3

Commands:

```bash
scripts/dev/complex_math_backprop/dialogues/00_fetch_public_sources.sh
wiki testbed init complex_math_backprop --force
VAULT_ROOT=testbed wiki status
VAULT_ROOT=testbed wiki add
VAULT_ROOT=testbed wiki build --wait
VAULT_ROOT=testbed wiki reindex
VAULT_ROOT=testbed wiki status
```

Assertions:

- `testbed/.curator/Collections/01_Contexts/` contains at least one `CTX-*.md`
  for the ResNet PDF.
- L1 contains intact math tokens from the source, including either:
  - `y = F(x, {W_i}) + x`, or
  - `F(x, {W_i}) + x`.
- L1 source sections include page/section provenance for the PDF.
- L2 contains Atoms for:
  - residual mapping / identity shortcut;
  - degradation problem;
  - 152-layer ImageNet result;
  - residual block equation.
- L3 contains Concepts clustering the above into at least:
  - residual learning mechanism;
  - deep network optimization/degradation.
- `dag_edges` includes `extracted_from` and `clustered_to` edges for this
  source.

### Phase 2: Verify L4 Curation

Commands:

```bash
VAULT_ROOT=testbed wiki curate --workspace testbed/01_Workspaces/ResNet_Dynamics_Lab
VAULT_ROOT=testbed wiki status
```

Assertions:

- `testbed/.curator/Collections/04_Exhibitions/` contains at least one `EXH-*.md`.
- The active workspace `curate.yml` records or references the Exhibition anchor
  expected by `curator_check_workspace`.
- The L4 page cites or links L3 Concepts; it must not be an ungrounded summary.
- L4 contains source-backed discussion of ResNet residual learning, not yet the
  later dynamics/PDE insight unless the research brief has already been promoted.

### Phase 3: Verify The Three User/Agent Retrieval Use Cases

Use a Python dialogue script that calls the MCP server tool functions through
`curator.mcp_server.build_server()` or through a real stdio MCP client. Prefer a
real MCP client if straightforward; otherwise, directly invoking registered
tools is acceptable only if the script clearly labels that it is exercising the
MCP tool implementation, not editing files or DB state directly.

#### Use Case A: Persona/Workspace `curator_query`

MCP sequence:

1. `curator_check_workspace(workspace_path=...)`
2. `curator_query(question="Why did residual learning help train very deep networks?", workspace_path=...)`
3. `curator_query(question="What is the residual block equation in the ResNet paper?", workspace_path=..., force_new=true)`

Assertions:

- result `ok == true`;
- `trace.l3_complete == true`;
- `trace.matched_concepts` is non-empty;
- `exhibition_id` starts with `EXH-`;
- the answer references residual functions/identity shortcut and includes the
  residual equation or its normalized text.

#### Use Case B: Evidence Traversal

MCP sequence:

1. take the `exhibition_id` returned from Use Case A;
2. call `curator_traverse_evidence(cur_id=exhibition_id, workspace_path=...)`;
3. fetch nodes referenced in the chain via `curator_get_node`.

Assertions:

- traversal returns an EXH -> CON -> ATM chain;
- at least one ATM points back to the ResNet PDF source or its CTX;
- evidence includes the residual equation and degradation/result claims;
- traversal fails the test if it returns only raw search hits without DAG links.

#### Use Case C: Source-Aware PDF Search

MCP sequence:

1. `curator_source_status(source_path=<testbed PDF path>)`
2. `curator_search_sources(query="identity shortcut residual mapping equation", source_path=<PDF>, limit=5)`
3. `curator_get_pdf_context(file_path=<PDF>, query="degradation problem residual learning", max_pages=4)`

Assertions:

- source status reports the PDF as tracked/indexed or L1/L3 complete according
  to current tool vocabulary;
- search hits include page provenance and a snippet mentioning residual mapping
  or identity shortcut;
- `curator_get_pdf_context` returns pages/text and does not report an empty PDF;
- the final assembled context can distinguish "current PDF source context" from
  workspace-level L3/L4 knowledge.

### Phase 4: Simulate External Research And Backprop A Dynamics Insight

Goal: validate the user's key loop:

```text
ResNet PDF ingested -> user asks several ResNet questions -> L4 exists ->
research dialogue discovers later dynamics interpretation -> user corrects the
generated Exhibition through MCP -> backprop updates dependent DAG knowledge ->
later queries retrieve the new dynamics insight with provenance.
```

Dialogue:

1. Run three `curator_query` calls in the workspace:
   - original ResNet degradation question;
   - residual block equation question;
   - "Can ResNet be interpreted as a dynamical system?"
2. Before correction, assert the system either:
   - does not know the dynamics insight yet, or
   - explicitly says the original paper itself does not make the later
     PDE/ODE interpretation.
3. Construct a replacement EXH markdown patch from
   `fixtures/dynamics_insight_exhibition_patch.md`. The patch must preserve
   immutable frontmatter and add a section:

   ```markdown
   ## Dynamics Insight Added By Research Dialogue

   The original ResNet paper defines residual blocks as
   $h_{k+1}=h_k+F_k(h_k)$ in effect. Later dynamical-systems work interprets
   this as a forward Euler discretization
   $h_{k+1}=h_k+\Delta t f(h_k,t_k,\theta_k)$.

   This is a later interpretation supported by Ruthotto-Haber (PDE view) and
   Neural ODEs, not an original claim of He et al.
   ```

4. Call `curator_update_node(node_id=<EXH>, new_content=<patched markdown>, workspace_path=...)`.

Assertions:

- `curator_update_node` returns `updated == true`.
- direct edits to `CON-` or `ATM-` are rejected in a negative control:

  ```python
  curator_update_node(node_id="ATM-...", new_content="...")
  ```

  must return an error explaining that only EXH nodes are agent-editable.
- propagation result has at least one of:
  - `concepts_updated` non-empty;
  - `atoms_updated` non-empty;
  - `feedback_required` non-empty with a clear reason;
  - explicit LLM/capacity blocker recorded.
- `routing_tables_rebuilt == true`.
- after `curator_reindex`, a forced `curator_query` for
  `"Explain ResNet as a forward Euler discretization"` returns:
  - an `EXH-` id;
  - matched L3 Concepts;
  - answer text containing `forward Euler` or `dynamical system`;
  - the distinction that this is a later insight rather than the original
    ResNet paper claim.

### Phase 5: Testbed Completion Gates

Full validation is complete only when all of these pass:

```bash
bash scripts/dev/complex_math_backprop/dialogues/00_fetch_public_sources.sh
bash scripts/dev/complex_math_backprop/dialogues/01_ingest_resnet_pdf.sh
python scripts/dev/complex_math_backprop/dialogues/02_verify_l1_l3_math_and_provenance.py
python scripts/dev/complex_math_backprop/dialogues/03_verify_three_query_use_cases.py
python scripts/dev/complex_math_backprop/dialogues/04_verify_mcp_backprop_dynamics_update.py
VAULT_ROOT=testbed wiki lint
```

If the configured LLM backend is unavailable, the scenario must still run the
deterministic gates:

- source download;
- `wiki testbed init`;
- `wiki add`;
- L1 math/provenance assertions;
- negative control for non-EXH `curator_update_node`.

The report must then mark L2/L3/L4/backprop synthesis as blocked by the exact
LLM error, not as passed.

## Implementation Steps After Approval

1. Replace the current `scripts/dev/complex_math_backprop/MASTER_PLAN.md` with
   this scenario contract.
2. Replace the generic backprop stage files with the ResNet PDF fetcher,
   workspace, and research brief.
3. Replace the existing dialogue scripts. Do not keep mocked source-aware search
   or direct Atom edits.
4. Add a small shared Python assertion helper under
   `scripts/dev/complex_math_backprop/dialogues/lib.py` if needed.
5. Run the full validation sequence.
6. Update this plan with command outputs and any blockers.
7. Update `.agents/relay.md` after implementation/validation.

## Non-Goals

- Do not edit `03_Notes/` in the generated testbed during validation.
- Do not mutate `.curator/` directly in dialogue scripts except through project
  commands or MCP tools.
- Do not claim the dynamics interpretation was present in the original ResNet
  paper.
- Do not use private Zotero libraries or private PDFs.
