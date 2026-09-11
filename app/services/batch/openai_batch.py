"""
OpenAI Batch API client (stub).
No real network calls — every submitted batch is immediately "completed"
with zero results, so poll_* tasks resolve on the first poll during local
preview instead of actually round-tripping to OpenAI.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

TERMINAL_STATUSES = {"completed", "failed", "expired", "cancelled"}


def build_extraction_jsonl_line(custom_id: str, transcript_text: str, source_url: str, platform: str) -> str:
    return f'{{"custom_id": "{custom_id}", "source_url": "{source_url}"}}'


def build_adaptation_jsonl_line(
    custom_id: str,
    ingredient_context: str,
    age_band: str,
    dietary_filters: list[str],
    recipe_title: str,
    servings: int,
) -> str:
    return f'{{"custom_id": "{custom_id}", "recipe_title": "{recipe_title}"}}'


async def submit_batch(lines: list[str], metadata: dict) -> dict:
    return {"id": f"batch_stub_{uuid.uuid4().hex[:12]}"}


async def get_batch_status(batch_id: str) -> dict:
    return {
        "status": "completed",
        "request_counts": {"completed": 0, "total": 0},
        "output_file_id": None,
    }


async def download_results(output_file_id: str) -> AsyncIterator[dict]:
    return
    yield  # pragma: no cover - makes this an async generator


def extract_content_from_result(result: dict) -> str | None:
    return None


def get_usage_from_result(result: dict) -> dict:
    return {"input_tokens": 0, "output_tokens": 0}
