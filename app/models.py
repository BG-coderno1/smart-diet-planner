from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import Index
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    weight_kg = db.Column(db.Float)
    height_cm = db.Column(db.Float)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    plans = db.relationship("DietPlan", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    meal_logs = db.relationship("MealLog", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"


class DietPlan(db.Model):
    __tablename__ = "diet_plans"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    name = db.Column(db.String(200), nullable=False)
    meals_count = db.Column(db.Integer, nullable=False)
    weight_kg = db.Column(db.Float, nullable=False)
    height_cm = db.Column(db.Float, nullable=False)

    target_calories = db.Column(db.Integer, nullable=False)
    target_protein = db.Column(db.Float, nullable=False)
    target_carbs = db.Column(db.Float, nullable=False)
    target_fat = db.Column(db.Float, nullable=False)

    # Real JSON column (JSONB on Postgres, JSON-as-text on SQLite) instead of
    # str()/eval() round-tripping, which was an arbitrary-code-execution risk.
    plan_data = db.Column(db.JSON, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def bmi(self):
        try:
            h_m = self.height_cm / 100.0
            return round(self.weight_kg / (h_m * h_m), 2)
        except (ZeroDivisionError, TypeError):
            return None


class MealLog(db.Model):
    __tablename__ = "meal_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    source = db.Column(db.String(20), nullable=False, default="manual")  # manual | text | photo
    items = db.Column(db.JSON, nullable=False)  # list of {name, calories, protein, carbs, fat, confidence?}
    totals = db.Column(db.JSON, nullable=False)  # {calories, protein, carbs, fat}
    logged_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_meal_logs_user_logged_at", "user_id", "logged_at"),
    )
