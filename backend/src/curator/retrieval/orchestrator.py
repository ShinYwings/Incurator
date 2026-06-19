"""Query orchestrator (v0.3.1).

Single entry point for the curation-native query path: resolve the workspace's
CurationPolicy, choose a route, build an evidence pack (DB graph + hybrid search),
run the route's registered query prompt with tracing, and return a result with
the full QTR trace (route, evidence ids, prompt trace ids).
"""

from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path
from typing import Any

from .. import config as cfg
from .. import curate_yml, db, prompting
from . import evidence as evidence_mod
from . import router
from .models import EvidencePack, QueryRequest, QueryResultV031

__all__ = ["QueryOrchestrator"]

_DEFAULT_POLICY_PROJECT = "default"


def _default_policy() -> curate_yml.CurationPolicy:
    spec = curate_yml.CurateSpec(project=_DEFAULT_POLICY_PROJECT)
    return curate_yml.compile_curate_policy(spec)


def _resolve_policy(workspace_path: str) -> tuple[curate_yml.CurationPolicy, str]:
    if workspace_path:
        try:
            spec = curate_yml.load_curate_spec(Path(workspace_path))
        except Exception:
            spec = None
        if spec is not None:
            ws = Path(workspace_path)
            policy = curate_yml.compile_curate_policy(spec, ws)
            return policy, curate_yml.curate_spec_hash(ws)
    return _default_policy(), ""


def _question_hash(question: str, working_query: str = "") -> str:
    raw = (working_query or question).strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _evidence_json(pack: EvidencePack) -> list[dict]:
    return [
        {
            "id": item.id,
            "kind": item.kind,
            "title": item.title,
            "score": item.score,
            "source_span_ids": item.source_span_ids,
            "community_report_id": item.community_report_id,
            "synthesis_node_id": item.synthesis_node_id,
            "memory_path_id": item.memory_path_id,
        }
        for item in pack.items
    ]


def _build_retrieval_trace(pack: EvidencePack, route: str, reason: str) -> dict:
    """Build the Plan A retrieval_trace_json contract (SCHEMA §22.4 / §30.2)."""
    base = pack.retrieval_trace.copy() if pack.retrieval_trace else {}
    base.update({
        "contract_version": "1",
        "retrieval_execution_id": pack.retrieval_execution_id,
        "route": {"selected": route, "reason": reason},
        "selection": {
            "candidate_count": len(pack.items) + sum(pack.omitted_counts.values()),
            "selected_count": len(pack.items),
            "omitted_counts": pack.omitted_counts,
        },
        "warnings": pack.warnings,
    })
    return base


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
        policy, spec_hash = _resolve_policy(request.workspace_path)
        status = router.graph_status(self.paths.state_db)
        route, reason = router.choose_route(request, policy, status)

        if route != "explore":
            from ..context_service import ContextService

            context_pack = ContextService(self.paths, self.client).context_fetch(request)
            result = QueryResultV031(
                question=request.question,
                route=context_pack["route"],
                trace_id=context_pack["trace_id"],
                input_language=request.input_language,
                english_query=request.working_query,
                final_output_language=request.final_output_language,
                source_span_ids=context_pack["source_span_ids"],
                community_report_ids=context_pack["community_report_ids"],
                synthesis_node_ids=context_pack["synthesis_node_ids"],
                memory_path_ids=context_pack["memory_path_ids"],
                warnings=[context_pack["route_reason"], *context_pack["warnings"]],
            )
            self._run_answer_from_context(request, context_pack, spec_hash, result)
            self._update_context_trace_after_synthesis(
                result,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            return result

        trace_id = f"QTR-{uuid.uuid4().hex[:8]}"

        pack = evidence_mod.build_evidence(self.paths, request, route, policy=policy)
        result = QueryResultV031(
            question=request.question,
            route=route,
            trace_id=trace_id,
            input_language=request.input_language,
            english_query=request.working_query,
            final_output_language=request.final_output_language,
            source_span_ids=pack.source_span_ids,
            community_report_ids=pack.community_report_ids,
            synthesis_node_ids=pack.synthesis_node_ids,
            memory_path_ids=pack.memory_path_ids,
            warnings=[reason, *pack.warnings],
        )

        self._run_explore(request, pack, spec_hash, result)
        retrieval_trace = _build_retrieval_trace(pack, result.route, reason)
        db.insert_query_trace(
            self.paths.state_db,
            trace_id=result.trace_id,
            workspace_id=policy.workspace_id,
            question_hash=_question_hash(request.question, request.working_query),
            route=result.route,
            route_reason=reason,
            evidence=_evidence_json(pack),
            source_span_ids=result.source_span_ids,
            community_report_ids=result.community_report_ids,
            synthesis_node_ids=result.synthesis_node_ids,
            memory_path_ids=result.memory_path_ids,
            prompt_trace_ids=result.prompt_trace_ids,
            insight_candidate_ids=result.insight_candidate_ids,
            retrieval_trace=retrieval_trace,
            warnings=result.warnings,
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
            result.error = "answer synthesis failed validation"
            result.source_span_ids = []
            result.community_report_ids = []
            result.synthesis_node_ids = []
            result.memory_path_ids = []
            result.insight_candidate_ids = []
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
        for prompt_trace_id in result.prompt_trace_ids:
            order = len(actions) + 1
            synthesis_failed = result.error is not None
            actions.append({
                "action_id": f"CTXA-{uuid.uuid4().hex[:8]}",
                "trace_id": result.trace_id,
                "order": order,
                "action_type": "synthesis",
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
    def _run_explore(
        self, request: QueryRequest, pack: EvidencePack, spec_hash: str,
        result: QueryResultV031,
    ) -> None:
        contract = prompting.REGISTRY.get("curator.query_explore_expand")
        policy, _ = _resolve_policy(request.workspace_path)
        input_obj = contract.input_model(
            question=request.question,
            primer_block=pack.evidence_block(),
            valid_span_ids_block="\n".join(pack.source_span_ids),
            max_followups=policy.max_explore_followups,
        )
        run = prompting.run_prompt(
            self.paths.state_db, self.client, contract, input_obj,
            validation_context={"valid_span_ids": set(pack.source_span_ids)},
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
