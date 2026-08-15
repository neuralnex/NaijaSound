"""Cloudinary upload helpers for generated audio tracks + cover art."""
from __future__ import annotations

import logging
from typing import Any, Optional

import cloudinary
import cloudinary.uploader

from app.core.config import settings

logger = logging.getLogger(__name__)


class CloudinaryError(Exception):
    pass


def _configure() -> None:
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


class CloudinaryService:
    def __init__(self) -> None:
        _configure()

    @staticmethod
    def _public_id_for(user_id: int, song_id: int, kind: str) -> str:
        return f"{settings.CLOUDINARY_FOLDER}/user_{user_id}/song_{song_id}/{kind}"

    def upload_audio(
        self,
        user_id: int,
        song_id: int,
        source: str | bytes,
        *,
        resource_type: str = "video",  # Cloudinary treats audio under "video"
    ) -> dict[str, Any]:
        """Upload an audio track. `source` can be a remote URL or raw bytes."""
        public_id = self._public_id_for(user_id, song_id, "track")
        try:
            result = cloudinary.uploader.upload(
                source,
                public_id=public_id,
                resource_type=resource_type,
                folder=None,  # already in public_id
                overwrite=True,
                invalidate=True,
                audio_codec="mp3",
            )
        except Exception as exc:  # cloudinary raises broad exceptions
            logger.exception("Cloudinary audio upload failed")
            raise CloudinaryError(str(exc)) from exc

        return {
            "url": result.get("secure_url"),
            "public_id": result.get("public_id"),
            "duration": result.get("duration"),
            "format": result.get("format"),
            "bytes": result.get("bytes"),
        }

    def upload_cover(
        self,
        user_id: int,
        song_id: int,
        source: str | bytes,
    ) -> dict[str, Any]:
        public_id = self._public_id_for(user_id, song_id, "cover")
        try:
            result = cloudinary.uploader.upload(
                source,
                public_id=public_id,
                resource_type="image",
                overwrite=True,
                invalidate=True,
            )
        except Exception as exc:
            raise CloudinaryError(str(exc)) from exc
        return {"url": result.get("secure_url"), "public_id": result.get("public_id")}

    def delete(self, public_id: str, resource_type: str = "video") -> None:
        try:
            cloudinary.uploader.destroy(public_id, resource_type=resource_type, invalidate=True)
        except Exception as exc:
            logger.warning("Cloudinary delete failed for %s: %s", public_id, exc)


cloudinary_service = CloudinaryService()
