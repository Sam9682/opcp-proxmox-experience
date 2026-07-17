"""Application configuration."""

import os

PORT = int(os.environ.get("PORT", 5000))
HOST = os.environ.get("HOST", "0.0.0.0")
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")
FLASK_ENV = os.environ.get("FLASK_ENV", "production")
