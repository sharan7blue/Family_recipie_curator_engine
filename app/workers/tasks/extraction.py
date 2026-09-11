"""Transcript fetch (stub) — pretends to pull a transcript per item."""

from __future__ import annotations

from celery.utils.log import get_task_logger

from app.workers.celery_app import celery_app
from app.services.extractor import detect_platform

logger = get_task_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.extraction.fetch_transcripts_for_chunk",
    queue="batch",
)
def fetch_transcripts_for_chunk(chunk: list[dict], bulk_job_id: str) -> list[dict]:
    results = []
    for item in chunk:
        url = item["url"]
        results.append({
            "item": item,
            "platform": detect_platform(url),
            "transcript": f"stub transcript for {url}",
            "failed": False,
        })
    logger.info(f"[EXTRACTION] Fetched {len(results)} stub transcripts for job {bulk_job_id}")
    return results
