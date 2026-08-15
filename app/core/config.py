"""Application configuration loaded from environment variables."""
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
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

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    # AI Provider
    AI_API_BASE_URL: str = "https://api.example.com/v1"
    AI_API_KEY: str = "changeme"
    AI_LYRICS_MODEL: str = "lyric-v1"
    AI_MUSIC_MODEL: str = "eleven-music-v2"

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    CLOUDINARY_FOLDER: str = "naijasound/tracks"

    # Bootstrap admin
    FIRST_SUPERUSER_EMAIL: str = "admin@naijasound.ai"
    FIRST_SUPERUSER_PASSWORD: str = "ChangeMe123!"

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
