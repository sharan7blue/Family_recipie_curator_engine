"""
PrepLink Recipe Cache
========================
Thin async wrapper around Redis used for the recipe result cache and the
per-IP rate limiter. Falls back to an in-memory dict when Redis is
unreachable, so the API still boots for local preview without Redis running.
"""

from __future__ import annotations

import time
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logger import logger


class RecipeCache:
    def __init__(self, url: str):
        self._url = url
        self._client: Optional[aioredis.Redis] = None
        self._memory: dict[str, tuple[str, float]] = {}  # key -> (value, expires_at)
        self._redis_ok = False

    def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._url, decode_responses=True, socket_timeout=2)
        return self._client

    async def ping(self) -> bool:
        try:
            await self._get_client().ping()
            self._redis_ok = True
        except Exception:
            self._redis_ok = False
        return self._redis_ok

    async def incr(self, key: str) -> int:
        if self._redis_ok:
            try:
                return await self._get_client().incr(key)
            except Exception:
                self._redis_ok = False
        val, exp = self._memory.get(key, ("0", 0))
        if exp and exp < time.time():
            val = "0"
        new_val = int(val) + 1
        self._memory[key] = (str(new_val), self._memory.get(key, ("0", 0))[1])
        return new_val

    async def expire(self, key: str, seconds: int) -> None:
        if self._redis_ok:
            try:
                await self._get_client().expire(key, seconds)
                return
            except Exception:
                self._redis_ok = False
        val, _ = self._memory.get(key, ("0", 0))
        self._memory[key] = (val, time.time() + seconds)

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass


recipe_cache = RecipeCache(settings.REDIS_CACHE_URL)
