"""
PrepLink Redis Job Store
=========================
Replaces the in-memory _bulk_jobs dict from the APScheduler era.
All bulk job state lives in Redis so:
  - Multiple Celery workers can read/write the same job
  - API process restart doesn't lose in-progress jobs
  - Results survive until TTL expires (7 days)

Key schema:
  bulk_job:{id}              → Redis Hash   (job metadata)
  bulk_job:{id}:items        → Redis Hash   (custom_id → JSON result per item)
  bulk_job:{id}:prov_batches → Redis List   (provider batch IDs)

All values are JSON-serialised strings.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import redis

from app.core.config import settings
from app.core.logger import logger
from app.schemas.batch import BatchJobStatus, BatchProvider, BatchResultItem, BulkJobResults, estimate_cost


# ─── Redis client (synchronous — used from Celery tasks) ─────────────────────

def _redis() -> redis.Redis:
    return redis.from_url(
        settings.REDIS_CACHE_URL,
        decode_responses=True,
        socket_timeout=5,
        socket_connect_timeout=5,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


JOB_TTL = settings.BULK_JOB_TTL_SECONDS   # 7 days


# ─── Write helpers ────────────────────────────────────────────────────────────

def create_job(
    bulk_job_id: str,
    total_items: int,
    provider: str,
    job_name: Optional[str] = None,
    notify_webhook: Optional[str] = None,
) -> None:
    r = _redis()
    key = f"bulk_job:{bulk_job_id}"
    r.hset(key, mapping={
        "bulk_job_id":      bulk_job_id,
        "status":           BatchJobStatus.QUEUED.value,
        "provider":         provider,
        "total_items":      total_items,
        "completed_items":  0,
        "failed_items":     0,
        "input_tokens":     0,
        "output_tokens":    0,
        "job_name":         job_name or f"Bulk {bulk_job_id[:8]}",
        "notify_webhook":   notify_webhook or "",
        "created_at":       _now(),
        "started_at":       "",
        "completed_at":     "",
    })
    r.expire(key, JOB_TTL)
    logger.info(f"[JOB_STORE] Created bulk_job:{bulk_job_id}")


def set_status(bulk_job_id: str, status: BatchJobStatus) -> None:
    r = _redis()
    key = f"bulk_job:{bulk_job_id}"
    r.hset(key, "status", status.value)
    if status == BatchJobStatus.IN_PROGRESS:
        r.hset(key, "started_at", _now())
    elif status in (BatchJobStatus.COMPLETED, BatchJobStatus.PARTIAL, BatchJobStatus.FAILED):
        r.hset(key, "completed_at", _now())
    r.expire(key, JOB_TTL)


def increment_completed(bulk_job_id: str, delta: int = 1) -> None:
    r = _redis()
    r.hincrby(f"bulk_job:{bulk_job_id}", "completed_items", delta)


def increment_failed(bulk_job_id: str, delta: int = 1) -> None:
    r = _redis()
    r.hincrby(f"bulk_job:{bulk_job_id}", "failed_items", delta)


def add_tokens(bulk_job_id: str, input_tokens: int, output_tokens: int) -> None:
    r = _redis()
    r.hincrby(f"bulk_job:{bulk_job_id}", "input_tokens", input_tokens)
    r.hincrby(f"bulk_job:{bulk_job_id}", "output_tokens", output_tokens)


def add_provider_batch(bulk_job_id: str, provider_batch_id: str) -> None:
    r = _redis()
    r.rpush(f"bulk_job:{bulk_job_id}:prov_batches", provider_batch_id)
    r.expire(f"bulk_job:{bulk_job_id}:prov_batches", JOB_TTL)


def set_item_result(bulk_job_id: str, result: BatchResultItem) -> None:
    r = _redis()
    key = f"bulk_job:{bulk_job_id}:items"
    r.hset(key, result.custom_id, result.model_dump_json())
    r.expire(key, JOB_TTL)


# ─── Read helpers ─────────────────────────────────────────────────────────────

def get_job(bulk_job_id: str) -> Optional[dict]:
    r = _redis()
    data = r.hgetall(f"bulk_job:{bulk_job_id}")
    if not data:
        return None
    # Cast numerics
    for field in ("total_items", "completed_items", "failed_items", "input_tokens", "output_tokens"):
        data[field] = int(data.get(field, 0))
    return data


def get_job_progress_pct(bulk_job_id: str) -> float:
    job = get_job(bulk_job_id)
    if not job:
        return 0.0
    done = job["completed_items"] + job["failed_items"]
    return round(done / max(job["total_items"], 1) * 100, 1)


def get_provider_batches(bulk_job_id: str) -> list[str]:
    r = _redis()
    return r.lrange(f"bulk_job:{bulk_job_id}:prov_batches", 0, -1)


def get_job_results(bulk_job_id: str) -> Optional[BulkJobResults]:
    job = get_job(bulk_job_id)
    if not job:
        return None

    r = _redis()
    raw_items = r.hgetall(f"bulk_job:{bulk_job_id}:items")
    items = [BatchResultItem.model_validate_json(v) for v in raw_items.values()]

    inp  = job["input_tokens"]
    out  = job["output_tokens"]
    cost = estimate_cost(inp, out, "gpt-4o-2024-08-06", is_batch=True)

    return BulkJobResults(
        bulk_job_id=bulk_job_id,
        status=job["status"],
        total=job["total_items"],
        succeeded=sum(1 for i in items if i.status == "succeeded"),
        failed=sum(1 for i in items if i.status != "succeeded"),
        items=items,
        total_cost_usd=round(cost, 6),
    )


def list_jobs(limit: int = 50) -> list[dict]:
    """Scan all bulk_job:* keys. Acceptable for ops dashboards; not hot-path."""
    r = _redis()
    keys = r.keys("bulk_job:*")
    # Exclude sub-keys
    job_keys = [k for k in keys if k.count(":") == 1]
    jobs = []
    for key in job_keys[:limit]:
        data = r.hgetall(key)
        if not data:
            continue
        for f in ("total_items", "completed_items", "failed_items"):
            data[f] = int(data.get(f, 0))
        done = data["completed_items"] + data["failed_items"]
        data["progress_pct"] = round(done / max(data["total_items"], 1) * 100, 1)
        jobs.append(data)
    return sorted(jobs, key=lambda j: j.get("created_at", ""), reverse=True)
