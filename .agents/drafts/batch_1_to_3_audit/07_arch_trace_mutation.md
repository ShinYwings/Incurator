# Architectural Code Review: Destructive Trace Mutation on Synthesis Failure

## Target
`backend/src/curator/retrieval/orchestrator.py` -> `_run_answer_from_context()`

## Vulnerability Description
When the LLM answer synthesis fails validation, the orchestrator destructively mutates the provenance arrays of the root trace.

### Code Reference
```python
        if run.ok and run.parsed is not None:
            # Success path
        else:
            result.error = "answer synthesis failed validation"
            result.source_span_ids = []
            result.community_report_ids = []
            result.synthesis_node_ids = []
            result.memory_path_ids = []
```

### Deep Analysis
1. **Corruption of Retrieval Metrics:** The `source_span_ids` and other arrays on the `QueryResultV031` object represent the evidence *retrieved* and *packed* by the `ContextService`. By clearing these arrays to `[]` upon a *synthesis* failure, the orchestrator erases the historical fact that evidence was actually retrieved. 
2. **False Negatives in Evaluation:** When the QA evaluation runner inspects the `QTR-*` trace, it will see 0 `source_span_ids`. The failure will be misclassified as a "Retrieval Failure" (Recall=0) instead of an "Answer Synthesis Failure".
3. **Violates Pipeline Boundaries:** The `ContextService` is responsible for packing evidence. Synthesis is an *optional* downstream consumer. A failure in the consumer must not delete the output of the producer.

### Recommended Rewrite
If synthesis fails, the system should leave `result.source_span_ids` intact. It should only clear synthesis-specific fields (like `result.answer` or `used_report_ids`). To indicate that the answer lacks support, it should append a fatal warning or set an explicit `synthesis_status="failed"` field on the trace, preserving the pristine retrieval evidence arrays.
