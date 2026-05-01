"""Prompt templates for the LLM Curator pipeline.

The Curator runs four sequential passes per source, building a DAG:

    sync   → Pass 0 (SUMMARY)  — L1: 1:1 hash-matched source summary
    ingest → Pass 1 (ATOMS)    — L2: irreducible facts / equations
    ingest → Pass 2 (CONCEPTS) — L3: clustered atoms into coherent concepts
    ingest → Pass 3 (SYNTHESIS)— L4: cross-domain terminal knowledge outputs

All pages use UUID-based IDs (SUM-, ATM-, CON-, SYN-) so the Agent can
traverse the DAG by ID without relying on human-readable slugs.
"""

from __future__ import annotations

from .llm import ChatMessage


# ---------------------------------------------------------------------------
# System prompt — Curator identity, shared across all passes
# ---------------------------------------------------------------------------

CURATOR_SYSTEM_PROMPT = """\
You are the CURATOR — a background abstraction engine whose sole purpose is to \
transform raw human knowledge into a machine-readable DAG (Directed Acyclic Graph) \
stored in `.curator/Collections/`.

Your output is consumed ONLY by AI agents. DO NOT consider human readability at all.
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
# Pass 0 — SUMMARY  (L1: runs during `wiki sync`)
# ---------------------------------------------------------------------------

SUMMARY_INSTRUCTIONS = """\
You are processing a source document for the Curator knowledge pipeline.

Generate a highly detailed and comprehensive machine-readable summary of the source below.

