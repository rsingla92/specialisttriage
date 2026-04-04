"""Application configuration."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

_DEV_SECRET_KEY = "dev-secret-key-change-in-production"


def _fix_database_url(url):
    """Fix common DATABASE_URL issues for SQLAlchemy compatibility."""
    if not url:
        return url
    # Heroku/Supabase may provide postgres:// but SQLAlchemy 2.x requires postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET_KEY)
    SQLALCHEMY_DATABASE_URI = _fix_database_url(
        os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'specialisttriage.db'}")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "pool_recycle": 3600,
        "pool_pre_ping": True,
    }
    WTF_CSRF_ENABLED = True

    # OceanMD API settings
    OCEAN_MD_BASE_URL = os.environ.get("OCEAN_MD_BASE_URL", "https://ocean.cognisantmd.com/api")
    OCEAN_MD_API_KEY = os.environ.get("OCEAN_MD_API_KEY", "")

    # Triage thresholds
    TRIAGE_HIGH_PRIORITY_THRESHOLD = 75
    TRIAGE_ROUTINE_THRESHOLD = 50


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_ENGINE_OPTIONS = {}


class ProductionConfig(Config):
    """Configuration for production environment."""
    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET_KEY)
    WTF_CSRF_ENABLED = True

    # Secure cookies
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Require DATABASE_URL in production
    SQLALCHEMY_DATABASE_URI = _fix_database_url(os.environ.get("DATABASE_URL", ""))

    # Use SSL for Postgres connections
    @staticmethod
    def init_app(app):
        db_url = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if not db_url:
            raise RuntimeError(
                "DATABASE_URL environment variable must be set in production."
            )
        if "postgresql" in db_url and "sslmode" not in db_url:
            sep = "&" if "?" in db_url else "?"
            app.config["SQLALCHEMY_DATABASE_URI"] = db_url + sep + "sslmode=require"


config = {
    "development": Config,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": Config,
}
