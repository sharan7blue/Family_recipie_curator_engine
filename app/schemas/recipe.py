"""PrepLink Recipe Schemas (stub) — minimal shapes to satisfy the pipeline."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class AgeGroup(str, Enum):
    INFANT = "infant"
    TODDLER = "toddler"
    CHILD = "child"
    TEEN = "teen"
    ADULT = "adult"


class DietaryFlag(str, Enum):
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    GLUTEN_FREE = "gluten_free"
    DAIRY_FREE = "dairy_free"
    NUT_FREE = "nut_free"


class UnitSystem(str, Enum):
    IMPERIAL = "imperial"
    METRIC = "metric"


class Ingredient(BaseModel):
    name: str
    quantity: float
    unit: str


class RecipeMetadata(BaseModel):
    title: str
    servings: int
    source_url: str = ""


class ExtractedRecipe(BaseModel):
    metadata: RecipeMetadata
    ingredients: list[Ingredient]
    steps: list[str] = []
    confidence: float = 1.0
    extraction_method: str = "stub"


class AdaptedRecipe(BaseModel):
    metadata: RecipeMetadata
    ingredients: list[Ingredient]
    steps: list[str] = []
    age_group: AgeGroup = AgeGroup.ADULT
    dietary_filters: list[DietaryFlag] = []
    warnings: list[str] = []
    confidence: float = 1.0
    extraction_method: str = "stub"


class LLMIngredientExtractionOutput(BaseModel):
    title: str
    servings: int = 4
    ingredients: list[Ingredient] = []
    steps: list[str] = []


class LLMAdaptationOutput(BaseModel):
    adapted_ingredients: list[Ingredient] = []
    warnings: list[str] = []
