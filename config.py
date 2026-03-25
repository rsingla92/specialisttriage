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


class ProductionConfig(Config):
    # In production, SECRET_KEY must be explicitly provided via environment.
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY environment variable must be set for ProductionConfig."
        )
    WTF_CSRF_ENABLED = True
    # SECRET_KEY must be provided via environment variable in production.
    # The application factory will raise RuntimeError if the insecure dev default is used.
    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET_KEY)


config = {
    "development": Config,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": Config,
}
