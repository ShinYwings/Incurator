# Draft: Sidechat Analyse/Review/Update Loop Regression

## Problem Definition
The user reported a regression in the sidechat agent's execution loop. The expected behavior is a deliberate, multi-step process: `analysed` -> `reviewed` -> `updated` -> `reviewed`. However, the provided chat logs indicate that the agent is bypassing this strict sequence, immediately transitioning from "Optimized tool selection" to file edits without formal intermediate review or analysis phases. 

## "Why" This is Needed
The strict `analysed, reviewed, updated, reviewed` loop is critical to prevent "vibe-coding" and ensure that the agent thoroughly understands the logical gaps before modifying the codebase. Skipping these steps leads to incomplete or hallucinated changes, as seen in the user's example where the agent failed to properly explain how camera pose is found because it didn't formally review its own plan first.

## Constraints & Architectural Vectors
1. **State Machine Enforcement**: The sidechat agent must be constrained to follow the explicit review loop. It cannot be allowed to optimize away the analysis and review phases.
2. **System Prompt / Tooling**: We must audit the system prompt or tool chain that currently allows the agent to bypass the review step. The agent must be forced to output its analysis and review findings as distinct, observable steps before invoking any file modification tools.

## Success Criteria
- The sidechat agent reliably executes the full `analysed, reviewed, updated, reviewed` sequence for all file modifications.
- The agent explicitly halts or outputs its review state before mutating files.
