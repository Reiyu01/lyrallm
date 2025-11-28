import logging
from functools import lru_cache
from fastapi import APIRouter, HTTPException
from lyrallm.adapters.factory import get_adapters

router = APIRouter()
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_usage_adapter():
    """Return the first analytics adapter that can aggregate per-user tokens."""
    adapters = get_adapters('analytics')
    for adapter in adapters:
        if hasattr(adapter, 'query_user_total_tokens'):
            return adapter
    return None


@router.get("/api/token-usage/{user_id}")
async def get_user_token_usage(user_id: str):
    """Return the aggregated token usage totals for a user."""
    user_id = (user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    adapter = _get_usage_adapter()
    if adapter is None:
        raise HTTPException(status_code=503, detail="No analytics adapter available for token usage queries")

    try:
        totals = await adapter.query_user_total_tokens(user_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to query token usage for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail=f"Failed to query token usage: {exc}")

    return {
        "user_id": totals.get("user_id", user_id),
        "prompt_tokens": totals.get("prompt_tokens", 0),
        "completion_tokens": totals.get("completion_tokens", 0),
        "total_tokens": totals.get("total_tokens", 0),
    }
