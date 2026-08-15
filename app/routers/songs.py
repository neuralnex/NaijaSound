"""Song routes — generate, list, fetch, stream."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Song, User
from app.schemas.schemas import (
    LyricsRequest,
    LyricsResponse,
    SongGenerateRequest,
    SongListResponse,
    SongRead,
)
from app.services.ai_service import (
    LYRICS_CREDIT_COST,
    MUSIC_CREDIT_COST,
    AIServiceError,
    ai_service,
)
from app.services.cloudinary_service import CloudinaryError, cloudinary_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/songs", tags=["songs"])


def _ensure_credits(user: User, needed: int) -> None:
    if user.credits < needed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits: need {needed}, have {user.credits}",
        )


@router.post(
    "/lyrics",
    response_model=LyricsResponse,
    summary="Generate multilingual Nigerian lyrics (1 credit)",
)
async def generate_lyrics(
    payload: LyricsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LyricsResponse:
    _ensure_credits(current_user, LYRICS_CREDIT_COST)

    try:
        lyrics = await ai_service.generate_lyrics(
            theme=payload.theme,
            language_mix=payload.language_mix,
            style_hint=payload.style_hint,
        )
    except AIServiceError as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc

    current_user.credits -= LYRICS_CREDIT_COST
    db.add(current_user)
    await db.commit()

    return LyricsResponse(lyrics=lyrics, credits_used=LYRICS_CREDIT_COST)


@router.post(
    "",
    response_model=SongRead,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a full vocal track and store it in the user's dashboard",
)
async def create_song(
    payload: SongGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Song:
    # 1) Figure out how many credits this will cost (rough estimate — exact cost
    #    is reconciled after generation since lyrics may or may not be generated).
    estimated_cost = MUSIC_CREDIT_COST
    if payload.generate_lyrics and not (payload.lyrics and payload.lyrics.strip()):
        estimated_cost += LYRICS_CREDIT_COST

    _ensure_credits(current_user, estimated_cost)

    # 2) Create the row in `pending` state so the user sees it in their dashboard
    #    immediately, then update as generation progresses.
    song = Song(
        title=payload.title,
        theme=payload.theme,
        style=payload.style,
        language_mix=payload.language_mix,
        lyrics=payload.lyrics if payload.lyrics else None,
        lyrics_generated=False,
        status="processing",
        credits_used=0,
        owner_id=current_user.id,
    )
    db.add(song)
    await db.commit()
    await db.refresh(song)

    # 3) Run the AI pipeline
    try:
        lyrics, audio, credits_used = await ai_service.generate_full_track(
            theme=payload.theme,
            style=payload.style,
            language_mix=payload.language_mix,
            user_lyrics=payload.lyrics,
            duration_seconds=payload.duration_seconds,
        )
    except AIServiceError as exc:
        song.status = "failed"
        song.error_message = str(exc)
        await db.commit()
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc

    song.lyrics = lyrics
    song.lyrics_generated = bool(payload.lyrics is None and payload.generate_lyrics)
    song.credits_used = credits_used

    # 4) Upload to Cloudinary
    audio_source = audio.get("audio_url") or audio.get("audio_base64")
    if not audio_source:
        song.status = "failed"
        song.error_message = "AI provider returned no audio payload"
        await db.commit()
        raise HTTPException(status_code=502, detail="AI provider returned no audio payload")

    try:
        upload = cloudinary_service.upload_audio(
            user_id=current_user.id,
            song_id=song.id,
            source=audio_source,
        )
    except CloudinaryError as exc:
        song.status = "failed"
        song.error_message = f"Cloudinary upload failed: {exc}"
        await db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    song.audio_url = upload["url"]
    song.audio_public_id = upload["public_id"]
    song.duration_seconds = upload.get("duration") or audio.get("duration_seconds")

    # 5) Reconcile the user's credit wallet
    current_user.credits -= credits_used

    song.status = "ready"
    db.add(current_user)
    await db.commit()
    await db.refresh(song)
    return song


@router.get("", response_model=SongListResponse, summary="List the user's dashboard songs")
async def list_songs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SongListResponse:
    base = select(Song).where(Song.owner_id == current_user.id)
    if status_filter:
        base = base.where(Song.status == status_filter)

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        await db.execute(
            base.order_by(Song.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()

    return SongListResponse(
        items=[SongRead.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{song_id}", response_model=SongRead, summary="Fetch a single song")
async def get_song(
    song_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Song:
    song = await db.get(Song, song_id)
    if song is None or song.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Song not found")
    return song


@router.delete(
    "/{song_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a song from the user's dashboard",
)
async def delete_song(
    song_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    song = await db.get(Song, song_id)
    if song is None or song.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Song not found")

    if song.audio_public_id:
        try:
            cloudinary_service.delete(song.audio_public_id, resource_type="video")
        except Exception:  # don't fail the request on Cloudinary cleanup
            logger.warning("Cloudinary cleanup failed for %s", song.audio_public_id)

    await db.delete(song)
    await db.commit()
