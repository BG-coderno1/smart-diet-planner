import os
import requests
import random

# We'll use Nutritionix for food lookups if needed
APP_ID = os.environ.get('NUTRITIONIX_APP_ID')
API_KEY = os.environ.get('NUTRITIONIX_API_KEY')
HEADERS = {
    "x-app-id": APP_ID,
    "x-app-key": API_KEY,
    "Content-Type": "application/json"
}
NATURAL_NUTRIENTS_URL = "https://trackapi.nutritionix.com/v2/natural/nutrients"
SEARCH_INSTANT_URL = "https://trackapi.nutritionix.com/v2/search/instant"

# A small fallback food database with approximate macros (per serving)
FALLBACK_FOODS = [
    {"name":"Oatmeal (1 cup cooked)","cal":154,"protein":6,"carbs":27,"fat":3},
    {"name":"Egg (large)","cal":72,"protein":6,"carbs":0.4,"fat":4.8},
    {"name":"Grilled chicken breast (100g)","cal":165,"protein":31,"carbs":0,"fat":3.6},
    {"name":"Brown rice (1 cup cooked)","cal":216,"protein":5,"carbs":45,"fat":1.8},
    {"name":"Banana (medium)","cal":105,"protein":1.3,"carbs":27,"fat":0.3},
    {"name":"Greek yogurt (1 cup)","cal":130,"protein":11,"carbs":9,"fat":4},
    {"name":"Almonds (30g)","cal":173,"protein":6,"carbs":6.1,"fat":15},
    {"name":"Broccoli (1 cup)","cal":55,"protein":3.7,"carbs":11,"fat":0.6}
]

def recommend_meals(meals_count, weight, height, target_calories, target_protein, target_carbs, target_fat):
    """
    Simple greedy recommender: split targets equally across meals, then fill each meal with items
    from fallback or Nutritionix to meet meal-level targets.
    """
    per_meal_targets = {
        'calories': target_calories / max(1, meals_count),
        'protein': target_protein / max(1, meals_count),
        'carbs': target_carbs / max(1, meals_count),
        'fat': target_fat / max(1, meals_count)
    }

    meals = []
    for i in range(meals_count):
        # naive approach: select 2-3 items that roughly sum to per_meal_targets
        meal_items = []
        current = {'cal':0, 'protein':0, 'carbs':0, 'fat':0}
        tries = 0
        while (current['cal'] < per_meal_targets['calories']*0.9 or current['protein'] < per_meal_targets['protein']*0.9) and tries < 10:
            # pick a candidate from fallback (random pick weighted towards higher protein when protein deficit)
            deficit_protein = per_meal_targets['protein'] - current['protein']
            if deficit_protein > 5:
                # prefer high-protein items
                candidates = sorted(FALLBACK_FOODS, key=lambda f: -f['protein'])
            else:
                candidates = FALLBACK_FOODS[:]
            pick = random.choice(candidates)
            meal_items.append(pick)
            current['cal'] += pick['cal']
            current['protein'] += pick['protein']
            current['carbs'] += pick['carbs']
            current['fat'] += pick['fat']
            tries += 1

        meals.append({
            'meal_index': i+1,
            'items': meal_items,
            'totals': {k: round(v,1) for k,v in current.items()},
            'targets': {k: round(v,1) for k,v in per_meal_targets.items()}
        })

    # Aggregate totals
    agg = {'calories': sum(m['totals']['cal'] for m in meals),
           'protein': sum(m['totals']['protein'] for m in meals),
           'carbs': sum(m['totals']['carbs'] for m in meals),
           'fat': sum(m['totals']['fat'] for m in meals)}

    return {
        'bmi_estimate': calculate_bmi(weight, height),
        'meals': meals,
        'aggregate': agg,
        'targets': {
            'calories': target_calories,
            'protein': target_protein,
            'carbs': target_carbs,
            'fat': target_fat
        }
    }

def calculate_bmi(weight_kg, height_cm):
    try:
        h_m = height_cm / 100.0
        bmi = weight_kg / (h_m*h_m)
        return round(bmi,1)
    except:
        return None
