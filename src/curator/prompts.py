"""Prompt templates for the LLM Curator (Compiler) pipeline.

The Curator runs four sequential passes per source, building a DAG:

    add    → Pass 0 (CONTEXT)    — L1: 1:1 hash-matched source context summary
    curate → Pass 1 (ATOMS)      — L2: irreducible atomic knowledge units
    curate → Pass 2 (CONCEPTS)   — L3: clustered atoms into coherent concepts
    curate → Pass 3 (EXHIBITIONS)— L4: cross-domain terminal packaged contexts

All pages use UUID-based IDs (CTX-, ATM-, CON-, EXH-) so the Agent (Artist) can
traverse the DAG by ID without relying on human-readable slugs.
"""

from __future__ import annotations

from .llm import ChatMessage


# ---------------------------------------------------------------------------
# System prompt — Curator identity, shared across all passes
# ---------------------------------------------------------------------------

CURATOR_SYSTEM_PROMPT = """\
You are the CURATOR (Compiler) — a background abstraction engine whose sole purpose is to \
transform raw human knowledge into a machine-readable DAG (Directed Acyclic Graph) \
stored in `.curator/Collections/`.

Your output is consumed ONLY by AI agents (Artists). DO NOT consider human readability at all.
Optimize entirely for machine parsability, logical structure, and semantic density.
Use dense bullet points, structured data formats, and explicit logical operators wherever possible instead of flowing human prose.

Rules you MUST follow:
1. Every page begins with strict YAML frontmatter. No exceptions.
2. IDs are pre-assigned by the pipeline and provided to you — use them exactly.
3. Use [[wikilinks]] (format: [[LAYER/ID]]) for all cross-references.
   Example: [[02_Atoms/ATM-abc12345]] — never plain markdown links.
4. Be maximally precise. Prefer formal definitions, equations (LaTeX), and
   explicit logical relationships over prose summaries.
5. Never invent facts. If the source does not support a claim, omit it.
6. Timestamps are ISO 8601: YYYY-MM-DDThh:mm:ssZ.
7. Confidence scores: 0.00–1.00 float.
8. LANGUAGE: All generated output MUST be strictly in English. If the source text is in Korean or another language, seamlessly translate it and write your entire response in English.
9. LaTeX format: You MUST use LaTeX format ($ or $$) for ALL mathematical equations, formulas, definitions, and symbols across the entire document (including description, summary, context, and all other sections). Do NOT skip, omit, or simplify any mathematical derivations, equations, or formulas under any circumstances—they are the highest-priority information.
"""


# ---------------------------------------------------------------------------
# Pass 0 — CONTEXT  (L1: runs during `wiki add`)
# ---------------------------------------------------------------------------

SUMMARY_INSTRUCTIONS = """\
You are processing a source document for the Curator knowledge pipeline.

Generate a highly detailed and comprehensive machine-readable summary of the source below.

Return ONLY a valid JSON object with this exact schema:
{
  "title": "Precise, specific document title (max 100 chars)",
  "domain": "Primary knowledge domain (e.g. 'history', 'machine-learning', 'cooking', 'philosophy')",
  "summary": "An EXTREMELY GRANULAR, highly detailed, section-by-section summary. Do not compress or skip details; extract meaning almost paragraph-by-paragraph. Thoroughly explain all core arguments, background context, mathematical formulations, and technical implications. CRITICAL: Preserve all mathematical equations and formulas precisely using LaTeX format ($ or $$).",
  "key_claims": [
    "Claim 1 — precise, falsifiable factual statement",
    "Claim 2",
    "Claim 3"
  ],
  "atom_candidates": [
    {
      "name": "Canonical concept/entity name",
      "type": "fact | claim | entity | procedure | relationship",
      "one_liner": "Single-sentence definition or description"
    }
  ],
  "tags": ["tag1", "tag2", "tag3"]
}

Rules:
- summary: A single Markdown-formatted string containing a highly extensive, section-by-section breakdown. DO NOT write flowing prose for humans. Use extreme structural Markdown formatting (dense bullet points, nested lists, explicit logic blocks). Leave no detail behind. **CRITICAL: You MUST extract and preserve ALL important mathematical formulas, equations, and formal definitions in their entirety using LaTeX math blocks ($ or $$). Do NOT omit or simplify equations.**
- key_claims: Extract ALL key claims. Each must be a precise, falsifiable statement. Do not limit the number of items.
- atom_candidates: Extract ALL potential concepts substantive enough for their own Atom page. Do not limit the number of items.
- tags: Provide comprehensive broad domain labels. Do not limit the number of tags.
- Return ONLY the JSON. No prose, no markdown fences.
"""


