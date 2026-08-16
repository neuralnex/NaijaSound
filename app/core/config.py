"""Application configuration loaded from environment variables."""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    APP_NAME: str = "NaijaSound AI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Security
    SECRET_KEY: str = "dev-only-change-me-in-production-please-32-chars-min"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./naijasound.db"

    # CORS — read as a raw string (comma-separated) and split via property below.
    # pydantic-settings tries json.loads() on List[str] fields, which fails for
    # "http://a,http://b", so we keep this as `str`.
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # AI Provider — Tempolor (https://api.tempolor.com/open-apis/v1)
    AI_API_BASE_URL: str = "https://api.tempolor.com/open-apis/v1"
    AI_API_KEY: str = "Tempo-changeme"
    # Eleven Music V2 — vocal or instrumental tracks (up to 5 min, 44.1kHz MP3/WAV)
    AI_MUSIC_MODEL: str = "Eleven Music V2"
    # Lyric v1 — lyrics from a theme/description
    AI_LYRICS_MODEL: str = "Lyric v1"
    # Tempolor models
    AI_COVER_MODEL: str = "tempolor-latest"
    AI_STEMS_MODEL: str = "Stems v2"
    # Public URL Tempolor will POST back to when async generation finishes.
    # Must be reachable from the internet — use ngrok/cloudflare tunnel for local dev.
    AI_CALLBACK_URL: str = "https://yourdomin.com/music-gen/tempolor/callback"

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    CLOUDINARY_FOLDER: str = "naijasound/tracks"

    # Bootstrap admin
    FIRST_SUPERUSER_EMAIL: str = "admin@naijasound.ai"
    FIRST_SUPERUSER_PASSWORD: str = "ChangeMe123!"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
