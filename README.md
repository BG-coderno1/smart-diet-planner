# Smart Diet Planner

A personalized diet-planning and meal-analysis web app for Indian nutrition,
rebuilt from an original prototype into an industry-structured Flask
application: blueprint-based architecture, Postgres-ready ORM models, real
input validation, CSRF protection, rate limiting, a deterministic meal
recommender, and a computer-vision food-photo scanner.

## What changed from the original prototype

| Area | Before | After |
|---|---|---|
| App structure | One `app.py` with all routes | Application factory + blueprints (`auth`, `diet`, `meals`, `vision`, `api`) |
| Plan storage | `str()` / `eval()` round-trip of a Python dict (arbitrary code execution risk) | Real `JSON`/`JSONB` column via SQLAlchemy |
| Database | SQLite only, hardcoded path | Postgres-ready via `DATABASE_URL`; SQLite auto-fallback for local dev |
| Input validation | Raw `request.form` access, no validation | Flask-WTF forms with server-side validation on every field |
| CSRF | None | Flask-WTF CSRF protection on all forms |
| Rate limiting | None | Flask-Limiter on login, photo scans, API search |
| Food lookup | Re-read the CSV from disk on every request; silent fuzzy-match failures | Cached, indexed `FoodDatabase` singleton; matching with confidence scores and no silent zeros |
| Meal recommender | Random pick from 8 hardcoded foods, unbounded retry loop | Deterministic greedy optimization over the full ~1,000-dish dataset |
| Computer vision | None | Real photo-based food recognition (see below) |
| Error handling | Default Flask error pages, unhandled 500s | Custom error pages + JSON error responses for API clients, logging to rotating file |
| Frontend | Default Bootstrap look | Custom design system (see `app/static/css/style.css`) |

## Computer vision: two backends, one contract

`app/ml/vision.py` is the single entry point both routes and tests call. It
picks a backend and always returns the same response shape:

- **Lite backend** (`app/ml/vision_lite.py`) — classical OpenCV color/texture
  features + a scikit-learn KNN classifier. Needs no GPU, no internet, no
  training data; runs out of the box. It recognizes **broad food
  categories** (rice/grain, roti/flatbread, curry, leafy dish, fried snack,
  dessert, beverage), then narrows to specific dishes by keyword match
  against the nutrition database.
- **Deep backend** (`app/ml/vision_deep.py`) — a MobileNetV3-Small pretrained
  on ImageNet with a replaced classification head, fine-tuned on your own
  labeled food photos for **exact per-dish recognition**. See
  `train_food_classifier.py` for the training script and expected dataset
  layout. Requires `pip install torch torchvision` plus a labeled photo
  dataset — neither is bundled, since they're large and optional.

`VISION_BACKEND=auto` (the default) uses the deep model automatically once
you've trained it and installed torch; until then it transparently falls
back to the lite backend, so the feature works immediately and upgrades
without any code changes.

## Project layout

```
run.py                     # entry point
config.py                  # env-based config (dev/test/prod)
train_food_classifier.py   # optional: fine-tune the deep CV model
requirements.txt
app/
  __init__.py              # application factory
  extensions.py            # db, login_manager, csrf, limiter, migrate
  models.py                # User, DietPlan, MealLog
  forms.py                 # WTForms validation
  auth/                    # register, login, logout
  diet/                    # dashboard, create/view/delete plan
  meals/                   # structured analyzer + free-text meal logging
  vision/                  # food photo scanner route
  api/                     # JSON API (health, food search, plan summary)
  ml/
    nutrient_analyzer.py   # FoodDatabase + NutrientAnalyzer
    recommender.py         # deterministic meal-plan optimizer
    vision.py               # backend orchestrator
    vision_lite.py          # OpenCV/sklearn backend
    vision_deep.py           # torchvision transfer-learning backend
  static/{css,js,data,uploads}/
  templates/
tests/
  test_basic.py
```

## Quick start

See `DEPLOYMENT.md` for full setup instructions. In short:

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # edit SECRET_KEY at minimum
flask --app run.py init-db
flask --app run.py seed-demo    # optional demo user
flask --app run.py run
```

## Tech stack

| Component | Technology |
|---|---|
| Backend | Flask (application factory + blueprints) |
| Database | PostgreSQL (production) / SQLite (dev fallback), via SQLAlchemy + Flask-Migrate |
| Auth | Flask-Login, hashed passwords (Werkzeug) |
| Forms/validation | Flask-WTF |
| Frontend | Server-rendered Jinja2, custom CSS design system, vanilla JS |
| Nutrition data | `Indian_Food_Nutrition_Processed.csv` (~1,000 dishes) |
| ML — meal planning | Deterministic greedy macro-optimization |
| ML — computer vision | OpenCV + scikit-learn (default) / MobileNetV3 transfer learning (optional, trainable) |
