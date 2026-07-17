import os
import uuid

from flask import Blueprint, render_template, current_app, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db, limiter
from app.forms import FoodPhotoForm
from app.ml.nutrient_analyzer import get_food_db
from app.ml.vision import analyze_food_photo
from app.models import MealLog

vision_bp = Blueprint("vision", __name__)


def _allowed_file(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]


@vision_bp.route("/meals/scan", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per hour")
def scan_photo():
    form = FoodPhotoForm()
    analysis = None

    if form.validate_on_submit():
        file = form.photo.data
        if not file or not _allowed_file(file.filename):
            flash("Please upload a JPG, PNG, or WEBP image.", "danger")
            return render_template("food_scan.html", form=form, analysis=None)

        filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
        save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)

        try:
            file.save(save_path)
            db_food = get_food_db(current_app.config["FOOD_CSV_PATH"])
            analysis = analyze_food_photo(
                save_path, db_food, backend_preference=current_app.config["VISION_BACKEND"]
            )

            if "error" not in analysis:
                all_matches = [
                    food for pred in analysis["predictions"] for food in pred["matched_foods"]
                ]
                if all_matches:
                    totals = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
                    for f in all_matches:
                        for key in totals:
                            totals[key] += f.get(key, 0)
                    totals = {k: round(v, 1) for k, v in totals.items()}
                    analysis["totals_estimate"] = totals

                    log = MealLog(user_id=current_user.id, source="photo", items=all_matches, totals=totals)
                    db.session.add(log)
                    db.session.commit()
        except Exception:
            current_app.logger.exception("Photo scan failed")
            analysis = {"error": "We couldn't process that photo. Please try again with a clearer image."}
        finally:
            # Don't keep raw uploads around longer than needed for analysis.
            if os.path.exists(save_path):
                try:
                    os.remove(save_path)
                except OSError:
                    pass

    return render_template("food_scan.html", form=form, analysis=analysis)
