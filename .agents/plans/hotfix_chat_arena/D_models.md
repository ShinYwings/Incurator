# Model catalogue proposal: refresh verified CLI offerings
Date: 2026-09-10 | Agent Persona: Runtime maintainer

## 1. Core Logic & Implementation
`backend/src/curator/data/models.json` is imported by plugin at build time and loaded by backend. Its first entry determines defaults; constants must match. Keep this shared mechanism, custom models and existing valid explicit choices.
Evidence: `agy models` (live 2026-09-10) lists Gemini 3.8, 3.7, 3.6 Flash; 3.1 Pro; Claude Sonnet/Opus 4.6 thinking; GPT-OSS. 3.5 Flash absent. Official https://antigravity.google/docs/models/ agrees. Add 3.8 at front, remove 3.5.
Codex local `~/.codex/models_cache.json` fetched 2026-09-10 lists GPT-6 Astra before 5.6 Sol/Terra/Luna and 5.5, all context 272000 for CLI; Astra low/medium/high/xhigh/max/ultra, default low. Exclude hidden reserve/review models. Official https://developers.openai.com/api/docs/models/gpt-6-astra confirms model, but API context is different, so preserve CLI-reported context.
Claude official https://platform.claude.com/docs/en/models/fable-5-1/overview confirms new claude-fable-5-1. Add to shared list; preserve current default Opus 5 as recommended for most workloads and existing choices. Do not invent unavailable Mythos access.
Update guides EN then KR, stale current spec model tables, constants and assertions. Test catalogue current/retired ids, CLI efforts and defaults. No network discovery per chat turn.

## 2. Pros & Cons
One catalogue prevents drift and adds no latency. Bundled snapshots remain subject to provider changes, so release notes record source/date. Removing retired entry must not silently remap arbitrary custom selections. Check persisted retired model handling; minimally preserve explicit choice and visibly offer supported replacements unless a narrowly justified migration is necessary.
