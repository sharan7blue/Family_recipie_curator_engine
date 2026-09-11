"""
PrepLink API Routes (local-preview stub)
===========================================
Wires the FastAPI surface to the (stubbed) pipeline. Interactive processing
tries to dispatch to Celery; if no broker/worker is reachable it falls back
to running the stub pipeline inline so the preview still works standalone.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core.logger import logger
from app.core.websocket_manager import ws_manager
from app.schemas.batch import BatchProvider
from app.schemas.recipe import AgeGroup, DietaryFlag, UnitSystem
from app.workers import job_store

recipe_router = APIRouter(prefix="/api/recipe", tags=["Recipe"])
cart_router = APIRouter(prefix="/api/cart", tags=["Cart"])
batch_router = APIRouter(prefix="/api/batch", tags=["Batch"])
ws_router = APIRouter(tags=["WebSocket"])

_interactive_results: dict[str, dict] = {}
_carts: dict[str, dict] = {}


# ─── Recipe (interactive) ──────────────────────────────────────────────────

class RecipeProcessRequest(BaseModel):
    url: str
    age_group: AgeGroup = AgeGroup.ADULT
    dietary_filters: list[DietaryFlag] = []
    unit_system: UnitSystem = UnitSystem.IMPERIAL
    servings_override: int | None = None
    include_medium_pantry: bool = False
    user_id: str = "local-preview-user"


@recipe_router.post("/process")
async def process_recipe(req: RecipeProcessRequest):
    job_id = str(uuid.uuid4())

    try:
        from app.workers.tasks.pipeline import process_interactive_recipe
        process_interactive_recipe.delay(
            job_id, req.url, req.age_group.value,
            [f.value for f in req.dietary_filters], req.unit_system.value,
            req.servings_override, req.include_medium_pantry, req.user_id,
        )
        _interactive_results[job_id] = {"status": "processing", "dispatch": "celery"}
        return {"job_id": job_id, "status": "processing", "dispatch": "celery"}
    except Exception as e:
        logger.warning(f"[API] Celery dispatch unavailable ({e}); running pipeline inline for local preview")

    from app.services import adaptor, cart_builder
    from app.services import extractor as ex

    extracted = await ex.extract_recipe(req.url)
    adapted = await adaptor.run_adaptation_pass(
        recipe=extracted,
        age_group=req.age_group,
        dietary_filters=req.dietary_filters,
        unit_system=req.unit_system,
        include_medium_pantry=req.include_medium_pantry,
    )
    cart = await cart_builder.build_instacart_cart(adapted_recipe=adapted, user_id=req.user_id, recipe_id=job_id)

    result = {"status": "complete", "recipe": adapted.model_dump(), "cart": cart.model_dump()}
    _interactive_results[job_id] = result
    _carts[job_id] = cart.model_dump()
    return {"job_id": job_id, **result, "dispatch": "inline"}


@recipe_router.get("/process/{job_id}")
async def get_recipe_status(job_id: str):
    result = _interactive_results.get(job_id)
    if not result:
        raise HTTPException(404, "job not found")
    return {"job_id": job_id, **result}


# ─── Cart ───────────────────────────────────────────────────────────────────

@cart_router.get("/{recipe_id}")
async def get_cart(recipe_id: str):
    cart = _carts.get(recipe_id)
    if not cart:
        raise HTTPException(404, "cart not found")
    return cart


# ─── Batch ──────────────────────────────────────────────────────────────────

class BatchJobRequest(BaseModel):
    items: list[dict]
    provider: BatchProvider = BatchProvider.OPENAI
    job_name: str | None = None
    notify_webhook: str | None = None


@batch_router.post("/jobs")
async def create_batch_job(req: BatchJobRequest):
    bulk_job_id = str(uuid.uuid4())
    job_store.create_job(
        bulk_job_id, total_items=len(req.items), provider=req.provider.value,
        job_name=req.job_name, notify_webhook=req.notify_webhook,
    )

    try:
        from app.workers.tasks.pipeline import run_bulk_pipeline
        run_bulk_pipeline.delay(bulk_job_id, req.items, req.provider.value, req.notify_webhook or "")
        dispatch = "celery"
    except Exception as e:
        logger.warning(f"[API] Celery dispatch unavailable ({e}); job left queued for local preview")
        dispatch = "queued-only (no broker reachable)"

    return {"bulk_job_id": bulk_job_id, "status": "queued", "dispatch": dispatch}


@batch_router.get("/jobs")
async def list_batch_jobs(limit: int = 50):
    return job_store.list_jobs(limit=limit)


@batch_router.get("/jobs/{bulk_job_id}")
async def get_batch_job(bulk_job_id: str):
    job = job_store.get_job(bulk_job_id)
    if not job:
        raise HTTPException(404, "job not found")
    job["progress_pct"] = job_store.get_job_progress_pct(bulk_job_id)
    return job


@batch_router.get("/jobs/{bulk_job_id}/results")
async def get_batch_job_results(bulk_job_id: str):
    results = job_store.get_job_results(bulk_job_id)
    if not results:
        raise HTTPException(404, "job not found")
    return results.model_dump()


# ─── WebSocket ──────────────────────────────────────────────────────────────

@ws_router.websocket("/ws/jobs/{job_id}")
async def job_progress_ws(websocket: WebSocket, job_id: str):
    await ws_manager.connect(job_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(job_id, websocket)
