"""
PrepLink Batch API Tasks
=========================
Tasks that interact with the OpenAI Batch API and Anthropic Message Batches API.
All on the `batch` queue.

Polling pattern: tasks use `self.retry(countdown=N)` to re-schedule themselves
rather than blocking on a while-loop. This keeps workers free and lets Celery
reschedule across available workers.

  submit_extraction_batch   → returns batch_id
  poll_extraction_batch     → retries every 30-120s until terminal, returns results
  submit_adaptation_batch   → returns batch_id
  poll_adaptation_batch     → retries until done, returns adapted results
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger

from app.workers.celery_app import celery_app
from app.workers import job_store
from app.schemas.batch import BatchJobStatus, BatchResultItem, estimate_cost

logger = get_task_logger(__name__)

POLL_COUNTDOWN_INITIAL = 30     # seconds before first poll retry
POLL_COUNTDOWN_MAX     = 120    # cap backoff at 2 minutes


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _backoff(retries: int) -> int:
    return min(POLL_COUNTDOWN_INITIAL * (1.5 ** retries), POLL_COUNTDOWN_MAX)


# ─── Extraction Batch ─────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="app.workers.tasks.batch_api.submit_extraction_batch",
    queue="batch",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def submit_extraction_batch(
    self: Task,
    transcript_results: list[dict],  # From fetch_transcripts_for_chunk
    bulk_job_id: str,
) -> dict:
    """
    Build JSONL from transcript results and submit to OpenAI Batch API.
    Returns {batch_id, custom_id_map, valid_count}.
    """
    from app.services.batch import openai_batch as ob
    from app.services import extractor as ex

    valid  = [r for r in transcript_results if not r["failed"] and r["transcript"]]
    if not valid:
        logger.warning(f"[BATCH_API] No valid transcripts for job {bulk_job_id}")
        return {"batch_id": None, "custom_id_map": {}, "valid_count": 0}

    lines        = []
    custom_id_map = {}   # custom_id → item dict

    for r in valid:
        item     = r["item"]
        url      = item["url"]
        platform = r["platform"]
        import hashlib
        key = hashlib.md5(f"{url}|{item.get('age_group','adult')}|{','.join(sorted(item.get('dietary_filters',[])))}".encode()).hexdigest()[:16]
        custom_id_map[key] = item

        lines.append(ob.build_extraction_jsonl_line(
            custom_id=key,
            transcript_text=r["transcript"],
            source_url=url,
            platform=platform,
        ))

    logger.info(f"[BATCH_API] Submitting extraction batch: {len(lines)} items for {bulk_job_id}")
    batch_obj = _run(ob.submit_batch(lines, metadata={"bulk_job_id": bulk_job_id, "phase": "extraction"}))
    batch_id  = batch_obj["id"]

    job_store.add_provider_batch(bulk_job_id, batch_id)
    logger.info(f"[BATCH_API] Extraction batch submitted: {batch_id}")

    return {
        "batch_id":      batch_id,
        "custom_id_map": custom_id_map,
        "valid_count":   len(lines),
    }


@celery_app.task(
    bind=True,
    name="app.workers.tasks.batch_api.poll_extraction_batch",
    queue="batch",
    max_retries=200,        # 200 × 2min max = ~6.5 hours of polling
    ignore_result=False,
)
def poll_extraction_batch(
    self: Task,
    submission: dict,       # Output of submit_extraction_batch
    bulk_job_id: str,
) -> list[dict]:
    """
    Poll OpenAI for batch completion. Uses self.retry() so the worker
    is free between polls. Returns list of {item, recipe_json, failed} dicts.
    """
    from app.services.batch import openai_batch as ob
    from app.schemas.recipe import LLMIngredientExtractionOutput
    from app.services import extractor as ex

    batch_id      = submission.get("batch_id")
    custom_id_map = submission.get("custom_id_map", {})

    if not batch_id:
        return []

    status_obj = _run(ob.get_batch_status(batch_id))
    status     = status_obj.get("status", "unknown")
    counts     = status_obj.get("request_counts", {})

    logger.info(
        f"[BATCH_API] Polling {batch_id}: status={status} "
        f"completed={counts.get('completed',0)}/{counts.get('total',0)}"
    )

    if status not in ob.TERMINAL_STATUSES:
        countdown = _backoff(self.request.retries)
        raise self.retry(countdown=countdown)

    if status != "completed":
        logger.error(f"[BATCH_API] Batch {batch_id} ended with status={status}")
        return []

    # Download and parse results
    output_file_id = status_obj.get("output_file_id")
    if not output_file_id:
        return []

    parsed = []
    async def _stream():
        async for result in ob.download_results(output_file_id):
            cid     = result.get("custom_id", "")
            item    = custom_id_map.get(cid)
            if not item:
                continue

            usage = ob.get_usage_from_result(result)
            job_store.add_tokens(bulk_job_id, usage["input_tokens"], usage["output_tokens"])

            content = ob.extract_content_from_result(result)
            if not content:
                parsed.append({"item": item, "llm_json": None, "failed": True})
                continue

            try:
                llm_out = LLMIngredientExtractionOutput.model_validate_json(content)
                recipe  = _run(ex.assemble_recipe(
                    llm_out, item["url"],
                    ex.detect_platform(item["url"]),
                    "transcript", 0.85
                ))
                parsed.append({
                    "item":     item,
                    "llm_json": recipe.model_dump_json(),
                    "failed":   False,
                })
            except Exception as e:
                logger.warning(f"[BATCH_API] Parse error for {cid}: {e}")
                parsed.append({"item": item, "llm_json": None, "failed": True, "error": str(e)})

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_stream())
    loop.close()

    ok = sum(1 for p in parsed if not p["failed"])
    logger.info(f"[BATCH_API] Extraction results: {ok}/{len(parsed)} OK for job {bulk_job_id}")
    return parsed


# ─── Adaptation Batch ─────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="app.workers.tasks.batch_api.submit_adaptation_batch",
    queue="batch",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def submit_adaptation_batch(
    self: Task,
    extraction_results: list[dict],  # From poll_extraction_batch
    bulk_job_id: str,
) -> dict:
    """Build and submit the age-adaptation batch."""
    from app.services.batch import openai_batch as ob
    from app.services.adaptor import resolve_age_band, classify_pantry, check_ingredient_safety_for_band
    from app.schemas.recipe import ExtractedRecipe

    valid = [r for r in extraction_results if not r.get("failed") and r.get("llm_json")]
    if not valid:
        return {"batch_id": None, "custom_id_map": {}, "valid_count": 0}

    lines         = []
    custom_id_map = {}

    for r in valid:
        item      = r["item"]
        recipe    = ExtractedRecipe.model_validate_json(r["llm_json"])
        age_group = item.get("age_group", "adult")
        filters   = item.get("dietary_filters", [])
        age_band  = resolve_age_band(__import__('app.schemas.recipe', fromlist=['AgeGroup']).AgeGroup(age_group)).value

        import hashlib
        key = hashlib.md5(f"{item['url']}|{age_group}|{','.join(sorted(filters))}".encode()).hexdigest()[:16]
        custom_id_map[key] = {"item": item, "recipe_json": r["llm_json"]}

        ing_lines = []
        for ing in recipe.ingredients:
            pantry_conf, _ = classify_pantry(ing.name)
            safety         = check_ingredient_safety_for_band(ing.name, age_band)
            line = f"- {ing.quantity} {ing.unit} {ing.name} | pantry={pantry_conf.value}"
            if safety and safety.highest_severity in ("forbidden", "modify"):
                line += f"\n  {safety.ui_warning_text or ''}"
            ing_lines.append(line)

        lines.append(ob.build_adaptation_jsonl_line(
            custom_id=key,
            ingredient_context="\n".join(ing_lines),
            age_band=age_band,
            dietary_filters=filters,
            recipe_title=recipe.metadata.title,
            servings=recipe.metadata.servings,
        ))

    logger.info(f"[BATCH_API] Submitting adaptation batch: {len(lines)} items for {bulk_job_id}")
    batch_obj = _run(ob.submit_batch(lines, metadata={"bulk_job_id": bulk_job_id, "phase": "adaptation"}))
    batch_id  = batch_obj["id"]
    job_store.add_provider_batch(bulk_job_id, batch_id)

    return {
        "batch_id":      batch_id,
        "custom_id_map": custom_id_map,
        "valid_count":   len(lines),
    }


@celery_app.task(
    bind=True,
    name="app.workers.tasks.batch_api.poll_adaptation_batch",
    queue="batch",
    max_retries=200,
    ignore_result=False,
)
def poll_adaptation_batch(
    self: Task,
    submission: dict,
    bulk_job_id: str,
) -> list[dict]:
    """Poll until adaptation batch completes. Returns list of {item, adapted_json}."""
    from app.services.batch import openai_batch as ob
    from app.schemas.recipe import ExtractedRecipe, LLMAdaptationOutput, AgeGroup, DietaryFlag, UnitSystem
    from app.services.adaptor import assemble_adapted_recipe

    batch_id      = submission.get("batch_id")
    custom_id_map = submission.get("custom_id_map", {})

    if not batch_id:
        return []

    status_obj = _run(ob.get_batch_status(batch_id))
    status     = status_obj.get("status", "unknown")

    logger.info(f"[BATCH_API] Polling adaptation {batch_id}: status={status}")

    if status not in ob.TERMINAL_STATUSES:
        raise self.retry(countdown=_backoff(self.request.retries))

    if status != "completed":
        return []

    output_file_id = status_obj.get("output_file_id")
    if not output_file_id:
        return []

    results = []

    async def _stream():
        async for result in ob.download_results(output_file_id):
            cid  = result.get("custom_id", "")
            meta = custom_id_map.get(cid)
            if not meta:
                continue

            usage = ob.get_usage_from_result(result)
            job_store.add_tokens(bulk_job_id, usage["input_tokens"], usage["output_tokens"])

            content = ob.extract_content_from_result(result)
            if not content:
                results.append({"item": meta["item"], "adapted_json": None, "failed": True})
                continue

            try:
                recipe  = ExtractedRecipe.model_validate_json(meta["recipe_json"])
                llm_out = LLMAdaptationOutput.model_validate_json(content)
                item    = meta["item"]
                adapted = _run(assemble_adapted_recipe(
                    recipe, llm_out,
                    age_group=AgeGroup(item.get("age_group", "adult")),
                    dietary_filters=[DietaryFlag(f) for f in item.get("dietary_filters", [])],
                    unit_system=UnitSystem(item.get("unit_system", "imperial")),
                    include_medium_pantry=False,
                ))
                results.append({
                    "item":         item,
                    "adapted_json": adapted.model_dump_json(),
                    "failed":       False,
                })
            except Exception as e:
                logger.warning(f"[BATCH_API] Adaptation parse error for {cid}: {e}")
                results.append({"item": meta["item"], "adapted_json": None, "failed": True, "error": str(e)})

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_stream())
    loop.close()

    ok = sum(1 for r in results if not r.get("failed"))
    logger.info(f"[BATCH_API] Adaptation results: {ok}/{len(results)} OK for job {bulk_job_id}")
    return results
