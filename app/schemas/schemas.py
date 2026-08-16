"""Pydantic schemas for request/response validation."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- User ----------
class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=64)
    full_name: Optional[str] = Field(None, max_length=120)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=120)
    avatar_url: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_superuser: bool
    avatar_url: Optional[str] = None
    credits: int
    voice_id: Optional[str] = None
    created_at: datetime


# ---------- Auth ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ---------- Songs ----------
class LyricsRequest(BaseModel):
    theme: str = Field(..., min_length=2, max_length=500)
    language_preset: str = Field(
        default="full-trilingual",
        description="One of: full-trilingual, igbo-yoruba, pidgin-heavy, "
        "hausa-fusion, english-only, custom",
    )
    custom_language_mix: Optional[str] = Field(
        None,
        max_length=200,
        description="Required when language_preset='custom'. Freeform mix like "
        "'Tiv, English, Pidgin'.",
    )
    style_hint: Optional[str] = Field(
        None, description="e.g. 'street-hop', 'highlife', 'afro-fusion'"
    )


class LyricsResponse(BaseModel):
    lyrics: str
    credits_used: int
    song_id: Optional[int] = Field(
        None,
        description="If the lyrics were persisted as a draft song, this is the id.",
    )


class SongGenerateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    theme: str = Field(..., min_length=2, max_length=500)
    style: str = Field(default="afro-fusion", max_length=100)
    language_preset: str = Field(
        default="full-trilingual",
        description="One of: full-trilingual, igbo-yoruba, pidgin-heavy, "
        "hausa-fusion, english-only, custom",
    )
    custom_language_mix: Optional[str] = Field(
        None, max_length=200, description="Required when language_preset='custom'."
    )
    # If the user already wrote lyrics, skip generation. Otherwise we'll generate them.
    lyrics: Optional[str] = Field(None, description="User-provided lyrics; auto-generated if omitted")
    generate_lyrics: bool = Field(
        default=True, description="If true and `lyrics` is empty, we'll write them"
    )
    duration_seconds: Optional[int] = Field(default=None, ge=15, le=300)


class InstrumentalRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    theme: str = Field(..., min_length=2, max_length=500)
    style: str = Field(default="amapiano", max_length=100)
    language_preset: str = Field(default="english-only")
    custom_language_mix: Optional[str] = Field(None, max_length=200)
    duration_seconds: Optional[int] = Field(default=None, ge=15, le=300)


class CoverRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    # Reference track id — must be a song the caller owns. We pass the
    # Cloudinary URL to Tempolor as `reference_url`.
    source_song_id: int = Field(..., ge=1)
    # Optional new lyrics for the cover (kept original if omitted).
    lyrics: Optional[str] = Field(None, description="New lyrics; if omitted the source lyrics are reused")
    # Optional style override ("reshape into amapiano", etc.).
    style: Optional[str] = Field(
        None,
        max_length=100,
        description="Target style — e.g. 'amapiano', 'highlife'. Keeps source style if omitted.",
    )
    theme: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional new theme — e.g. 'turn this into a Lagos wedding banger'.",
    )


class ProduceDraftRequest(BaseModel):
    duration_seconds: Optional[int] = Field(default=None, ge=15, le=300)


class ShareLinkResponse(BaseModel):
    song_id: int
    share_token: str
    share_url: str


class SharedSongRead(BaseModel):
    """Public-facing song payload returned by the share endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    theme: str
    style: str
    language_mix: str
    lyrics: Optional[str] = None
    audio_url: Optional[str] = None
    cover_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    created_at: datetime


class SongRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    theme: str
    style: str
    language_mix: str
    lyrics: Optional[str] = None
    lyrics_generated: bool
    audio_url: Optional[str] = None
    audio_public_id: Optional[str] = None
    duration_seconds: Optional[int] = None
    cover_url: Optional[str] = None
    cover_public_id: Optional[str] = None
    stems_vocals_url: Optional[str] = None
    stems_drums_url: Optional[str] = None
    stems_bass_url: Optional[str] = None
    stems_other_url: Optional[str] = None
    source_song_id: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    credits_used: int
    owner_id: int
    share_token: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SongListResponse(BaseModel):
    items: list[SongRead]
    total: int
    page: int
    page_size: int


# ---------- Prompt presets ----------
class PromptPresetRead(BaseModel):
    key: str
    title: str
    theme: str
    style: str
    language_preset: str
    description: str


class PromptPresetListResponse(BaseModel):
    items: list[PromptPresetRead]


# ---------- Voice cloning ----------
class VoiceCloneRequest(BaseModel):
    """Body for POST /users/me/voice — the actual audio upload is multipart."""

    sample_seconds: int = Field(default=30, ge=10, le=120)


class VoiceCloneResponse(BaseModel):
    voice_id: str
    sample_seconds: int
