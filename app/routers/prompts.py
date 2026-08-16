"""Curated Naija prompt presets — public, no auth, no credits."""
from fastapi import APIRouter

from app.prompts import NAIJA_PRESETS, get_preset
from app.schemas.schemas import PromptPresetListResponse, PromptPresetRead

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get(
    "/presets",
    response_model=PromptPresetListResponse,
    summary="List curated Naija prompt presets (Lagos Night Drive, Anambra Wedding, etc.)",
)
async def list_presets() -> PromptPresetListResponse:
    return PromptPresetListResponse(
        items=[PromptPresetRead(**p) for p in NAIJA_PRESETS]
    )


@router.get(
    "/presets/{key}",
    response_model=PromptPresetRead,
    summary="Fetch a single preset by key",
)
async def get_preset_by_key(key: str) -> PromptPresetRead:
    preset = get_preset(key)
    if preset is None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")
    return PromptPresetRead(**preset)
