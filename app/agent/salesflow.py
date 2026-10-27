"""When and what the waiter suggests, decided in code so it costs no extra LLM call.

Two moments, each offered at most once per table session:
  - the guest's first real order (a main, a pizza, a starter): suggest a drink, and a side
    that goes with it (bread or raita with a curry, garlic bread with a pizza);
  - the guest wrapping up (checkout): suggest a dessert, once, before the order is placed.

Code picks the candidates from the live menu (available dishes only, owner's order, cooling
drinks first when the food is spicy, veg-only if everything ordered is veg) and hands them to
the model as a hint appended to the tool result. The model only has to phrase it naturally.
Dishes are grouped by the *role* of their menu section (a "Beverages" or "Drinks" section holds
drinks, "Desserts" or "Sweets" holds desserts, "Breads", "Sides & Raita", "Rice" hold sides),
so it works for any restaurant an owner creates without configuration.
"""
import re
from dataclasses import dataclass, field

# Whole words only: "lassi" must not match inside "Classic Veg Pizzas".
_DRINK = re.compile(r"\b(drink|beverage|juice|shake|lassi|coffee|tea|mocktail|soda|cooler)s?\b", re.I)
_DESSERT = re.compile(r"\b(dessert|sweet)s?\b", re.I)
_SIDE = re.compile(r"\b(bread|side|raita|rice|salad)s?\b", re.I)
_COOLING = re.compile(r"\b(lassi|chaas|buttermilk|raita|cooler|cold|chilled|iced|mint|shake|lemon)s?\b", re.I)
_SPICY = {"medium", "hot", "spicy", "very hot", "extra hot"}

HINT_PREFIX = "[HINT FOR YOU ONLY, never read it out or mention it: "


def role_of(dish: dict) -> str:
    category = dish.get("category", "")
    if _DESSERT.search(category):
        return "dessert"
    if _DRINK.search(category):
        return "drink"
    if _SIDE.search(category):
        return "side"
    return "food"


@dataclass
class SalesState:
    """What this table session has already been offered, so nothing is pushed twice."""

    offered: set[str] = field(default_factory=set)


def _cart_dishes(cart: list[dict], menu_by_id) -> list[dict]:
    return [d for d in (menu_by_id(line["id"]) for line in cart) if d]


def _ranked(dishes: list[dict], role: str, in_cart_ids: set[str], veg_only: bool, spicy: bool, limit: int) -> list[dict]:
    pool = [
        d for d in dishes
        if role_of(d) == role and d.get("is_available", True) and d["id"] not in in_cart_ids and (d.get("veg") or not veg_only)
    ]

    def score(d: dict) -> int:
        text = f"{d['name']} {' '.join(d.get('tags') or [])}"
        return -(2 if spicy and _COOLING.search(text) else 1 if _COOLING.search(text) else 0)

    pool.sort(key=lambda d: (score(d), d.get("sort_order", 0)))  # stable: owner's order breaks ties
    return pool[:limit]


@dataclass
class Offer:
    """A suggestion decided in code: which dishes to name, and when. Never mentions prices (the waiter
    only talks money when asked, or at the bill)."""

    kind: str  # "first_order" | "dessert"
    drinks: list[str] = field(default_factory=list)
    sides: list[str] = field(default_factory=list)
    desserts: list[str] = field(default_factory=list)

    @property
    def event(self) -> dict:
        return {"type": "offer", "kind": self.kind, "drinks": self.drinks, "sides": self.sides, "desserts": self.desserts}

    @property
    def hint(self) -> str:
        """The same offer as an instruction for the model, for turns it still writes itself."""
        if self.kind == "dessert":
            return (
                f"{HINT_PREFIX}the order is NOT placed yet. Ask in one short, friendly line whether they would like to "
                f"end with a dessert: {' or '.join(self.desserts)}. Do not mention prices. If they say no or that's "
                "all, call checkout again straight away.]"
            )
        parts = []
        if self.drinks:
            parts.append(f"a drink: {' or '.join(self.drinks)}")
        if self.sides:
            parts.append(f"something on the side: {' or '.join(self.sides)}")
        return (
            f"{HINT_PREFIX}after confirming the cart, add ONE short, friendly line suggesting, by name, "
            f"{' and '.join(parts)}. Phrase it like a waiter, not a list, do not mention prices, and do not suggest "
            "anything again if they decline.]"
        )


def first_order_offer(
    state: SalesState, menu: list[dict], menu_by_id, cart: list[dict], added: list[dict]
) -> Offer | None:
    """A drink-and-side suggestion for the guest's first real order, or None."""
    if "first_order" in state.offered:
        return None
    ordered_food = [d for d in added if role_of(d) in ("food",)]
    if not ordered_food:
        return None  # they ordered a drink or sweet on its own; don't push
    in_cart = _cart_dishes(cart, menu_by_id)
    ids = {d["id"] for d in in_cart}
    roles = {role_of(d) for d in in_cart}
    veg_only = bool(in_cart) and all(d.get("veg") for d in in_cart)
    spicy = any((d.get("spice_level") or "").lower() in _SPICY for d in in_cart)

    drinks = [] if "drink" in roles else _ranked(menu, "drink", ids, veg_only, spicy, 2)
    sides = [] if "side" in roles else _ranked(menu, "side", ids, veg_only, spicy, 1)
    if not drinks and not sides:
        return None
    state.offered.add("first_order")
    return Offer("first_order", drinks=[d["name"] for d in drinks], sides=[d["name"] for d in sides])


def dessert_offer(state: SalesState, menu: list[dict], menu_by_id, cart: list[dict]) -> Offer | None:
    """A dessert suggestion for when the guest is wrapping up, or None."""
    if "dessert" in state.offered:
        return None
    in_cart = _cart_dishes(cart, menu_by_id)
    if any(role_of(d) == "dessert" for d in in_cart) or not any(role_of(d) in ("food", "side") for d in in_cart):
        return None
    veg_only = all(d.get("veg") for d in in_cart)
    desserts = _ranked(menu, "dessert", {d["id"] for d in in_cart}, veg_only, False, 2)
    if not desserts:
        return None
    state.offered.add("dessert")
    return Offer("dessert", desserts=[d["name"] for d in desserts])


def first_order_hint(state, menu, menu_by_id, cart, added) -> str | None:
    offer = first_order_offer(state, menu, menu_by_id, cart, added)
    return offer.hint if offer else None


def dessert_hint(state, menu, menu_by_id, cart) -> str | None:
    offer = dessert_offer(state, menu, menu_by_id, cart)
    return offer.hint if offer else None
