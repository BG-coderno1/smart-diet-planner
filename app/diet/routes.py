from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.forms import CreatePlanForm
from app.ml.nutrient_analyzer import get_food_db
from app.ml.recommender import recommend_meals, calculate_bmi
from app.models import DietPlan

diet_bp = Blueprint("diet", __name__)


@diet_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("diet.dashboard"))
    return render_template("index.html")


@diet_bp.route("/dashboard")
@login_required
def dashboard():
    plans = (
        DietPlan.query.filter_by(user_id=current_user.id)
        .order_by(DietPlan.created_at.desc())
        .all()
    )
    return render_template("dashboard.html", plans=plans)


@diet_bp.route("/plans/create", methods=["GET", "POST"])
@login_required
def create_plan():
    form = CreatePlanForm()

    if form.validate_on_submit():
        db_food = get_food_db(current_app.config["FOOD_CSV_PATH"])
        recommendation = recommend_meals(
            db=db_food,
            meals_count=form.meals_count.data,
            weight=form.user_weight.data,
            height=form.user_height.data,
            target_calories=form.target_calories.data,
            target_protein=form.target_protein.data,
            target_carbs=form.target_carbs.data,
            target_fat=form.target_fat.data,
        )

        plan = DietPlan(
            user_id=current_user.id,
            name=form.plan_name.data.strip(),
            meals_count=form.meals_count.data,
            weight_kg=form.user_weight.data,
            height_cm=form.user_height.data,
            target_calories=form.target_calories.data,
            target_protein=form.target_protein.data,
            target_carbs=form.target_carbs.data,
            target_fat=form.target_fat.data,
            plan_data=recommendation,
        )
        db.session.add(plan)
        db.session.commit()

        flash("Plan created successfully.", "success")
        return redirect(url_for("diet.view_plan", plan_id=plan.id))

    return render_template("create_plan.html", form=form)


@diet_bp.route("/plans/<int:plan_id>")
@login_required
def view_plan(plan_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    return render_template("view_plan.html", plan=plan.plan_data, bmi=plan.bmi(), plan_name=plan.name)


@diet_bp.route("/plans/<int:plan_id>/delete", methods=["POST"])
@login_required
def delete_plan(plan_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    flash("Diet plan deleted.", "info")
    return redirect(url_for("diet.dashboard"))
