"""Curated language_mix presets.

Each preset expands to a freeform mix string that goes into the lyrics prompt,
plus an optional style hint that nudges the model toward the right register.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional


class LanguagePreset(str, Enum):
    FULL_TRILINGUAL = "full-trilingual"
    IGBO_YORUBA = "igbo-yoruba"
    PIDGIN_HEAVY = "pidgin-heavy"
    HAUSA_FUSION = "hausa-fusion"
    ENGLISH_ONLY = "english-only"
    CUSTOM = "custom"


_PRESETS: dict[str, dict[str, str]] = {
    LanguagePreset.FULL_TRILINGUAL: {
        "mix": "English, Igbo, Yoruba, Hausa",
        "hint": "Modern afrobeats with seamless code-switching across all four languages",
    },
    LanguagePreset.IGBO_YORUBA: {
        "mix": "Igbo, Yoruba, English",
        "hint": "Eastern/Western Nigerian street-hop with traditional Igbo and Yoruba chants",
    },
    LanguagePreset.PIDGIN_HEAVY: {
        "mix": "Nigerian Pidgin, English",
        "hint": "Pidgin-dominant street-hop with English hooks, conversational tone",
    },
    LanguagePreset.HAUSA_FUSION: {
        "mix": "Hausa, English",
        "hint": "Northern Nigerian sound with Hausa phrases and modern afrobeats production",
    },
    LanguagePreset.ENGLISH_ONLY: {
        "mix": "English",
        "hint": "Mainstream afrobeats/afro-fusion, English-only vocals",
    },
    LanguagePreset.CUSTOM: {
        "mix": "English, Igbo, Yoruba, Hausa",
        "hint": "",
    },
}


def resolve_language_preset(preset: str, custom_mix: Optional[str] = None) -> dict[str, str]:
    """Expand a preset key into {mix, hint}. Falls back to FULL_TRILINGUAL."""
    entry = _PRESETS.get(preset)
    if entry is None:
        entry = _PRESETS[LanguagePreset.FULL_TRILINGUAL]
    out = dict(entry)
    if preset == LanguagePreset.CUSTOM and custom_mix:
        out["mix"] = custom_mix
    return out
