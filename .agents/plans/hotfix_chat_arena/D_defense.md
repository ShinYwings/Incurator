# Defense and revision on catalogue critique
Date: 2026-09-10 | Agent Persona: Runtime maintainer

## 1. Vulnerabilities & Flaws
Confirmed existing `plugin/main.ts::migrateUnavailableModelDefaults` already switches unavailable cloud models to catalogue default during load, and refresh does the same. Thus removing 3.5 does not strand current plugin users. Backend explicitly configured ids remain user choices; current default changes only apply when missing. Do not introduce a parallel compatibility shim.

## 2. Suggested Alternatives
Use existing migration path and regression-test it for retired 3.5 and still supported 3.7. Add current Gemini 3.8, GPT-6 Astra and Claude Fable 5.1; preserve Claude Opus 5 default to avoid changing ordinary workload to a slower long-running model. Use CLI context/effort metadata.
