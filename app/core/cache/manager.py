import json
from typing import Any, Optional, Union

from app.core.cache.redis import redis_client as default_redis_client

FilterValue = Union[str, int, float, bool]
PartType = Union[str, dict[str, FilterValue], None]


class CacheManager:
    def __init__(self, redis_client=default_redis_client):
        self.redis_client = redis_client

    @staticmethod
    def build_key(prefix: str, *parts: PartType) -> str:
        normalized_parts = []

        for part in parts:
            if part is None:
                continue

            if isinstance(part, dict):
                clean = {k: v for k, v in part.items() if v is not None}

                if not clean:
                    continue

                sorted_items = sorted(clean.items())
                query_string = "&".join(f"{k}={v}" for k, v in sorted_items)

                normalized_parts.append(query_string)
                continue

            if isinstance(part, str):
                normalized_part = part.strip().lower()
                if normalized_part:
                    normalized_parts.append(normalized_part)

        if not normalized_parts:
            return prefix

        return f"{prefix}:{':'.join(normalized_parts)}"

    async def get_cache(self, key: str) -> Optional[dict]:
        value = await self.redis_client.get(key)
        if value:
            return json.loads(value)
        return None

    async def set_cache(self, key: str, value: Any, ttl: int = 300):
        await self.redis_client.setex(key, ttl, json.dumps(value))

    async def delete_cache(self, key: str):
        await self.redis_client.delete(key)

    async def delete_pattern(self, pattern: str):
        async for key in self.redis_client.scan_iter(match=pattern):
            await self.redis_client.delete(key)