def build_summary_messages(source_title: str, source_text: str) -> list[ChatMessage]:
    """Pass 0 — generate L1 Context JSON during `wiki add`."""
    user_content = (
        f"{SUMMARY_INSTRUCTIONS}\n\n"
        f"---SOURCE TITLE---\n{source_title}\n\n"
        f"---SOURCE TEXT---\n{source_text}\n"
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


def build_summary_retry_messages(
    source_title: str, source_text: str, bad_response: str
) -> list[ChatMessage]:
    """Retry prompt after a JSON parse failure in Pass 0."""
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=f"{SUMMARY_INSTRUCTIONS}\n\n---SOURCE TITLE---\n{source_title}\n\n---SOURCE TEXT---\n{source_text}\n"),
        ChatMessage(role="assistant", content=bad_response[:2000]),
        ChatMessage(role="user", content="That was not valid JSON. Return ONLY the JSON object matching the schema above."),
    ]


def build_image_description_messages(context: str = "") -> list[ChatMessage]:
    """Vision prompt: describe an image for knowledge base indexing.

    The image bytes are attached by the caller via the vision API (not in text).
    """
    system = (
        "You are analyzing an image for a structured knowledge base. "
        "Extract ALL information visible: text, labels, diagrams, equations (write in LaTeX), "
        "chart/graph data and trends, object relationships, spatial layout. "
        "Be dense and precise. Output markdown. No preamble or meta-commentary."
    )
    user = "Describe this image in full detail for knowledge base indexing."
    if context:
        user += f"\n\nDocument context: {context[:400]}"
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]


# ---------------------------------------------------------------------------
# Pass 1 — ATOMS  (L2: irreducible facts / equations / constraints)
# ---------------------------------------------------------------------------

FRAGMENT_PAGE_TEMPLATE = """\
Write a single Atom page for the `.curator/Collections/02_Atoms/` layer.

Atom ID (pre-assigned): {fragment_id}
Concept name: {name}
Type: {fragment_type}
One-liner: {one_liner}
Parent context ID: {context_id}
Parent source path: {source_path}
Today (ISO 8601): {today}

Source excerpt relevant to this concept:
{excerpt}

Write the complete markdown page with:
1. YAML frontmatter — copy this EXACTLY, character-for-character. Do NOT alter any field values:
   ---
   id: {fragment_id}
   type: atom
   parent_source: "01_Contexts/{context_id}"
   source_path: "[[{source_path}]]"
   claim_type: {fragment_type}
   confidence_score: 0.00
   contradicts: []
   is_verified_by_human: false
   is_flagged_for_agent: false
   last_updated: {today}
   ---
   CRITICAL: `source_path` MUST be exactly `"[[{source_path}]]"` — never an empty string `""` or `''`.
   CRITICAL: Set `confidence_score` to a float between 0.00 and 1.00 reflecting how well-supported this atom is by the source. Do NOT omit this field.

2. An H1 heading: the canonical name of the concept.

3. Body sections, exactly these H2 headings:
   ## Definition / Claim
   Precise statement. **CRITICAL: You MUST use LaTeX format ($ or $$) for ALL mathematical equations, formal definitions, and symbols.**
   ## Context
   When / where does this apply?
   ## Constraints
   Boundary conditions, assumptions, or edge cases.
   ## Relations
   The ONLY valid wikilink for this page is [[01_Contexts/{context_id}]]. Write exactly this one link and no others. FORBIDDEN: do NOT invent wikilinks with unknown IDs. The only valid layer prefixes are 01_Contexts/, 02_Atoms/, 03_Concepts/, 04_Exhibitions/ — layers like 03_Collections/ or 04_Resources/ do NOT exist. NEVER write placeholder paths like [[02_Atoms/ATM-...]] or [[03_Collections/...]] — if you do not know an ID, omit the wikilink entirely.

Return ONLY the markdown. No preamble, no code fences.
"""


