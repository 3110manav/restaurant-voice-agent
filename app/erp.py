"""Optional "basic ERP" persistence: writes finalized orders and ambient
service/front-desk requests to Supabase, on top of the in-memory per-session
cart/service log the agent already keeps for the conversation itself. Also
exposes reads (`list_orders`, `list_requests`, `resolve_request`) backing
the staff-facing view at /admin.

This is a no-op whenever SUPABASE_URL / SUPABASE_SERVICE_KEY aren't set, so
the agent (and its tests) work exactly as before without a Supabase project
configured — see supabase/schema.sql for the two tables this writes to, and
README.md for how to wire up a project.

Writes are best-effort: a Supabase hiccup should never break an order or a
service request for the customer, so failures are swallowed rather than
raised.
"""
import logging
from datetime import datetime, timezone

from app import db

logger = logging.getLogger("sarthi.erp")

_client = db.get_client()

# Order columns added by migration 003 (the status values it lists are free text and need no column).
_MIGRATION_003_COLUMNS = {"short_code", "rx_path"}


def is_configured() -> bool:
    return _client is not None


def _tenant_fields(restaurant_id: str | None, table_no: str | None) -> dict:
    # Only sent when set: the legacy four-persona demo has no restaurant, and
    # leaving the keys out means it keeps working even before the multi-restaurant
    # migration (which adds these columns) has been applied.
    fields = {}
    if restaurant_id:
        fields["restaurant_id"] = restaurant_id
    if table_no:
        fields["table_no"] = table_no
    return fields


def record_order(
    session_id: str,
    persona: str,
    items: list[dict],
    total: float,
    restaurant_id: str | None = None,
    table_no: str | None = None,
    extra: dict | None = None,
) -> dict | None:
    """Returns the saved row (or None). `extra` carries the customer columns (customer_id, caller_phone,
    fulfilment, address_snapshot, needs_pharmacist, short_code, rx_path, status; migrations 002 and 003).
    If the database doesn't have them yet the order is still saved without them: an order must never be
    lost to a missing column."""
    if _client is None:
        return None
    row = {
        "session_id": session_id,
        "persona": persona,
        "items": items,
        "total": total,
        **_tenant_fields(restaurant_id, table_no),
    }
    # Newest columns first, then fewer: an order must be saved even if a migration hasn't been applied yet.
    attempts = [{**row, **(extra or {})}]
    if extra:
        attempts.append({**row, **{k: v for k, v in extra.items() if k not in _MIGRATION_003_COLUMNS}})
        attempts.append(row)
    for position, attempt in enumerate(attempts):
        try:
            return _client.table("orders").insert(attempt).execute().data[0]
        except Exception:
            logger.warning("order insert failed (attempt %d of %d)", position + 1, len(attempts), exc_info=position == len(attempts) - 1)
    return None


def record_request(
    session_id: str,
    persona: str,
    request_type: str,
    details: str = "",
    notes: str = "",
    restaurant_id: str | None = None,
    table_no: str | None = None,
) -> None:
    if _client is None:
        return
    try:
        _client.table("requests").insert(
            {
                "session_id": session_id,
                "persona": persona,
                "type": request_type,
                "details": details,
                "notes": notes,
                **_tenant_fields(restaurant_id, table_no),
            }
        ).execute()
    except Exception:
        pass


# --- Reads for the staff-facing view (app/main.py's /admin/* routes). ---
# Unlike the writes above, these are allowed to raise: a staff member
# looking at the ops view needs to know a read actually failed, rather
# than silently seeing an empty list.


def list_orders(limit: int = 100) -> list[dict]:
    if _client is None:
        return []
    result = _client.table("orders").select("*").order("created_at", desc=True).limit(limit).execute()
    return result.data


def list_requests(limit: int = 100) -> list[dict]:
    if _client is None:
        return []
    result = _client.table("requests").select("*").order("created_at", desc=True).limit(limit).execute()
    return result.data


def resolve_request(request_id: str) -> dict | None:
    if _client is None:
        return None
    result = (
        _client.table("requests")
        .update({"status": "resolved", "resolved_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", request_id)
        .execute()
    )
    return result.data[0] if result.data else None
