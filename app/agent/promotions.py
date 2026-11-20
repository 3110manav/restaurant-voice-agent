"""What the owner chose to push, and the switches that decide whether the waiter does.

Set in the owner console and stored on the restaurant (suggest_pairings, promote_bestsellers, promote_new_items)
and on each dish (is_bestseller, is_new, promo_note); see supabase/migrations/007_owner_promotions.sql. All three
switches are on until the owner turns one off, and a restaurant row from before the migration behaves the same.

Everything the agent sees goes through `featured_of`, so a switch that is off hides the flag from the waiter
entirely: it can't recommend what it can't see.
"""
from dataclasses import dataclass

MAX_PICKS_IN_PROMPT = 8  # a long list of "favourites" is no longer a recommendation
MAX_NOTE = 200


@dataclass(frozen=True)
class Promotions:
    pairings: bool = True
    bestsellers: bool = True
    new_items: bool = True

    @property
    def any(self) -> bool:
        return self.pairings or self.bestsellers or self.new_items


def settings(restaurant: dict | None) -> Promotions:
    r = restaurant or {}
    return Promotions(
        pairings=r.get("suggest_pairings") is not False,
        bestsellers=r.get("promote_bestsellers") is not False,
        new_items=r.get("promote_new_items") is not False,
    )


def featured_of(dish: dict, setting: Promotions) -> list[str]:
    """Why this dish is being pushed right now: "new" and/or "bestseller", only for the switches that are on."""
    out = []
    if dish.get("is_new") and setting.new_items:
        out.append("new")
    if dish.get("is_bestseller") and setting.bestsellers:
        out.append("bestseller")
    return out


def label(dish: dict) -> str:
    """A short marker for a dish in a search result, or ''."""
    featured = dish.get("featured") or []
    if "new" in featured:
        return " [NEW on the menu]"
    if "bestseller" in featured:
        return " [bestseller]"
    return ""


def prompt_block(menu: list[dict]) -> str:
    """The owner's picks for the waiter's prompt, or '' when nothing is being pushed."""
    available = [d for d in menu if d.get("featured") and d.get("is_available", True)]
    new = [d for d in available if "new" in d["featured"]]
    best = [d for d in available if "bestseller" in d["featured"] and "new" not in d["featured"]]
    lines = []
    if best:
        names = ", ".join(d["name"] for d in best[:MAX_PICKS_IN_PROMPT])
        lines.append(
            f"Bestsellers (the owner's picks): {names}. When a guest asks what is good, what to try, or for a "
            "recommendation, lead with the ones that suit what they said (veg or not, spice, mood). Never call "
            "any other dish a bestseller."
        )
    if new:
        for d in new[:MAX_PICKS_IN_PROMPT]:
            note = f" The owner's note: {d['promo_note']}" if d.get("promo_note") else ""
            lines.append(
                f"New on the menu: {d['name']}.{note} Mention it once, naturally, when it fits what the guest is "
                "choosing or when they ask what is new. If they pass on it, do not bring it up again."
            )
    if not lines:
        return ""
    return "\n\nThe owner's picks for today:\n" + "\n".join(lines)
