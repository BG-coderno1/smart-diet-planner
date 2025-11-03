import os
import pandas as pd
import difflib

# ---------- CONFIG ----------
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_PATH = os.path.join(BASE_DIR, "static", "data", "Indian_Food_Nutrition_Processed.csv")

# ---------- LOAD DATA ----------
try:
    food_df = pd.read_csv(DATA_PATH)
    food_df.columns = food_df.columns.str.strip()
    food_df["Dish Name"] = food_df["Dish Name"].str.strip().str.lower()
except Exception as e:
    print("⚠️ Error loading CSV:", e)
    food_df = pd.DataFrame()

# ---------- HELPER ----------
def find_food_in_db(food_name):
    """Find the closest match for a food or drink item."""
    if food_df.empty:
        return None

    food_name = food_name.lower().strip()
    matches = difflib.get_close_matches(food_name, food_df["Dish Name"], n=1, cutoff=0.6)
    if not matches:
        return None

    row = food_df.loc[food_df["Dish Name"] == matches[0]].iloc[0]
    return {
        "name": matches[0],
        "calories": float(row.get("Calories (kcal)", 0)),
        "protein": float(row.get("Protein (g)", 0)),
        "carbs": float(row.get("Carbohydrates (g)", 0)),
        "fat": float(row.get("Fats (g)", 0))
    }

# ---------- CORE ANALYZER ----------
def analyze_selected_meals(selected_meals, selected_drinks=None):
    total_calories = total_protein = total_carbs = total_fat = 0.0
    foods_analyzed = []
    all_items = []

    # 🟢 Handle both structures: list of dicts (new) or flat lists (old)
    if isinstance(selected_meals, list) and selected_meals and isinstance(selected_meals[0], dict):
        # new structured format: [{meal_type, foods, drinks}]
        for meal in selected_meals:
            meal_foods = meal.get("foods", [])
            meal_drinks = meal.get("drinks", [])
            all_items.extend(meal_foods + meal_drinks)
    else:
        # old format: just a list of strings
        if selected_meals:
            all_items.extend(selected_meals)
        if selected_drinks:
            all_items.extend(selected_drinks)

    # 🧮 Compute totals
    for item in all_items:
        row = food_df[food_df["Dish Name"].str.lower() == item.lower()]
        if not row.empty:
            cal = float(row["Calories (kcal)"].fillna(0).values[0])
            protein = float(row["Protein (g)"].fillna(0).values[0])
            carbs = float(row["Carbohydrates (g)"].fillna(0).values[0])
            fat = float(row["Fats (g)"].fillna(0).values[0])
        else:
            cal = protein = carbs = fat = 0.0

        total_calories += cal
        total_protein += protein
        total_carbs += carbs
        total_fat += fat

        foods_analyzed.append({
            "name": item,
            "calories": cal,
            "protein": protein,
            "carbs": carbs,
            "fat": fat
        })

    # 📊 Summarize totals
    totals = {
        "calories": round(total_calories, 1),
        "protein": round(total_protein, 1),
        "carbs": round(total_carbs, 1),
        "fat": round(total_fat, 1)
    }

    # 💡 Suggestions logic
    suggestions = []
    if totals["protein"] < 50:
        suggestions.append("Add high-protein foods like paneer, lentils, or eggs.")
    if totals["carbs"] < 200:
        suggestions.append("Include complex carbs like rice, oats, or whole grains.")
    if totals["fat"] < 60:
        suggestions.append("Add healthy fats such as nuts or ghee.")
    if totals["calories"] < 1800:
        suggestions.append("Your total calories are low — add a smoothie or snack.")

    # 🧠 Smart nutrient-based recommendations (optional extension)
    if totals["protein"] > 120:
        suggestions.append("You might reduce protein — balance with more veggies or carbs.")
    if totals["fat"] > 100:
        suggestions.append("High fat intake — consider reducing fried foods.")

    return {"totals": totals, "foods": foods_analyzed, "suggestions": suggestions}


# ---------- BACKWARD-COMPATIBLE WRAPPER ----------
def analyze_meal_text(meal_text):
    """
    Wrapper so old Flask route (single text input) still works.
    Splits comma-separated input like: "2 eggs, 1 apple, 1 cup rice"
    """
    items = [x.strip() for x in meal_text.split(",") if x.strip()]
    form_like = {"meals": [{"meal": x, "drink": ""} for x in items]}
    return analyze_selected_meals(form_like)

def get_all_foods():
    """
    Return a sorted list of all unique food items from the dataset.
    Used for populating dropdowns in the HTML form.
    """
    try:
        foods = sorted(food_df["Dish Name"].dropna().unique().tolist())
        return foods
    except Exception as e:
        print("Error getting food list:", e)
        return []
