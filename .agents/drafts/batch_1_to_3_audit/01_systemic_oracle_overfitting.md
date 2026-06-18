# Systemic Architectural Review (Batch 1): Oracle Baseline Overfitting

## Target Scope
**Batch 1 (Program 1)**: Truth Contract & Quality Observatory (Plan D1, D2, Plan E)

## Architectural Vulnerability Description
Batch 1 successfully established a rigid evaluation baseline (Failure Atlas) and an evaluation runner. However, the system is now structurally vulnerable to **Oracle Overfitting**.

### Deep Analysis
1. **Synthetic Bias in Oracles**: The current evaluation suites (e.g., `D2_HOLDOUT_RESULT.yml`, `F01~F13` cases) rely on specific, well-defined query-document pairs. If these test fixtures are highly synthetic or perfectly clean, they do not represent the chaotic, unstructured nature of real human notes (e.g., partial sentences, typos, implicit context).
2. **Optimization Illusion**: Batch 2 (Compiler) and Batch 3 (Serving) use the Batch 1 oracles as their mandatory release gates. If the Batch 1 oracles are flawed or overfitted, the entire system will optimize itself to pass the tests while failing in production. The system will look mathematically perfect in CI but feel broken to the user.
3. **Lack of Continuous Grounding**: The Quality Observatory currently lacks a continuous sampling mechanism for real user queries. It assumes the frozen holdouts are eternally valid. As the user's note-taking style evolves, the baseline silently decays in relevance.

### Recommended Mitigation
1. **Real-World Sampling (Telemetry/Feedback)**: Introduce a mechanism where the `ContextService` feedback loop (Batch 3, P7) actively captures failing real-world queries and automatically promotes them to the Batch 1 testbed as new adversarial fixtures.
2. **Noise Injection Testing**: The Evaluation Specification must mandate testing against intentionally degraded inputs (e.g., missing headers, broken Markdown tables, OCR errors in PDFs) to ensure the baseline measures resilience, not just perfect-path parsing.
