"""
Meal plan recommender.

The original prototype picked randomly from an 8-item hardcoded list and
could theoretically loop without making progress. This version:

- draws from the full ~1000-dish nutrition database instead of 8 fallback
  items, so recommendations are varied and India-specific
- is deterministic: given the same inputs it returns the same plan, which
  matters for testing and for user trust ("why did I get a different
  answer this time?")
- uses a bounded greedy scoring pass (a simplified knapsack heuristic) that
  is guaranteed to terminate in O(items x meals) time, instead of an
  unbounded random retry loop
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ml.nutrient_analyzer import FoodDatabase, FoodRecord

MAX_ITEMS_PER_MEAL = 6
CALORIE_OVERSHOOT_TOLERANCE = 1.15  # don't let one item blow the meal budget by more than 15%


@dataclass
class MealTarget:
    calories: float
    protein: float
    carbs: float
    fat: float


def calculate_bmi(weight_kg: float, height_cm: float):
    try:
        h_m = height_cm / 100.0
        if h_m <= 0:
            return None
        return round(weight_kg / (h_m * h_m), 1)
    except (TypeError, ZeroDivisionError):
        return None


def _score_item(record: FoodRecord, remaining: MealTarget) -> float:
    """Higher score = better next pick for closing the remaining gap without
    blowing past the calorie budget. Pure function, easy to unit test.

    Earlier version normalized by calories ("nutrient per calorie"), which
    systematically favored tiny, calorie-light items (soups, garnishes) and
    left meals well under their calorie target even after filling the item
    slots. This version scores on how much of the remaining macro gap an
    item closes *and* rewards using up more of the remaining calorie
    budget, so meals actually converge on the target instead of stalling.
    """
    if remaining.calories <= 0:
        return -1.0
    if record.calories > remaining.calories * CALORIE_OVERSHOOT_TOLERANCE:
        return -1.0

    protein_gain = min(record.protein, max(remaining.protein, 0))
    carb_gain = min(record.carbs, max(remaining.carbs, 0))
    fat_gain = min(record.fat, max(remaining.fat, 0))
    nutrient_score = (protein_gain * 2.0) + (carb_gain * 0.6) + (fat_gain * 0.8)

    # Reward filling more of the remaining calorie budget (capped at 1.0 so
    # a single huge item can't dominate purely by size).
    calorie_fit = min(record.calories / remaining.calories, 1.0)

    return nutrient_score + (calorie_fit * 8.0)


def _build_meal(candidates: list[FoodRecord], target: MealTarget, previously_used: set[str] | None = None) -> dict:
    remaining = MealTarget(target.calories, target.protein, target.carbs, target.fat)
    chosen: list[FoodRecord] = []
    totals = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    used_names = set()
    previously_used = previously_used or set()
    REPEAT_PENALTY = 3.0  # soft, not a hard ban: repeats are still allowed if nothing else fits

    for _ in range(MAX_ITEMS_PER_MEAL):
        best = None
        best_score = 0.0
        for record in candidates:
            if record.name in used_names:
                continue
            score = _score_item(record, remaining)
            if record.name in previously_used:
                score -= REPEAT_PENALTY
            if score > best_score:
                best_score = score
                best = record

        if best is None:
            break

        chosen.append(best)
        used_names.add(best.name)
        totals["calories"] += best.calories
        totals["protein"] += best.protein
        totals["carbs"] += best.carbs
        totals["fat"] += best.fat
        remaining.calories -= best.calories
        remaining.protein -= best.protein
        remaining.carbs -= best.carbs
        remaining.fat -= best.fat

        if remaining.calories <= target.calories * 0.1 and remaining.protein <= 2:
            break

    return {
        "foods": [r.as_dict() for r in chosen],
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "targets": {
            "calories": round(target.calories, 1),
            "protein": round(target.protein, 1),
            "carbs": round(target.carbs, 1),
            "fat": round(target.fat, 1),
        },
    }


def recommend_meals(
    db: FoodDatabase,
    meals_count: int,
    weight: float,
    height: float,
    target_calories: float,
    target_protein: float,
    target_carbs: float,
    target_fat: float,
) -> dict:
    meals_count = max(1, int(meals_count))

    per_meal = MealTarget(
        calories=target_calories / meals_count,
        protein=target_protein / meals_count,
        carbs=target_carbs / meals_count,
        fat=target_fat / meals_count,
    )

    candidates: list[FoodRecord] = []
    if db.is_ready:
        for name in db.all_names():
            record = db.exact_lookup(name)
            if record and record.calories > 0:
                candidates.append(record)

    meals = []
    used_across_meals: set[str] = set()
    for i in range(meals_count):
        meal = _build_meal(candidates, per_meal, used_across_meals) if candidates else {
            "foods": [],
            "totals": {"calories": 0, "protein": 0, "carbs": 0, "fat": 0},
            "targets": {
                "calories": round(per_meal.calories, 1),
                "protein": round(per_meal.protein, 1),
                "carbs": round(per_meal.carbs, 1),
                "fat": round(per_meal.fat, 1),
            },
        }
        meal["meal_index"] = i + 1
        meals.append(meal)
        used_across_meals.update(item["name"] for item in meal["foods"])

    aggregate = {
        "calories": round(sum(m["totals"]["calories"] for m in meals), 1),
        "protein": round(sum(m["totals"]["protein"] for m in meals), 1),
        "carbs": round(sum(m["totals"]["carbs"] for m in meals), 1),
        "fat": round(sum(m["totals"]["fat"] for m in meals), 1),
    }

    return {
        "bmi_estimate": calculate_bmi(weight, height),
        "meals": meals,
        "aggregate": aggregate,
        "targets": {
            "calories": target_calories,
            "protein": target_protein,
            "carbs": target_carbs,
            "fat": target_fat,
        },
        "data_source_unavailable": not bool(candidates),
    }
