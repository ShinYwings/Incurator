"""Entity/relation extraction prompt family (L3 graph).

Builds graph structure (typed entities + typed, directed, confidence-scored
relations) from knowledge units. Relation endpoints must be declared entities.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..contracts import PromptContract
from ..registry import register

PROMPT_ID = "curator.entity_relation_extract"
VERSION = "v1"

EntityType = Literal[
    "concept", "method", "dataset", "metric", "system", "person",
    "organization", "other",
]
AssertionSource = Literal["source_states", "system_infers", "workspace_derives"]


class EntityRelationExtractInput(BaseModel):
    units_block: str
    valid_span_ids_block: str


class ExtractedEntity(BaseModel):
    canonical_name: str
    entity_type: EntityType
    description: str = ""
    source_span_ids: list[str] = Field(default_factory=list)


class ExtractedRelation(BaseModel):
    source: str  # canonical_name of an entity in this output
    target: str  # canonical_name of an entity in this output
    relation_type: str
    description: str = ""
    assertion_source: AssertionSource = "source_states"
    source_span_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class EntityRelationExtractOutput(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)


SYSTEM_TEMPLATE = """\
You are the Curator's Graph Builder. From knowledge units, you extract named
entities and typed relations that form a knowledge graph.

Hard rules:
- Declare every entity you reference. A relation's source and target MUST each be
  the canonical_name of an entity you list in "entities".
- entity_type MUST be exactly one of: "concept", "method", "dataset", "metric",
  "system", "person", "organization", "other".
- relation_type is a short verb phrase, e.g. "improves", "is_a", "discretizes",
  "contradicts", "depends_on".
- assertion_source: "source_states" only when a source literally states the
  relation; "system_infers" when you infer it; "workspace_derives" for later
  interpretation. Only "source_states" relations are source-grounded.
- Cite source_span_ids from the allowed list only; never invent ids.
- confidence is a float in [0,1].
- Never propose editing the original source.

Return ONLY JSON:
{
  "entities": [
    {"canonical_name": "ResNet", "entity_type": "method", "description": "...",
     "source_span_ids": ["SPAN-..."]}
  ],
  "relations": [
    {"source": "ResNet", "target": "degradation problem",
     "relation_type": "addresses", "assertion_source": "source_states",
     "source_span_ids": ["SPAN-..."], "confidence": 0.9}
  ]
}"""

USER_TEMPLATE = """\
Allowed source span ids (cite only these):
{{ valid_span_ids_block }}

Knowledge units:
---
{{ units_block }}
---

Extract entities and relations as JSON."""


CONTRACT = register(
    PromptContract(
        prompt_id=PROMPT_ID,
        version=VERSION,
        family="entities",
        role="extractor",
        purpose="Build the entity/relation graph from knowledge units.",
        input_model=EntityRelationExtractInput,
        output_model=EntityRelationExtractOutput,
        system_template=SYSTEM_TEMPLATE,
        user_template=USER_TEMPLATE,
        validators=("relation_endpoints", "source_span_ids", "confidence_range",
                    "no_source_truth_pollution"),
        temperature=0.2,
        requires_source_spans=True,
    )
)
