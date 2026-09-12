"""
Nutrition safety rule tests (PRD §4.3, ADR-003 Gate 1)
=========================================================
Covers the deterministic AAP-sourced toddler/infant safety rules in
app/services/adaptor.py. These are the "10 nutrition safety rule tests"
referenced as a hard merge gate in ci.yml / production.yml.
"""

from __future__ import annotations

import asyncio

from app.schemas.recipe import AgeGroup, ExtractedRecipe, Ingredient, RecipeMetadata, UnitSystem
from app.services.adaptor import run_adaptation_pass


def _recipe(*ingredients: Ingredient) -> ExtractedRecipe:
    return ExtractedRecipe(
        metadata=RecipeMetadata(title="Test Recipe", servings=4),
        ingredients=list(ingredients),
    )


def _adapt(recipe: ExtractedRecipe, age_group: AgeGroup):
    return asyncio.run(
        run_adaptation_pass(
            recipe=recipe,
            age_group=age_group,
            dietary_filters=[],
            unit_system=UnitSystem.IMPERIAL,
            include_medium_pantry=False,
        )
    )


def test_honey_substituted_for_toddler():
    recipe = _recipe(Ingredient(name="Honey", quantity=2, unit="tbsp"))
    result = _adapt(recipe, AgeGroup.TODDLER)
    assert [i.name for i in result.ingredients] == ["maple syrup"]
    assert any("Swapped Honey for maple syrup" in w for w in result.warnings)


def test_honey_forbidden_and_removed_for_infant_under_1():
    recipe = _recipe(Ingredient(name="Honey", quantity=1, unit="tbsp"))
    result = _adapt(recipe, AgeGroup.INFANT)
    assert result.ingredients == []
    assert any("unsafe under 12 months" in w for w in result.warnings)


def test_whole_nuts_substituted_for_finely_ground():
    recipe = _recipe(Ingredient(name="Whole Nuts", quantity=0.5, unit="cup"))
    result = _adapt(recipe, AgeGroup.TODDLER)
    assert result.ingredients[0].name == "finely ground nuts"
    assert result.ingredients[0].quantity == 0.5


def test_popcorn_omitted_entirely():
    recipe = _recipe(
        Ingredient(name="Popcorn", quantity=1, unit="bag"),
        Ingredient(name="Butter", quantity=1, unit="tbsp"),
    )
    result = _adapt(recipe, AgeGroup.TODDLER)
    names = [i.name for i in result.ingredients]
    assert "Popcorn" not in names
    assert "Butter" in names
    assert any("Removed Popcorn" in w for w in result.warnings)


def test_raw_carrots_substituted_for_steamed():
    recipe = _recipe(Ingredient(name="Raw Carrots", quantity=3, unit="whole"))
    result = _adapt(recipe, AgeGroup.TODDLER)
    assert result.ingredients[0].name == "steamed carrots"


def test_hot_sauce_omitted():
    recipe = _recipe(Ingredient(name="Hot Sauce", quantity=1, unit="tbsp"))
    result = _adapt(recipe, AgeGroup.TODDLER)
    assert result.ingredients == []


def test_fish_sauce_reduced_to_50_percent():
    recipe = _recipe(Ingredient(name="Fish Sauce", quantity=2, unit="tbsp"))
    result = _adapt(recipe, AgeGroup.TODDLER)
    assert result.ingredients[0].quantity == 1.0
    assert any("50%" in w for w in result.warnings)


def test_added_salt_reduced_to_70_percent():
    recipe = _recipe(Ingredient(name="Salt", quantity=1, unit="tsp"))
    result = _adapt(recipe, AgeGroup.TODDLER)
    assert result.ingredients[0].quantity == 0.7
    assert any("70%" in w for w in result.warnings)


def test_alcohol_omitted():
    recipe = _recipe(Ingredient(name="Alcohol", quantity=0.5, unit="cup"))
    result = _adapt(recipe, AgeGroup.TODDLER)
    assert result.ingredients == []
    assert any("Removed Alcohol" in w for w in result.warnings)


def test_no_rules_applied_for_adult_household():
    recipe = _recipe(
        Ingredient(name="Honey", quantity=2, unit="tbsp"),
        Ingredient(name="Popcorn", quantity=1, unit="bag"),
    )
    result = _adapt(recipe, AgeGroup.ADULT)
    names = [i.name for i in result.ingredients]
    assert names == ["Honey", "Popcorn"]
    assert result.warnings == []
