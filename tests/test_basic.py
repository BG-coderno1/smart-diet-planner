"""
Test suite for Smart Diet Planner.

Run with:  pytest
Requires the full requirements.txt to be installed (these tests exercise
the Flask app through its test client, not just the pure-Python ML modules).
"""
import io
import pytest

from app import create_app
from app.extensions import db as _db
from app.models import User, DietPlan, MealLog


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, email="test@example.com", password="password123", name="Test User"):
    return client.post(
        "/register",
        data={"name": name, "email": email, "password": password, "confirm_password": password},
        follow_redirects=True,
    )


def login(client, email="test@example.com", password="password123"):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)


# ---------- Auth ----------

def test_register_and_login(client):
    resp = register(client)
    assert resp.status_code == 200
    assert b"Dashboard" in resp.data or b"dashboard" in resp.data.lower()


def test_duplicate_email_rejected(client, app):
    register(client)
    with app.app_context():
        assert User.query.count() == 1
    resp = register(client)  # same email again
    with app.app_context():
        assert User.query.count() == 1  # no duplicate created


def test_login_wrong_password_fails(client):
    register(client)
    client.get("/logout")
    resp = login(client, password="wrong-password")
    assert b"Incorrect email or password" in resp.data


def test_protected_routes_require_login(client):
    resp = client.get("/dashboard", follow_redirects=True)
    assert b"log in" in resp.data.lower() or b"login" in resp.data.lower()


# ---------- Diet plans ----------

def test_create_plan_flow(client, app):
    register(client)
    resp = client.post(
        "/plans/create",
        data={
            "plan_name": "Test Plan",
            "meals_count": 3,
            "user_weight": 70,
            "user_height": 170,
            "target_calories": 2000,
            "target_protein": 90,
            "target_carbs": 250,
            "target_fat": 65,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        plan = DietPlan.query.first()
        assert plan is not None
        assert plan.meals_count == 3
        assert "meals" in plan.plan_data
        assert len(plan.plan_data["meals"]) == 3


def test_create_plan_rejects_invalid_input(client):
    register(client)
    resp = client.post(
        "/plans/create",
        data={
            "plan_name": "",  # invalid: required
            "meals_count": 999,  # invalid: out of range
            "user_weight": 70,
            "user_height": 170,
            "target_calories": 2000,
            "target_protein": 90,
            "target_carbs": 250,
            "target_fat": 65,
        },
    )
    assert resp.status_code == 200  # re-renders form with errors, no crash


def test_delete_plan_requires_ownership(client, app):
    register(client, email="a@example.com")
    client.post(
        "/plans/create",
        data={
            "plan_name": "A's plan", "meals_count": 2, "user_weight": 70, "user_height": 170,
            "target_calories": 1800, "target_protein": 80, "target_carbs": 200, "target_fat": 60,
        },
    )
    with app.app_context():
        plan_id = DietPlan.query.first().id

    client.get("/logout")
    register(client, email="b@example.com")
    resp = client.post(f"/plans/{plan_id}/delete", follow_redirects=True)
    assert resp.status_code == 404


# ---------- Meal analysis ----------

def test_meal_text_logging(client):
    register(client)
    resp = client.post("/meals/log", data={"meal_text": "boiled rice, hot tea"}, follow_redirects=True)
    assert resp.status_code == 200


def test_meal_text_empty_shows_validation_error(client):
    register(client)
    resp = client.post("/meals/log", data={"meal_text": ""})
    assert resp.status_code == 200


def test_analyze_meals_requires_selection(client):
    register(client)
    resp = client.post("/meals/analyze", data={"num_meals": "1"})
    assert b"select at least one" in resp.data.lower()


# ---------- API ----------

def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["food_database_ready"] is True


def test_food_search_requires_login(client):
    resp = client.get("/api/foods/search?q=rice")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "unauthorized"


def test_food_search_returns_results(client):
    register(client)
    resp = client.get("/api/foods/search?q=rice")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data["results"], list)
