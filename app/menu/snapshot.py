"""In-memory menu snapshots: how the agent reads a restaurant's menu.

A `RestaurantMenu` is an immutable copy of one restaurant's dishes. It answers
everything the agent's tools ask — lookup by name, by id, listing, "explain this
dish" — from memory, with zero network calls; only semantic search touches the
network (one cached query embedding plus one Supabase vector query).

Name lookup is a ladder, cheapest first: exact → dish name contained in what was
said → a unique substring → fuzzy match (Whisper hears "butter chiken", "garlic
nan"). Anything ambiguous returns None from `find_by_name` and the candidates from
`candidates`, so the agent asks "Margherita Classic or Double Cheese Margherita?"
instead of silently picking one.

`MenuCache` keeps one snapshot per restaurant and re-checks `menu_version` (one
cheap read) at most every few seconds, so an owner's edit shows up for guests
almost immediately, on any backend instance. `LiveMenu` is the handle an agent
session actually holds: it resolves to the current snapshot on every call, so a
session that started before an edit still sees the edit.

The dish dict shape deliberately matches the legacy JSON-catalog items
(`veg`, `description`, `spice_level`, ...) so app/agent/tools.py works on both.
"""
import logging
import re
import threading
import time

from rapidfuzz import fuzz, process

from app.menu import embedding, repository

logger = logging.getLogger("sarthi.menu")

FUZZY_CUTOFF = 85
VERSION_CHECK_SECONDS = 15


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def dish_from_row(row: dict, category_names: dict[str, str]) -> dict:
    variants = sorted(row.get("dish_variants") or [], key=lambda v: v.get("sort_order", 0))
    return {
        "id": row["id"],
        "name": row["name"],
        "category": category_names.get(row.get("category_id"), "Menu"),
        "price": float(row["price"]),
        "veg": row["is_veg"],
        "spice_level": row.get("spice_level"),
        "description": row.get("short_description") or "",
        "long_description": row.get("long_description") or "",
        "ingredients": row.get("ingredients") or [],
        "allergens": row.get("allergens") or [],
        "tags": row.get("tags") or [],
        "variants": [{"name": v["name"], "price": float(v["price"])} for v in variants],
        "is_available": row["is_available"],
        "image_url": row.get("image_url"),
        "knowledge_status": row.get("knowledge_status", "missing"),
        "sort_order": row.get("sort_order", 0),
    }


