"""
Application configuration.

Reads everything from environment variables (via python-dotenv locally) so the
exact same codebase runs unmodified in dev, test, and production. Postgres is
the target production database; SQLite is used automatically as a zero-config
fallback for local development if DATABASE_URL is not set.
"""
import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _normalize_db_url(url: str) -> str:
    """Heroku/Render/Railway style URLs sometimes use the legacy 'postgres://'
    scheme, which SQLAlchemy 1.4+/2.x rejects. Normalize to 'postgresql://'."""
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # os.environ.get("DATABASE_URL", default) only falls back to `default`
    # when the variable is completely absent — but a `.env` file with
    # `DATABASE_URL=` (empty) still sets it to "", which os.environ.get
    # happily returns as-is. Treat blank the same as unset here.
    _database_url = os.environ.get("DATABASE_URL", "").strip()
    if not _database_url:
        _database_url = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'app.db')}"

    SQLALCHEMY_DATABASE_URI = _normalize_db_url(_database_url)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,  # avoids "server closed connection" errors on Postgres
    }

    # Sessions / auth
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Uploads (used by the food photo scanner)
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "app", "static", "uploads")
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    # Data
    FOOD_CSV_PATH = os.environ.get(
        "FOOD_CSV_PATH",
        os.path.join(BASE_DIR, "app", "static", "data", "Indian_Food_Nutrition_Processed.csv"),
    )

    # Rate limiting
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    # Third-party (optional; app degrades gracefully without these)
    NUTRITIONIX_APP_ID = os.environ.get("NUTRITIONIX_APP_ID")
    NUTRITIONIX_API_KEY = os.environ.get("NUTRITIONIX_API_KEY")

    # Vision engine mode: "auto" picks the deep model if torch is installed,
    # otherwise falls back to the classical OpenCV pipeline.
    VISION_BACKEND = os.environ.get("VISION_BACKEND", "auto")

    WTF_CSRF_TIME_LIMIT = None


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    name = name or os.environ.get("FLASK_ENV", "development")
    return config_by_name.get(name, DevelopmentConfig)
