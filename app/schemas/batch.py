"""PrepLink Batch Schemas (stub)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class BatchJobStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class BatchProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class BatchResultItem(BaseModel):
    custom_id: str
    status: str
    recipe_json: str | None = None
    error: str | None = None


class BulkJobResults(BaseModel):
    bulk_job_id: str
    status: str
    total: int
    succeeded: int
    failed: int
    items: list[BatchResultItem]
    total_cost_usd: float


# Rough per-1M-token prices, gpt-4o-2024-08-06, USD. Batch API is ~50% off.
_INPUT_PER_M = 2.50
_OUTPUT_PER_M = 10.00


def estimate_cost(input_tokens: int, output_tokens: int, model: str, is_batch: bool = False) -> float:
    discount = 0.5 if is_batch else 1.0
    return (input_tokens / 1_000_000 * _INPUT_PER_M + output_tokens / 1_000_000 * _OUTPUT_PER_M) * discount
