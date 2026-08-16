"""User dashboard routes — profile, credits, voice."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, hash_password
from app.models.models import User
from app.schemas.schemas import UserRead, UserUpdate, VoiceCloneResponse
from app.services.cloudinary_service import CloudinaryError, cloudinary_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url
    if payload.password:
        current_user.hashed_password = hash_password(payload.password)

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/me/dashboard")
async def dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lightweight dashboard summary for the home page."""
    await db.execute(select(User).where(User.id == current_user.id))
    return {
        "user": UserRead.model_validate(current_user).model_dump(mode="json"),
        "credits_remaining": current_user.credits,
        "songs_count": len(current_user.songs),
    }


# ---------- Voice cloning (stub) ----------
#
# Wire this up when you confirm the voice-clone provider (ElevenLabs Voice Cloning
# is the standard). The endpoint uploads the user's sample to Cloudinary, then
# hands the URL off to the voice-clone API and persists the returned voice_id on
# the user. Until a provider is configured we keep the endpoint, but reject the
# request with a clear 501 so the frontend can show a "coming soon" message.
@router.post(
    "/me/voice",
    response_model=VoiceCloneResponse,
    summary="Upload a voice sample and clone it for future generations (provider TBD)",
)
async def clone_voice(
    sample: Annotated[UploadFile, File(description="Voice sample, 10-120 seconds")],
    current_user: User = Depends(get_current_user),
) -> VoiceCloneResponse:
    sample_bytes = await sample.read()
    if not sample_bytes:
        raise HTTPException(status_code=400, detail="Empty voice sample")
    if len(sample_bytes) > 10 * 1024 * 1024:  # 10 MB ceiling
        raise HTTPException(status_code=413, detail="Voice sample too large (max 10 MB)")

    # Upload to Cloudinary so the provider gets a URL it can fetch.
    try:
        cloudinary_service.upload_audio(
            user_id=current_user.id,
            song_id=0,  # voice samples aren't tied to a song row
            source=sample_bytes,
        )
    except CloudinaryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # TODO: when the voice-clone provider is wired up, call it here with the
    # Cloudinary URL and replace the placeholder below with the returned voice_id.
    # Example shape (ElevenLabs):
    #   voice_id = await voice_provider.clone(url=upload["url"], sample_seconds=...)
    #   current_user.voice_id = voice_id
    #   await db.commit()
    raise HTTPException(
        status_code=501,
        detail="Voice cloning provider not yet configured — see README 'Switching "
        "the AI provider' to enable it.",
    )
