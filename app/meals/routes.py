from flask import Blueprint, render_template, request, current_app, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.forms import MealTextForm
from app.ml.nutrient_analyzer import get_food_db, NutrientAnalyzer
from app.models import MealLog

meals_bp = Blueprint("meals", __name__)

MEAL_TYPES = ["Breakfast", "Lunch", "Dinner", "Snack"]


def _get_analyzer() -> NutrientAnalyzer:
    return NutrientAnalyzer(get_food_db(current_app.config["FOOD_CSV_PATH"]))


def _save_log(source: str, result: dict) -> None:
    """Best-effort persistence: a failed save should never break the user's
    view of their analysis, so errors are logged, not raised."""
    try:
        log = MealLog(
            user_id=current_user.id,
            source=source,
            items=result.get("foods", result.get("parsed_items", [])),
            totals=result.get("totals", {}),
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to save meal log")


@meals_bp.route("/meals/analyze", methods=["GET", "POST"])
@login_required
def analyze_meals():
    analyzer = _get_analyzer()
    all_foods = analyzer.db.all_names()
    result = None

    if request.method == "POST":
        try:
            num_meals = max(1, min(5, int(request.form.get("num_meals", 1))))
        except (TypeError, ValueError):
            num_meals = 1

        selected_items = []
        for i in range(num_meals):
            selected_items.extend(f for f in request.form.getlist(f"meal_food_{i}[]") if f and f.strip())
            selected_items.extend(d for d in request.form.getlist(f"meal_drink_{i}[]") if d and d.strip())

        if not selected_items:
            result = {"error": "Please select at least one food or drink item."}
        else:
            result = analyzer.analyze_items(selected_items)
            if "error" not in result:
                result["foods_display"] = [f["name"] for f in result["foods"]]
                _save_log("manual", result)

    return render_template(
        "analyze_meals.html",
        result=result,
        all_foods=all_foods,
        meal_types=MEAL_TYPES,
    )


@meals_bp.route("/meals/log", methods=["GET", "POST"])
@login_required
def meal_logging():
    form = MealTextForm()
    result = None

    if form.validate_on_submit():
        analyzer = _get_analyzer()
        result = analyzer.analyze_free_text(form.meal_text.data)
        if "error" not in result:
            _save_log("text", result)
            flash("Meal logged.", "success")

    recent_logs = (
        MealLog.query.filter_by(user_id=current_user.id)
        .order_by(MealLog.logged_at.desc())
        .limit(10)
        .all()
    )

    return render_template("meal_logging.html", form=form, result=result, recent_logs=recent_logs)
