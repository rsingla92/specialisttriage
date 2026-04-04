"""Flask application factory."""
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

from config import config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


def create_app(config_name="default"):
    app = Flask(__name__)
    cfg = config[config_name]
    app.config.from_object(cfg)

    # Run config-specific initialization (e.g., production SSL enforcement)
    if hasattr(cfg, "init_app"):
        cfg.init_app(app)

    # Fail fast in production if the insecure dev default secret key is used.
    from config import _DEV_SECRET_KEY
    if config_name == "production" and app.config.get("SECRET_KEY") == _DEV_SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY environment variable must be set in production. "
            "The development default must never be used in a production deployment."
        )

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # Serve static files efficiently in production
    if config_name == "production":
        from whitenoise import WhiteNoise
        app.wsgi_app = WhiteNoise(app.wsgi_app, root=app.static_folder, prefix="static/")

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access the specialist triage portal."
    login_manager.login_message_category = "info"

    from app.models import User  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.referrals import referrals_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.api import api_bp
    from app.routes.templates import templates_bp
    from app.routes.pathways import pathways_bp
    from app.routes.analytics import analytics_bp
    from app.routes.admin import admin_bp
    from app.routes.clinic import clinic_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(referrals_bp, url_prefix="/referrals")
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(templates_bp, url_prefix="/templates")
    app.register_blueprint(pathways_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(clinic_bp, url_prefix="/clinic")

    return app
