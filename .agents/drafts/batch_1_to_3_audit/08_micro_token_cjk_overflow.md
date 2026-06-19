# Micro-Level Code Review: Token Estimator CJK Overflow & Overpacking

## Target
`backend/src/curator/context_service.py` -> `_estimate_tokens()`, `_apply_budget()`

## Vulnerability Description
The heuristic used for token estimation is mathematically unsafe for Non-English (CJK: Chinese, Japanese, Korean) text, leading to massive context window overflows at the LLM provider boundary.

### Code Trace & Line-by-Line Analysis
In `_estimate_tokens`:
```python
def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)
```

1. **The Fallacy of Length-Based Tokenization**: The algorithm assumes an average of 4 characters per token (typical for English text with `cl100k_base` or `o200k_base`).
2. **CJK Token Explosion**: In Korean text (which is a primary target given `USER_GUIDE_KR.md`), a single Unicode character (e.g., '수') often maps to 1, 2, or even 3 tokens depending on the BPE vocabulary. 
3. **The Budget Collapse**: If the agent sets `limit_tokens = 4000`, the `available` budget is calculated as 3000 tokens. The packing loop (`if used + cost <= available`) will continue until `used` hits 3000. 
   - A 12,000-character Korean document will be estimated as `12000 // 4 = 3000` tokens and packed successfully.
   - When this payload is sent to the LLM (e.g., Claude 3.5 Sonnet or GPT-4o), those 12,000 Korean characters will tokenize into ~15,000+ tokens.
   - If the agent's actual remaining window was strictly 4,000 tokens, the provider API will throw a `400 Bad Request: Context Length Exceeded` or silently truncate the user prompt, breaking the entire pipeline.

### Recommended Architectural Fix
The fallback `_estimate_tokens` must not use a hardcoded `/ 4` division across all languages.
1. **Model-Aware Tokenizer**: The system MUST inject the actual model tokenizer (e.g., `tiktoken.encoding_for_model`) or use a byte-length multiplier fallback (`len(text.encode('utf-8')) / 3`) which safely overestimates CJK text costs rather than drastically underestimating them.
2. **Estimation Mode Flag**: The `estimation_mode: "conservative"` flag in the payload is a lie; it is currently an "aggressive" underestimate for CJK. It must be renamed or fixed.
