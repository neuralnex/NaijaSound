"""Song routes — generate, list, fetch, stream, share, cover, instrumental, drafts."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Song, User
from app.schemas.language import resolve_language_preset
from app.schemas.schemas import (
    CoverRequest,
    InstrumentalRequest,
    LyricsRequest,
    LyricsResponse,
    ProduceDraftRequest,
    ShareLinkResponse,
    SharedSongRead,
    SongGenerateRequest,
    SongListResponse,
    SongRead,
)
from app.services.ai_service import (
    COVER_CREDIT_COST,
    LYRICS_CREDIT_COST,
    MUSIC_CREDIT_COST,
    AIServiceError,
    ai_service,
    STEMS_V2_CREDIT_COST,
    STEMS_V3_CREDIT_COST,
)
from app.services.cloudinary_service import CloudinaryError, cloudinary_service
from app.core.config import settings
from app.utils.tokens import new_share_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/songs", tags=["songs"])


def _ensure_credits(user: User, needed: int) -> None:
    if (user.credits - user.reserved_credits) < needed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits: need {needed}, available {user.credits - user.reserved_credits}",
        )


async def _reserve_credits_atomic(db: AsyncSession, user_id: int, amount: int) -> None:
    """Atomics reservation of credits to prevent race conditions."""
    stmt = (
        update(User)
        .where(User.id == user_id)
        .where((User.credits - User.reserved_credits) >= amount)
        .values(reserved_credits=User.reserved_credits + amount)
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits to reserve {amount}",
        )
    await db.commit()


async def _finalize_credits_atomic(
    db: AsyncSession, user_id: int, actual_cost: int, reserved_amount: int
) -> None:
    """Deducts actual cost and releases the reserved amount."""
    stmt = (
        update(User)
        .where(User.id == user_id)
        .values(
            credits=User.credits - actual_cost,
            reserved_credits=User.reserved_credits - reserved_amount,
        )
    )
    await db.execute(stmt)
    await db.commit()


async def _refund_credits_atomic(db: AsyncSession, user_id: int, reserved_amount: int) -> None:
    """Releases the reserved amount back to the available pool without deducting."""
    stmt = (
        update(User)
        .where(User.id == user_id)
        .values(reserved_credits=User.reserved_credits - reserved_amount)
    )
    await db.execute(stmt)
    await db.commit()


async def _upload_audio_or_fail(song: Song, current_user: User, audio: dict) -> None:
    """Common audio→Cloudinary pipeline shared by song/instrumental/cover/produce."""
    audio_source = audio.get("audio_url") or audio.get("audio_base64")
    if not audio_source:
        song.status = "failed"
        song.error_message = "AI provider returned no audio payload"
        raise HTTPException(status_code=502, detail="AI provider returned no audio payload")
    try:
        upload = await cloudinary_service.upload_audio(
            user_id=current_user.id,
            song_id=song.id,
            source=audio_source,
        )
    except CloudinaryError as exc:
        song.status = "failed"
        song.error_message = f"Cloudinary upload failed: {exc}"
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    song.audio_url = upload["url"]
    song.audio_public_id = upload["public_id"]
    song.duration_seconds = upload.get("duration") or audio.get("duration_seconds")


# ---------- Lyrics-only (and lyrics-as-draft) ----------
@router.post(
    "/lyrics",
    response_model=LyricsResponse,
    summary="Generate multilingual Nigerian lyrics (1 credit)",
)
async def generate_lyrics(
    payload: LyricsRequest,
    persist_draft: bool = Query(
        False,
        description="If true, also persist the lyrics as a draft Song row "
        "that can be produced later with POST /songs/{id}/produce.",
    ),
    title: Optional[str] = Query(
        None, max_length=200, description="Title used when persist_draft=true"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LyricsResponse:
    _ensure_credits(current_user, LYRICS_CREDIT_COST)
    current_user.reserved_credits += LYRICS_CREDIT_COST
    db.add(current_user)
    await db.commit()

    try:
        lyrics = await ai_service.generate_lyrics(
            theme=payload.theme,
            language_preset=payload.language_preset,
            custom_mix=payload.custom_language_mix,
            style_hint=payload.style_hint,
        )
    except AIServiceError as exc:
        current_user.reserved_credits -= LYRICS_CREDIT_COST
        await db.commit()
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc
    except Exception as exc:
        logger.exception("Unexpected error during lyrics generation")
        current_user.reserved_credits -= LYRICS_CREDIT_COST
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {str(exc)}") from exc

    current_user.credits -= LYRICS_CREDIT_COST
    current_user.reserved_credits -= LYRICS_CREDIT_COST
    db.add(current_user)

    song_id: Optional[int] = None
    if persist_draft:
        resolved = resolve_language_preset(payload.language_preset, payload.custom_language_mix)
        song = Song(
            title=title or f"Draft — {payload.theme[:80]}",
            theme=payload.theme,
            style=payload.style_hint or "afro-fusion",
            language_mix=payload.language_preset,
            lyrics=lyrics,
            lyrics_generated=True,
            status="draft",
            credits_used=LYRICS_CREDIT_COST,
            owner_id=current_user.id,
        )
        db.add(song)
        await db.commit()
        await db.refresh(song)
        song_id = song.id

    await db.commit()
    return LyricsResponse(lyrics=lyrics, credits_used=LYRICS_CREDIT_COST, song_id=song_id)


# ---------- Full song generation ----------
@router.post(
    "",
    response_model=SongRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate a full vocal track (Async)",
)
async def create_song(
    payload: SongGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Song:
    estimated_cost = MUSIC_CREDIT_COST
    if payload.generate_lyrics and not (payload.lyrics and payload.lyrics.strip()):
        estimated_cost += LYRICS_CREDIT_COST

    # 1. Atomic Reservation
    await _reserve_credits_atomic(db, current_user.id, estimated_cost)

    # 2. Create Song record in 'processing' state
    song = Song(
        title=payload.title,
        theme=payload.theme,
        style=payload.style,
        language_mix=payload.language_preset,
        lyrics=payload.lyrics if payload.lyrics else None,
        lyrics_generated=False,
        status="processing",
        credits_used=estimated_cost, # Store reservation cost here
        owner_id=current_user.id,
    )
    db.add(song)
    await db.commit()
    await db.refresh(song)

    # 3. Submit to AI provider
    try:
        callback_url = f"{settings.AI_CALLBACK_URL}?song_id={song.id}"

        await ai_service.submit_full_track(
            theme=payload.theme,
            style=payload.style,
            language_preset=payload.language_preset,
            custom_mix=payload.custom_language_mix,
            user_lyrics=payload.lyrics,
            duration_seconds=payload.duration_seconds,
            callback_url=callback_url,
        )
    except AIServiceError as exc:
        # Refund immediately if submission fails
        await _refund_credits_atomic(db, current_user.id, estimated_cost)
        song.status = "failed"
        song.error_message = str(exc)
        await db.commit()
        raise HTTPException(status_code=502, detail=f"AI submission failed: {exc}")

    return song


# ---------- Instrumental-only ----------
@router.post(
    "/instrumental",
    response_model=SongRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate an instrumental beat (Async). 70 credits.",
)
async def create_instrumental(
    payload: InstrumentalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Song:
    estimated_cost = MUSIC_CREDIT_COST
    await _reserve_credits_atomic(db, current_user.id, estimated_cost)

    song = Song(
        title=payload.title,
        theme=payload.theme,
        style=payload.style,
        language_mix=payload.language_preset,
        lyrics=None,
        lyrics_generated=False,
        status="processing",
        credits_used=0,
        owner_id=current_user.id,
    )
    db.add(song)
    await db.commit()
    await db.refresh(song)

    try:
        audio, credits_used = await ai_service.generate_instrumental(
            theme=payload.theme,
            style=payload.style,
            duration_seconds=payload.duration_seconds,
        )
    except AIServiceError as exc:
        song.status = "failed"
        song.error_message = str(exc)
        current_user.reserved_credits -= MUSIC_CREDIT_COST
        await db.commit()
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc

    song.credits_used = credits_used
    try:
        _upload_audio_or_fail(song, current_user, audio)
    except HTTPException:
        current_user.reserved_credits -= MUSIC_CREDIT_COST
        await db.commit()
        raise

    current_user.credits -= credits_used
    current_user.reserved_credits -= MUSIC_CREDIT_COST
    song.status = "ready"
    db.add(current_user)
    await db.commit()
    await db.refresh(song)
    return song


# ---------- Cover / Remix ----------
@router.post(
    "/cover",
    response_model=SongRead,
    status_code=status.HTTP_201_CREATED,
    summary="Cover/remix one of your existing tracks (10 credits). Vocal only.",
)
async def create_cover(
    payload: CoverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Song:
    _ensure_credits(current_user, COVER_CREDIT_COST)
    current_user.reserved_credits += COVER_CREDIT_COST
    db.add(current_user)
    await db.commit()

    source = await db.get(Song, payload.source_song_id)
    if source is None or source.owner_id != current_user.id:
        current_user.reserved_credits -= COVER_CREDIT_COST
        await db.commit()
        raise HTTPException(status_code=404, detail="Source song not found in your dashboard")
    if source.status != "ready" or not source.audio_url:
        current_user.reserved_credits -= COVER_CREDIT_COST
        await db.commit()
        raise HTTPException(
            status_code=400,
            detail="Source song is not ready or has no audio to cover",
        )

    cover = Song(
        title=payload.title,
        theme=payload.theme or source.theme,
        style=payload.style or source.style,
        language_mix=source.language_mix,
        lyrics=payload.lyrics or source.lyrics,
        lyrics_generated=False,
        status="processing",
        credits_used=0,
        owner_id=current_user.id,
        source_song_id=source.id,
    )
    db.add(cover)
    await db.commit()
    await db.refresh(cover)

    try:
        lyrics, audio, credits_used = await ai_service.generate_cover_track(
            source_song=source,
            new_lyrics=payload.lyrics,
            style=payload.style,
            theme=payload.theme,
        )
    except AIServiceError as exc:
        cover.status = "failed"
        cover.error_message = str(exc)
        current_user.reserved_credits -= COVER_CREDIT_COST
        await db.commit()
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc

    cover.lyrics = lyrics
    cover.credits_used = credits_used
    try:
        _upload_audio_or_fail(cover, current_user, audio)
    except HTTPException:
        current_user.reserved_credits -= COVER_CREDIT_COST
        await db.commit()
        raise

    current_user.credits -= credits_used
    current_user.reserved_credits -= COVER_CREDIT_COST
    cover.status = "ready"
    db.add(current_user)
    await db.commit()
    await db.refresh(cover)
    return cover


# ---------- Produce a draft ----------
@router.post(
    "/{song_id}/produce",
    response_model=SongRead,
    summary="Turn a draft Song (lyrics only) into a full vocal track. 70 credits.",
)
async def produce_draft(
    song_id: int,
    payload: ProduceDraftRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Song:
    song = await db.get(Song, song_id)
    if song is None or song.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Song not found")
    if song.status != "draft":
        raise HTTPException(status_code=400, detail=f"Song is not a draft (status={song.status})")
    if not song.lyrics:
        raise HTTPException(status_code=400, detail="Draft has no lyrics to produce")

    estimated_cost = MUSIC_CREDIT_COST
    await _reserve_credits_atomic(db, current_user.id, estimated_cost)

    song.status = "processing"
    await db.commit()

    music_prompt = (
        f"{song.style.capitalize()} track about {song.theme}. "
        f"Groovy basslines, crisp percussion, polished 44.1kHz vocals."
    )
    try:
        audio = await ai_service.generate_song(
            prompt=music_prompt,
            lyrics=song.lyrics,
            duration_seconds=payload.duration_seconds,
        )
    except AIServiceError as exc:
        song.status = "failed"
        song.error_message = str(exc)
        current_user.reserved_credits -= MUSIC_CREDIT_COST
        await db.commit()
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc

    try:
        _upload_audio_or_fail(song, current_user, audio)
    except HTTPException:
        current_user.reserved_credits -= MUSIC_CREDIT_COST
        await db.commit()
        raise

    song.credits_used = MUSIC_CREDIT_COST
    current_user.credits -= MUSIC_CREDIT_COST
    current_user.reserved_credits -= MUSIC_CREDIT_COST
    song.status = "ready"
    db.add(current_user)
    await db.commit()
    await db.refresh(song)
    return song


# ---------- Share / fork ----------
@router.post(
    "/{song_id}/share",
    response_model=ShareLinkResponse,
    summary="Mint a public share token for this song",
)
async def enable_share(
    song_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShareLinkResponse:
    song = await db.get(Song, song_id)
    if song is None or song.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Song not found")
    if song.status != "ready":
        raise HTTPException(status_code=400, detail="Only ready songs can be shared")

    if not song.share_token:
        song.share_token = new_share_token()
        await db.commit()
    return ShareLinkResponse(
        song_id=song.id,
        share_token=song.share_token,
        share_url=f"/songs/share/{song.share_token}",
    )


@router.delete(
    "/{song_id}/share",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the share token",
)
async def disable_share(
    song_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    song = await db.get(Song, song_id)
    if song is None or song.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Song not found")
    song.share_token = None
    await db.commit()


# ---------- Callback Handler ----------
@router.post(
    "/callback",
    summary="AI provider callback to finalize song generation",
)
async def ai_callback(
    song_id: int = Query(...),
    payload: dict = ...,
    db: AsyncSession = Depends(get_db),
) -> dict:
    song = await db.get(Song, song_id)
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")

    user = await db.get(User, song.owner_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    status_val = (payload.get("status") or "").lower()

    if status_val == "succeeded":
        # 1. Handle Audio Upload
        audio_data = {
            "audio_url": payload.get("audio_url"),
            "duration_seconds": payload.get("duration") or payload.get("duration_seconds"),
        }
        try:
            await _upload_audio_or_fail(song, user, audio_data)
        except Exception as exc:
            song.status = "failed"
            song.error_message = f"Post-processing failed: {exc}"
            await _refund_credits_atomic(db, user.id, song.credits_used if song.credits_used else 0) # This is tricky
            # Wait, we need to know the reserved amount.
            # Let's store the reservation cost in the Song model or a separate table.
            # Actually, let's check how we define the cost.
            # For now, I'll use the estimated cost based on the song type.
            await db.commit()
            return {"status": "error", "detail": str(exc)}

        # 2. Finalize Song
        song.status = "ready"

        # 3. Finalize Credits
        # We need the original reserved amount. Let's assume we store it in `credits_used`
        # during the reservation phase.
        actual_cost = song.credits_used
        await _finalize_credits_atomic(db, user.id, actual_cost, actual_cost)

        await db.commit()
        return {"status": "ok"}

    elif status_val == "failed":
        song.status = "failed"
        song.error_message = payload.get("error", "AI provider reported failure")

        # Refund the reserved amount
        await _refund_credits_atomic(db, user.id, song.credits_used)

        await db.commit()
        return {"status": "refunded"}

    return {"status": "ignored", "detail": f"Unsupported status: {status_val}"}
@router.get(
    "/share/{token}",
    response_model=SharedSongRead,
    summary="Public read-only view of a shared song",
)
async def view_shared(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> Song:
    song = (
        await db.execute(select(Song).where(Song.share_token == token))
    ).scalar_one_or_none()
    if song is None or song.status != "ready":
        raise HTTPException(status_code=404, detail="Shared song not found")
    return song


@router.post(
    "/share/{token}/fork",
    response_model=SongRead,
    status_code=status.HTTP_201_CREATED,
    summary="Fork a shared song into your own dashboard (no credits, just a copy).",
)
async def fork_shared(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Song:
    source = (
        await db.execute(select(Song).where(Song.share_token == token))
    ).scalar_one_or_none()
    if source is None or source.status != "ready":
        raise HTTPException(status_code=404, detail="Shared song not found")

    fork = Song(
        title=f"{source.title} (fork)",
        theme=source.theme,
        style=source.style,
        language_mix=source.language_mix,
        lyrics=source.lyrics,
        lyrics_generated=source.lyrics_generated,
        audio_url=source.audio_url,
        audio_public_id=None,  # don't share cleanup rights with a stranger
        duration_seconds=source.duration_seconds,
        cover_url=source.cover_url,
        cover_public_id=None,
        status="ready",
        credits_used=0,
        owner_id=current_user.id,
        source_song_id=source.id,
    )
    db.add(fork)
    await db.commit()
    await db.refresh(fork)
    return fork


# ---------- Listing / fetch / delete ----------
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
        except Exception:
            logger.warning("Cloudinary cleanup failed for %s", song.audio_public_id)
    if song.cover_public_id:
        try:
            cloudinary_service.delete(song.cover_public_id, resource_type="image")
        except Exception:
            logger.warning("Cloudinary cleanup failed for %s", song.cover_public_id)

    await db.delete(song)
    await db.commit()


@router.post(
    "/{song_id}/stems",
    response_model=SongRead,
    summary="Generate stems (vocals/drums/bass/other) for an existing song",
)
async def generate_stems_for_song(
    song_id: int,
    model: Optional[str] = Query(None, description='"Stems v2" (4-stem) or "Stems v3" (8-stem)'),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Song:
    # load song and permissions
    song = await db.get(Song, song_id)
    if song is None or song.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Song not found")

    if not song.audio_url:
        raise HTTPException(status_code=400, detail="Song has no audio to separate into stems")

    # determine model and cost
    model = model or settings.AI_STEMS_MODEL
    if model == "Stems v2":
        needed = STEMS_V2_CREDIT_COST
    elif model == "Stems v3":
        needed = STEMS_V3_CREDIT_COST
    else:
        raise HTTPException(status_code=400, detail="Unsupported stems model")

    _ensure_credits(current_user, needed)
    current_user.reserved_credits += needed
    db.add(current_user)
    await db.commit()

    # run stem separation (submit+poll)
    try:
        result = await ai_service.generate_stems(audio_url=song.audio_url, model=model)
    except AIServiceError as exc:
        song.status = "failed"
        song.error_message = str(exc)
        current_user.reserved_credits -= needed
        await db.commit()
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc

    stems = result.get("stems") or {}

    # Try to upload each discovered stem to Cloudinary and save the secure URL
    try:
        for key, url in stems.items():
            if not isinstance(url, str) or not url.startswith("http"):
                continue
            upload = cloudinary_service.upload_audio(user_id=current_user.id, song_id=song.id, source=url)
            public_url = upload.get("url")
            if not public_url:
                continue
            if key == "vocals":
                song.stems_vocals_url = public_url
            elif key == "drums":
                song.stems_drums_url = public_url
            elif key == "bass":
                song.stems_bass_url = public_url
            else:
                # map other/lead/backing/instruments to `stems_other_url` if present
                song.stems_other_url = public_url
    except CloudinaryError as exc:
        song.status = "failed"
        song.error_message = f"Cloudinary upload failed: {exc}"
        current_user.reserved_credits -= needed
        await db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Reconcile credits and persist
    current_user.credits -= needed
    current_user.reserved_credits -= needed
    song.credits_used += needed
    song.status = "ready"
    db.add(current_user)
    db.add(song)
    await db.commit()
    await db.refresh(song)
    return song
