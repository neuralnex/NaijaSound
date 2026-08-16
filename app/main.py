"""FastAPI entry point for NaijaSound AI."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db
from app.core.security import get_current_superuser, hash_password
from app.models.models import User
from app.routers import auth, prompts, songs, users
from app.schemas.schemas import UserRead

logging.basicConfig(level=logging.INFO if not settings.DEBUG else logging.DEBUG)
logger = logging.getLogger("naijasound")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks."""
    await init_db()
    await _bootstrap_superuser()
    logger.info("🚀 NaijaSound AI backend ready (env=%s)", settings.APP_ENV)
    yield
    logger.info("👋 NaijaSound shutting down")


async def _bootstrap_superuser() -> None:
    """Create the FIRST_SUPERUSER if no users exist yet (dev convenience)."""
    if not settings.FIRST_SUPERUSER_EMAIL or not settings.FIRST_SUPERUSER_PASSWORD:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).limit(1))
        if result.scalar_one_or_none() is not None:
            return

        admin = User(
            email=settings.FIRST_SUPERUSER_EMAIL,
            username="admin",
            full_name="NaijaSound Admin",
            hashed_password=hash_password(settings.FIRST_SUPERUSER_PASSWORD),
            is_superuser=True,
            credits=1000,
        )
        db.add(admin)
        await db.commit()
        logger.info("�  Bootstrapped superuser: %s", settings.FIRST_SUPERUSER_EMAIL)


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "AI-powered Nigerian music generation backend. "
        "Generate multilingual lyrics + vocal tracks, store on Cloudinary, "
        "play them back from each creator's dashboard."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}


# Routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(songs.router, prefix=settings.API_V1_PREFIX)
app.include_router(prompts.router, prefix=settings.API_V1_PREFIX)


# Re-export the superuser dep so it's importable elsewhere
__all__ = ["app", "get_current_superuser", "UserRead"]
