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
from . import constants as consts

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

Your goal is MAXIMUM INFORMATION EXTRACTION — not compression, not a brief summary.
Think of yourself as a meticulous archivist who must preserve every meaningful detail.

Return ONLY a valid JSON object with this exact schema:
{
  "title": "Precise, specific document title (max 100 chars)",
  "domain": "Primary knowledge domain (e.g. 'domain-name', 'broad-topic')",
  "summary": "<see rules below>",
  "key_claims": [
    "Claim 1 — precise, falsifiable factual statement",
    "Claim 2"
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

SUMMARY RULES (read carefully — this is the most important field):
- Write a DENSE, SECTION-BY-SECTION breakdown of the entire source.
- For EVERY section or major paragraph of the source: write at least 3–5 bullet points capturing its specific content. Do NOT collapse multiple paragraphs into a single vague sentence.
- Use nested bullet points for sub-arguments, steps, or sub-components.
- FORBIDDEN: do NOT write "the paper discusses X" or "the author argues Y" — instead extract the ACTUAL content of X or Y with full specificity.
- FORBIDDEN: do NOT skip or compress any section because it seems minor. Include ALL sections.
- FORBIDDEN: do NOT write flowing prose. Use only dense Markdown bullet points and nested lists.
- If the source contains equations, algorithms, procedures, or formal definitions: reproduce them ENTIRELY using LaTeX math blocks ($ or $$). Do NOT paraphrase or omit them.
- Prefer to write TOO MUCH over too little. A 2000-word summary of a 10-page paper is appropriate.

KEY_CLAIMS RULES:
- Extract ALL falsifiable factual claims the source makes. Minimum 5; aim for 10–15 for a typical paper.
- Each claim must be self-contained: a reader with no source access should understand exactly what is claimed.
- Include quantitative results, comparisons, and thresholds when present.

ATOM_CANDIDATES RULES:
- Extract EVERY concept, entity, method, procedure, or relationship substantive enough for its own knowledge node.
- Minimum 5 candidates; no upper limit. A 10-page technical paper may yield 20–40 candidates.
- one_liner: a single precise sentence — not vague ("an important concept") but specific ("Concept X achieves Y by applying transformation Z to component W").

Return ONLY the JSON. No prose, no markdown fences.
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
   parent_source: {layer_l1}/{context_id}
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
        layer_l1=consts.LAYER_L1,
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
# Pass 1½ — ATOM COORDINATOR (cross-source semantic deduplication)
# ---------------------------------------------------------------------------

ATOM_COORDINATOR_INSTRUCTIONS = """\
You are the Knowledge Coordinator. You receive a list of newly extracted Atoms \
and existing Atoms from the same domain.

Your task: identify pairs of Atoms that describe the SAME underlying concept \
and should be merged into one.

Merge criteria (ALL must hold):
- Identical or near-identical core claim
- Overlapping subject even if named differently
- One is a subset of the other

Return ONLY valid JSON:
{
  "merge_pairs": [
    {"keep_id": "ATM-xxx", "absorb_id": "ATM-yyy", "reason": "one-line justification"}
  ],
  "no_action": ["ATM-zzz"]
}

Rules:
- Only merge when clearly the SAME concept — different aspects = keep separate
- keep_id must be the more complete or more recently updated atom
- If uncertain, put both in no_action
- If nothing to merge, return {"merge_pairs": [], "no_action": [...all ids...]}
"""


def build_atom_coordinator_messages(
    new_atoms_summary: str,
    existing_atoms_summary: str,
    domain: str,
) -> list[ChatMessage]:
    """Coordinator: detect semantic duplicates across new and existing atoms."""
    user_content = (
        f"Domain: {domain}\n\n"
        f"### Newly extracted Atoms\n{new_atoms_summary}\n\n"
        f"### Existing Atoms in same domain\n{existing_atoms_summary or '(none yet)'}\n\n"
        "Identify merge pairs following the instructions."
    )
    return [
        ChatMessage(role="system", content=ATOM_COORDINATOR_INSTRUCTIONS),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Pass 1 Orchestrator — decompose extraction into parallel tasks
# ---------------------------------------------------------------------------

ATOM_ORCHESTRATOR_INSTRUCTIONS = """\
You are the Extraction Orchestrator. Given a source document summary and the \
list of atom candidates to extract, divide the work into independent tasks.

Return ONLY valid JSON:
{
  "tasks": [
    {
      "task_id": "t1",
      "candidates": ["candidate name 1", "candidate name 2"],
      "context_hint": "one-sentence focus area for the extractor"
    }
  ]
}

Rules:
- Each task: 2–5 candidates that share a coherent sub-topic
- Tasks must be non-overlapping
- If ≤ 3 total candidates: return a single task containing all of them
- context_hint must be concrete: e.g. "mathematical foundations of the specific sub-topic" \
not just "the sub-topic"
"""


def build_atom_orchestrator_messages(
    source_title: str,
    domain: str,
    candidates_summary: str,
    existing_atoms_summary: str,
) -> list[ChatMessage]:
    """Orchestrator: plan task decomposition for parallel atom extraction."""
    user_content = (
        f"Source: {source_title} (domain: {domain})\n\n"
        f"### Candidates to extract\n{candidates_summary}\n\n"
        f"### Existing Atoms in same domain (for context)\n"
        f"{existing_atoms_summary or '(none yet)'}\n\n"
        "Divide the candidates into parallel extraction tasks."
    )
    return [
        ChatMessage(role="system", content=ATOM_ORCHESTRATOR_INSTRUCTIONS),
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
You are an elite curator synthesizing a L4 Exhibition page. This is the ultimate "Fusion Point" where objective source knowledge (Concepts) meets the user's workspace context and agent instructions. 

Your goal is NOT to summarize, but to build a **RICH, COMPREHENSIVE, and AUTHORITATIVE** knowledge document with high **KNOWLEDGE DENSITY**.

Rules for Rich Synthesis:
- DEEP INTEGRATION: Actively blend external facts (Concepts) with internal workspace context. Explain how prior knowledge applies to the current project/research situation.
- BEYOND SUMMARY: Do not just list facts. Connect them, find emerging patterns, and provide deep reasoning. The prose must be dense, professional, and authoritative.

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


_EXHIBITION_INTENT_DIRECTIVES: dict[str, str] = {
    "researcher": (
        "Suggest specific follow-up papers, open hypotheses, and experimental validations "
        "the researcher should pursue next based on the evidence in this exhibition."
    ),
    "engineer": (
        "Describe specific code, system, or pipeline implementation steps the engineer "
        "should execute next. Include API calls, data structures, or algorithms where applicable."
    ),
    "learner": (
        "List the core concepts the learner should review and provide concrete practice "
        "exercises or worked examples to solidify understanding of this exhibition's content."
    ),
}
_EXHIBITION_INTENT_DEFAULT = (
    "Explicit instructions and hypotheses for the AI Agent (Artist). "
    "What specific code, pipeline, or research task should the Agent execute next based on this exhibition?"
)


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
    exhibition_intent: str = "",
) -> list[ChatMessage]:
    """Pass 3 — draft a single L4 Exhibition page."""
    theme_ids_yaml = ", ".join(f"'03_Concepts/{t}'" for t in theme_ids)
    if flagged_fragment_ids:
        flagged_fragments = ", ".join(f"[[02_Atoms/{f}]]" for f in flagged_fragment_ids)
    else:
        flagged_fragments = "none"

    directive = _EXHIBITION_INTENT_DIRECTIVES.get(exhibition_intent, _EXHIBITION_INTENT_DEFAULT)
    template = CURATION_PAGE_TEMPLATE.replace(
        "   - **3. Actionable Directives for Agent**: Explicit instructions and hypotheses for the AI Agent (Artist). What specific code, pipeline, or research task should the Agent execute next based on this exhibition? Confidence score: {confidence}. Flagged atoms that require human review: {flagged_fragments}",
        f"   - **3. Actionable Directives for Agent**: {directive} Confidence score: {{confidence}}. Flagged atoms that require human review: {{flagged_fragments}}",
    )

    user_content = template.format(
        curation_id=curation_id,
        topic=topic,
        domain=domain or consts.DOMAIN_GENERAL,
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
- domain: a short slug derived from the concepts' shared domain (e.g. "broad-topic", "sub-topic").
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

EXHIBITION_SMART_UPDATE_PROMPT = """\
You are an expert curator updating a L4 Exhibition page. You must integrate new information \
into the existing Exhibition body while maintaining its premium structure and formatting.

The new information may come from conversational insights (Follow-up questions) or \
updated downstream Concepts (Supporting Concepts).

## Current Exhibition Body ({exh_id})
{existing_body}

## New Information to Integrate
{updates}

## Your task
Rewrite the Exhibition body to incorporate the new information. This page is the "Final Synthesis" where objective source knowledge meets the user's workspace insights. Your goal is NOT to summarize, but to build a **RICH, COMPREHENSIVE, and AUTHORITATIVE** knowledge document with high **KNOWLEDGE DENSITY**.

Rules:
- DEEP SYNTHESIS: Actively blend external facts from Concepts with internal insights from the Workspace. Create a narrative that shows how these two worlds connect.
- TOPIC-CENTRIC INTEGRATION: Seamlessly integrate updates into appropriate sections (Executive Brief, Background, Key Facts, Directives, etc.). The final output must read as a single, coherent knowledge document about the topic itself.
- NO META-COMMENTARY: Do NOT include any meta-talk or changelog-style phrases. Never say "Updated section:", "This was modified to include...", or "The following information was added...".
- PRIORITY TRUTH: If new information CONTRADICTS the current body, prioritize the new information as the latest truth.
- FORMATTING: Maintain the bold-bullet format (- **Section**: Content). No ## headers in body.
- PRESERVATION: Preserve ALL existing [[03_Concepts/CON-xxx]] wikilinks unless specifically deprecated.
- OUTPUT ONLY: Output ONLY the updated markdown body. No frontmatter, no preamble, no commentary.
"""


def build_exhibition_refinement_messages(
    exh_id: str,
    existing_body: str,
    updates: str,
) -> list[ChatMessage]:
    """Build smart update prompt for an Exhibition using unified template."""
    user_content = EXHIBITION_SMART_UPDATE_PROMPT.format(
        exh_id=exh_id,
        existing_body=existing_body,
        updates=updates,
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
You are updating a L3 Concept page based on corrections or new insights found in a L4 Exhibition. \
This Concept may be an existing dependency or a related topic found via semantic search.

## Upstream Exhibition ({exh_id})
{exh_content}

## Target Concept page ({con_id}) — to be updated
{con_content}

## Your task
Rewrite the Concept page to incorporate the information from the Exhibition.

Rules:
- TOPIC-CENTRIC INTEGRATION: Merge updates seamlessly into the flow of the topic. The resulting page must read as a pure, coherent knowledge document.
- NO META-COMMENTARY: Do NOT include meta-talk in the body. Never say "Updated to match...", "This was corrected by...", or "Following the exhibition...".
- PRIORITY TRUTH: If the Exhibition CORRECTS the Concept, update the claims to be consistent with the latest truth.
- PRESERVATION: Preserve the CON- ID, YAML structure, and existing wikilinks.
- METADATA: Add `corrected_by: [[04_Exhibitions/{exh_id}]]` and update `updated: {today}` in the frontmatter.
- OUTPUT ONLY: Output ONLY the full updated markdown. No preamble, no code fences, no commentary.
"""

ATOM_UPDATE_FROM_CONCEPT_PROMPT = """\
You are updating a L2 Atom page based on changes in a L3 Concept. This Atom's core claim \
must be checked for consistency with the latest Concept description.

## Upstream Concept ({con_id})
{con_content}

## Target Atom page ({atm_id}) — to be checked and updated
{atm_content}

## Your task
Reconcile the Atom's claim with the Concept. 

Rules:
- ATOMIC RECONCILIATION: Reconcile the Atom's claim with the Concept seamlessly. The resulting page must read as a pure, atomic fact about the topic.
- NO META-COMMENTARY: Do NOT include any meta-talk or changelog phrases in the body. Never say "Updated to match...", "This was corrected by...", etc.
- PRIORITY TRUTH: If the Concept CONTRADICTS the Atom, update the `one_liner` and the "Definition / Claim" section to resolve the conflict.
- METADATA: If updating, set `is_flagged_for_agent: true` and `updated: {today}` in frontmatter.
- PRESERVATION: Preserve the ATM- ID and all wikilinks exactly.
- OUTPUT ONLY: Output ONLY the full updated markdown. No preamble, no code fences, no commentary.
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


BATCH_CONCEPT_UPDATE_FROM_EXHIBITION_PROMPT = """\
You are updating multiple L3 Concept pages based on corrections or new insights found in a L4 Exhibition.

## Upstream Exhibition ({exh_id})
{exh_content}

## Target Concept pages
{concept_blocks}

## Your task
For each target Concept, decide whether it needs to change. Return JSON only:

{{
  "concepts": [
    {{
      "id": "CON-...",
      "changed": true,
      "markdown": "full updated markdown page"
    }}
  ]
}}

Rules:
- Include changed Concept IDs only. Omit Concepts that do not need changes.
- If you include an unchanged Concept, set `changed` to false and omit `markdown`.
- TOPIC-CENTRIC INTEGRATION: Merge updates seamlessly into the topic. The resulting page must read as a pure, coherent knowledge document.
- NO META-COMMENTARY: Do NOT include meta-talk in the body. Never say "Updated to match...", "This was corrected by...", or "Following the exhibition...".
- PRIORITY TRUTH: If the Exhibition CORRECTS the Concept, update the claims to be consistent with the latest truth.
- PRESERVATION: Preserve each CON- ID, YAML structure, and existing wikilinks.
- METADATA: For changed Concepts, add `corrected_by: [[04_Exhibitions/{exh_id}]]` and update `updated: {today}` in frontmatter.
- OUTPUT ONLY: valid JSON. No preamble, no code fences, no markdown outside JSON.
"""


def build_batch_concept_update_from_exhibition_messages(
    exh_id: str,
    exh_content: str,
    concept_pages: list[tuple[str, str]],
    today: str,
) -> list[ChatMessage]:
    """Backward propagation: update several CON pages in one structured call."""
    blocks: list[str] = []
    for con_id, con_content in concept_pages:
        blocks.append(
            f"### Concept {con_id}\n"
            f"{con_content[:2200]}"
        )
    user_content = BATCH_CONCEPT_UPDATE_FROM_EXHIBITION_PROMPT.format(
        exh_id=exh_id,
        exh_content=exh_content[:3000],
        concept_blocks="\n\n".join(blocks),
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
# Exhibition update from conversational insight
# ---------------------------------------------------------------------------

EXHIBITION_UPDATE_FROM_INSIGHT_PROMPT = """\
You are updating a L4 Exhibition page to incorporate a new conversational insight or direct correction.

## Current Exhibition Body ({exh_id})
{exh_content}

## New Insight or Correction
{insight}

## Context / Reasoning
{context}

## Your task
Rewrite the Exhibition body to incorporate this update.

Rules:
- Seamlessly integrate the new information into the appropriate sections. 
- If the new insight CONTRADICTS the current body, prioritize the new information (it represents the latest consensus).
- Maintain the bold-bullet format (- **Section**: Content).
- Do NOT delete existing [[03_Concepts/CON-xxx]] wikilinks unless the concept itself is being deprecated by this update.
- Output ONLY the full updated markdown body.
"""


def build_exhibition_update_from_insight_messages(
    exh_id: str,
    exh_content: str,
    insight: str,
    context: str = "",
) -> list[ChatMessage]:
    """Build prompt for integrating a conversational insight into an Exhibition's body."""
    updates = f"Conversational Insight: {insight}\nContext: {context}"
    return build_exhibition_refinement_messages(exh_id, exh_content, updates)


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

_CURATOR_PERSONA_FIELDS = """\
Target JSON schema (curator persona):
{
  "area": "STEM | Humanities | Arts | Business | Personal",
  "text": "2-4 sentence description of the vault's knowledge focus and goals",
  "knowledge_artifacts": ["primary artifact types this vault contains, e.g. research papers, code, reports, recipes"],
  "verification_philosophy": "one or more ordered canonical methods, e.g. citation-and-derivation or citation-and-derivation + logical-coherence",
  "exhibition_intent": "knowledge-worker | researcher | engineer | learner",
  "confidence": {"high_threshold": 0.85, "low_threshold": 0.55},
  "disambiguation_keywords": ["3-8 domain-specific terms to disambiguate concepts"]
}"""

_ARTIST_PERSONA_FIELDS = """\
Target JSON schema (artist persona for workspace "{project}"):
{
  "domain": "primary domain slug, e.g. domain-name, broad-topic",
  "subdomain": "more specific focus, e.g. specific-subtopic (optional)",
  "goal": "2-4 sentence description of this workspace's knowledge goal",
  "exhibition_intent": "researcher | engineer | learner",
  "disambiguation_keywords": ["3-8 workspace-specific terms for concept disambiguation"],
  "confidence": {"high_threshold": 0.85, "low_threshold": 0.55}
}
exhibition_intent meanings:
- researcher: next papers/hypotheses to validate
- engineer: specific code/system implementation steps
- learner: concepts to review and practice exercises"""

PERSONA_INTERVIEW_CURATOR_SYSTEM = """\
You are a knowledge-base consultant interviewing a user to configure their Curator persona (the Vault's knowledge identity).

{field_schema}

The interview consists of 4 questions. You must ask them ONE AT A TIME in English.
Q1: What is the broad area and main focus of this Vault? (area + text)
Q2: What are your source(s) of truth for verifying knowledge in this Vault? (verification_philosophy; multi-select allowed)
Q3: What types of knowledge artifacts does this Vault primarily contain? (knowledge_artifacts)
Q4: How should ambiguous or uncertain knowledge be handled? (confidence + disambiguation_keywords)

For EACH question, infer the user's intent from previous answers and provide 5 tailored choices.
Q1 and Q4 are single-select by default. Q2 and Q3 allow multi-select answers
such as "1,4"; clearly label them as multi-select in the question text.

Format your message EXACTLY like this:
Q[X]/4: [Question Content]

  1) [Recommended Choice 1]
  2) [Recommended Choice 2]
  3) [Recommended Choice 3]
  4) [Recommended Choice 4]
  5) [Recommended Choice 5]

  Or type your own answer (s = skip). For multi-select questions, comma-separated numbers are allowed.

Rules:
- Speak in English.
- Ask ONLY ONE question per turn.
- Wait for the user's reply (a number 1-5, comma-separated numbers when the question says multi-select, free text, or 's').
- After receiving the answer to Q4, DO NOT ask another question. Instead, output ONLY a JSON object:
  {{"done": true, "persona": {{...filled fields...}}}}
- If the user types "s" or "skip" at any point, use default values for that question and move to the next. If they skip the whole interview at the start, return {{"done": true, "persona": null}}.
"""

PERSONA_INTERVIEW_ARTIST_SYSTEM = """\
You are a knowledge-base consultant interviewing a user to configure their Artist persona for workspace "{project}".

{field_schema}

The interview consists of 5 questions. You must ask them ONE AT A TIME in English.
Q1: What is the main topic or theme of this workspace? (domain & subdomain)
Q2: What is the primary knowledge goal of this workspace? (goal)
Q3: How do you intend to use the final output? (exhibition_intent)
Q4: Are there any specific terms that need precise definition in this workspace? (disambiguation_keywords)
Q5: What confidence thresholds should filter knowledge for this workspace? (confidence)

For EACH question, infer the user's intent from previous answers and provide 5 tailored choices.

Format your message EXACTLY like this:
Q[X]/5: [Question Content]

  1) [Recommended Choice 1]
  2) [Recommended Choice 2]
  3) [Recommended Choice 3]
  4) [Recommended Choice 4]
  5) [Recommended Choice 5]

  Or type your own answer (s = skip)

Rules:
- Speak in English.
- Ask ONLY ONE question per turn.
- Wait for the user's reply (a number 1-5, or free text, or 's').
- After receiving the answer to Q5, DO NOT ask another question. Instead, output ONLY a JSON object:
  {{"done": true, "persona": {{...filled fields...}}}}
- If the user types "s" or "skip", use default values for that question and move to the next. If they skip at the start, return {{"done": true, "persona": null}}.
"""

PERSONA_INTERVIEW_CURATOR_OPENER = """\
I will ask you 4 questions to set up the knowledge identity (Curator Persona) for the entire Vault.
"""

PERSONA_INTERVIEW_ARTIST_OPENER = """\
I will ask you 5 questions to set up the knowledge goal (Artist Persona) for the "{project}" workspace.
"""


def build_persona_interview_messages(
    history: list[dict],
    is_workspace: bool = False,
    project: str = "",
) -> list[ChatMessage]:
    """Build message list for a persona interview turn.

    history: list of {"role": "user"|"assistant", "content": "..."} dicts.
    The history should include the opener as the first assistant message.
    is_workspace: True for artist persona (workspace-level), False for curator persona.
    project: workspace name, used in artist persona field schema.
    """
    if is_workspace:
        field_schema = _ARTIST_PERSONA_FIELDS.replace("{project}", project or "this workspace")
        system = PERSONA_INTERVIEW_ARTIST_SYSTEM.replace("{field_schema}", field_schema)
    else:
        system = PERSONA_INTERVIEW_CURATOR_SYSTEM.replace("{field_schema}", _CURATOR_PERSONA_FIELDS)
    messages = [ChatMessage(role="system", content=system)]
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

# ---------------------------------------------------------------------------
# L1 Context Update (Backward Propagation from L2)
# ---------------------------------------------------------------------------

CONTEXT_UPDATE_FROM_ATOM_PROMPT = """You are updating an L1 Context page to reflect a corrected or refined L2 Atom.

L2 Atom (Corrected):
{atm_content}

L1 Context (Original):
{ctx_content}

Today's Date: {today}

Rules:
1. Update the L1 Context body to stay consistent with the corrected Atom. 
2. If the Atom introduces new factual details that were missing from the source summary, incorporate them.
3. Preserve the original source provenance and metadata.
4. Output the full markdown (frontmatter + body).
"""

def build_context_update_from_atom_messages(
    atm_id: str,
    atm_content: str,
    ctx_id: str,
    ctx_content: str,
    today: str,
) -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content="You are a meticulous knowledge curator."),
        ChatMessage(
            role="user",
            content=CONTEXT_UPDATE_FROM_ATOM_PROMPT.format(
                atm_id=atm_id,
                atm_content=atm_content,
                ctx_id=ctx_id,
                ctx_content=ctx_content,
                today=today,
            ),
        ),
    ]

# ---------------------------------------------------------------------------
# Feedback Requests
# ---------------------------------------------------------------------------

MISSING_L1_CONTEXT_FEEDBACK_PROMPT = """The following L2 Atom has been updated or created, but no matching L1 Context (source) could be identified to justify this knowledge.

L2 Atom:
{atm_content}

Please provide the source (URL, file path, or manual notes) that supports this claim, or confirm if this should be treated as an unverified agent assumption.
"""

def build_backprop_insight_extraction_messages(page_body: str, gap_reasoning: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are an expert insight extractor. You will be provided with the body of a knowledge node, "
                "and a logical verification gap describing 'external facts' that this node introduces. "
                "Your job is to extract ONLY those new external facts and claims into a cohesive, standalone paragraph. "
                "Do not include meta-commentary, just the facts themselves."
            ),
        },
        {
            "role": "user",
            "content": f"Node Body:\n{page_body}\n\nGap Reasoning:\n{gap_reasoning}\n\nPlease extract the specific new insights or claims.",
        },
    ]
