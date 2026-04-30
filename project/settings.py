import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
    HOST = os.environ.get("FLASK_RUN_HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", os.environ.get("FLASK_RUN_PORT", "5000")))
    DEBUG = os.environ.get("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", "10")) * 1024 * 1024
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "uploads")),
    )
    DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required. SQLite fallback has been removed.")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

