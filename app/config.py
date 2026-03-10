# Path: app/config.py
import os
from datetime import timedelta


def _database_uri():
    """URI для БД. SQLAlchemy требует postgresql://; при postgres:// подменяем префикс."""
    url = (
        os.getenv("DATABASE_URL")
        or "postgresql://postgres:asdf1234@localhost:5432/StroyBase"
    )
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-jwt-secret-key")
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    # BOT_TOKEN = os.getenv("BOT_TOKEN")  # опционально
    BASE_DIR = os.getenv(
        "BASE_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    MEDIA_DIR = os.path.join(BASE_DIR, "app", "static", "media")
    # LOG_FILE = os.path.join(BASE_DIR, "logs", "app.log")
    YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "your-yandex-api-key-here")
