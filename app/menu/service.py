"""Menu writes: validate, save, re-embed only what changed, bump the menu
version, and drop the cached snapshot.

An owner editing one dish costs one database write and — only if the dish's
semantic text changed — one embedding call. Price, availability, images and POS
ids never re-embed (see embedding.dish_embedding_text). A bulk import does the
same work once for the whole batch: many dish writes, one embedding sync, one
version bump.

Embedding is best-effort on single saves: if Gemini is rate-limited or down, the
dish is still saved and live (name lookups work immediately); `embedding_synced`
comes back False and `sync_restaurant_embeddings` catches it up later.
"""
import logging
from datetime import datetime, timezone

from app.menu import embedding, repository
from app.menu.snapshot import dish_from_row, menu_cache

logger = logging.getLogger("sarthi.menu")

SPICE_LEVELS = {"none", "mild", "medium", "hot"}
KNOWLEDGE_STATUSES = {"missing", "ai_draft", "approved"}
SOURCES = {"manual", "excel", "image", "pos", "starter"}


class MenuValidationError(ValueError):
    pass


def _clean_list(values) -> list[str]:
    return [v.strip() for v in (values or []) if isinstance(v, str) and v.strip()]


def _clean_variants(variants) -> list[dict]:
    cleaned, seen = [], set()
    for v in variants or []:
        name = (v.get("name") or "").strip()
        if not name:
            raise MenuValidationError("every size/portion needs a name")
        if name.lower() in seen:
            raise MenuValidationError(f"duplicate size '{name}'")
        seen.add(name.lower())
        price = float(v.get("price", -1))
        if price < 0:
            raise MenuValidationError(f"size '{name}' needs a price of 0 or more")
        cleaned.append({"name": name, "price": price})
    return cleaned


def validate_dish(payload: dict, partial: bool) -> dict:
    """Return only the known, validated fields of `payload`. With partial=True
    (an update), absent fields are simply left out; otherwise name and a price
    (or sizes) are required."""
    out: dict = {}
    if "name" in payload or not partial:
        name = (payload.get("name") or "").strip()
        if not name:
            raise MenuValidationError("a dish needs a name")
        out["name"] = name
    if "variants" in payload and payload["variants"] is not None:
        out["variants"] = _clean_variants(payload["variants"])
    if out.get("variants"):
        out["price"] = min(v["price"] for v in out["variants"])
    elif "price" in payload and payload["price"] is not None:
        price = float(payload["price"])
        if price < 0:
            raise MenuValidationError("price can't be negative")
        out["price"] = price
    elif not partial:
        raise MenuValidationError("a dish needs a price (or sizes with prices)")
    if "spice_level" in payload and payload["spice_level"] is not None:
        if payload["spice_level"] not in SPICE_LEVELS:
            raise MenuValidationError(f"spice level must be one of {sorted(SPICE_LEVELS)}")
        out["spice_level"] = payload["spice_level"]
    for key in ("is_veg", "is_available"):
        if key in payload and payload[key] is not None:
            out[key] = bool(payload[key])
    for key in ("short_description", "long_description", "image_url", "pos_item_id", "category"):
        if key in payload and payload[key] is not None:
            out[key] = str(payload[key]).strip()
    for key in ("ingredients", "allergens", "tags"):
        if key in payload and payload[key] is not None:
            out[key] = _clean_list(payload[key])
    if "sort_order" in payload and payload["sort_order"] is not None:
        out["sort_order"] = int(payload["sort_order"])
    if "knowledge_status" in payload and payload["knowledge_status"] is not None:
        if payload["knowledge_status"] not in KNOWLEDGE_STATUSES:
            raise MenuValidationError(f"knowledge status must be one of {sorted(KNOWLEDGE_STATUSES)}")
        out["knowledge_status"] = payload["knowledge_status"]
    return out


class _Categories:
    """name -> id for one restaurant, creating categories as dishes need them."""

    def __init__(self, restaurant_id: str):
        self.restaurant_id = restaurant_id
        self.ids = {c["name"]: c["id"] for c in repository.list_categories(restaurant_id)}

    def ensure(self, name: str) -> str:
        if name not in self.ids:
            self.ids[name] = repository.create_category(self.restaurant_id, name, len(self.ids))["id"]
        return self.ids[name]

    def names(self) -> dict[str, str]:
        return {v: k for k, v in self.ids.items()}


