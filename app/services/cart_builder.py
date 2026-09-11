"""Instacart cart builder (stub)."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.recipe import AdaptedRecipe


class CartItem(BaseModel):
    name: str
    quantity: float
    unit: str


class Cart(BaseModel):
    recipe_id: str
    user_id: str
    items: list[CartItem]
    instacart_url: str = "https://instacart.com/stub-cart"


async def build_instacart_cart(adapted_recipe: AdaptedRecipe, user_id: str, recipe_id: str) -> Cart:
    return Cart(
        recipe_id=recipe_id,
        user_id=user_id,
        items=[CartItem(name=i.name, quantity=i.quantity, unit=i.unit) for i in adapted_recipe.ingredients],
    )
