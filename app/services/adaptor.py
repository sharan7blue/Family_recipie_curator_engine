"""
Age adaptation rule engine (PRD §4.3)
========================================
Deterministic AAP-sourced safety rules for toddler/infant households —
substitute, omit, or reduce specific ingredients and surface a plain-language
reason. Per the PRD, zero adaptation rules require LLM inference; this runs
entirely on ingredient-name matching, same spirit as extractor.py's Gemini
pass but with no model call at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.schemas.recipe import (
    AdaptedRecipe,
    AgeGroup,
    DietaryFlag,
    ExtractedRecipe,
    Ingredient,
    LLMAdaptationOutput,
    UnitSystem,
)


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


class RuleAction(str, Enum):
    SUBSTITUTE = "substitute"
    OMIT = "omit"
    REDUCE = "reduce"


@dataclass(frozen=True)
class SafetyRule:
    trigger: str  # matched as a case-insensitive substring of the ingredient name
    action: RuleAction
    reason: str
    substitute: str | None = None
    keep_fraction: float | None = None  # for REDUCE: fraction of the original quantity kept


# PRD §4.3 — deterministic, AAP-sourced. Applies to toddler (1-3yr) and
# infant households; adults/children 4+ are unaffected (resolve_age_band
# maps everything else to FOUR_PLUS).
TODDLER_SAFETY_RULES: list[SafetyRule] = [
    SafetyRule("honey", RuleAction.SUBSTITUTE, "Botulism risk <2yr", substitute="maple syrup"),
    SafetyRule("whole nuts", RuleAction.SUBSTITUTE, "Choking hazard", substitute="finely ground nuts"),
    SafetyRule("popcorn", RuleAction.OMIT, "Choking hazard"),
    SafetyRule("raw carrots", RuleAction.SUBSTITUTE, "Choking hazard", substitute="steamed carrots"),
    SafetyRule("hot sauce", RuleAction.OMIT, "Capsaicin, no nutritional need"),
    SafetyRule("fish sauce", RuleAction.REDUCE, "Sodium content", keep_fraction=0.5),
    SafetyRule("salt", RuleAction.REDUCE, "Renal load", keep_fraction=0.7),
    SafetyRule("alcohol", RuleAction.OMIT, "Safety"),
]


def _matching_rule(ingredient_name: str) -> SafetyRule | None:
    name = ingredient_name.lower()
    return next((rule for rule in TODDLER_SAFETY_RULES if rule.trigger in name), None)


def apply_age_safety_rules(ingredients: list[Ingredient], age_band: AgeBand) -> tuple[list[Ingredient], list[str]]:
    """Deterministic pass over ingredients for toddler/infant households.

    Returns the adapted ingredient list (substitutions applied, omissions
    dropped, quantities reduced) plus a plain-language warning per change.
    """
    if age_band == AgeBand.FOUR_PLUS:
        return ingredients, []

    adapted: list[Ingredient] = []
    warnings: list[str] = []
    for ingredient in ingredients:
        rule = _matching_rule(ingredient.name)
        if rule is None:
            adapted.append(ingredient)
            continue

        if rule.action == RuleAction.OMIT:
            warnings.append(f"Removed {ingredient.name} — {rule.reason}.")
        elif rule.action == RuleAction.SUBSTITUTE:
            adapted.append(ingredient.model_copy(update={"name": rule.substitute}))
            warnings.append(f"Swapped {ingredient.name} for {rule.substitute} — original contains: {rule.reason}.")
        elif rule.action == RuleAction.REDUCE:
            reduced_qty = round(ingredient.quantity * rule.keep_fraction, 3)
            adapted.append(ingredient.model_copy(update={"quantity": reduced_qty}))
            pct = int(rule.keep_fraction * 100)
            warnings.append(f"Reduced {ingredient.name} to {pct}% of the stated amount — {rule.reason}.")

    return adapted, warnings


async def run_adaptation_pass(
    recipe: ExtractedRecipe,
    age_group: AgeGroup,
    dietary_filters: list[DietaryFlag],
    unit_system: UnitSystem,
    include_medium_pantry: bool,
) -> AdaptedRecipe:
    age_band = resolve_age_band(age_group)
    warnings: list[str] = []

    # Hard-forbidden items (currently: honey under 12mo) are dropped outright
    # before the substitution table runs, since "swap it" isn't an option.
    survivors: list[Ingredient] = []
    for ingredient in recipe.ingredients:
        forbidden = check_ingredient_safety_for_band(ingredient.name, age_band.value)
        if forbidden and forbidden.highest_severity == "forbidden":
            warnings.append(f"Removed {ingredient.name} — {forbidden.ui_warning_text}")
            continue
        survivors.append(ingredient)

    adapted_ingredients, rule_warnings = apply_age_safety_rules(survivors, age_band)
    warnings.extend(rule_warnings)

    return AdaptedRecipe(
        metadata=recipe.metadata,
        ingredients=adapted_ingredients,
        steps=recipe.steps,
        age_group=age_group,
        dietary_filters=dietary_filters,
        warnings=warnings,
        confidence=recipe.confidence,
        extraction_method=recipe.extraction_method,
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
