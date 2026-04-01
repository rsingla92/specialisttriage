"""Application configuration."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

_DEV_SECRET_KEY = "dev-secret-key-change-in-production"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET_KEY)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'specialisttriage.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Connection pool settings prevent connection exhaustion under load.
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
    # SQLite in-memory databases use StaticPool, which does not support the
    # pool_size / pool_recycle / pool_pre_ping options set in the base Config.
    SQLALCHEMY_ENGINE_OPTIONS = {}


class ProductionConfig(Config):
    """Configuration for production environment."""
    # SECRET_KEY is read from the environment; if unset, the insecure
    # development default will be used. The application factory is
    # responsible for validating that a secure, non-default SECRET_KEY
    # is provided when running in production.
    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET_KEY)
    WTF_CSRF_ENABLED = True


config = {
    "development": Config,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": Config,
}
