"""Thin wrapper over the Tempolor AI provider.

Tempolor exposes async endpoints under `https://api.tempolor.com/open-apis/v1`:

  POST /lyrics/generate   — writes structured multilingual lyrics
  POST /song/generate     — produces the vocal or instrumental track
  POST /song/cover        — reference-based cover/remix (tempolor-latest)

Each endpoint requires the API key in the `Authorization` header. Tempolor keys
are issued in the form `Tempo-********************************-3w` and are sent
verbatim — NOT as a Bearer token.

Generation is asynchronous: we POST the job and Tempolor calls our
`AI_CALLBACK_URL` back when the track is ready. We poll the response here in
the meantime so the user still gets a synchronous-feeling experience.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Cost in credits per call. Surfaced back to the user so we can deduct from their wallet.
# Lyric v1 — lyrics generation (1 credit / $0.01).
LYRICS_CREDIT_COST = 1
# Eleven Music V2 — vocal or instrumental music generation (70 credits / $0.70).
MUSIC_CREDIT_COST = 70
# tempolor-latest — cover/remix generation (10 credits / $0.10). Vocal only.
COVER_CREDIT_COST = 10
# Stems v2 — 4-stem separation (vocals/drums/bass/other). 5 credits / $0.05.
STEMS_V2_CREDIT_COST = 5
# Stems v3 — 8-stem separation. 15 credits / $0.15.
STEMS_V3_CREDIT_COST = 15

# Tempolor endpoints (relative to AI_API_BASE_URL).
LYRICS_PATH = "/lyrics/generate"
LYRICS_QUERY_PATH = "/lyrics/query"
SONG_PATH = "/song/generate"
COVER_PATH = "/song/cover"
STEMS_PATH = "/stems"
STEMS_QUERY_PATH = "/stems/query"


class AIServiceError(Exception):
    """Raised when the upstream AI provider fails or returns an unusable payload."""


class AIService:
    """Async client for lyrics + music + cover generation via Tempolor."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        callback_url: Optional[str] = None,
        timeout: float = 120.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = (base_url or settings.AI_API_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.AI_API_KEY
        self.callback_url = callback_url or settings.AI_CALLBACK_URL
        self.timeout = timeout
        self.client = client

    # ---------------- internal helpers ----------------
    def _headers(self) -> dict[str, str]:
        # Tempolor keys are sent verbatim: `Authorization: Tempo-***-xxx`.
        # Do NOT prefix with `Bearer`.
        return {
            "Authorization": self.api_key,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"

        # Use shared client if available, otherwise create a temporary one
        if self.client:
            client = self.client
        else:
            client = httpx.AsyncClient(timeout=self.timeout)

        try:
            if not self.client:
                async with client:
                    resp = await client.post(url, json=payload, headers=self._headers())
            else:
                resp = await client.post(url, json=payload, headers=self._headers())
        except httpx.HTTPError as exc:
            logger.exception("AI provider network error: %s", exc)
            raise AIServiceError(f"AI provider unreachable: {exc}") from exc
        finally:
            # If we created a temporary client, it's already closed by the 'async with'
            pass

        if resp.status_code >= 400:
            logger.error("AI provider %s -> %s: %s", url, resp.status_code, resp.text)
            raise AIServiceError(
                f"AI provider returned {resp.status_code}: {resp.text[:500]}"
            )

        try:
            return resp.json() or {}
        except ValueError as exc:
            logger.error("AI provider returned non-JSON response: %s", resp.text)
            raise AIServiceError("AI provider returned non-JSON response") from exc

    # ---------------- public API ----------------
    async def query_lyrics(
        self,
        item_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Poll for the results of a lyrics generation job."""
        if not item_ids:
            return []
        payload = {"item_ids": item_ids}
        data = await self._post(LYRICS_QUERY_PATH, payload)
        # Use a helper to safely navigate nested dictionaries that might contain None
        data_content = data.get("data") if isinstance(data, dict) else None
        lyrics_list = data_content.get("lyrics", []) if isinstance(data_content, dict) else []
        if isinstance(lyrics_list, dict):
            lyrics_list = [lyrics_list]
        # Filter out None values to prevent crashes in polling loop
        return [item for item in lyrics_list if item is not None]

    async def generate_lyrics(
        self,
        theme: str,
        language_preset: str = "full-trilingual",
        custom_mix: Optional[str] = None,
        style_hint: Optional[str] = None,
        poll_interval: float = 2.0,
        poll_timeout: float = 60.0,
    ) -> str:
        """Step 1: produce multilingual, structured lyrics via Tempolor (Async with polling)."""
        try:
            from app.schemas.language import resolve_language_preset

            resolved = resolve_language_preset(language_preset, custom_mix)

            prompt_parts = [
                f"Genre: Nigerian street music",
                f"Languages to weave together: {resolved['mix']}",
                f"Theme: {theme}",
            ]
            if style_hint or resolved.get("hint"):
                hint = style_hint or resolved["hint"]
                prompt_parts.append(f"Style: {hint}")
            prompt_parts.append(
                "Include structured [Intro], [Verse], [Chorus], [Bridge], [Outro] tags."
            )

            payload = {
                "prompt": "\n".join(prompt_parts),
                "song_model": settings.AI_LYRICS_MODEL,
                "callback_url": self.callback_url,
            }

            # 1. Submit task
            data = await self._post(LYRICS_PATH, payload)
            logger.info("AI Lyrics Submit Data: %s", data)

            if data is None:
                raise AIServiceError("AI provider returned None as response")

            data_content = data.get("data") if isinstance(data, dict) else None
            item_ids = data_content.get("item_ids") if isinstance(data_content, dict) else None
            if not item_ids or not isinstance(item_ids, list):
                raise AIServiceError(f"Lyrics submit returned no item_ids: {data}")

            # 2. Poll for completion
            import asyncio
            elapsed = 0.0
            while elapsed < poll_timeout:
                logger.info("Polling lyrics for items: %s", item_ids)
                results = await self.query_lyrics(item_ids)
                logger.info("Polling results: %s", results)
                if results:
                    item = results[0]
                    if item is None:
                        logger.warning("First result item is None")
                        continue
                    status = (item.get("status") or "").lower()
                    if status == "succeeded":
                        lyrics = item.get("lyric")
                        if lyrics:
                            return str(lyrics).strip()
                    if status == "failed":
                        raise AIServiceError(f"Lyrics generation failed: {item}")

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            raise AIServiceError(f"Lyrics generation timed out after {poll_timeout}s")
        except AIServiceError:
            raise
        except Exception as e:
            logger.exception("CRASH in generate_lyrics")
            raise AIServiceError(f"Unexpected crash in AI service: {str(e)}")

    async def generate_song(
        self,
        prompt: str,
        lyrics: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        instrumental: bool = False,
    ) -> dict[str, Any]:
        """Step 2: produce the vocal or instrumental track via Tempolor."""
        payload: dict[str, Any] = {
            "model": settings.AI_MUSIC_MODEL,
            "prompt": prompt,
            "callback_url": self.callback_url,
        }
        if instrumental:
            payload["instrumental"] = True
            payload["lyrics"] = ""
        else:
            payload["lyrics"] = lyrics or ""
        if duration_seconds:
            payload["duration"] = duration_seconds

        data = await self._post(SONG_PATH, payload)
        return data

    async def generate_cover(
        self,
        reference_url: str,
        new_lyrics: Optional[str] = None,
        style: Optional[str] = None,
        theme: Optional[str] = None,
    ) -> dict[str, Any]:
        """Reference-based cover/remix (tempolor-latest, 10 credits)."""
        payload: dict[str, Any] = {
            "model": settings.AI_COVER_MODEL,
            "reference_url": reference_url,
            "callback_url": self.callback_url,
        }
        if new_lyrics is not None:
            payload["lyrics"] = new_lyrics
        if style:
            payload["style"] = style
        if theme:
            payload["prompt"] = theme

        data = await self._post(COVER_PATH, payload)
        return data

    async def submit_full_track(
        self,
        theme: str,
        style: str,
        language_preset: str = "full-trilingual",
        custom_mix: Optional[str] = None,
        user_lyrics: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        callback_url: Optional[str] = None,
    ) -> None:
        """Submit a request for a full track without polling for the result."""
        if user_lyrics and user_lyrics.strip():
            lyrics = user_lyrics.strip()
        else:
            # We still need to generate lyrics synchronously as a first step
            # because the music generation requires lyrics as input.
            lyrics = await self.generate_lyrics(
                theme=theme,
                language_preset=language_preset,
                custom_mix=custom_mix,
            )

        music_prompt = (
            f"{style.capitalize()} track about {theme}. "
            f"Groovy basslines, crisp percussion, polished 44.1kHz vocals."
        )

        # Overwrite the default callback URL with the song-specific one
        original_callback = self.callback_url
        if callback_url:
            self.callback_url = callback_url

        try:
            await self.generate_song(
                prompt=music_prompt,
                lyrics=lyrics,
                duration_seconds=duration_seconds,
            )
        finally:
            self.callback_url = original_callback

    async def submit_instrumental(
        self,
        theme: str,
        style: str,
        duration_seconds: Optional[int] = None,
        callback_url: Optional[str] = None,
    ) -> None:
        """Submit an instrumental request without polling."""
        music_prompt = (
            f"Instrumental {style} track about {theme}. "
            f"Groovy basslines, crisp percussion, polished 44.1kHz production."
        )

        original_callback = self.callback_url
        if callback_url:
            self.callback_url = callback_url

        try:
            await self.generate_song(
                prompt=music_prompt,
                instrumental=True,
                duration_seconds=duration_seconds,
            )
        finally:
            self.callback_url = original_callback

    async def submit_cover(
        self,
        reference_url: str,
        new_lyrics: Optional[str] = None,
        style: Optional[str] = None,
        theme: Optional[str] = None,
        callback_url: Optional[str] = None,
    ) -> None:
        """Submit a cover request without polling."""
        original_callback = self.callback_url
        if callback_url:
            self.callback_url = callback_url

        try:
            await self.generate_cover(
                reference_url=reference_url,
                new_lyrics=new_lyrics,
                style=style,
                theme=theme,
            )
        finally:
            self.callback_url = original_callback

    async def submit_stems(
        self,
        audio_url: str,
        model: str,
    ) -> list[str]:
        """Kick off a stem-separation job. Returns the list of item_ids we need to poll."""
        payload = {
            "url": audio_url,
            "callback_url": self.callback_url,
            "model": model,
        }
        data = await self._post(STEMS_PATH, payload)
        ids = data.get("item_ids") or data.get("item_id") or data.get("id")
        if isinstance(ids, str):
            ids = [ids]
        if not ids:
            raise AIServiceError(
                f"Stems submit returned no item_ids: {data}"
            )
        return list(ids)

    async def query_stems(
        self,
        item_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Poll for the results of a stem-separation job."""
        if not item_ids:
            return []
        payload = {"item_ids": item_ids[:10]}  # Tempolor caps at 10 per query
        data = await self._post(STEMS_QUERY_PATH, payload)

        # Robust navigation: data -> data -> stems (following the lyrics pattern)
        data_content = data.get("data") if isinstance(data, dict) else None
        stems_list = data_content.get("stems", []) if isinstance(data_content, dict) else []

        if isinstance(stems_list, dict):
            stems_list = [stems_list]

        # Filter out None values to prevent crashes in the generate_stems polling loop
        return [item for item in stems_list if item is not None]

    async def generate_stems(
        self,
        audio_url: str,
        model: Optional[str] = None,
        poll_interval: float = 5.0,
        poll_timeout: float = 600.0,
    ) -> dict[str, Any]:
        """Submit a stems job, poll until done, and return the final payload.

        Returns a dict like:
          {"model": "Stems v2", "stems": {"vocals": "https://...", "drums": "...", ...},
           "item_id": "...", "raw": {...}}
        For 8-stem (Stems v3) jobs the dict will include all 8 stem keys.
        """
        model = model or settings.AI_STEMS_MODEL
        if model not in ("Stems v2", "Stems v3"):
            raise AIServiceError(f"Unsupported stems model: {model}")

        item_ids = await self.submit_stems(audio_url=audio_url, model=model)
        item_id = item_ids[0]

        elapsed = 0.0
        while elapsed < poll_timeout:
            items = await self.query_stems(item_ids)
            item = next((i for i in items if i.get("item_id") == item_id), items[0] if items else None)
            if not item:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                continue

            status = (item.get("status") or "").lower()
            if status == "succeeded":
                # Tempolor returns a single `stems_url` (zip of all stems) in the
                # docs summary — but in practice each item can carry per-stem
                # URLs. We surface both shapes.
                stems_url = item.get("stems_url")
                stems_map: dict[str, str] = {}
                for key in (
                    "vocals",
                    "drums",
                    "bass",
                    "other",
                    "lead_vocals",
                    "dry_vocals",
                    "backing_vocals",
                    "guitar",
                    "piano",
                    "instruments",
                ):
                    url = item.get(f"{key}_url") or item.get(key)
                    if isinstance(url, str) and url.startswith("http"):
                        stems_map[key] = url
                return {
                    "model": model,
                    "item_id": item_id,
                    "stems_url": stems_url,
                    "stems": stems_map,
                    "raw": item,
                }
            if status == "failed":
                raise AIServiceError(f"Stems job failed: {item}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise AIServiceError(f"Stems job timed out after {poll_timeout}s")


# Singleton
ai_service = AIService()
