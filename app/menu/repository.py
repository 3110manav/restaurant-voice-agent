"""All Supabase reads and writes for restaurants, menus and dish embeddings.

Raw rows in, raw rows out — turning them into the dish dicts the agent's tools
use is snapshot.py's job, and orchestrating a write (save + re-embed + bump the
version + drop caches) is service.py's. Calls raise if Supabase isn't
configured: unlike erp.py's best-effort order logging, a menu that can't be
read is a real failure the caller has to surface.
"""
import functools
import logging

import httpx

from app import db

logger = logging.getLogger("sarthi.menu")


def _read(fn):
    """Reads are safe to repeat, so retry one once. Supabase closes idle connections, and the
    first request on a stale one fails with a transport error (a guest's menu would not load
    after a quiet spell). Writes are deliberately not wrapped: repeating one could duplicate it."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except httpx.TransportError as exc:
            logger.info("retrying %s after %s", fn.__name__, type(exc).__name__)
            return fn(*args, **kwargs)

    return wrapper


def _c():
    client = db.get_client()
    if client is None:
        raise RuntimeError("Supabase isn't configured (SUPABASE_URL / SUPABASE_SERVICE_KEY)")
    return client


# --------------------------------------------------------------- restaurants --


@_read
def get_restaurant_by_slug(slug: str) -> dict | None:
    rows = _c().table("restaurants").select("*").eq("slug", slug).limit(1).execute().data
    return rows[0] if rows else None


@_read
def get_restaurant(restaurant_id: str) -> dict | None:
    rows = _c().table("restaurants").select("*").eq("id", restaurant_id).limit(1).execute().data
    return rows[0] if rows else None


@_read
def list_restaurant_slugs() -> list[str]:
    return [r["slug"] for r in _c().table("restaurants").select("slug").order("slug").execute().data]


@_read
def list_restaurants_for_user(user_id: str) -> list[dict]:
    members = _c().table("restaurant_members").select("restaurant_id, role").eq("user_id", user_id).execute().data
    if not members:
        return []
    roles = {m["restaurant_id"]: m["role"] for m in members}
    rows = _c().table("restaurants").select("*").in_("id", list(roles)).order("created_at").execute().data
    return [{**r, "role": roles[r["id"]]} for r in rows]


@_read
def user_role(user_id: str, restaurant_id: str) -> str | None:
    rows = (
        _c().table("restaurant_members").select("role")
        .eq("user_id", user_id).eq("restaurant_id", restaurant_id).limit(1).execute().data
    )
    return rows[0]["role"] if rows else None


def create_restaurant(owner_id: str, name: str, slug: str, cuisine: str | None) -> dict:
    result = _c().rpc(
        "create_restaurant", {"p_owner": owner_id, "p_name": name, "p_slug": slug, "p_cuisine": cuisine}
    ).execute()
    return result.data


def update_restaurant(restaurant_id: str, fields: dict) -> dict:
    return _c().table("restaurants").update(fields).eq("id", restaurant_id).execute().data[0]


@_read
def get_menu_version(restaurant_id: str) -> int | None:
    rows = _c().table("restaurants").select("menu_version").eq("id", restaurant_id).limit(1).execute().data
    return rows[0]["menu_version"] if rows else None


def bump_menu_version(restaurant_id: str) -> int:
    return _c().rpc("bump_menu_version", {"p_restaurant_id": restaurant_id}).execute().data


# ---------------------------------------------------------------------- menu --


@_read
def load_menu_rows(restaurant_id: str) -> tuple[list[dict], list[dict]]:
    """(categories, dishes) — each dish row carries its variants nested under
    `dish_variants`."""
    categories = (
        _c().table("menu_categories").select("*").eq("restaurant_id", restaurant_id)
        .order("sort_order").execute().data
    )
    dishes = (
        _c().table("dishes").select("*, dish_variants(id, name, price, sort_order)")
        .eq("restaurant_id", restaurant_id).order("sort_order").execute().data
    )
    return categories, dishes


@_read
def get_dish(restaurant_id: str, dish_id: str) -> dict | None:
    rows = (
        _c().table("dishes").select("*, dish_variants(id, name, price, sort_order)")
        .eq("restaurant_id", restaurant_id).eq("id", dish_id).limit(1).execute().data
    )
    return rows[0] if rows else None


def get_or_create_category(restaurant_id: str, name: str, sort_order: int = 0) -> str:
    rows = (
        _c().table("menu_categories").select("id")
        .eq("restaurant_id", restaurant_id).eq("name", name).limit(1).execute().data
    )
    if rows:
        return rows[0]["id"]
    created = (
        _c().table("menu_categories")
        .insert({"restaurant_id": restaurant_id, "name": name, "sort_order": sort_order}).execute().data
    )
    return created[0]["id"]


@_read
def find_dish_id_by_name(restaurant_id: str, name: str) -> str | None:
    rows = (
        _c().table("dishes").select("id").eq("restaurant_id", restaurant_id).eq("name", name).limit(1).execute().data
    )
    return rows[0]["id"] if rows else None


def insert_dish(row: dict) -> dict:
    return _c().table("dishes").insert(row).execute().data[0]


def update_dish(restaurant_id: str, dish_id: str, fields: dict) -> dict | None:
    rows = (
        _c().table("dishes").update(fields).eq("restaurant_id", restaurant_id).eq("id", dish_id).execute().data
    )
    return rows[0] if rows else None


def delete_dish(restaurant_id: str, dish_id: str) -> None:
    _c().table("dishes").delete().eq("restaurant_id", restaurant_id).eq("id", dish_id).execute()


def replace_variants(restaurant_id: str, dish_id: str, variants: list[dict]) -> None:
    _c().table("dish_variants").delete().eq("dish_id", dish_id).execute()
    if variants:
        _c().table("dish_variants").insert(
            [
                {
                    "dish_id": dish_id,
                    "restaurant_id": restaurant_id,
                    "name": v["name"],
                    "price": v["price"],
                    "sort_order": i,
                }
                for i, v in enumerate(variants)
            ]
        ).execute()


# ---------------------------------------------------------------- embeddings --


@_read
def embedding_hashes(restaurant_id: str) -> dict[str, str]:
    rows = _c().table("dish_embeddings").select("dish_id, content_hash").eq("restaurant_id", restaurant_id).execute().data
    return {r["dish_id"]: r["content_hash"] for r in rows}


def upsert_embeddings(rows: list[dict]) -> None:
    if rows:
        _c().table("dish_embeddings").upsert(rows, on_conflict="dish_id").execute()


@_read
def match_dishes(restaurant_id: str, query_vector: list[float], limit: int) -> list[dict]:
    return (
        _c().rpc("match_dishes", {"p_restaurant_id": restaurant_id, "p_query": query_vector, "p_limit": limit})
        .execute().data
    )


# ------------------------------------------------------- orders and requests --


@_read
def list_orders(restaurant_id: str, limit: int = 100) -> list[dict]:
    return (
        _c().table("orders").select("*").eq("restaurant_id", restaurant_id)
        .order("created_at", desc=True).limit(limit).execute().data
    )


@_read
def list_requests(restaurant_id: str, limit: int = 100) -> list[dict]:
    return (
        _c().table("requests").select("*").eq("restaurant_id", restaurant_id)
        .order("created_at", desc=True).limit(limit).execute().data
    )


# ------------------------------------------------------------ small helpers --


@_read
def list_categories(restaurant_id: str) -> list[dict]:
    return (
        _c().table("menu_categories").select("*").eq("restaurant_id", restaurant_id).order("sort_order").execute().data
    )


def create_category(restaurant_id: str, name: str, sort_order: int) -> dict:
    return (
        _c().table("menu_categories")
        .insert({"restaurant_id": restaurant_id, "name": name, "sort_order": sort_order}).execute().data[0]
    )


@_read
def embedding_hash(dish_id: str) -> str | None:
    rows = _c().table("dish_embeddings").select("content_hash").eq("dish_id", dish_id).limit(1).execute().data
    return rows[0]["content_hash"] if rows else None


def insert_restaurant(fields: dict) -> dict:
    return _c().table("restaurants").insert(fields).execute().data[0]


def add_member(restaurant_id: str, user_id: str, role: str = "owner") -> None:
    _c().table("restaurant_members").upsert(
        {"restaurant_id": restaurant_id, "user_id": user_id, "role": role}, on_conflict="restaurant_id,user_id"
    ).execute()


def resolve_request(restaurant_id: str, request_id: str) -> dict | None:
    from datetime import datetime, timezone

    rows = (
        _c().table("requests")
        .update({"status": "resolved", "resolved_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", request_id).eq("restaurant_id", restaurant_id).execute().data
    )
    return rows[0] if rows else None
