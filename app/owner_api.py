"""The restaurant owner's API (mounted at /owner by app/main.py).

Every request carries the owner's Supabase access token (`Authorization: Bearer`).
We validate it by asking Supabase Auth itself (`auth.get_user`) — no signing keys
or JWT secrets to manage here, and it keeps working whichever signing scheme the
project uses. Validated tokens are remembered for a minute so editing a menu
doesn't cost an auth round-trip per click.

Authorization is per restaurant: the logged-in user must be a member of the
restaurant in the URL (menu and settings edits need owner or manager; reading
orders and closing requests is open to staff too). All writes then go through
app/menu/service.py, which re-embeds only what changed and invalidates caches.
"""
import re
import threading
import time

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app import db
from app.menu import repository, service
from app.menu.snapshot import menu_cache

router = APIRouter(prefix="/owner", tags=["owner"])

_TOKEN_TTL_SECONDS = 60
_tokens: dict[str, tuple[str, float]] = {}
_tokens_lock = threading.Lock()

EDITOR_ROLES = {"owner", "manager"}


def current_user_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Log in to continue")
    token = authorization.split(" ", 1)[1].strip()
    now = time.monotonic()
    with _tokens_lock:
        cached = _tokens.get(token)
        if cached and cached[1] > now:
            return cached[0]
    client = db.get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase isn't configured on the backend")
    try:
        user = client.auth.get_user(token).user
    except Exception:
        user = None
    if user is None:
        raise HTTPException(status_code=401, detail="Your session has expired — log in again")
    with _tokens_lock:
        _tokens[token] = (user.id, now + _TOKEN_TTL_SECONDS)
        if len(_tokens) > 500:
            for stale in [t for t, (_, exp) in _tokens.items() if exp <= now]:
                _tokens.pop(stale, None)
    return user.id


def _restaurant_for(user_id: str, restaurant_id: str, editor: bool = False) -> dict:
    """The restaurant row, if `user_id` belongs to it (404 otherwise — don't reveal which ids exist)."""
    role = repository.user_role(user_id, restaurant_id)
    if role is None or (editor and role not in EDITOR_ROLES):
        raise HTTPException(status_code=404, detail="Restaurant not found")
    restaurant = repository.get_restaurant(restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return restaurant


# ------------------------------------------------------------------ payloads --


class VariantIn(BaseModel):
    name: str
    price: float


class DishIn(BaseModel):
    name: str | None = None
    category: str | None = None
    price: float | None = None
    is_veg: bool | None = None
    spice_level: str | None = None
    is_available: bool | None = None
    image_url: str | None = None
    short_description: str | None = None
    long_description: str | None = None
    ingredients: list[str] | None = None
    allergens: list[str] | None = None
    tags: list[str] | None = None
    variants: list[VariantIn] | None = None
    pos_item_id: str | None = None
    sort_order: int | None = None
    knowledge_status: str | None = None


class RestaurantIn(BaseModel):
    name: str
    slug: str | None = None
    cuisine: str | None = None
    starter_menu: bool = False


class RestaurantPatch(BaseModel):
    name: str | None = None
    cuisine: str | None = None
    tagline: str | None = None
    agent_name: str | None = None
    accent_color: str | None = None
    status: str | None = None


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "restaurant"


def _payload(dish: DishIn) -> dict:
    return dish.model_dump(exclude_unset=True)


# ----------------------------------------------------------------- endpoints --


@router.get("/restaurants")
def my_restaurants(user_id: str = Depends(current_user_id)) -> dict:
    return {"restaurants": repository.list_restaurants_for_user(user_id)}


@router.post("/restaurants")
def create_restaurant(body: RestaurantIn, user_id: str = Depends(current_user_id)) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Give the restaurant a name")
    base = _slugify(body.slug or name)
    restaurant = None
    for attempt in range(1, 8):
        slug = base if attempt == 1 else f"{base}-{attempt}"
        if repository.get_restaurant_by_slug(slug):
            continue
        restaurant = repository.create_restaurant(user_id, name, slug, (body.cuisine or "").strip() or None)
        break
    if restaurant is None:
        raise HTTPException(status_code=409, detail="That web address is taken — try another name")
    imported = None
    if body.starter_menu:
        from app.seed_restaurants import load_starter_menu

        starter = load_starter_menu()
        service.ensure_categories(restaurant, starter["categories"])
        imported = service.bulk_upsert_dishes(restaurant, starter["dishes"], source="starter")
    return {"restaurant": restaurant, "imported": imported}


@router.patch("/restaurants/{restaurant_id}")
def update_restaurant(restaurant_id: str, body: RestaurantPatch, user_id: str = Depends(current_user_id)) -> dict:
    restaurant = _restaurant_for(user_id, restaurant_id, editor=True)
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if fields.get("status") not in (None, "draft", "live"):
        raise HTTPException(status_code=422, detail="status must be 'draft' or 'live'")
    updated = repository.update_restaurant(restaurant_id, fields)
    repository.bump_menu_version(restaurant_id)
    menu_cache.invalidate(restaurant["slug"])
    return {"restaurant": updated}


@router.get("/restaurants/{restaurant_id}/menu")
def get_menu(restaurant_id: str, user_id: str = Depends(current_user_id)) -> dict:
    restaurant = _restaurant_for(user_id, restaurant_id)
    return {"restaurant": restaurant, **service.menu_for_owner(restaurant_id)}


@router.post("/restaurants/{restaurant_id}/dishes")
def create_dish(restaurant_id: str, body: DishIn, user_id: str = Depends(current_user_id)) -> dict:
    restaurant = _restaurant_for(user_id, restaurant_id, editor=True)
    try:
        return service.save_dish(restaurant, None, _payload(body))
    except service.MenuValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/restaurants/{restaurant_id}/dishes/{dish_id}")
def update_dish(restaurant_id: str, dish_id: str, body: DishIn, user_id: str = Depends(current_user_id)) -> dict:
    restaurant = _restaurant_for(user_id, restaurant_id, editor=True)
    try:
        return service.save_dish(restaurant, dish_id, _payload(body))
    except service.MenuValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Dish not found") from exc


@router.delete("/restaurants/{restaurant_id}/dishes/{dish_id}")
def delete_dish(restaurant_id: str, dish_id: str, user_id: str = Depends(current_user_id)) -> dict:
    restaurant = _restaurant_for(user_id, restaurant_id, editor=True)
    service.delete_dish(restaurant, dish_id)
    return {"deleted": dish_id}


@router.post("/restaurants/{restaurant_id}/embeddings/sync")
def sync_embeddings(restaurant_id: str, user_id: str = Depends(current_user_id)) -> dict:
    restaurant = _restaurant_for(user_id, restaurant_id, editor=True)
    return service.sync_restaurant_embeddings(restaurant)


@router.get("/restaurants/{restaurant_id}/orders")
def list_orders(restaurant_id: str, user_id: str = Depends(current_user_id)) -> dict:
    _restaurant_for(user_id, restaurant_id)
    return {"orders": repository.list_orders(restaurant_id)}


@router.get("/restaurants/{restaurant_id}/requests")
def list_requests(restaurant_id: str, user_id: str = Depends(current_user_id)) -> dict:
    _restaurant_for(user_id, restaurant_id)
    return {"requests": repository.list_requests(restaurant_id)}


@router.post("/restaurants/{restaurant_id}/requests/{request_id}/resolve")
def resolve_request(restaurant_id: str, request_id: str, user_id: str = Depends(current_user_id)) -> dict:
    _restaurant_for(user_id, restaurant_id)
    updated = repository.resolve_request(restaurant_id, request_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return updated
