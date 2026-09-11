"""
PrepLink Pipeline Orchestration Task
======================================
The top-level task that chains all 4 phases for a bulk job using
Celery primitives: chain, group, chord.

Architecture:
  run_bulk_pipeline
    └─ For each chunk:
         chain(
           fetch_transcripts_for_chunk.s(items, bulk_job_id)
           | submit_extraction_batch.s(bulk_job_id)
           | poll_extraction_batch.s(bulk_job_id)
           | submit_adaptation_batch.s(bulk_job_id)
           | poll_adaptation_batch.s(bulk_job_id)
           | build_carts_for_chunk.s(bulk_job_id)
         )
    └─ chord(chunk_chains | finalize_bulk_job.s(bulk_job_id))

Why chord not group:
  chord fires the callback (finalize_bulk_job) only after ALL chunk chains
  succeed. This gives us a clean "all chunks done" signal without polling.
"""

from __future__ import annotations

from celery import chain, chord
from celery.utils.log import get_task_logger

from app.core.pipeline_router import chunk_for_batch
from app.schemas.batch import BatchJobStatus
from app.workers import job_store
from app.workers.celery_app import celery_app
from app.workers.tasks.batch_api import (
    poll_adaptation_batch,
    poll_extraction_batch,
    submit_adaptation_batch,
    submit_extraction_batch,
)
from app.workers.tasks.cart import build_carts_for_chunk, notify_webhook
from app.workers.tasks.extraction import fetch_transcripts_for_chunk

logger = get_task_logger(__name__)

CHUNK_SIZE = 500    # Items per Celery task chain (not the same as OpenAI batch chunk)


@celery_app.task(
    name="app.workers.tasks.pipeline.run_bulk_pipeline",
    queue="batch",
    bind=True,
    max_retries=1,
)
def run_bulk_pipeline(
    self,
    bulk_job_id: str,
    items: list[dict],          # Serialised BulkRecipeItem dicts
    provider: str = "openai",
    notify_webhook_url: str = "",
) -> str:
    """
    Entry point: fired by the API route immediately after job_store.create_job().
    Builds the full Celery chord and dispatches it.
    Returns bulk_job_id.
    """
    logger.info(
        f"[PIPELINE] Starting bulk job {bulk_job_id}: "
        f"{len(items)} items, provider={provider}"
    )
    job_store.set_status(bulk_job_id, BatchJobStatus.IN_PROGRESS)

    # Split items into manageable chunks — one chain per chunk
    chunks = chunk_for_batch(items, CHUNK_SIZE)
    logger.info(f"[PIPELINE] Split into {len(chunks)} chunks of ≤{CHUNK_SIZE}")

    chunk_chains = []
    for chunk in chunks:
        c = chain(
            fetch_transcripts_for_chunk.s(chunk, bulk_job_id),
            submit_extraction_batch.s(bulk_job_id),
            poll_extraction_batch.s(bulk_job_id),
            submit_adaptation_batch.s(bulk_job_id),
            poll_adaptation_batch.s(bulk_job_id),
            build_carts_for_chunk.s(bulk_job_id),
        )
        chunk_chains.append(c)

    # chord: all chunk chains must finish before finalize fires
    callback = finalize_bulk_job.s(bulk_job_id, notify_webhook_url)
    chord(chunk_chains)(callback)

    return bulk_job_id


