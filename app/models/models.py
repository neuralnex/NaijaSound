"""SQLAlchemy ORM models for users and songs."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship


from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    credits: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # free starter credits
    reserved_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # ElevenLabs-style cloned voice id (set after user uploads a 30s sample).
    voice_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    songs: Mapped[list["Song"]] = relationship(
        "Song", back_populates="owner", cascade="all, delete-orphan"
    )


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    theme: Mapped[str] = mapped_column(String(500), nullable=False)
    style: Mapped[str] = mapped_column(String(100), default="afro-fusion", nullable=False)
    # Either a curated preset key (see LANGUAGE_PRESETS) or a freeform comma-list.
    language_mix: Mapped[str] = mapped_column(String(200), default="full-trilingual")

    # Lyrics + track
    lyrics: Mapped[str | None] = mapped_column(Text, nullable=True)
    lyrics_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Cloudinary-hosted audio
    audio_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    audio_public_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cover_public_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Stems produced by the stem-separation job (vocals/drums/bass/other).
    stems_vocals_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    stems_drums_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    stems_bass_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    stems_other_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Source track id (used for covers/remixes — points at the reference song).
    source_song_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("songs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Status: draft | pending -> processing -> ready | failed
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cost tracking (credits spent)
    credits_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Public share token — null until the user opts in to sharing.
    share_token: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )

    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    owner: Mapped[User] = relationship("User", back_populates="songs")
    source: Mapped["Song | None"] = relationship(
        "Song", remote_side="Song.id", foreign_keys=[source_song_id]
    )