class RestaurantMenu:
    def __init__(self, restaurant: dict, categories: list[dict], dishes: list[dict], version: int):
        self.restaurant = restaurant
        self.version = version
        self.category_order = [c["name"] for c in categories]
        rank = {name: i for i, name in enumerate(self.category_order)}
        self.menu = sorted(dishes, key=lambda d: (rank.get(d["category"], 999), d["sort_order"], d["name"]))
        self.by_id = {d["id"]: d for d in self.menu}
        self._norm_names = [_norm(d["name"]) for d in self.menu]

    @property
    def categories(self) -> list[str]:
        return [c for c in self.category_order if any(d["category"] == c for d in self.menu)]

    def get(self, item_id: str) -> dict | None:
        return self.by_id.get(item_id)

    def candidates(self, name: str, limit: int = 4) -> list[dict]:
        """Dishes `name` could plausibly mean, best first (empty if nothing is close)."""
        q = _norm(name)
        if not q:
            return []
        subs = [d for d, n in zip(self.menu, self._norm_names) if q in n]
        if subs:
            return subs[:limit]
        found = process.extract(q, self._norm_names, scorer=fuzz.WRatio, limit=limit, score_cutoff=FUZZY_CUTOFF)
        return [self.menu[idx] for _, _, idx in found]

    def find_by_name(self, name: str) -> dict | None:
        """The one dish `name` unambiguously means, or None."""
        q = _norm(name)
        if not q:
            return None
        for d, n in zip(self.menu, self._norm_names):
            if n == q:
                return d
        # "margherita pizza large" -> the dish whose whole name appears in what was said
        contained = [(len(n), d) for d, n in zip(self.menu, self._norm_names) if n and n in q]
        if contained:
            return max(contained, key=lambda t: t[0])[1]
        subs = [d for d, n in zip(self.menu, self._norm_names) if q in n]
        if len(subs) == 1:
            return subs[0]
        if len(subs) > 1:
            return None
        found = process.extract(q, self._norm_names, scorer=fuzz.WRatio, limit=2, score_cutoff=FUZZY_CUTOFF)
        if not found:
            return None
        top_score, _, top_idx = found[0]
        if len(found) == 1 or top_score >= 92 or top_score - found[1][0] >= 6:
            return self.menu[top_idx]
        return None

    def search(self, query: str, k: int = 4) -> list[dict]:
        try:
            vector = embedding.embed_query(query)
            matches = repository.match_dishes(self.restaurant["id"], vector, k)
            dishes = [self.by_id[m["dish_id"]] for m in matches if m["dish_id"] in self.by_id]
            if dishes:
                return dishes
        except Exception:
            logger.warning("semantic search failed, falling back to keywords", exc_info=True)
        return self._keyword_search(query, k)

    def _keyword_search(self, query: str, k: int) -> list[dict]:
        tokens = [t for t in _norm(query).split() if len(t) > 2]
        if not tokens:
            return []
        scored = []
        for d in self.menu:
            if not d["is_available"]:
                continue
            haystack = _norm(
                " ".join([d["name"], d["category"], d["description"], " ".join(d["ingredients"]), " ".join(d["tags"])])
            )
            score = sum(1 for t in tokens if t in haystack)
            if score:
                scored.append((score, d))
        scored.sort(key=lambda t: -t[0])
        return [d for _, d in scored[:k]]


class MenuCache:
    def __init__(self, version_check_seconds: float = VERSION_CHECK_SECONDS):
        self._ttl = version_check_seconds
        self._entries: dict[str, tuple[RestaurantMenu, float]] = {}
        self._lock = threading.Lock()

    def get(self, slug: str) -> RestaurantMenu | None:
        now = time.monotonic()
        entry = self._entries.get(slug)
        if entry and now - entry[1] < self._ttl:
            return entry[0]
        if entry:
            current = repository.get_menu_version(entry[0].restaurant["id"])
            if current == entry[0].version:
                self._entries[slug] = (entry[0], now)
                return entry[0]
        return self._load(slug)

    def invalidate(self, slug: str) -> None:
        self._entries.pop(slug, None)

    def _load(self, slug: str) -> RestaurantMenu | None:
        with self._lock:
            restaurant = repository.get_restaurant_by_slug(slug)
            if restaurant is None:
                self._entries.pop(slug, None)
                return None
            categories, rows = repository.load_menu_rows(restaurant["id"])
            names = {c["id"]: c["name"] for c in categories}
            menu = RestaurantMenu(
                restaurant, categories, [dish_from_row(r, names) for r in rows], restaurant["menu_version"]
            )
            self._entries[slug] = (menu, time.monotonic())
            return menu


menu_cache = MenuCache()


class LiveMenu:
    """The menu handle an agent session holds (see module docstring)."""

    def __init__(self, slug: str, cache: MenuCache = menu_cache):
        self.slug = slug
        self._cache = cache

    def _current(self) -> RestaurantMenu:
        menu = self._cache.get(self.slug)
        if menu is None:
            raise LookupError(f"restaurant '{self.slug}' no longer exists")
        return menu

    @property
    def restaurant(self) -> dict:
        return self._current().restaurant

    @property
    def menu(self) -> list[dict]:
        return self._current().menu

    @property
    def categories(self) -> list[str]:
        return self._current().categories

    def get(self, item_id: str) -> dict | None:
        return self._current().get(item_id)

    def find_by_name(self, name: str) -> dict | None:
        return self._current().find_by_name(name)

    def candidates(self, name: str, limit: int = 4) -> list[dict]:
        return self._current().candidates(name, limit)

    def search(self, query: str, k: int = 4) -> list[dict]:
        return self._current().search(query, k)
