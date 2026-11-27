"""Storage for POS integrations (table pos_integrations, migration 013).

Everything that leaves this module through list/get is MASKED: encrypted columns and the webhook-token hash are
dropped, only the 4-character hints remain. The decrypted credentials come out of exactly one function,
get_credentials(), which the POS adapters call when they talk to Petpooja; nothing returns them to a browser.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app import db
from app.pos import crypto

SECRET_FIELDS = ("app_key", "app_secret", "access_token")
_PRIVATE_COLUMNS = {f"{f}_enc" for f in SECRET_FIELDS} | {"webhook_token_hash"}


class NotConfiguredError(RuntimeError):
    pass


class DuplicateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Credentials:
    integration_id: str
    restaurant_id: str
    provider: str
    environment: str
    pos_restaurant_id: str
    app_key: str
    app_secret: str
    access_token: str

    def __repr__(self) -> str:  # never let a log line or traceback print the secrets
        return f"Credentials({self.provider}/{self.environment} restID={self.pos_restaurant_id})"


def _c():
    client = db.get_client()
    if client is None:
        raise NotConfiguredError("Supabase isn't configured on the backend")
    return client


def _context(integration_id: str, field: str) -> str:
    return f"{integration_id}:{field}"


def _mask(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in _PRIVATE_COLUMNS}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encrypted(integration_id: str, secrets_in: dict[str, str]) -> dict:
    out: dict = {}
    for field in SECRET_FIELDS:
        if field in secrets_in:
            value = secrets_in[field].strip()
            out[f"{field}_enc"] = crypto.encrypt(value, _context(integration_id, field))
            out[f"{field}_hint"] = crypto.hint(value)
    return out


def _log(integration_id: str, kind: str, detail: dict | None = None) -> None:
    _c().table("pos_integration_events").insert(
        {"integration_id": integration_id, "kind": kind, "detail": detail or {}}
    ).execute()


def _is_unique_violation(exc: Exception) -> bool:
    text = str(exc)
    return "23505" in text or "duplicate key" in text


# --------------------------------------------------------------------- reads --


def list_integrations() -> list[dict]:
    rows = (
        _c().table("pos_integrations")
        .select("*, restaurants(id, name, slug)")
        .order("created_at", desc=True)
        .execute()
        .data
    )
    return [_mask(r) for r in rows]


def get_integration(integration_id: str) -> dict | None:
    rows = (
        _c().table("pos_integrations").select("*, restaurants(id, name, slug)")
        .eq("id", integration_id).limit(1).execute().data
    )
    return _mask(rows[0]) if rows else None


def list_events(integration_id: str, limit: int = 50) -> list[dict]:
    return (
        _c().table("pos_integration_events").select("kind, detail, created_at")
        .eq("integration_id", integration_id).order("created_at", desc=True).limit(limit).execute().data
    )


def find_by_pos_restaurant(provider: str, pos_restaurant_id: str, environment: str | None = None) -> dict | None:
    """How an inbound webhook finds its restaurant (masked row, plus the token hash for verifying the caller)."""
    query = (
        _c().table("pos_integrations").select("*")
        .eq("provider", provider).eq("pos_restaurant_id", pos_restaurant_id.strip())
    )
    if environment:
        query = query.eq("environment", environment)
    rows = query.execute().data
    if len(rows) != 1:
        return None  # none, or the same restID in sandbox AND production: the caller must say which
    row = rows[0]
    return {**_mask(row), "webhook_token_hash": row["webhook_token_hash"]}


def get_credentials(integration_id: str) -> Credentials:
    rows = _c().table("pos_integrations").select("*").eq("id", integration_id).limit(1).execute().data
    if not rows:
        raise LookupError("No such POS integration")
    row = rows[0]
    values = {f: crypto.decrypt(row[f"{f}_enc"], _context(row["id"], f)) for f in SECRET_FIELDS}
    return Credentials(
        integration_id=row["id"],
        restaurant_id=row["restaurant_id"],
        provider=row["provider"],
        environment=row["environment"],
        pos_restaurant_id=row["pos_restaurant_id"],
        **values,
    )


# -------------------------------------------------------------------- writes --


def create_integration(
    restaurant_id: str,
    provider: str,
    environment: str,
    pos_restaurant_id: str,
    secrets_in: dict[str, str],
    notes: str = "",
) -> tuple[dict, str]:
    """Saves a new integration. Returns (masked row, webhook token) — the token is never retrievable again."""
    integration_id = str(uuid.uuid4())
    token = crypto.new_webhook_token()
    row = {
        "id": integration_id,
        "restaurant_id": restaurant_id,
        "provider": provider,
        "environment": environment,
        "pos_restaurant_id": pos_restaurant_id.strip(),
        "webhook_token_hash": crypto.hash_token(token),
        "webhook_token_hint": token[-4:],
        "notes": notes,
        **_encrypted(integration_id, secrets_in),
    }
    try:
        _c().table("pos_integrations").insert(row).execute()
    except Exception as exc:
        if _is_unique_violation(exc):
            raise DuplicateError(
                f"This restaurant already has a {provider} {environment} integration, or that restID is already "
                "linked to another restaurant"
            ) from exc
        raise
    _log(integration_id, "created", {"environment": environment, "pos_restaurant_id": row["pos_restaurant_id"]})
    return get_integration(integration_id), token


def update_integration(integration_id: str, fields: dict, secrets_in: dict[str, str]) -> dict:
    update = dict(fields)
    if secrets_in:
        update.update(_encrypted(integration_id, secrets_in))
        update["credentials_updated_at"] = _now()
    if not update:
        return get_integration(integration_id)
    before = get_integration(integration_id)
    if before is None:
        raise LookupError("No such POS integration")
    update["updated_at"] = _now()
    try:
        _c().table("pos_integrations").update(update).eq("id", integration_id).execute()
    except Exception as exc:
        if _is_unique_violation(exc):
            raise DuplicateError("That restID is already linked to another restaurant") from exc
        raise
    if secrets_in:
        _log(integration_id, "credentials_rotated", {"fields": sorted(secrets_in)})
    for key in ("status", "pos_restaurant_id"):
        if key in fields and fields[key] != before.get(key):
            _log(integration_id, f"{key}_changed", {"from": before.get(key), "to": fields[key]})
    return get_integration(integration_id)


def rotate_webhook_token(integration_id: str) -> tuple[dict, str]:
    token = crypto.new_webhook_token()
    result = (
        _c().table("pos_integrations")
        .update({"webhook_token_hash": crypto.hash_token(token), "webhook_token_hint": token[-4:], "updated_at": _now()})
        .eq("id", integration_id).execute().data
    )
    if not result:
        raise LookupError("No such POS integration")
    _log(integration_id, "webhook_token_rotated")
    return get_integration(integration_id), token
