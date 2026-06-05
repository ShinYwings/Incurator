# Phase J: LLM Prompt Vulnerabilities & YAML Hallucinations

**Target File**: `prompts.py`

**Panel**: Frank (Backend Specialist), Alice (Chief Architect)

## The LLM YAML Trap

**Frank (Backend Specialist)**:
"I reviewed `prompts.py` and found a catastrophic vulnerability in how we ask the LLM to generate DAG nodes (Atoms, Concepts, Exhibitions). 

Look at `FRAGMENT_PAGE_TEMPLATE` (Lines 150-194) and `THEME_PAGE_TEMPLATE` (Lines 433-473). We are asking the LLM to **write raw YAML frontmatter** alongside the markdown body:

```text
Write the complete markdown page:
1. YAML frontmatter — copy this EXACTLY, character-for-character:
   ---
   id: {fragment_id}
   type: atom
   ...
```

**Verdict**: This is a severe anti-pattern in Agentic Engineering. 
1. **Syntax Fragility**: If the LLM hallucinates a single unescaped quote or misses an indentation in the YAML, `page_writer.parse_page()` will crash.
2. **Token Waste**: We are burning LLM output tokens to regurgitate deterministic data (IDs, dates, paths) that the Python backend already knows.
3. **Security/Integrity Risk**: We are trusting the LLM to set `is_verified_by_human: false` and `confidence_score`. The LLM could hallucinate `is_verified_by_human: true` and bypass the HITL (Human-In-The-Loop) guardrails entirely.

### Action Item [Backend]
- **Refactor Prompts to JSON/Structured Output**: The LLM should *only* output the content (the body, the logical links, the confidence score) in a strict JSON schema or via function calling.
- **Python-Side Assembling**: The Python engine (`page_writer.py`) must be the only system that constructs the YAML frontmatter. Never trust the LLM to write raw YAML block syntax.
