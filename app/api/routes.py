"""
PrepLink API Routes
=====================
Per ADR-004: no Celery, no job queue, no WebSocket. Each recipe request is
processed synchronously in-process (extract -> adapt -> build cart) and the
finished result is returned in the same HTTP response, matching the PRD's
<15s P95 cart-build budget. Recipes are then cached in Redis by id so
share/reload flows can fetch them again afterwards (see recipe_store.py).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import recipe_store
from app.schemas.recipe import AgeGroup, DietaryFlag, UnitSystem

recipe_router = APIRouter(prefix="/api/recipe", tags=["Recipe"])
cart_router = APIRouter(prefix="/api/cart", tags=["Cart"])


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
    from app.services import adaptor, cart_builder
    from app.services import extractor as ex

    recipe_id = str(uuid.uuid4())

    extracted = await ex.extract_recipe(req.url)

    if req.servings_override and req.servings_override != extracted.metadata.servings:
        scale = req.servings_override / extracted.metadata.servings
        extracted = extracted.model_copy(update={
            "ingredients": [
                i.model_copy(update={"quantity": round(i.quantity * scale, 3)})
                for i in extracted.ingredients
            ],
            "metadata": extracted.metadata.model_copy(update={"servings": req.servings_override}),
        })

    adapted = await adaptor.run_adaptation_pass(
        recipe=extracted,
        age_group=req.age_group,
        dietary_filters=req.dietary_filters,
        unit_system=req.unit_system,
        include_medium_pantry=req.include_medium_pantry,
    )
    cart = await cart_builder.build_instacart_cart(adapted_recipe=adapted, user_id=req.user_id, recipe_id=recipe_id)

    recipe_json = adapted.model_dump(mode="json")
    cart_json = cart.model_dump(mode="json")
    recipe_store.save_recipe(recipe_id, recipe_json, cart_json)

    return {"job_id": recipe_id, "status": "complete", "recipe": recipe_json, "cart": cart_json}


@recipe_router.get("/process/{recipe_id}")
async def get_recipe(recipe_id: str):
    stored = recipe_store.get_recipe(recipe_id)
    if not stored:
        raise HTTPException(404, "recipe not found")
    return {"job_id": recipe_id, "status": "complete", **stored}


# ─── Cart ───────────────────────────────────────────────────────────────────

@cart_router.get("/{recipe_id}")
async def get_cart(recipe_id: str):
    stored = recipe_store.get_recipe(recipe_id)
    if not stored:
        raise HTTPException(404, "cart not found")
    return stored["cart"]
