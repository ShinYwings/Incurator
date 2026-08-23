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

#: What KIND of answer the message wants. Deliberately not the route: a route is
#: the intent PLUS `policy.allowed_routes` PLUS `GraphStatus`. Emitting routes
#: here would hand the model a policy decision it cannot see.
#: Kept in step with `retrieval.models.QUERY_INTENTS` by a test.
Intent = Literal["lookup", "synthesis", "discovery"]


# --- internal search query -------------------------------------------

class SearchQueryInput(BaseModel):
    message: str


class SearchQueryOutput(BaseModel):
    """The INTERNAL search query, or an explicit decision that there is none."""

    search_query: str = ""
    is_knowledge_question: bool = True
    reason: str = ""


class SearchQueryOutputV2(SearchQueryOutput):
    """v2 adds the intent the extraction step already had to understand.

    Measured before this existed: asking "내 볼트 전체의 주제를 정리해줘" eight
    times produced eight different English queries, and the route flipped with
    the synonym — `themes` and `summary` matched `_GLOBAL_SIGNALS`, `overview`
    did not, so the SAME question reached `global` 6 times and `local` 2 times.
    Routing on surface keywords of a sampled paraphrase is a lottery; routing on
    a stated intent is not.

    Defaults to "lookup" because a model that omits the field is expressing no
    opinion, and no opinion must land on today's behaviour.
    """

    intent: Intent = "lookup"


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

#: v2 = v1's rules verbatim, plus the intent. Additive, never a rewrite: every
#: hard-won rule above (the pasted-body case, the notation-preservation rule,
#: the 20-word cap) is load-bearing and is carried across unchanged.
SEARCH_QUERY_SYSTEM_V2 = SEARCH_QUERY_SYSTEM.replace(
    '''Return ONLY JSON:
{"search_query": "...", "is_knowledge_question": true, "reason": "..."}''',
    '''Also state the INTENT — what kind of answer the message wants:
- "lookup"    — a specific fact, definition, mechanism, or named entity.
- "synthesis" — a picture drawn ACROSS several sources or the whole corpus:
                "summarise", "compare across the papers", "what are the themes",
                "여러 논문을 종합해서", "전체의 주제를 정리". A whole-corpus question
                often has NO search terms; that is correct — leave search_query
                empty and set intent to "synthesis".
- "discovery" — open-ended: what else is here, what connects to what, what is
                worth noticing.
Judge the intent of the MESSAGE. Never judge it from whichever English words you
happened to choose for search_query.

Return ONLY JSON:
{"search_query": "...", "is_knowledge_question": true, "intent": "lookup", "reason": "..."}''',
)

SEARCH_QUERY_USER = """\
Message:
{{ message }}

Return the JSON."""


#: v1 stays registered so historical `prompt_runs` rows keep resolving. The
#: registry returns the highest version for a bare `get(prompt_id)`, so nothing
#: at the call site changes.
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
#: A `.replace()` that misses returns the original unchanged — so if v1's JSON
#: line is ever edited, v2 would silently lose its intent instructions and the
#: router would go back to reading keywords off a paraphrase. Fail at import
#: instead.
assert SEARCH_QUERY_SYSTEM_V2 != SEARCH_QUERY_SYSTEM, (
    "SEARCH_QUERY_SYSTEM_V2's replace() no-opped: v1's closing JSON line changed"
)
assert "INTENT" in SEARCH_QUERY_SYSTEM_V2

SEARCH_QUERY_CONTRACT_V2 = register(
    PromptContract(
        prompt_id="curator.query_search_terms",
        version="v2",
        family="query",
        role="router",
        purpose=(
            "Derive the internal English search query AND the message's intent, "
            "or decide there is no knowledge question."
        ),
        input_model=SearchQueryInput,
        output_model=SearchQueryOutputV2,
        system_template=SEARCH_QUERY_SYSTEM_V2,
        user_template=SEARCH_QUERY_USER,
        temperature=0.0,
    )
)


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
