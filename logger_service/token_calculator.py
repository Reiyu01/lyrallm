"""
Token calculator module

Implements token usage calculation with the following priority (recommended):
 1. Use provider/SDK reported usage if present (most accurate, matches billing).
 2. Otherwise use tiktoken to estimate token usage per model.
 3. Fallback to simple word-count estimate.

This module follows the guidance similar to LiteLLM's token usage approach:
prefer provider usage and fall back to tokenizer-based estimation. It also
exposes a small function that can be run as a microservice via FastAPI
(`token_service.py`) if you prefer a separate service for token calculation.

The public function is `compute_token_usage(response_obj, messages, model_name, model_config)`
which returns a dict with keys: prompt_tokens, completion_tokens, total_tokens,
cost_usd, tokens_source, provider_usage (if any), tiktoken_estimate (if any).
"""

from typing import Any, Dict, List, Optional, Callable
import logging

logger = logging.getLogger(__name__)


def _extract_provider_usage(response_obj: Any) -> Optional[Dict[str, int]]:
    """Try to extract provider usage from SDK response object or dict."""
    try:
        if response_obj is None:
            return None
        if isinstance(response_obj, dict):
            usage = response_obj.get("usage") or response_obj.get("meta", {}).get("usage")
            if usage:
                return {
                    "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                    "completion_tokens": int(usage.get("completion_tokens", 0)),
                    "total_tokens": int(usage.get("total_tokens", 0) or (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)))
                }
        else:
            usage = getattr(response_obj, "usage", None)
            if usage:
                # support object-like usage
                return {
                    "prompt_tokens": int(getattr(usage, "prompt_tokens", 0)),
                    "completion_tokens": int(getattr(usage, "completion_tokens", 0)),
                    "total_tokens": int(getattr(usage, "total_tokens", 0) or (getattr(usage, "prompt_tokens", 0) + getattr(usage, "completion_tokens", 0)))
                }
    except Exception as e:
        logger.debug(f"extract provider usage failed: {e}")
    return None


def _tiktoken_estimate(messages: List[Any], response_text: str, model_name: str) -> Dict[str, int]:
    """Estimate tokens using tiktoken when available.

    messages: list of objects with `.content` attribute or dict with 'content'.
    returns dict with prompt_tokens, completion_tokens, total_tokens
    """
    # support passing a custom tokenizer or count function via outer helpers
    logger.debug("_tiktoken_estimate: selecting tokenizer for model: %s", model_name)
    try:
        count_fn = _get_count_function(model_name, None)
    except Exception:
        logger.debug("tiktoken not available or selection failed, using word-count fallback")
        count_fn = lambda s: len(s.split())

    try:
        prompt_tokens = 0
        for m in messages:
            content = m.content if hasattr(m, 'content') else (m.get('content') if isinstance(m, dict) else str(m))
            prompt_tokens += count_fn(content)

        completion_tokens = count_fn(response_text)
        return {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens}
    except Exception as e:
        logger.debug(f"tiktoken estimation failed: {e}")
        # fallback word-count
        prompt = sum(len((m.content if hasattr(m, 'content') else m.get('content', '')).split()) for m in messages)
        completion = len(response_text.split())
        return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}


def _get_count_function(model: Optional[str], custom_tokenizer: Optional[Callable[[str], int]] = None) -> Callable[[str], int]:
    """Return a token counting function.

    Preference order:
      1. If custom_tokenizer is a callable, return it.
      2. If tiktoken is available, pick an encoding for the model.
      3. Fallback to simple word-count.
    """
    if custom_tokenizer and callable(custom_tokenizer):
        return custom_tokenizer

    try:
        import tiktoken
        model_to_use = model or ""
        # special-case very large encodings (litellm uses o200k_base for gpt-4o)
        try:
            if "gpt-4o" in model_to_use:
                enc = tiktoken.get_encoding("o200k_base")
            else:
                enc = tiktoken.encoding_for_model(model_to_use)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")

        def count_tokens(text: str) -> int:
            return len(enc.encode(text))

        return count_tokens
    except Exception:
        # fallback word-count
        return lambda s: len(s.split())


def _compute_cost(prompt_tokens: int, completion_tokens: int, model_config: Optional[Dict[str, Any]]) -> float:
    # model_config may provide input_cost_per_1k and output_cost_per_1k
    input_cost = 0.0
    output_cost = 0.0
    if model_config:
        input_cost = float(model_config.get('input_cost_per_1k', model_config.get('input_cost', 0.0)))
        output_cost = float(model_config.get('output_cost_per_1k', model_config.get('output_cost', 0.0)))
    cost = (prompt_tokens / 1000.0) * input_cost + (completion_tokens / 1000.0) * output_cost
    # round to 8 decimal places for storage
    return round(cost, 8)


