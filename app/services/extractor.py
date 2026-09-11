"""Recipe extraction (stub) — returns fake data instead of calling an LLM."""

from __future__ import annotations

from app.schemas.recipe import ExtractedRecipe, Ingredient, LLMIngredientExtractionOutput, RecipeMetadata


def detect_platform(url: str) -> str:
    if "tiktok" in url:
        return "tiktok"
    if "instagram" in url:
        return "instagram"
    if "youtube" in url or "youtu.be" in url:
        return "youtube"
    return "unknown"


async def extract_recipe(url: str) -> ExtractedRecipe:
    """Stub: pretends to pull a transcript + run LLM extraction."""
    return ExtractedRecipe(
        metadata=RecipeMetadata(title="Stub Recipe from " + detect_platform(url), servings=4, source_url=url),
        ingredients=[
            Ingredient(name="flour", quantity=2, unit="cup"),
            Ingredient(name="egg", quantity=2, unit="whole"),
            Ingredient(name="milk", quantity=1, unit="cup"),
        ],
        steps=["Mix dry ingredients.", "Whisk in eggs and milk.", "Cook until golden."],
    )


async def assemble_recipe(
    llm_out: LLMIngredientExtractionOutput,
    url: str,
    platform: str,
    source: str,
    confidence: float,
) -> ExtractedRecipe:
    return ExtractedRecipe(
        metadata=RecipeMetadata(title=llm_out.title, servings=llm_out.servings, source_url=url),
        ingredients=llm_out.ingredients,
        steps=llm_out.steps,
    )
