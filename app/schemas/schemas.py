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
    language_mix: str = Field(
        default="English, Igbo, Yoruba, Hausa",
        description="Comma-separated list of languages to weave together",
    )
    style_hint: Optional[str] = Field(
        None, description="e.g. 'street-hop', 'highlife', 'afro-fusion'"
    )


class LyricsResponse(BaseModel):
    lyrics: str
    credits_used: int


class SongGenerateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    theme: str = Field(..., min_length=2, max_length=500)
    style: str = Field(default="afro-fusion", max_length=100)
    language_mix: str = Field(default="English, Igbo, Yoruba, Hausa", max_length=200)
    # If the user already wrote lyrics, skip generation. Otherwise we'll generate them.
    lyrics: Optional[str] = Field(None, description="User-provided lyrics; auto-generated if omitted")
    generate_lyrics: bool = Field(
        default=True, description="If true and `lyrics` is empty, we'll write them"
    )
    duration_seconds: Optional[int] = Field(default=None, ge=15, le=240)


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
    status: str
    error_message: Optional[str] = None
    credits_used: int
    owner_id: int
    created_at: datetime
    updated_at: datetime


class SongListResponse(BaseModel):
    items: list[SongRead]
    total: int
    page: int
    page_size: int