def build_fragment_page_messages(
    fragment_id: str,
    name: str,
    fragment_type: str,
    one_liner: str,
    context_id: str,
    source_path: str,
    excerpt: str,
    today: str,
) -> list[ChatMessage]:
    """Pass 1 — draft a single L2 Atom page."""
    # Wikilinks must not include file extensions (Obsidian convention)
    source_path_link = source_path.removesuffix(".md")
    user_content = FRAGMENT_PAGE_TEMPLATE.format(
        fragment_id=fragment_id,
        name=name,
        fragment_type=fragment_type,
        one_liner=one_liner,
        context_id=context_id,
        source_path=source_path_link,
        excerpt=excerpt,
        today=today,
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


MERGE_FRAGMENT_TEMPLATE = """\
Update this existing Atom page with new information from a new source.

---EXISTING ATOM PAGE---
{existing_content}
---END EXISTING---

New source context ID: {new_context_id}
New source path: {new_source_path}
New information about '{name}':
{new_description}

Relevant excerpt from new source:
{excerpt}

Update rules:
1. DO NOT simply append text. You must synthesize the new information logically.
2. Determine if the new info:
   - Corroborates existing facts
   - Expands/Adds new technical details or equations
   - Contradicts existing claims
3. If the new info CONTRADICTS, you MUST set `is_flagged_for_agent: true` in the YAML frontmatter, add "[[01_Contexts/{new_context_id}]]" to the `contradicts:` list, and thoroughly document the conflict under a `## Logical Conflict` heading.
4. If it Corroborates or Expands, weave the new facts logically under the appropriate existing headings, or create new headings if necessary.
5. Update `last_updated: {today}` in frontmatter.
6. Keep all existing [[wikilinks]] intact.
7. CRITICAL: Preserve all LaTeX math formatting ($ or $$).

Return ONLY the complete updated markdown. No preamble, no code fences.
"""


def build_merge_atom_messages(
    existing_content: str,
    name: str,
    new_context_id: str,
    new_source_path: str,
    new_description: str,
    excerpt: str,
    today: str,
) -> list[ChatMessage]:
    """Pass 1b — merge new source info into an existing Atom page."""
    user_content = MERGE_FRAGMENT_TEMPLATE.format(
        existing_content=existing_content,
        name=name,
        new_context_id=new_context_id,
        new_source_path=new_source_path,
        new_description=new_description,
        excerpt=excerpt,
        today=today,
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Pass 2 — CONCEPTS  (L3: clustered atoms → coherent conceptual units)
# ---------------------------------------------------------------------------

CONCEPT_CLUSTERING_INSTRUCTIONS = """\
You are building L3 Concept pages by clustering related L2 Atoms.

Return ONLY a valid JSON object:
{
  "concepts": [
    {
      "name": "Concept name",
      "domain": "knowledge domain string",
      "atom_ids": ["ATM-xxxx", "ATM-yyyy"],
      "description": "Extensive explanation of how these atoms cohere into one concept"
    }
  ]
}

Rules:
- A Concept groups Atoms that share the SAME underlying principle, pattern, method, or directly interacting claim.
- Boundary preservation is more important than density. Do NOT merge Atoms only because they share abstract vocabulary.
- Cross-source merging is encouraged only when different sources describe the same underlying logic with different terminology.
- Keep unrelated domains separate. Do not cluster Atoms from distinct fields unless a source explicitly defines that bridge.
- Prefer compact clusters of 2-8 tightly related Atoms. Larger clusters are allowed only when every Atom directly participates in the same mechanism.
- Do NOT create singleton concepts unless an Atom truly has no related partner; a precise singleton is better than a false merge.
- Return ONLY the JSON. No prose, no fences.
"""


def build_concept_clustering_messages(
    atom_summaries: list[dict],
) -> list[ChatMessage]:
    """Pass 2 — cluster atoms into L3 Concept groups.

    Args:
        atom_summaries: List of dicts with keys: id, name, claim_type, one_liner
    """
    atoms_text = "\n".join(
        f"- {a['id']}: [{a['claim_type']}] {a['name']} — {a['one_liner']}"
        for a in atom_summaries
    )
    user_content = (
        f"{CONCEPT_CLUSTERING_INSTRUCTIONS}\n\n"
        f"---ATOMS TO CLUSTER---\n{atoms_text}\n"
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


THEME_PAGE_TEMPLATE = """\
Write a single Concept page for the `.curator/Collections/03_Concepts/` layer.

Concept ID (pre-assigned): {theme_id}
Concept name: {name}
Domain: {domain}
Today (ISO 8601): {today}

Constituent Atom IDs and their content:
{fragments_content}

Write the complete markdown page:
1. YAML frontmatter:
   ---
   id: {theme_id}
   type: concept
   domain: "{domain}"
   confidence_score: 0.00
   last_updated: {today}
   ---
   CRITICAL: Set `confidence_score` to a float between 0.00 and 1.00 reflecting how coherent and well-supported this concept is by its constituent atoms. Do NOT omit this field.

2. H1: concept name

3. Body:
   ## 1. Core Idea
   What does this concept represent as a unified whole?
   ## 2. How the Atoms Connect
   How do the constituent Atoms logically or thematically connect to form this concept? Cite each atom using exactly [[02_Atoms/ATM-xxx]] with its real ID from the list above. NEVER write double brackets [[[[02_Atoms/ATM-xxx]]]].
   ## 3. Key Patterns
   Key recurring patterns, principles, or mechanisms. Use LaTeX ($ or $$) for equations where applicable.
   ## 4. Open Questions
   Unresolved tensions or contradictions within this concept (if any).
   ## Relations
   List every constituent atom as a wikilink, one per line. Use ONLY the real IDs from the list above — do NOT invent IDs.

FRONTMATTER RULE: Do NOT include `dependencies`; the `## Relations` section is the single source of truth for Concept → Atom links.
WIKILINK RULE: In BODY only, write every wikilink with EXACTLY ONE pair of brackets [[path/id]]. NEVER nest brackets. The atom IDs provided above are the ONLY valid IDs — do not invent others.

Return ONLY the markdown. No preamble, no code fences.
"""


def build_theme_page_messages(
    theme_id: str,
    name: str,
    domain: str,
    fragment_ids: list[str],
    fragments_content: str,
    today: str,
    workspace_context: str = "",
) -> list[ChatMessage]:
    """Pass 2 — draft a single L3 Concept page."""
    user_content = THEME_PAGE_TEMPLATE.format(
        theme_id=theme_id,
        name=name,
        domain=domain,
        fragments_content=fragments_content,
        today=today,
    )
    if workspace_context:
        user_content = f"## Workspace Context\n{workspace_context}\n\n{user_content}"
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Pass 3 — CURATIONS  (L4: cross-domain terminal packaged contexts)
# ---------------------------------------------------------------------------

CURATION_PAGE_TEMPLATE = """\
Write a single Exhibition page for the `.curator/Collections/04_Exhibitions/` layer.

Exhibition ID (pre-assigned): {curation_id}
Topic: {topic}
Domain: {domain}
Today (ISO 8601): {today}

Core concepts involved:
{themes_content}

Write the complete markdown page:
1. YAML frontmatter:
   ---
   id: {curation_id}
   type: exhibition
   domain: {domain}
   core_concepts: [{theme_ids_yaml}]
   confidence_score: {confidence}
   last_updated: {today}
   ---

2. H1: exhibition topic name

3. Body (use bold-bullet format — NOT ## section headers):
   - **1. Executive Brief**: What is the terminal conclusion or actionable context that emerges from combining these concepts?
   - **2. Background & Evidence**: Trace the reasoning path from Atoms → Concepts → this Exhibition. Cite concepts with [[03_Concepts/CON-xxx]] using real IDs from the list above. **CRITICAL: You MUST use LaTeX format ($ or $$) for ALL mathematical derivations, formulas, and symbols.**
   - **3. Actionable Directives for Agent**: Explicit instructions and hypotheses for the AI Agent (Artist). What specific code, pipeline, or research task should the Agent execute next based on this exhibition? Confidence score: {confidence}. Flagged atoms that require human review: {flagged_fragments}
   - **4. Key Facts**: Bullet list of the most critical atomic facts extracted from the cited Atoms (max 5 items). Each fact should be a single dense sentence.
   - **5. Open Questions**: Knowledge gaps, unresolved contradictions, or claims flagged for human verification.

FRONTMATTER RULE: `core_concepts` entries must be plain strings like '03_Concepts/CON-xxxx' (no [[ ]] wrappers). Include `domain` only if non-empty.
WIKILINK RULE: In BODY only, write every wikilink with EXACTLY ONE pair of brackets [[path/id]]. NEVER nest brackets like [[[[path/id]]]]. Only use IDs that were explicitly provided above.

Return ONLY the markdown. No preamble, no code fences.
"""


def build_curation_page_messages(
    curation_id: str,
    topic: str,
    theme_ids: list[str],
    themes_content: str,
    confidence: float,
    today: str,
    domain: str = "",
    flagged_fragment_ids: list[str] | None = None,
    agent_context: str = "",
) -> list[ChatMessage]:
    """Pass 3 — draft a single L4 Exhibition page."""
    theme_ids_yaml = ", ".join(f"'03_Concepts/{t}'" for t in theme_ids)
    if flagged_fragment_ids:
        flagged_fragments = ", ".join(f"[[02_Atoms/{f}]]" for f in flagged_fragment_ids)
    else:
        flagged_fragments = "none"
    user_content = CURATION_PAGE_TEMPLATE.format(
        curation_id=curation_id,
        topic=topic,
        domain=domain or "general",
        theme_ids_yaml=theme_ids_yaml,
        themes_content=themes_content,
        confidence=f"{confidence:.2f}",
        today=today,
        flagged_fragments=flagged_fragments,
    )
    if agent_context:
        user_content = f"## Agent Context\n{agent_context}\n\n{user_content}"
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Curation planning — decide which themes merit a curation
# ---------------------------------------------------------------------------

CURATION_PLANNING_INSTRUCTIONS = """\
You are deciding which L3 Concepts should be packaged into L4 Exhibitions.

Return ONLY a valid JSON object:
{
  "synthesis_plans": [
    {
      "topic": "Exhibition topic name",
      "concept_ids": ["CON-xxxx", "CON-yyyy"],
      "confidence": 0.85,
      "domain": "knowledge-domain-slug",
      "rationale": "1 sentence explaining what emergent insight this exhibition captures"
    }
  ]
}

Rules:
- Only propose an exhibition if 2+ concepts share a non-trivial logical connection.
- confidence: 0.90+ = direct retrieval quality; 0.60-0.90 = needs backtracking; <0.60 = HITL required.
- domain: a short slug derived from the concepts' shared domain (e.g. "cooking-techniques", "machine-learning").
- Propose 1–5 exhibition plans.
- Return ONLY the JSON. No prose, no fences.
"""


def build_curation_planning_messages(
    concept_summaries: list[dict],
    high_threshold: float = 0.90,
    low_threshold: float = 0.60,
) -> list[ChatMessage]:
    """Decide which concept clusters merit L4 exhibition.

    Args:
        concept_summaries: List of dicts with keys: id, name, domain, atom_count
        high_threshold: Confidence floor for direct retrieval quality.
        low_threshold: Confidence floor below which HITL is required.
    """
    instructions = CURATION_PLANNING_INSTRUCTIONS.replace(
        "0.90+", f"{high_threshold:.2f}+"
    ).replace(
        "0.60-0.90", f"{low_threshold:.2f}-{high_threshold:.2f}"
    ).replace(
        "<0.60", f"<{low_threshold:.2f}"
    )
    concepts_text = "\n".join(
        f"- {c['id']}: [{c['domain']}] {c['name']} ({c['atom_count']} atoms)"
        for c in concept_summaries
    )
    user_content = (
        f"{instructions}\n\n"
        f"---CONCEPTS---\n{concepts_text}\n"
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Exhibition refinement  (used by `wiki curate --workspace` re-run)
# ---------------------------------------------------------------------------

EXHIBITION_REFINEMENT_TEMPLATE = """\
Refine an existing L4 Exhibition based on accumulated session questions.

Exhibition ID: {exh_id}
Today (ISO 8601): {today}

---EXISTING EXHIBITION---
{existing_body}

---ACCUMULATED FOLLOW-UP QUESTIONS (integrate and discard)---
{followup_questions}

---SUPPORTING CONCEPTS---
{concepts_content}

Rewrite the Exhibition body. Preserve ALL existing sections but update:
- **1. Executive Brief**: Update based on what the Follow-up questions revealed about the agent's real concerns.
- **3. Actionable Directives for Agent**: Revise to reflect the agent's current task context.
- **4. Key Facts**: Add any new facts surfaced by the Follow-up questions.
- **5. Open Questions**: Update with remaining gaps revealed by the conversation.

IMPORTANT:
- Keep the YAML frontmatter EXACTLY as provided above — do NOT regenerate or modify it.
- Remove ALL "## Follow-up:" sections — their insights must be integrated into the body sections instead.
- Keep the bold-bullet body format. No ## headers in body.
- Return ONLY the full markdown (frontmatter + body). No preamble, no code fences.
"""


def build_exhibition_refinement_messages(
    exh_id: str,
    today: str,
    existing_content: str,
    followup_questions: list[str],
    concepts_content: str,
) -> list[ChatMessage]:
    """Build refinement prompt for an existing Exhibition with accumulated Follow-ups."""
    followup_block = "\n".join(f"- {q}" for q in followup_questions) if followup_questions else "(none)"
    user_content = EXHIBITION_REFINEMENT_TEMPLATE.format(
        exh_id=exh_id,
        today=today,
        existing_body=existing_content,
        followup_questions=followup_block,
        concepts_content=concepts_content or "(no supporting concepts available)",
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Logical deduction verification  (used by `wiki sync`)
# ---------------------------------------------------------------------------

THEME_LOGIC_VERIFY_PROMPT = """\
You are a deductive logic auditor for a knowledge DAG.

## L3 Concept under review
{theme_content}

## L2 Atoms this Concept synthesizes
{fragments_content}

## Task
Determine whether the Concept's synthesis is logically derivable from the given Atoms.
- Evaluate these fixed checks:
  1) Claim coverage: every major claim maps to at least one Atom.
  2) Precision fidelity: specific claims, formulas, or technical definitions are supported by Atom content.
  3) Scope discipline: no external facts absent from all Atoms.
  4) Relation fidelity: referenced ATM IDs are real and in-scope.
  5) Contradiction check: no claim conflicts with supplied Atoms.
- Do not mark invalid merely because domain-standard notation or terminology is not
  re-defined, as long as the related claim or principle is present in an Atom.
- Treat concise restatement, grouping, and naming as valid when the Concept does
  not add a new unsupported claim, empirical result, or cross-domain bridge.

Respond ONLY with a JSON object — no prose, no markdown fences:
{{"valid": true}}
or
{{"valid": false, "reasoning": "<failed check #> - <specific gap>"}}
"""

CURATION_LOGIC_VERIFY_PROMPT = """\
You are a deductive logic auditor for a knowledge DAG.
{concept_verification_context}
## L4 Exhibition under review
{curation_content}

## L3 Concepts this Exhibition synthesizes
{themes_content}

## Task
Determine whether the Exhibition's synthesis is logically derivable from the given Concepts.
- Evaluate these fixed checks:
  1) Executive brief grounding in supplied Concepts.
  2) Reasoning chain correctness (L2→L3→L4 narrative).
  3) Directive validity (actions are justified by Concept evidence).
  4) Scope discipline: no external facts absent from all Concepts.
  5) Concept citation fidelity: referenced CON IDs are real and in-scope.
- If a Concept was already verified invalid in Phase 1, treat its reasoning as a known gap.

Respond ONLY with a JSON object — no prose, no markdown fences:
{{"valid": true}}
or
{{"valid": false, "reasoning": "<failed check #> - <specific gap>"}}
"""


def build_theme_logic_verify_messages(
    theme_content: str,
    fragments_content: str,
    domain_context: str = "",
) -> list[ChatMessage]:
    """Logical deduction check: can CON be derived from its ATMs?"""
    user_content = THEME_LOGIC_VERIFY_PROMPT.format(
        theme_content=theme_content,
        fragments_content=fragments_content,
    )
    if domain_context:
        user_content = f"## Domain Context\n{domain_context}\n\n{user_content}"
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


def build_curation_logic_verify_messages(
    curation_content: str,
    themes_content: str,
    concept_verification_summary: list[dict] | None = None,
    domain_context: str = "",
) -> list[ChatMessage]:
    """Logical deduction check: can EXH be derived from its CONs?

    concept_verification_summary: Phase 1 JSON results for each referenced CON,
    e.g. [{"id": "CON-xxx", "valid": true}, {"id": "CON-yyy", "valid": false, "reasoning": "..."}]
    """
    if concept_verification_summary:
        lines = ["## Phase 1 Concept Verification Results"]
        for r in concept_verification_summary:
            status = "VALID" if r.get("valid", True) else f"INVALID — {r.get('reasoning', '')}"
            lines.append(f"- {r['id']}: {status}")
        concept_verification_context = "\n".join(lines) + "\n\n"
    else:
        concept_verification_context = ""
    user_content = CURATION_LOGIC_VERIFY_PROMPT.format(
        curation_content=curation_content,
        themes_content=themes_content,
        concept_verification_context=concept_verification_context,
    )
    if domain_context:
        user_content = f"## Domain Context\n{domain_context}\n\n{user_content}"
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Backward propagation prompts — agent-correction flows (L4 → L3 → L2)
# ---------------------------------------------------------------------------

CONCEPT_UPDATE_FROM_EXHIBITION_PROMPT = """\
A human agent has corrected a L4 Exhibition page. You must update a dependent L3 Concept \
page so it is logically consistent with the corrected Exhibition.

## Corrected Exhibition ({exh_id})
{exh_content}

## Current Concept page ({con_id}) — to be updated
{con_content}

## Your task
Rewrite the Concept page to reflect the Exhibition's corrections.

Rules:
- Preserve the existing CON- ID, YAML frontmatter structure, and all wikilinks.
- Only change claims that are DIRECTLY contradicted or supplemented by the corrected Exhibition.
- Add the field `corrected_by: [[04_Exhibitions/{exh_id}]]` to the frontmatter.
- Update `updated: {today}` in frontmatter.
- Do NOT change the `## Relations` Atom links unless absolutely required.
- If no changes are needed, return the Concept page UNCHANGED (same content).
- Output ONLY the full updated markdown. No preamble, no code fences.
"""

ATOM_UPDATE_FROM_CONCEPT_PROMPT = """\
A L3 Concept page has been updated due to a human agent's correction. You must update a \
dependent L2 Atom page if its core claim is directly contradicted by the updated Concept.

## Updated Concept ({con_id})
{con_content}

## Current Atom page ({atm_id}) — to be checked and possibly updated
{atm_content}

## Your task
Rewrite the Atom only if its claim is DIRECTLY contradicted by the Concept.

Rules:
- If the Atom is NOT contradicted: return it COMPLETELY UNCHANGED.
- If the Atom IS contradicted: update ONLY the `one_liner` frontmatter field and the \
  "Definition / Claim" section in the body. Keep everything else the same.
- If updating, set `is_flagged_for_agent: true` and `updated: {today}` in frontmatter.
- Preserve the ATM- ID and all wikilinks exactly.
- Output ONLY the full updated markdown. No preamble, no code fences.
"""


def build_concept_update_from_exhibition_messages(
    exh_id: str,
    exh_content: str,
    con_id: str,
    con_content: str,
    today: str,
) -> list[ChatMessage]:
    """Backward propagation: update a CON to be consistent with a corrected EXH."""
    user_content = CONCEPT_UPDATE_FROM_EXHIBITION_PROMPT.format(
        exh_id=exh_id,
        exh_content=exh_content[:2000],
        con_id=con_id,
        con_content=con_content[:2000],
        today=today,
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


def build_atom_update_from_concept_messages(
    con_id: str,
    con_content: str,
    atm_id: str,
    atm_content: str,
    today: str,
) -> list[ChatMessage]:
    """Backward propagation: update an ATM if directly contradicted by an updated CON."""
    user_content = ATOM_UPDATE_FROM_CONCEPT_PROMPT.format(
        con_id=con_id,
        con_content=con_content[:1500],
        atm_id=atm_id,
        atm_content=atm_content[:1200],
        today=today,
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Contradiction detection (used by `wiki lint --deep`)
# ---------------------------------------------------------------------------

CONTRADICTION_RESOLUTION_PROMPT = """\
You are resolving a factual conflict between two L2 Atom pages.

Atom A ({path_a}):
---
{content_a}
---

Atom B ({path_b}):
---
{content_b}
---

Identified conflict:
{conflict_reasoning}

Propose minimal body edits to make both Atoms factually consistent.
Preserve the existing structure (sections, wikilinks) as much as possible.

Return ONLY a valid JSON object:
{{
  "reasoning": "One or two sentences explaining how the conflict is resolved",
  "atom_a_body_revised": "<revised body for Atom A — sections only, no frontmatter>",
  "atom_b_body_revised": "<revised body for Atom B — sections only, no frontmatter>"
}}

Return ONLY the JSON. No prose, no code fences.
"""


def build_contradiction_resolution_messages(
    path_a: str,
    content_a: str,
    path_b: str,
    content_b: str,
    conflict_reasoning: str,
) -> list[ChatMessage]:
    """Build messages for LLM-powered contradiction resolution."""
    user_content = CONTRADICTION_RESOLUTION_PROMPT.format(
        path_a=path_a,
        content_a=content_a[:3000],
        path_b=path_b,
        content_b=content_b[:3000],
        conflict_reasoning=conflict_reasoning[:500],
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


CONTRADICTION_DETECTION_PROMPT = """\
You are the Curator reviewing two Atom or Concept pages for contradictions.

Page A: {path_a}
---
{content_a}
---

Page B: {path_b}
---
{content_b}
---

Compare the factual claims. If there is a clear, direct contradiction between
specific claims in these pages, describe it exhaustively in detail, citing the exact
conflicting statements.

Only flag REAL contradictions — not differences in scope, detail level, or framing.
An elaboration is NOT a contradiction.

If no contradiction: respond exactly with: NONE
Otherwise: state the conflict directly, no preamble.
"""


# ---------------------------------------------------------------------------
# Lint --fix: LLM-powered broken wikilink reconnection
# ---------------------------------------------------------------------------

LINT_RELINK_PROMPT = """\
You are repairing a broken wikilink in a Curator knowledge DAG page.

## Page with the broken link
Path: {page_path}

{page_content}

## Broken link
[[{broken_target}]] — this target page no longer exists.

## Candidate pages in {expected_layer}
{candidates_list}

## Task
Identify the single best candidate that [[{broken_target}]] was INTENDED to reference,
based on the broken link's name and the surrounding context in the page above.

Reply with ONLY one of:
- The exact slug from the candidates list (e.g. `02_Atoms/ATM-abc12345`)
- The word `NONE` if no candidate is a plausible semantic match

No explanation. No preamble. One line only.
"""


# ---------------------------------------------------------------------------
# Persona interview — multi-turn LLM conversation for persona setup
# ---------------------------------------------------------------------------

PERSONA_INTERVIEW_SYSTEM = """\
You are a thoughtful knowledge-base consultant interviewing a user to configure their personal knowledge vault.

Your goal: extract enough information to produce a structured persona JSON. Ask focused follow-up questions when the user's answer is vague. When you have enough information, propose the JSON and ask for confirmation.

Rules:
- Ask one or two questions at a time — do not overwhelm.
- If the user says something vague (e.g. "tech stuff"), probe: "Are you focusing more on software engineering, mathematics, data science, or something else?"
- When ready, respond with ONLY a JSON object with the key "done": true and the persona fields. No prose.
- If the user says "skip" at any point, respond immediately with {"done": true, "persona": null} and nothing else.
"""

PERSONA_INTERVIEW_CURATOR_OPENER = """\
I'll ask a few short questions to configure the Curator persona for this vault.
This helps the Curator tailor how it organizes and verifies knowledge across all sources.

What kinds of knowledge do you plan to collect in this vault?
(e.g. academic research, technical notes, business insights, creative writing, recipes…)
"""

PERSONA_INTERVIEW_ARTIST_OPENER = """\
I'll ask a few short questions to configure the Artist persona for "{project}".
This shapes how concepts and exhibitions are generated for this workspace.

What is the main domain or topic of this workspace?
(e.g. 3D rendering, machine learning, cooking techniques, historical analysis…)
"""


def build_persona_interview_messages(
    history: list[dict],
    is_workspace: bool = False,
    project: str = "",
) -> list[ChatMessage]:
    """Build message list for a persona interview turn.

    history: list of {"role": "user"|"assistant", "content": "..."} dicts.
    The history should include the opener as the first assistant message.
    """
    messages = [ChatMessage(role="system", content=PERSONA_INTERVIEW_SYSTEM)]
    for turn in history:
        messages.append(ChatMessage(role=turn["role"], content=turn["content"]))
    return messages


def build_lint_relink_messages(
    page_path: str,
    page_content: str,
    broken_target: str,
    expected_layer: str,
    candidates_list: str,
) -> list[ChatMessage]:
    """Lint --fix: ask the LLM to find the best replacement for a broken wikilink."""
    user_content = LINT_RELINK_PROMPT.format(
        page_path=page_path,
        page_content=page_content,
        broken_target=broken_target,
        expected_layer=expected_layer,
        candidates_list=candidates_list,
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]
