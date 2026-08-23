"""Query orchestrator (v0.3.1).

Single entry point for the curation-native query path: resolve the workspace's
CurationPolicy, choose a route, build an evidence pack (DB graph + hybrid search),
run the route's registered query prompt with tracing, and return a result with
the full QTR trace (route, evidence ids, prompt trace ids).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from .. import config as cfg
from .. import curate_yml, db, prompting
from ..llm import LLMError
from .models import QueryRequest, QueryResultV031

__all__ = ["QueryOrchestrator"]

def _context_evidence_block(items: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    sep = "\n\n"
    for item in items:
        chunk = (
            f"[{item.get('kind') or ''} {item.get('record_id') or item.get('item_id') or ''}] "
            f"{item.get('summary') or ''}\n{item.get('detail') or ''}"
        ).strip()
        chunks.append(chunk)
    return sep.join(chunks)


class QueryOrchestrator:
    def __init__(self, paths: cfg.WikiPaths, client: Any) -> None:
        self.paths = paths
        self.client = client

    def fetch_context(self, request: QueryRequest) -> dict:
        """Curated-context surface (no synthesis) for reasoning agents.

        Returns the workspace-KRS-biased evidence pack the agent's own reasoning
        LLM should ground on — the primary product for external/Obsidian agents.
        This is curation as a *dynamic lens over the live DAG*, not a frozen
        Exhibition.
        """
        from ..context_service import ContextService

        return ContextService(self.paths, self.client).context_fetch(request)

    def run(self, request: QueryRequest) -> QueryResultV031:
        started = time.monotonic()
        from ..context_service import ContextService

        # Every route — including `explore` — grounds on the unified pack path
        # (SYSTEM_BEHAVIOR §31.8). The synthesis phase below branches on the
        # *served* route; explore is a pack consumer, not a divergent pipeline.
        context_pack = ContextService(self.paths, self.client).context_fetch(request)
        # Reuse the policy hash context_fetch already resolved (in the snapshot)
        # instead of re-parsing curate.yml a second time.
        spec_hash = str(context_pack["snapshot"]["policy_hash"])
        result = QueryResultV031(
            question=request.question,
            route=context_pack["route"],
            trace_id=context_pack["trace_id"],
            input_language=request.input_language,
            # From the PACK, not the request: the funnel may have derived a
            # query (`context_service.context_fetch`), and it does so on a
            # `replace()`d local. Reading `request` here would report the raw
            # question while the system searched the derived one.
            english_query=context_pack.get("english_query") or request.working_query,
            final_output_language=request.final_output_language,
            source_span_ids=context_pack["source_span_ids"],
            community_report_ids=context_pack["community_report_ids"],
            synthesis_node_ids=context_pack["synthesis_node_ids"],
            memory_path_ids=context_pack["memory_path_ids"],
            warnings=[context_pack["route_reason"], *context_pack["warnings"]],
        )
        try:
            if context_pack["route"] == "explore":
                self._run_explore_from_context(request, context_pack, spec_hash, result)
            else:
                self._run_answer_from_context(request, context_pack, spec_hash, result)
        except LLMError as exc:
            result.prompt_trace_ids = [
                run["trace_id"]
                for run in db.list_prompt_runs_for_query(
                    self.paths.state_db, result.trace_id
                )
            ]
            result.error = str(exc)
        self._update_context_trace_after_synthesis(
            result,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        return result

    def _run_answer_from_context(
        self,
        request: QueryRequest,
        context_pack: dict[str, Any],
        spec_hash: str,
        result: QueryResultV031,
    ) -> None:
        prompt_id = (
            "curator.query_global_reduce" if context_pack["route"] == "global"
            else "curator.query_local_answer"
        )
        contract = prompting.REGISTRY.get(prompt_id)
        valid_spans = set(context_pack["source_span_ids"])
        evidence_block = _context_evidence_block(context_pack["items"])
        if context_pack["route"] == "global":
            input_obj = contract.input_model(
                question=request.question,
                report_points_block=evidence_block,
                valid_span_ids_block="\n".join(context_pack["source_span_ids"]),
                final_output_language=request.final_output_language,
            )
        else:
            input_obj = contract.input_model(
                question=request.question,
                evidence_block=evidence_block,
                valid_span_ids_block="\n".join(context_pack["source_span_ids"]),
                final_output_language=request.final_output_language,
            )
        run = prompting.run_prompt(
            self.paths.state_db, self.client, contract, input_obj,
            validation_context={"valid_span_ids": valid_spans},
            curate_spec_hash=spec_hash, query_trace_id=result.trace_id,
        )
        result.prompt_trace_ids.append(run.trace_id)
        if run.ok and run.parsed is not None:
            result.answer = getattr(run.parsed, "answer", "")
            result.community_report_ids = sorted(
                set(result.community_report_ids) | set(getattr(run.parsed, "used_report_ids", []))
            )
            if hasattr(run.parsed, "source_span_ids"):
                result.source_span_ids = getattr(run.parsed, "source_span_ids") or []
        else:
            # Synthesis failed, but the evidence WAS retrieved and packed by
            # ContextService. Preserve the retrieval provenance exactly as the
            # explore route does — clearing it here would overwrite the root QTR-*
            # trace during _update_context_trace_after_synthesis and misclassify a
            # synthesis failure as a retrieval failure (recall=0). The synthesis
            # failure is recorded separately via the synthesis action's
            # synthesis_status="failed" (SYSTEM_BEHAVIOR §31.8).
            result.error = "answer synthesis failed validation"
            result.warnings.extend(run.validation.errors)

    def _update_context_trace_after_synthesis(
        self,
        result: QueryResultV031,
        *,
        latency_ms: int,
    ) -> None:
        trace = db.get_query_trace(self.paths.state_db, result.trace_id)
        if trace is None:
            return
        retrieval_trace = dict(trace.get("retrieval_trace") or {})
        context = dict(retrieval_trace.get("context_service", {}))
        actions = list(context.get("actions", []))
        action_type = "explore" if result.route == "explore" else "synthesis"
        for prompt_trace_id in result.prompt_trace_ids:
            order = len(actions) + 1
            synthesis_failed = result.error is not None
            actions.append({
                "action_id": f"CTXA-{uuid.uuid4().hex[:8]}",
                "trace_id": result.trace_id,
                "order": order,
                "action_type": action_type,
                "child_id": prompt_trace_id,
                "payload": {
                    "synthesis_status": "failed" if synthesis_failed else "ok",
                    "cited_source_span_ids": [] if synthesis_failed else result.source_span_ids,
                },
            })
        context["actions"] = actions
        retrieval_trace["context_service"] = context
        db.insert_query_trace(
            self.paths.state_db,
            trace_id=result.trace_id,
            workspace_id=trace["workspace_id"],
            question_hash=trace["question_hash"],
            route=result.route,
            route_reason=trace["route_reason"],
            evidence=trace["evidence"],
            source_span_ids=result.source_span_ids,
            community_report_ids=result.community_report_ids,
            synthesis_node_ids=result.synthesis_node_ids,
            memory_path_ids=result.memory_path_ids,
            prompt_trace_ids=result.prompt_trace_ids,
            insight_candidate_ids=result.insight_candidate_ids,
            retrieval_trace=retrieval_trace,
            warnings=result.warnings,
            latency_ms=latency_ms,
        )

    # -- explore route ---------------------------------------------------------
    def _run_explore_from_context(
        self, request: QueryRequest, context_pack: dict[str, Any], spec_hash: str,
        result: QueryResultV031,
    ) -> None:
        """Explore synthesis as a consumer of the unified ContextService pack.

        Grounding evidence (entities, associative memory paths, primers) is already
        budgeted and traced by ``context_fetch``; this phase only generates the
        explore-specific follow-up questions and provisional insight candidates from
        that normalized pack (SYSTEM_BEHAVIOR §31.8). Provenance arrays on ``result``
        are left intact — a synthesis failure never erases retrieved evidence.
        """
        contract = prompting.REGISTRY.get("curator.query_explore_expand")
        policy, _ = curate_yml.resolve_curate_policy(request.workspace_path)
        valid_spans = set(context_pack["source_span_ids"])
        input_obj = contract.input_model(
            question=request.question,
            primer_block=_context_evidence_block(context_pack["items"]),
            valid_span_ids_block="\n".join(context_pack["source_span_ids"]),
            max_followups=policy.max_explore_followups,
        )
        run = prompting.run_prompt(
            self.paths.state_db, self.client, contract, input_obj,
            validation_context={"valid_span_ids": valid_spans},
            curate_spec_hash=spec_hash, query_trace_id=result.trace_id,
        )
        result.prompt_trace_ids.append(run.trace_id)
        if run.parsed is None:
            result.error = "explore expansion failed validation"
            result.warnings.extend(run.validation.errors)
            return

        followups = getattr(run.parsed, "followup_questions", [])
        candidates = getattr(run.parsed, "insight_candidates", [])
        workspace_id = policy.workspace_id
        for cand in candidates:
            ins_id = db.create_insight_candidate(
                self.paths.state_db,
                classification="derived_insight",
                statement=cand.statement,
                workspace_id=workspace_id,
                source_event_id=result.trace_id,
                evidence=[{"source_span_ids": cand.source_span_ids}],
                confidence=cand.confidence,
                prompt_run_id=run.trace_id,
            )
            result.insight_candidate_ids.append(ins_id)
        lines = ["## Follow-up questions"]
        lines += [f"- {q}" for q in followups]
        lines += ["", "## Insight candidates (provisional, need review)"]
        lines += [f"- {c.statement}" for c in candidates]
        result.answer = "\n".join(lines).strip()
