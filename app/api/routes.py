from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user

from app.extensions import limiter
from app.ml.nutrient_analyzer import get_food_db
from app.models import DietPlan

api_bp = Blueprint("api", __name__)


@api_bp.route("/health")
def health():
    db_food = get_food_db(current_app.config["FOOD_CSV_PATH"])
    return jsonify(
        status="ok" if db_food.is_ready else "degraded",
        food_database_ready=db_food.is_ready,
        food_count=len(db_food.all_names()) if db_food.is_ready else 0,
    )


@api_bp.route("/foods/search")
@login_required
@limiter.limit("60 per minute")
def food_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify(results=[])
    if len(query) > 100:
        return jsonify(error="Query too long"), 400

    db_food = get_food_db(current_app.config["FOOD_CSV_PATH"])
    if not db_food.is_ready:
        return jsonify(error="Food database is currently unavailable"), 503

    records = db_food.search(query, limit=10)
    return jsonify(results=[r.as_dict() for r in records])


@api_bp.route("/plans/<int:plan_id>")
@login_required
def plan_summary(plan_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=current_user.id).first()
    if plan is None:
        return jsonify(error="Plan not found"), 404
    return jsonify(
        id=plan.id,
        name=plan.name,
        bmi=plan.bmi(),
        targets={
            "calories": plan.target_calories,
            "protein": plan.target_protein,
            "carbs": plan.target_carbs,
            "fat": plan.target_fat,
        },
        plan_data=plan.plan_data,
    )
