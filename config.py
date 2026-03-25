"""Application configuration."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
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


config = {
    "development": Config,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": Config,
}