def _write_dish(
    restaurant_id: str, dish_id: str | None, fields: dict, categories: _Categories, source: str, status_hint: bool
) -> str:
    """Persist one dish (+ its sizes) and return its id. No embedding, no version bump."""
    fields = dict(fields)
    category_name = fields.pop("category", None)
    variants = fields.pop("variants", None)
    row = fields
    if category_name:
        row["category_id"] = categories.ensure(category_name)
    if status_hint and "long_description" in row and "knowledge_status" not in row:
        # An owner who writes (or edits) the story has reviewed it.
        row["knowledge_status"] = "approved" if row["long_description"] else "missing"
    row["updated_at"] = datetime.now(timezone.utc).isoformat()

    if dish_id is None:
        row.update(restaurant_id=restaurant_id, source=source)
        dish_id = repository.insert_dish(row)["id"]
    else:
        if repository.update_dish(restaurant_id, dish_id, row) is None:
            raise LookupError("dish not found")
    if variants is not None:
        repository.replace_variants(restaurant_id, dish_id, variants)
    return dish_id


def _dish_dicts(restaurant_id: str) -> list[dict]:
    categories, rows = repository.load_menu_rows(restaurant_id)
    names = {c["id"]: c["name"] for c in categories}
    return [dish_from_row(r, names) for r in rows]


def _sync_embeddings(restaurant_id: str, dishes: list[dict]) -> dict:
    """Embed only the dishes whose embedding text changed (or were never embedded)."""
    existing = repository.embedding_hashes(restaurant_id)
    stale = []
    for d in dishes:
        text = embedding.dish_embedding_text(d)
        h = embedding.content_hash(text)
        if existing.get(d["id"]) != h:
            stale.append((d["id"], text, h))
    if stale:
        vectors = embedding.embed_documents([t for _, t, _ in stale])
        repository.upsert_embeddings(
            [
                {
                    "dish_id": dish_id,
                    "restaurant_id": restaurant_id,
                    "embedding": vector,
                    "content_hash": h,
                    "model": embedding.EMBED_MODEL,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                for (dish_id, _, h), vector in zip(stale, vectors)
            ]
        )
    return {"embedded": len(stale), "unchanged": len(dishes) - len(stale)}


def _publish(restaurant: dict) -> None:
    repository.bump_menu_version(restaurant["id"])
    menu_cache.invalidate(restaurant["slug"])


def save_dish(restaurant: dict, dish_id: str | None, payload: dict, source: str = "manual") -> dict:
    """Create (dish_id None) or update one dish. Returns {"dish": ..., "embedding_synced": bool}."""
    fields = validate_dish(payload, partial=dish_id is not None)
    categories = _Categories(restaurant["id"])
    try:
        dish_id = _write_dish(restaurant["id"], dish_id, fields, categories, source, status_hint=True)
    except Exception as exc:
        if "duplicate key" in str(exc) and "name" in str(exc).lower():
            raise MenuValidationError(f"there's already a dish called '{fields.get('name')}'") from exc
        raise
    row = repository.get_dish(restaurant["id"], dish_id)
    dish = dish_from_row(row, categories.names())
    synced = True
    try:
        _sync_embeddings(restaurant["id"], [dish])
    except Exception:
        logger.warning("embedding sync failed for dish %s; saved without it", dish_id, exc_info=True)
        synced = False
    _publish(restaurant)
    return {"dish": dish, "embedding_synced": synced}


def delete_dish(restaurant: dict, dish_id: str) -> None:
    repository.delete_dish(restaurant["id"], dish_id)
    _publish(restaurant)


def sync_restaurant_embeddings(restaurant: dict) -> dict:
    result = _sync_embeddings(restaurant["id"], _dish_dicts(restaurant["id"]))
    _publish(restaurant)
    return result


def bulk_upsert_dishes(restaurant: dict, payloads: list[dict], source: str) -> dict:
    """Import many dishes at once (seeding, starter menus, later Excel/image
    imports). Idempotent by dish name: re-running updates in place. One embedding
    sync and one version bump for the whole batch."""
    categories = _Categories(restaurant["id"])
    written = 0
    for position, payload in enumerate(payloads):
        fields = validate_dish(payload, partial=False)
        fields.setdefault("sort_order", position)
        existing_id = repository.find_dish_id_by_name(restaurant["id"], fields["name"])
        _write_dish(restaurant["id"], existing_id, fields, categories, source, status_hint=False)
        written += 1
    result = _sync_embeddings(restaurant["id"], _dish_dicts(restaurant["id"]))
    _publish(restaurant)
    return {"written": written, **result}


def menu_for_owner(restaurant_id: str) -> dict:
    """Fresh (uncached) menu for the owner's editor, including unavailable dishes."""
    categories, rows = repository.load_menu_rows(restaurant_id)
    names = {c["id"]: c["name"] for c in categories}
    order = {c["name"]: i for i, c in enumerate(categories)}
    dishes = sorted(
        (dish_from_row(r, names) for r in rows), key=lambda d: (order.get(d["category"], 999), d["sort_order"])
    )
    return {"categories": list(order), "dishes": dishes}


def ensure_categories(restaurant: dict, names: list[str]) -> None:
    """Create categories in the given order (existing ones keep their place)."""
    categories = _Categories(restaurant["id"])
    for name in names:
        categories.ensure(name)
