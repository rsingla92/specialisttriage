"""WSGI entry point for production deployment."""
import os

os.environ.setdefault("FLASK_ENV", "production")

from app import create_app  # noqa: E402

app = create_app(os.environ.get("FLASK_ENV", "production"))
