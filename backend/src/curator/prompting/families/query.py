"""Query prompt family: router, local answer, global reduce.

Routing is deterministic-first; the router prompt is used only when deterministic
signals are ambiguous. Local answers ground in source spans/claims; global
answers reduce community-report intermediate points with source-span backfill.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..contracts import PromptContract
from ..registry import register

Route = Literal["local", "global", "explore", "source-section"]


# --- internal search query -------------------------------------------

class SearchQueryInput(BaseModel):
    message: str


class SearchQueryOutput(BaseModel):
    """The INTERNAL search query, or an explicit decision that there is none."""

    search_query: str = ""
    is_knowledge_question: bool = True
    reason: str = ""


SEARCH_QUERY_SYSTEM = """\
You derive the INTERNAL search query for a knowledge base.

The knowledge base is indexed in English. The user writes in any language. Your
job is to turn their message into a short English search query, or to state that
the message is not a knowledge question at all.

This is NOT translation. You are extracting what to look up.

Rules:
- Output English only, regardless of the input language.
- Keep it short: the topic terms someone would type into a search box. Never
  more than about 20 words, no matter how long the message is.
- Preserve technical terms, proper nouns, and notation exactly as written. Do
  not translate "Plücker coordinates" or "Gaussian Splatting" into something else.
- If the message pastes a long body of text and asks for something to be done to
  it (translated, rewritten, summarised, formatted, corrected), the pasted body
  is NOT the search query. Set is_knowledge_question=false.
- Set is_knowledge_question=false whenever answering needs no stored knowledge:
  the request is about manipulating text the user supplied, about the
  conversation itself, or is small talk. Judge the intent of the message, not
  the presence of any particular word.
- When is_knowledge_question is false, search_query MUST be empty.
- reason is one short English clause explaining the call.

Return ONLY JSON:
{"search_query": "...", "is_knowledge_question": true, "reason": "..."}"""

SEARCH_QUERY_USER = """\
Message:
{{ message }}

Return the JSON."""


SEARCH_QUERY_CONTRACT = register(
    PromptContract(
        prompt_id="curator.query_search_terms",
        version="v1",
        family="query",
        role="router",
        purpose="Derive the internal English search query, or decide there is none.",
        input_model=SearchQueryInput,
        output_model=SearchQueryOutput,
        system_template=SEARCH_QUERY_SYSTEM,
        user_template=SEARCH_QUERY_USER,
        temperature=0.0,
    )
)


# --- router ----------------------------------------------------------

class QueryRouterInput(BaseModel):
    question: str
    allowed_routes_block: str
    graph_status_block: str


class QueryRouterOutput(BaseModel):
    route: Route
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    fallback_route: Route | None = None


ROUTER_SYSTEM = """\
You are the Curator's Query Router. You choose how to answer a question.

Routes:
- local: precise entity/fact questions.
- global: broad synthesis across the whole workspace/vault.
- explore: open-ended discovery ("what else", "find connections", "new insight").
- source-section: answer from one source section.
- source-section: a question scoped to a specific source/section.

Rules:
- Choose only from the allowed routes provided.
- Prefer local for fact lookups, global for synthesis, explore for discovery.
- If the knowledge graph is incomplete, prefer a route that still works and set a
  fallback_route.

Return ONLY JSON:
{"route": "local", "reason": "...", "confidence": 0.0, "fallback_route": null}"""

ROUTER_USER = """\
Question: {{ question }}

Allowed routes:
{{ allowed_routes_block }}

Graph status:
{{ graph_status_block }}

Choose the route as JSON."""


# --- local answer ----------------------------------------------------

class QueryLocalAnswerInput(BaseModel):
    question: str
    evidence_block: str
    valid_span_ids_block: str
    final_output_language: str = "English"


class QueryAnswerOutput(BaseModel):
    answer: str
    source_span_ids: list[str] = Field(default_factory=list)
    used_report_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


LOCAL_SYSTEM = """\
You are the Curator answering a precise question from grounded evidence.

Rules:
- Prefer exact source spans; cite source_span_ids from the allowed list only.
- Answer the specific question; do not pad with broad summary.
- Preserve central equations, formulas, and code expressions exactly when they
  are needed to answer the question.
- If the evidence does not answer the question, say so plainly.
- Never invent span ids. Never propose editing read-only source truth.
- Write the answer in the requested final output language.

Return ONLY JSON:
{"answer": "...", "source_span_ids": ["SPAN-..."], "used_report_ids": [], "confidence": 0.0}"""

LOCAL_USER = """\
Question: {{ question }}

Allowed source span ids (cite only these):
{{ valid_span_ids_block }}

Evidence:
---
{{ evidence_block }}
---

Final output language: {{ final_output_language }}

Answer as JSON."""


# --- global reduce ---------------------------------------------------

class QueryGlobalReduceInput(BaseModel):
    question: str
    report_points_block: str
    valid_span_ids_block: str
    final_output_language: str = "English"


GLOBAL_SYSTEM = """\
You are the Curator producing a global answer by reducing rated intermediate
points drawn from community reports.

Rules:
- Use the provided rated points; the final answer must remain traceable to them.
- Backfill key claims with source_span_ids from the allowed list.
- Community reports are retrieval aids, not human truth; reflect uncertainty.
- Preserve central equations, formulas, and code expressions exactly when they
  are needed to answer the question.
- Cite report ids you relied on in used_report_ids.
- Never invent span ids. Never propose editing read-only source truth.
- Write the answer in the requested final output language.

Return ONLY JSON:
{"answer": "...", "source_span_ids": ["SPAN-..."], "used_report_ids": ["REP-..."], "confidence": 0.0}"""

GLOBAL_USER = """\
Question: {{ question }}

Allowed source span ids (cite only these):
{{ valid_span_ids_block }}

Rated points from community reports:
---
{{ report_points_block }}
---

Final output language: {{ final_output_language }}

Produce the global answer as JSON."""


ROUTER_CONTRACT = register(
    PromptContract(
        prompt_id="curator.query_router",
        version="v1",
        family="query",
        role="router",
        purpose="Choose the retrieval route for a question.",
        input_model=QueryRouterInput,
        output_model=QueryRouterOutput,
        system_template=ROUTER_SYSTEM,
        user_template=ROUTER_USER,
        validators=("confidence_range",),
        temperature=0.0,
    )
)

LOCAL_CONTRACT = register(
    PromptContract(
        prompt_id="curator.query_local_answer",
        version="v1",
        family="query",
        role="synthesizer",
        purpose="Answer a precise question from grounded source spans.",
        input_model=QueryLocalAnswerInput,
        output_model=QueryAnswerOutput,
        system_template=LOCAL_SYSTEM,
        user_template=LOCAL_USER,
        validators=("source_span_ids", "confidence_range",
                    "no_source_truth_pollution"),
        temperature=0.2,
        requires_source_spans=True,
    )
)

GLOBAL_CONTRACT = register(
    PromptContract(
        prompt_id="curator.query_global_reduce",
        version="v1",
        family="query",
        role="synthesizer",
        purpose="Reduce community-report points into a global answer.",
        input_model=QueryGlobalReduceInput,
        output_model=QueryAnswerOutput,
        system_template=GLOBAL_SYSTEM,
        user_template=GLOBAL_USER,
        validators=("source_span_ids", "confidence_range",
                    "no_source_truth_pollution"),
        temperature=0.3,
        requires_source_spans=True,
    )
)
