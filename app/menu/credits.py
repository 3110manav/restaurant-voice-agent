"""Who to credit for the dish photos currently on a restaurant's menu.

Openly licensed photos (CC BY and similar) must be credited where they are shown. The credit for
each photo is written to app/data/images/credits.json when app/menu_images.py saves it; this module
reads that file back for the restaurant page's "Photo credits" list. An entry only counts while the
dish still shows that same photo, so an owner replacing a photo with their own drops the old credit.
"""
import json
from pathlib import Path

CREDITS_FILE = Path(__file__).parent.parent / "data" / "images" / "credits.json"


def _load() -> dict:
    try:
        return json.loads(CREDITS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def photo_credits(slug: str, dishes: list[dict]) -> list[dict]:
    entries = _load().get(slug, {})
    credits = []
    for dish in dishes:
        entry = entries.get(dish["name"])
        if entry and dish.get("image_url") and entry.get("image_url") == dish["image_url"]:
            credits.append(
                {
                    "dish": dish["name"],
                    "credit": entry["credit"],
                    "license": entry.get("license"),
                    "license_url": entry.get("license_url"),
                    "page": entry.get("page"),
                }
            )
    return credits
