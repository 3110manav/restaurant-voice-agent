"""Restaurant onboarding for POS integrations (mounted at /admin/pos, X-Admin-Key only).

Onboarding a Petpooja restaurant = pick an existing restaurant or create a new (draft) one, paste the restID /
mapping code and the app key, app secret and access token from Petpooja's Configuration page. The credentials are
encrypted before they are stored and are never sent back: responses only carry their last 4 characters. A webhook
token is generated and shown ONCE, together with what to paste into Petpooja's webhook configuration.
"""
import os
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from app import db
from app.admin_auth import require_admin
from app.menu import repository as menu_repository
from app.pos import crypto, repository

router = APIRouter(prefix="/admin/pos", tags=["admin-pos"], dependencies=[Depends(require_admin)])

Provider = Literal["petpooja"]
Environment = Literal["sandbox", "production"]
Status = Literal["draft", "menu_synced", "live", "paused"]

_POS_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
_SECRET_RE = re.compile(r"^\S{8,512}$")


def _check_pos_id(v: str) -> str:
    v = v.strip()
    if not _POS_ID_RE.match(v):
        raise ValueError("restID / mapping code should be 3-64 letters, digits, - or _")
    return v


def _check_secret(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not _SECRET_RE.match(value):
        raise ValueError(f"{label} looks wrong: it should be 8-512 characters with no spaces")
    return value


class NewRestaurant(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    cuisine: str | None = Field(default=None, max_length=80)
    owner_email: str | None = Field(default=None, max_length=200)


class OnboardIn(BaseModel):
    restaurant_id: str | None = None
    new_restaurant: NewRestaurant | None = None
    provider: Provider = "petpooja"
    environment: Environment
    pos_restaurant_id: str
    app_key: str
    app_secret: str
    access_token: str
    notes: str = Field(default="", max_length=500)

    @field_validator("pos_restaurant_id")
    @classmethod
    def _pos_id(cls, v: str) -> str:
        return _check_pos_id(v)

    @field_validator("app_key", "app_secret", "access_token")
    @classmethod
    def _secret(cls, v: str, info) -> str:
        return _check_secret(v, info.field_name.replace("_", " "))

    @model_validator(mode="after")
    def _one_restaurant(self):
        if bool(self.restaurant_id) == bool(self.new_restaurant):
            raise ValueError("Pick an existing restaurant or describe a new one (not both)")
        return self


class IntegrationPatch(BaseModel):
    pos_restaurant_id: str | None = None
    status: Status | None = None
    notes: str | None = Field(default=None, max_length=500)
    app_key: str | None = None
    app_secret: str | None = None
    access_token: str | None = None

    @field_validator("pos_restaurant_id")
    @classmethod
    def _pos_id(cls, v: str | None) -> str | None:
        return _check_pos_id(v) if v is not None else None

    @field_validator("app_key", "app_secret", "access_token")
    @classmethod
    def _secret(cls, v: str | None, info) -> str | None:
        return _check_secret(v or None, info.field_name.replace("_", " "))


# ------------------------------------------------------------------- helpers --


def _webhook_setup(provider: str, token: str | None) -> dict:
    """What to paste into the POS's webhook configuration. The inbound endpoints themselves arrive in part 2."""
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    return {
        "base_url": f"{base}/pos/{provider}/" if base else None,
        "base_url_missing": not base,
        "client_authorization": f"Bearer {token}" if token else None,
    }


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "restaurant"


def _create_restaurant(new: NewRestaurant) -> tuple[dict, str | None]:
    base = _slugify(new.name)
    for attempt in range(1, 8):
        slug = base if attempt == 1 else f"{base}-{attempt}"
        if menu_repository.get_restaurant_by_slug(slug):
            continue
        # Draft: not served to customers until it has a menu and someone switches it live.
        restaurant = menu_repository.insert_restaurant(
            {"slug": slug, "name": new.name.strip(), "cuisine": (new.cuisine or "").strip() or None, "status": "draft"}
        )
        break
    else:
        raise HTTPException(status_code=409, detail="Couldn't find a free web address for that name")
    owner_note = None
    if new.owner_email:
        from app.seed_restaurants import find_user_id

        user_id = find_user_id(new.owner_email.strip())
        if user_id:
            menu_repository.add_member(restaurant["id"], user_id, "owner")
        else:
            owner_note = f"No account for {new.owner_email} yet: they can sign up and be added as owner later"
    return restaurant, owner_note


def _require_crypto() -> None:
    if not crypto.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Set POS_ENCRYPTION_KEY on the API first (generate one with `python -m app.pos.crypto`)",
        )


def _require_db() -> None:
    if not db.is_configured():
        raise HTTPException(status_code=503, detail="Supabase isn't configured on the backend")


# ----------------------------------------------------------------- endpoints --


@router.get("/overview")
def overview() -> dict:
    _require_db()
    restaurants = (
        db.get_client().table("restaurants").select("id, name, slug, status").order("name").execute().data
    )
    return {
        "restaurants": restaurants,
        "integrations": repository.list_integrations(),
        "encryption_ready": crypto.is_configured(),
        "public_base_url_set": bool(os.environ.get("PUBLIC_BASE_URL")),
    }


@router.post("/integrations")
def onboard(body: OnboardIn) -> dict:
    _require_db()
    _require_crypto()
    owner_note = None
    if body.restaurant_id:
        restaurant = menu_repository.get_restaurant(body.restaurant_id)
        if restaurant is None:
            raise HTTPException(status_code=404, detail="No such restaurant")
    else:
        restaurant, owner_note = _create_restaurant(body.new_restaurant)
    try:
        integration, token = repository.create_integration(
            restaurant_id=restaurant["id"],
            provider=body.provider,
            environment=body.environment,
            pos_restaurant_id=body.pos_restaurant_id,
            secrets_in={"app_key": body.app_key, "app_secret": body.app_secret, "access_token": body.access_token},
            notes=body.notes.strip(),
        )
    except repository.DuplicateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "integration": integration,
        "webhook": _webhook_setup(body.provider, token),
        "owner_note": owner_note,
    }


@router.patch("/integrations/{integration_id}")
def update(integration_id: str, body: IntegrationPatch) -> dict:
    _require_db()
    data = body.model_dump(exclude_unset=True)
    secrets_in = {k: data.pop(k) for k in repository.SECRET_FIELDS if data.get(k)}
    for k in repository.SECRET_FIELDS:
        data.pop(k, None)  # an empty secret field means "keep the saved one"
    if "notes" in data:
        data["notes"] = (data["notes"] or "").strip()
    data = {k: v for k, v in data.items() if v is not None}
    if secrets_in:
        _require_crypto()
    try:
        integration = repository.update_integration(integration_id, data, secrets_in)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except repository.DuplicateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"integration": integration}


@router.post("/integrations/{integration_id}/webhook-token")
def rotate_webhook_token(integration_id: str) -> dict:
    _require_db()
    try:
        integration, token = repository.rotate_webhook_token(integration_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"integration": integration, "webhook": _webhook_setup(integration["provider"], token)}


@router.get("/integrations/{integration_id}/events")
def events(integration_id: str) -> dict:
    _require_db()
    return {"events": repository.list_events(integration_id)}
