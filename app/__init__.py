import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, request, jsonify

from config import get_config
from app.extensions import db, migrate, login_manager, csrf, limiter


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_cli(app)
    _configure_logging(app)

    @app.context_processor
    def inject_globals():
        return {"app_name": "Smart Diet Planner"}

    return app


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import request, jsonify, redirect, url_for
        if request.path.startswith("/api/"):
            return jsonify(error="unauthorized", message="Login required"), 401
        return redirect(url_for("auth.login", next=request.path))


def _register_blueprints(app: Flask) -> None:
    from app.auth.routes import auth_bp
    from app.diet.routes import diet_bp
    from app.meals.routes import meals_bp
    from app.vision.routes import vision_bp
    from app.api.routes import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(diet_bp)
    app.register_blueprint(meals_bp)
    app.register_blueprint(vision_bp)
    app.register_blueprint(api_bp, url_prefix="/api")


def _wants_json() -> bool:
    return (
        request.path.startswith("/api/")
        or request.accept_mimetypes.best == "application/json"
        or request.is_json
    )


def _register_error_handlers(app: Flask) -> None:
    from app.extensions import db as _db

    @app.errorhandler(400)
    def bad_request(e):
        if _wants_json():
            return jsonify(error="bad_request", message=str(e)), 400
        return render_template("errors/error.html", code=400, message="That request didn't look right."), 400

    @app.errorhandler(404)
    def not_found(e):
        if _wants_json():
            return jsonify(error="not_found", message="Resource not found"), 404
        return render_template("errors/error.html", code=404, message="We couldn't find that page."), 404

    @app.errorhandler(413)
    def too_large(e):
        if _wants_json():
            return jsonify(error="payload_too_large", message="File is too large"), 413
        return render_template("errors/error.html", code=413, message="That file is too large (max 8 MB)."), 413

    @app.errorhandler(429)
    def rate_limited(e):
        if _wants_json():
            return jsonify(error="rate_limited", message="Too many requests, slow down."), 429
        return render_template("errors/error.html", code=429, message="Too many requests — please slow down."), 429

    @app.errorhandler(500)
    def server_error(e):
        _db.session.rollback()
        app.logger.exception("Unhandled server error")
        if _wants_json():
            return jsonify(error="server_error", message="Something went wrong on our end."), 500
        return render_template("errors/error.html", code=500, message="Something went wrong on our end."), 500


def _register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Create all tables directly (quick setup for dev/demo). For
        production schema changes, prefer Flask-Migrate: `flask db migrate`
        and `flask db upgrade` (see DEPLOYMENT.md)."""
        db.create_all()
        print("Database tables created.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Create a demo user for quick local testing: demo@example.com / password123"""
        from app.models import User

        if not User.query.filter_by(email="demo@example.com").first():
            user = User(name="Demo User", email="demo@example.com")
            user.set_password("password123")
            db.session.add(user)
            db.session.commit()
            print("Created demo user: demo@example.com / password123")
        else:
            print("Demo user already exists.")


def _configure_logging(app: Flask) -> None:
    if app.debug or app.testing:
        return
    log_dir = os.path.join(app.instance_path, "logs")
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(os.path.join(log_dir, "app.log"), maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d] %(message)s"
    ))
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
