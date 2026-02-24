"""Application configuration."""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # Google OAuth2
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")

    # Google Calendar API scopes
    GOOGLE_SCOPES: list = ["https://www.googleapis.com/auth/calendar.events"]

    # Anthropic API (for Claude Vision OCR)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # App settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Upload settings
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "/tmp/calendar-sync-uploads")
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB


settings = Settings()
