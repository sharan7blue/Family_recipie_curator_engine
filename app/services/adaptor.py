"""Age/dietary adaptation (stub) — passes ingredients through unchanged."""

from __future__ import annotations

from enum import Enum

from app.schemas.recipe import AdaptedRecipe, AgeGroup, DietaryFlag, ExtractedRecipe, LLMAdaptationOutput, UnitSystem


class AgeBand(str, Enum):
    UNDER_1 = "under_1"
    ONE_TO_THREE = "1_to_3"
    FOUR_PLUS = "4_plus"


def resolve_age_band(age_group: AgeGroup) -> AgeBand:
    return {
        AgeGroup.INFANT: AgeBand.UNDER_1,
        AgeGroup.TODDLER: AgeBand.ONE_TO_THREE,
    }.get(age_group, AgeBand.FOUR_PLUS)


class PantryConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def classify_pantry(ingredient_name: str) -> tuple[PantryConfidence, float]:
    return PantryConfidence.HIGH, 1.0


class SafetyResult:
    def __init__(self, highest_severity: str = "none", ui_warning_text: str = ""):
        self.highest_severity = highest_severity
        self.ui_warning_text = ui_warning_text


def check_ingredient_safety_for_band(ingredient_name: str, age_band: str):
    if "honey" in ingredient_name.lower() and age_band == AgeBand.UNDER_1.value:
        return SafetyResult(highest_severity="forbidden", ui_warning_text="Honey is unsafe under 12 months.")
    return None


async def run_adaptation_pass(
    recipe: ExtractedRecipe,
    age_group: AgeGroup,
    dietary_filters: list[DietaryFlag],
    unit_system: UnitSystem,
    include_medium_pantry: bool,
) -> AdaptedRecipe:
    return AdaptedRecipe(
        metadata=recipe.metadata,
        ingredients=recipe.ingredients,
        steps=recipe.steps,
        age_group=age_group,
        dietary_filters=dietary_filters,
        warnings=[],
    )


async def assemble_adapted_recipe(
    recipe: ExtractedRecipe,
    llm_out: LLMAdaptationOutput,
    age_group: AgeGroup,
    dietary_filters: list[DietaryFlag],
    unit_system: UnitSystem,
    include_medium_pantry: bool,
) -> AdaptedRecipe:
    return AdaptedRecipe(
        metadata=recipe.metadata,
        ingredients=llm_out.adapted_ingredients or recipe.ingredients,
        steps=recipe.steps,
        age_group=age_group,
        dietary_filters=dietary_filters,
        warnings=llm_out.warnings,
    )