def compute_token_usage(response_obj: Any, messages: List[Any], model_name: str, model_config: Optional[Dict[str, Any]] = None, response_text: Optional[str] = None, custom_tokenizer: Optional[Callable[[str], int]] = None) -> Dict[str, Any]:
    """Compute token usage and cost.

    Returns a dictionary with keys:
      - prompt_tokens, completion_tokens, total_tokens, cost_usd
      - tokens_source: 'provider'|'tiktoken'|'fallback'
      - provider_usage: raw provider usage dict or None
      - tiktoken_estimate: dict or None
    """
    provider = _extract_provider_usage(response_obj)
    tk = None
    chosen = None

    # if response_text not provided, try to derive from response_obj
    if response_text is None:
        try:
            if isinstance(response_obj, dict):
                response_text = str(response_obj.get('text') or response_obj.get('content') or '')
            else:
                # try common attributes
                response_text = str(getattr(response_obj, 'content', '') or getattr(response_obj, 'text', ''))
        except Exception:
            response_text = ''

    if provider:
        prompt_tokens = int(provider.get('prompt_tokens', 0))
        completion_tokens = int(provider.get('completion_tokens', 0))
        total_tokens = int(provider.get('total_tokens', prompt_tokens + completion_tokens))
        chosen = 'provider'
    else:
        # if a custom callable is provided, use it to count tokens
        if custom_tokenizer and callable(custom_tokenizer):
            try:
                prompt_tokens = 0
                for m in messages:
                    content = m.content if hasattr(m, 'content') else (m.get('content') if isinstance(m, dict) else str(m))
                    prompt_tokens += custom_tokenizer(content)
                completion_tokens = custom_tokenizer(response_text)
                tk = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens}
            except Exception as e:
                logger.debug(f"custom_tokenizer failed: {e}")
                tk = _tiktoken_estimate(messages, response_text, model_name)
        else:
            tk = _tiktoken_estimate(messages, response_text, model_name)
        prompt_tokens = int(tk.get('prompt_tokens', 0))
        completion_tokens = int(tk.get('completion_tokens', 0))
        total_tokens = int(tk.get('total_tokens', prompt_tokens + completion_tokens))
        chosen = 'tiktoken' if tk else 'fallback'

    cost_usd = _compute_cost(prompt_tokens, completion_tokens, model_config)

    result = {
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'total_tokens': total_tokens,
        'cost_usd': cost_usd,
        'tokens_source': chosen,
        'provider_usage': provider,
        'tiktoken_estimate': tk
    }
    return result


def compute_token_usage_from_chunks(response_obj: Any, messages: List[Any], model_name: str, model_config: Optional[Dict[str, Any]] = None, chunks: Optional[List[str]] = None) -> Dict[str, Any]:
    """Compute token usage when a response is streamed in multiple text chunks.

    Strategy:
      - The safest approach is to re-join all chunks into the final `response_text`
        and run `compute_token_usage` once. This guarantees identical tokenization
        to treating the response as a single string.
      - We also provide helpers to estimate per-chunk token counts (using
        the tokenizer when available) and to aggregate them; note that summing
        per-chunk token counts may produce small differences vs tokenizing the
        concatenated text because of tokenizer boundary behavior (rare, but
        possible with some BPE/tokenizer implementations).

    Returns the same dict shape as `compute_token_usage`.
    """
    if not chunks:
        # fallback: behave like compute_token_usage with provided response_text
        return compute_token_usage(response_obj, messages, model_name, model_config, None)

    response_text = ''.join(chunks)
    return compute_token_usage(response_obj, messages, model_name, model_config, response_text)


def chunk_token_counts(chunks: List[str], model_name: str) -> List[int]:
    """Return token counts per chunk using tiktoken if available, otherwise word-count."""
    counts = []
    try:
        import tiktoken
        try:
            enc = tiktoken.encoding_for_model(model_name)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
        for c in chunks:
            counts.append(len(enc.encode(c)))
        return counts
    except Exception:
        # fallback simple word-count estimation per chunk
        for c in chunks:
            counts.append(len(c.split()))
        return counts


def aggregate_chunk_counts(counts: List[int]) -> Dict[str, int]:
    """Aggregate a list of per-chunk token counts into a summary dict.

    Note: This is a best-effort aggregation. For exact counts prefer
    tokenizing the concatenated text once (compute_token_usage_from_chunks).
    """
    total = sum(counts)
    return {"per_chunk": counts, "total_tokens": total}
