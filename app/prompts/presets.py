"""Curated Naija prompt presets.

One-click starting points for the frontend — a single POST /prompts/presets call
returns this list and the user picks one instead of typing a theme from scratch.
"""
from __future__ import annotations

from typing import TypedDict


class PromptPreset(TypedDict):
    key: str
    title: str
    theme: str
    style: str
    language_preset: str
    description: str


NAIJA_PRESETS: list[PromptPreset] = [
    {
        "key": "lagos-night-drive",
        "title": "Lagos Night Drive",
        "theme": "rolling through Lekki at 1am with friends, palm-tree lights, "
        "bass-thumping, the city that never sleeps",
        "style": "afro-fusion",
        "language_preset": "pidgin-heavy",
        "description": "Late-night cruise anthem, warm 808s, singalong chorus.",
    },
    {
        "key": "anambra-wedding-banger",
        "title": "Anambra Wedding Banger",
        "theme": "a massive Igbo wedding celebration, money spray, dance floor "
        "on fire, the bride's entrance",
        "style": "highlife",
        "language_preset": "igbo-yoruba",
        "description": "Traditional highlife with brass, ululations, and "
        "modern afrobeats bounce.",
    },
    {
        "key": "aba-market-riddim",
        "title": "Aba Market Riddim",
        "theme": "the chaos and commerce of Ariaria International Market, "
        "traders calling, bargaining, hustler energy",
        "style": "gqom-afro",
        "language_preset": "pidgin-heavy",
        "description": "Hard percussive riddim, raw vocal chants, street energy.",
    },
    {
        "key": "sokoto-prayer-song",
        "title": "Sokoto Prayer Song",
        "theme": "a Friday morning call to prayer over the rooftops of Sokoto, "
        "spiritual yearning, gratitude, hope",
        "style": "afro-spiritual",
        "language_preset": "hausa-fusion",
        "description": "Soothing Hausa vocals with gentle kora and calabash percussion.",
    },
    {
        "key": "yaba-mentor-advice",
        "title": "Yaba Mentor Advice",
        "theme": "an older brother in Yaba tech hub giving raw life advice to "
        "a younger one trying to make it, hustle and grace",
        "style": "street-hop",
        "language_preset": "pidgin-heavy",
        "description": "Gritty storytelling verses, soulful hook, conversational tone.",
    },
    {
        "key": "eko-street-romance",
        "title": "Eko Street Romance",
        "theme": "falling in love on the streets of Lagos Island, first touch, "
        "Surulere sunsets, late-night suya dates",
        "style": "afro-rnb",
        "language_preset": "full-trilingual",
        "description": "Smooth afrobeats with R&B harmonies and a romantic bridge.",
    },
    {
        "key": "naija-diaspora-homesick",
        "title": "Diaspora Homesick",
        "theme": "a Nigerian abroad missing home — jollof rice, family WhatsApp "
        "calls, the airport reunion, longing",
        "style": "alté",
        "language_preset": "english-only",
        "description": "Atmospheric alté production, emotional vocals, nostalgic.",
    },
    {
        "key": "abuja-night-club",
        "title": "Abuja Night Club",
        "theme": "Wuse 2 nightclub, strobe lights, Hennessy, the DJ drops a "
        "banger, the floor goes up",
        "style": "amapiano",
        "language_preset": "pidgin-heavy",
        "description": "Log-drum amapiano bounce, chant-worthy hook, club energy.",
    },
    {
        "key": "kano-wedding-farmer",
        "title": "Kano Wedding Praise",
        "theme": "a Kano walima celebration, family pride, drums and praise "
        "for the bride and groom",
        "style": "hausa-pop",
        "language_preset": "hausa-fusion",
        "description": "Vibrant Hausa vocals, talking drum, modern pop production.",
    },
    {
        "key": "ph-city-gospel",
        "title": "Port Harcourt Gospel Lift",
        "theme": "testimony after struggle, giving God the glory, Ph City "
        "gospel choir energy",
        "style": "afro-gospel",
        "language_preset": "pidgin-heavy",
        "description": "Live choir, uplifting tempo, call-and-response chorus.",
    },
]


def get_preset(key: str) -> PromptPreset | None:
    for p in NAIJA_PRESETS:
        if p["key"] == key:
            return p
    return None
