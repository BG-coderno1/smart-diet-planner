# Deployment Guide

## 1. Local development (SQLite, zero config)

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# open .env and set SECRET_KEY to any long random string

flask --app run.py init-db        # creates instance/app.db and tables
flask --app run.py seed-demo       # optional: demo@example.com / password123
flask --app run.py run             # http://127.0.0.1:5000
```

No `DATABASE_URL` is needed for this path — `config.py` falls back to a
local SQLite file automatically.

## 2. Local development with Postgres

```bash
# create a database and user (example, adjust to your setup)
createdb smart_diet_planner
psql -c "CREATE USER sdp_user WITH PASSWORD 'sdp_password';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE smart_diet_planner TO sdp_user;"
```

In `.env`:
```
DATABASE_URL=postgresql://sdp_user:sdp_password@localhost:5432/smart_diet_planner
```

Then use Flask-Migrate instead of `init-db` (recommended for anything past
local experimentation, since it gives you versioned schema changes):

```bash
flask --app run.py db init        # first time only, creates migrations/
flask --app run.py db migrate -m "initial schema"
flask --app run.py db upgrade
```

## 3. Production deployment

1. Set environment variables (don't commit real secrets):
   - `FLASK_ENV=production`
   - `SECRET_KEY` — a long, random value
   - `DATABASE_URL` — your Postgres connection string
   - `VISION_BACKEND=auto` (or `lite` to force the offline CV path)

2. Run migrations: `flask --app run.py db upgrade`

3. Serve with a production WSGI server (never `flask run` in production):
   ```bash
   gunicorn -w 4 -b 0.0.0.0:8000 "run:app"
   ```

4. Put a reverse proxy (nginx, Caddy, or your platform's load balancer) in
   front of gunicorn for TLS termination and static file serving.

5. Point `RATELIMIT_STORAGE_URI` at Redis in multi-process deployments —
   the default in-memory limiter only tracks requests per-process, so
   `memory://` under-counts once you run more than one worker:
   ```
   RATELIMIT_STORAGE_URI=redis://localhost:6379/0
   ```

### Platform notes

- **Render / Railway / Heroku-style platforms**: these typically inject
  `DATABASE_URL` with the legacy `postgres://` scheme — `config.py` already
  normalizes this to `postgresql://` for you.
- **Docker**: a minimal `Dockerfile` would be:
  ```dockerfile
  FROM python:3.12-slim
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "run:app"]
  ```

## 4. Enabling exact-dish photo recognition (optional)

The app works fully without this — it just uses the lightweight
category-level photo recognizer. To get exact-dish recognition:

```bash
pip install torch torchvision

# Organize photos as: data/food_images/<dish name>/*.jpg
# (dish names should match "Dish Name" in the nutrition CSV)

python train_food_classifier.py --data-dir data/food_images --epochs 15
```

This writes `model_weights/food_classifier.pt` and `model_weights/labels.json`.
The app picks these up automatically on next restart — no code changes
needed, and no action needed if you never run this (the lite backend keeps
working either way).

## 5. Running tests

```bash
pip install pytest
pytest
```

## 6. Common issues

| Symptom | Likely cause | Fix |
|---|---|---|
| `sqlalchemy.exc.OperationalError` on startup | `DATABASE_URL` unreachable | Check Postgres is running and credentials are correct |
| Food search / analysis always returns empty | CSV path wrong or file missing | Confirm `app/static/data/Indian_Food_Nutrition_Processed.csv` exists, or set `FOOD_CSV_PATH` |
| Photo scan says "lightweight offline recognizer" | Expected until you train the deep model | See section 4 above |
| CSRF error on form submit | Session/cookie blocked, or form missing `{{ form.hidden_tag() }}` | Ensure cookies are allowed; every POST form must include the CSRF token |
| Rate limit errors under load testing | Multiple workers with in-memory limiter | Switch `RATELIMIT_STORAGE_URI` to Redis |
