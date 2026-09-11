"""Cart building + webhook notification (stub)."""

from __future__ import annotations

from celery.utils.log import get_task_logger

from app.workers.celery_app import celery_app
from app.workers import job_store

logger = get_task_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.cart.build_carts_for_chunk",
    queue="batch",
)
def build_carts_for_chunk(adaptation_results: list[dict], bulk_job_id: str) -> dict:
    succeeded = sum(1 for r in adaptation_results if not r.get("failed"))
    failed = len(adaptation_results) - succeeded
    job_store.increment_completed(bulk_job_id, succeeded)
    job_store.increment_failed(bulk_job_id, failed)
    logger.info(f"[CART] Chunk done for {bulk_job_id}: succeeded={succeeded} failed={failed}")
    return {"succeeded": succeeded, "failed": failed}


@celery_app.task(
    name="app.workers.tasks.cart.notify_webhook",
    queue="batch",
)
def notify_webhook(bulk_job_id: str, webhook_url: str, status: str) -> None:
    logger.info(f"[WEBHOOK] Would POST to {webhook_url}: job={bulk_job_id} status={status}")
