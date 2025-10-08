from typing import Dict, Any


class BaseAdapter:
    """Abstract storage adapter interface."""

    async def connect(self):
        raise NotImplementedError()

    async def close(self):
        raise NotImplementedError()

    async def write_token_usage(self, event: Dict[str, Any]):
        """Write a token usage event into the storage backend."""
        raise NotImplementedError()

    async def query_token_usage(self, limit: int = 10):
        raise NotImplementedError()