@celery_app.task(
    name="app.workers.tasks.pipeline.finalize_bulk_job",
    queue="batch",
)
def finalize_bulk_job(
    chunk_results: list[dict],  # List of {succeeded, failed} from each chunk
    bulk_job_id: str,
    notify_webhook_url: str = "",
) -> dict:
    """
    Chord callback — fires after ALL chunk chains complete.
    Sets final job status and triggers webhook notification.
    """
    total_succeeded = sum(r.get("succeeded", 0) for r in (chunk_results or []))
    total_failed    = sum(r.get("failed",    0) for r in (chunk_results or []))

    job = job_store.get_job(bulk_job_id)
    if not job:
        logger.error(f"[PIPELINE] Job {bulk_job_id} not found during finalize")
        return {}

    if total_failed == 0:
        status = BatchJobStatus.COMPLETED
    elif total_succeeded == 0:
        status = BatchJobStatus.FAILED
    else:
        status = BatchJobStatus.PARTIAL

    job_store.set_status(bulk_job_id, status)

    logger.info(
        f"[PIPELINE] Job {bulk_job_id} finalized: "
        f"status={status.value} succeeded={total_succeeded} failed={total_failed}"
    )

    # Webhook — non-blocking separate task
    if notify_webhook_url:
        notify_webhook.apply_async(
            args=[bulk_job_id, notify_webhook_url, status.value],
            countdown=2,
        )

    return {
        "bulk_job_id": bulk_job_id,
        "status":      status.value,
        "succeeded":   total_succeeded,
        "failed":      total_failed,
    }


# ─── Interactive single-recipe task ──────────────────────────────────────────

@celery_app.task(
    name="app.workers.tasks.pipeline.process_interactive_recipe",
    queue="interactive",
    bind=True,
    max_retries=1,
    soft_time_limit=45,
    time_limit=60,
)
def process_interactive_recipe(
    self,
    job_id: str,
    url: str,
    age_group: str,
    dietary_filters: list[str],
    unit_system: str,
    servings_override: int | None,
    include_medium_pantry: bool,
    user_id: str,
) -> dict:
    """
    Full interactive pipeline for a single URL.
    Runs on the `interactive` queue with strict time limits.
    Pushes WebSocket events as it progresses.
    """
    import asyncio

    from app.core.websocket_manager import ws_manager
    from app.schemas.recipe import AgeGroup, DietaryFlag, UnitSystem
    from app.services import adaptor, cart_builder
    from app.services import extractor as ex

    async def _run_pipeline():
        await ws_manager.push_job_progress(job_id, user_id, "extracting", 15, "Fetching recipe…")

        extracted = await ex.extract_recipe(url)

        if servings_override and servings_override != extracted.metadata.servings:
            scale = servings_override / extracted.metadata.servings
            extracted = extracted.model_copy(update={
                "ingredients": [
                    i.model_copy(update={"quantity": round(i.quantity * scale, 3)})
                    for i in extracted.ingredients
                ],
                "metadata": extracted.metadata.model_copy(update={"servings": servings_override}),
            })

        await ws_manager.push_job_progress(job_id, user_id, "adapting", 55, "Applying safety rules…")

        adapted = await adaptor.run_adaptation_pass(
            recipe=extracted,
            age_group=AgeGroup(age_group),
            dietary_filters=[DietaryFlag(f) for f in dietary_filters],
            unit_system=UnitSystem(unit_system),
            include_medium_pantry=include_medium_pantry,
        )

        await ws_manager.push_job_progress(job_id, user_id, "cart_building", 85, "Building cart…")

        cart = await cart_builder.build_instacart_cart(
            adapted_recipe=adapted,
            user_id=user_id,
            recipe_id=job_id,
        )
        return adapted, cart

    loop = asyncio.new_event_loop()
    try:
        adapted, cart = loop.run_until_complete(_run_pipeline())
        result = {
            "status":  "complete",
            "recipe":  adapted.model_dump(),
            "cart":    cart.model_dump(),
        }
        # Push completion over WebSocket
        loop.run_until_complete(
            ws_manager.push_job_complete(
                job_id, user_id,
                recipe=adapted.model_dump(),
                cart=cart.model_dump(),
                processing_time_ms=0,
            )
        )
        return result
    except Exception as e:
        loop.run_until_complete(ws_manager.push_job_error(job_id, user_id, str(e)))
        raise
    finally:
        loop.close()