Return ONLY a valid JSON object with this exact schema:
{
  "title": "Precise, specific document title (max 100 chars)",
  "domain": "Primary knowledge domain (e.g. 'computer-vision', 'mathematics', 'nlp')",
  "summary": "An EXTREMELY GRANULAR, highly detailed, section-by-section summary. Do not compress or skip details; extract meaning almost paragraph-by-paragraph. Thoroughly explain all core arguments, background context, mathematical formulations, and technical implications. CRITICAL: Preserve all mathematical equations and formulas precisely using LaTeX format ($ or $$).",
  "key_claims": [
    "Claim 1 — precise, falsifiable factual statement",
    "Claim 2",
    "Claim 3"
  ],
  "atom_candidates": [
    {
      "name": "Canonical concept/entity name",
      "type": "fact | equation | theoretical_constraint | entity | technique",
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
    """Pass 0 — generate L1 Summary JSON during `wiki sync`."""
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

ATOM_PAGE_TEMPLATE = """\
Write a single Atom page for the `.curator/Collections/02_Atoms/` layer.

Atom ID (pre-assigned): {atom_id}
Concept name: {name}
Type: {atom_type}
One-liner: {one_liner}
Parent source summary ID: {summary_id}
Parent source path: {source_path}
Today (ISO 8601): {today}

Source excerpt relevant to this concept:
{excerpt}

Write the complete markdown page with:
1. YAML frontmatter — use EXACTLY this structure:
   ---
   id: {atom_id}
   type: atom
   parent_source: "[[01_Summaries/{summary_id}]]"
   source_path: "[[{source_path}]]"
   claim_type: {atom_type}
   contradicts: []
   is_verified_by_human: false
   is_flagged_for_agent: false
   last_updated: {today}
   ---

2. An H1 heading: the canonical name of the concept.

3. Body (machine-optimized):
   - **Definition / Claim**: Precise statement. **CRITICAL: You MUST use LaTeX format ($ or $$) for ALL mathematical equations, formal definitions, and symbols.**
   - **Context**: When / where does this apply?
   - **Constraints**: Boundary conditions, assumptions, or edge cases.
   - **Relations**: [[wikilinks]] to related atoms or concepts.

4. A brief `## Source` section linking to [[01_Summaries/{summary_id}]].

Return ONLY the markdown. No preamble, no code fences.
"""


def build_atom_page_messages(
    atom_id: str,
    name: str,
    atom_type: str,
    one_liner: str,
    summary_id: str,
    source_path: str,
    excerpt: str,
    today: str,
) -> list[ChatMessage]:
    """Pass 1 — draft a single L2 Atom page."""
    user_content = ATOM_PAGE_TEMPLATE.format(
        atom_id=atom_id,
        name=name,
        atom_type=atom_type,
        one_liner=one_liner,
        summary_id=summary_id,
        source_path=source_path,
        excerpt=excerpt,
        today=today,
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


MERGE_ATOM_TEMPLATE = """\
Update this existing Atom page with new information from a new source.

---EXISTING ATOM PAGE---
{existing_content}
---END EXISTING---

New source summary ID: {new_summary_id}
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
3. If the new info CONTRADICTS, you MUST set `is_flagged_for_agent: true` in the YAML frontmatter, add "[[01_Summaries/{new_summary_id}]]" to the `contradicts:` list, and thoroughly document the conflict under a `## Logical Conflict` heading.
4. If it Corroborates or Expands, weave the new facts logically under the appropriate existing headings, or create new headings if necessary.
5. Update `last_updated: {today}` in frontmatter.
6. Keep all existing [[wikilinks]] intact.
7. CRITICAL: Preserve all LaTeX math formatting ($ or $$).

Return ONLY the complete updated markdown. No preamble, no code fences.
"""


def build_merge_atom_messages(
    existing_content: str,
    name: str,
    new_summary_id: str,
    new_source_path: str,
    new_description: str,
    excerpt: str,
    today: str,
) -> list[ChatMessage]:
    """Pass 1b — merge new source info into an existing Atom page."""
    user_content = MERGE_ATOM_TEMPLATE.format(
        existing_content=existing_content,
        name=name,
        new_summary_id=new_summary_id,
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
- A Concept groups multiple Atoms that share a coherent logical theme. Do not restrict the number of Atoms per Concept.
- Do NOT create singleton concepts (1 atom = 1 concept) — that's redundant.
- Prefer fewer, denser concepts over many sparse ones.
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


CONCEPT_PAGE_TEMPLATE = """\
Write a single Concept page for the `.curator/Collections/03_Concepts/` layer.

Concept ID (pre-assigned): {concept_id}
Concept name: {name}
Domain: {domain}
Today (ISO 8601): {today}

Constituent Atom IDs and their content:
{atoms_content}

Write the complete markdown page:
1. YAML frontmatter:
   ---
   id: {concept_id}
   type: concept
   dependencies: [{atom_ids_yaml}]
   domain: "{domain}"
   last_updated: {today}
   ---

2. H1: concept name

3. Body :
   - **1. Core Architecture**: What does this concept represent as a unified whole?
   - **2. Interaction of Atoms**: How do the constituent Atoms mathematically or logically weave together to form this concept? You MUST explain the exact relationship between these atoms and cite them via [[02_Atoms/ATM-xxx]].
   - **3. Mathematical Framework**: Detail the foundational equations and formulations supporting this concept. **CRITICAL: You MUST use LaTeX format ($ or $$) for ALL mathematical equations, formal definitions, and symbols.**
   - **4. Open Questions**: Unresolved tensions or contradictions within this concept (if any).

Return ONLY the markdown. No preamble, no code fences.
"""


def build_concept_page_messages(
    concept_id: str,
    name: str,
    domain: str,
    atom_ids: list[str],
    atoms_content: str,
    today: str,
) -> list[ChatMessage]:
    """Pass 2 — draft a single L3 Concept page."""
    atom_ids_yaml = ", ".join(f'"[[02_Atoms/{a}]]"' for a in atom_ids)
    user_content = CONCEPT_PAGE_TEMPLATE.format(
        concept_id=concept_id,
        name=name,
        domain=domain,
        atom_ids_yaml=atom_ids_yaml,
        atoms_content=atoms_content,
        today=today,
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Pass 3 — SYNTHESIS  (L4: cross-domain terminal knowledge outputs)
# ---------------------------------------------------------------------------

SYNTHESIS_PAGE_TEMPLATE = """\
Write a single Synthesis page for the `.curator/Collections/04_Synthesis/` layer.

Synthesis ID (pre-assigned): {synthesis_id}
Topic: {topic}
Today (ISO 8601): {today}

Core concepts involved:
{concepts_content}

Write the complete markdown page:
1. YAML frontmatter:
   ---
   id: {synthesis_id}
   type: synthesis
   core_concepts: [{concept_ids_yaml}]
   confidence_score: {confidence}
   requires_math_rigor: {requires_math}
   last_updated: {today}
   ---

2. H1: synthesis topic name

3. Body:
   - **1. Executive Research Brief**: What is the terminal conclusion or state of the art that emerges from combining these concepts?
   - **2. Theoretical Foundation**: Trace the logical and mathematical path from Atoms → Concepts → this Synthesis. Use [[wikilinks]]: [[03_Concepts/CON-xxx]], [[02_Atoms/ATM-yyy]]. **CRITICAL: You MUST use LaTeX format ($ or $$) for ALL mathematical derivations, formulas, and symbols.**
   - **3. State of the Art & Limitations**: Discuss unresolved tensions, edge cases, and contradictions. Why is the confidence score {confidence}? What flagged atoms (`is_flagged_for_agent: true`) affect this?
   - **4. Actionable Directives for Agent**: Explicit instructions and hypotheses for the AI Agent. What specific code, pipeline, or research task should the Agent execute next based on this synthesis?

Return ONLY the markdown. No preamble, no code fences.
"""


def build_synthesis_page_messages(
    synthesis_id: str,
    topic: str,
    concept_ids: list[str],
    concepts_content: str,
    confidence: float,
    requires_math: bool,
    today: str,
) -> list[ChatMessage]:
    """Pass 3 — draft a single L4 Synthesis page."""
    concept_ids_yaml = ", ".join(f'"[[03_Concepts/{c}]]"' for c in concept_ids)
    user_content = SYNTHESIS_PAGE_TEMPLATE.format(
        synthesis_id=synthesis_id,
        topic=topic,
        concept_ids_yaml=concept_ids_yaml,
        concepts_content=concepts_content,
        confidence=f"{confidence:.2f}",
        requires_math=str(requires_math).lower(),
        today=today,
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Synthesis planning — decide which concepts merit a synthesis
# ---------------------------------------------------------------------------

SYNTHESIS_PLANNING_INSTRUCTIONS = """\
You are deciding which L3 Concepts should be synthesized into L4 outputs.

Return ONLY a valid JSON object:
{
  "synthesis_plans": [
    {
      "topic": "Synthesis topic name",
      "concept_ids": ["CON-xxxx", "CON-yyyy"],
      "confidence": 0.85,
      "requires_math_rigor": true,
      "rationale": "1 sentence explaining what emergent insight this synthesis captures"
    }
  ]
}

Rules:
- Only propose a synthesis if 2+ concepts share a non-trivial logical connection.
- confidence: 0.90+ = direct retrieval quality; 0.60-0.90 = needs backtracking; <0.60 = HITL required.
- requires_math_rigor: true if the synthesis involves equations, proofs, or geometric arguments.
- Propose 1–5 synthesis plans.
- Return ONLY the JSON. No prose, no fences.
"""


def build_synthesis_planning_messages(
    concept_summaries: list[dict],
) -> list[ChatMessage]:
    """Decide which concept clusters merit L4 synthesis.

    Args:
        concept_summaries: List of dicts with keys: id, name, domain, atom_count
    """
    concepts_text = "\n".join(
        f"- {c['id']}: [{c['domain']}] {c['name']} ({c['atom_count']} atoms)"
        for c in concept_summaries
    )
    user_content = (
        f"{SYNTHESIS_PLANNING_INSTRUCTIONS}\n\n"
        f"---CONCEPTS---\n{concepts_text}\n"
    )
    return [
        ChatMessage(role="system", content=CURATOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# Contradiction detection (used by `wiki lint --deep`)
# ---------------------------------------------------------------------------

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
