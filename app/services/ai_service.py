"""Thin wrapper over the AI provider (Tempolor / ElevenLabs / etc.).

The original snippet hit the same `tempolor.com` URL twice with different
payloads — first for lyrics, then for the vocal track. We model that exact
two-step flow but keep the provider pluggable so you can swap models without
touching route code.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Cost in credits per call. Surfaced back to the user so we can deduct from their wallet.
LYRICS_CREDIT_COST = 1        # $0.01
MUSIC_CREDIT_COST = 70        # $0.70 — premium vocal track


class AIServiceError(Exception):
    """Raised when the upstream AI provider fails or returns an unusable payload."""


class AIService:
    """Async client for lyrics + music generation."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or settings.AI_API_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.AI_API_KEY
        self.timeout = timeout

    # ---------------- internal helpers ----------------
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(url, json=payload, headers=self._headers())
            except httpx.HTTPError as exc:
                logger.exception("AI provider network error: %s", exc)
                raise AIServiceError(f"AI provider unreachable: {exc}") from exc

            if resp.status_code >= 400:
                logger.error("AI provider %s -> %s: %s", url, resp.status_code, resp.text)
                raise AIServiceError(
                    f"AI provider returned {resp.status_code}: {resp.text[:500]}"
                )

            try:
                return resp.json()
            except ValueError as exc:
                raise AIServiceError("AI provider returned non-JSON response") from exc

    # ---------------- public API ----------------
    async def generate_lyrics(
        self,
        theme: str,
        language_mix: str = "English, Igbo, Yoruba, Hausa",
        style_hint: Optional[str] = None,
    ) -> str:
        """Step 1: produce multilingual, structured lyrics."""
        prompt = (
            f"Write a Nigerian song about {theme}. "
            f"Use a seamless mix of {language_mix}. "
            f"{f'Style: {style_hint}. ' if style_hint else ''}"
            f"Include structured [Verse] and [Chorus] tags. "
            f"Keep it authentic to Nigerian street culture and rhythm."
        )
        payload = {"model": settings.AI_LYRICS_MODEL, "prompt": prompt}

        # The Tempolor flow posts the same payload to the lyrics endpoint; in
        # practice the path differs per provider, so callers can configure it.
        # We default to /lyrics.
        data = await self._post("/lyrics", payload)
        lyrics = data.get("lyrics") or data.get("text") or data.get("output")
        if not lyrics:
            raise AIServiceError("Lyrics endpoint returned empty body")
        return lyrics.strip()

    async def generate_song(
        self,
        prompt: str,
        lyrics: str,
        duration_seconds: Optional[int] = None,
    ) -> dict[str, Any]:
        """Step 2: produce the vocal track. Returns provider response verbatim."""
        payload: dict[str, Any] = {
            "model": settings.AI_MUSIC_MODEL,
            "prompt": prompt,
            "lyrics": lyrics,
        }
        if duration_seconds:
            payload["duration"] = duration_seconds

        data = await self._post("/music", payload)
        # Expected fields: { audio_url, audio_base64, duration_seconds, ... }
        return data

    async def generate_full_track(
        self,
        theme: str,
        style: str,
        language_mix: str,
        user_lyrics: Optional[str] = None,
        duration_seconds: Optional[int] = None,
    ) -> tuple[str, dict[str, Any], int]:
        """Convenience: lyrics (auto or provided) → music. Returns (lyrics, audio, credits_used)."""
        if user_lyrics and user_lyrics.strip():
            lyrics = user_lyrics.strip()
            credits = MUSIC_CREDIT_COST
        else:
            lyrics = await self.generate_lyrics(theme=theme, language_mix=language_mix)
            credits = LYRICS_CREDIT_COST + MUSIC_CREDIT_COST

        # Run generation — the prompt drives the *sound*, the lyrics drive the words.
        music_prompt = (
            f"A high-energy modern {style} track about {theme}. "
            f"Groovy basslines, crisp percussion, smooth sax, polished 44.1kHz vocals."
        )

        # Retry once on transient failures
        last_err: Optional[Exception] = None
        for attempt in range(2):
            try:
                audio = await self.generate_song(
                    prompt=music_prompt,
                    lyrics=lyrics,
                    duration_seconds=duration_seconds,
                )
                return lyrics, audio, credits
            except AIServiceError as exc:
                last_err = exc
                await asyncio.sleep(2 ** attempt)

        raise AIServiceError(f"Music generation failed after retries: {last_err}")


# Singleton
ai_service = AIService()
