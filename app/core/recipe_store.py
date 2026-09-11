"""
PrepLink Recipe Store
========================
Per ADR-004, there is no job queue anymore — a recipe is fully processed
within a single request. This module exists only so a processed recipe can
be looked up again by id afterwards (share links, reloading /recipe.html).

Not a job/task store: there is no "processing" state to track. A recipe
either exists (complete) or doesn't (never processed / expired).
"""

from __future__ import annotations

import json

import redis

from app.core.config import settings
from app.core.logger import logger

RECIPE_TTL = settings.RECIPE_TTL_SECONDS


def _redis() -> redis.Redis:
    return redis.from_url(
        settings.REDIS_CACHE_URL,
        decode_responses=True,
        socket_timeout=3,
        socket_connect_timeout=3,
    )


def save_recipe(recipe_id: str, recipe: dict, cart: dict) -> None:
    try:
        r = _redis()
        r.set(f"recipe:{recipe_id}", json.dumps({"recipe": recipe, "cart": cart}), ex=RECIPE_TTL)
    except Exception as e:
        logger.warning(f"[RECIPE_STORE] Could not persist recipe {recipe_id}: {e}")


def get_recipe(recipe_id: str) -> dict | None:
    try:
        r = _redis()
        raw = r.get(f"recipe:{recipe_id}")
        if not raw:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"[RECIPE_STORE] Could not fetch recipe {recipe_id}: {e}")
        return None
