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
import os
from datetime import datetime, timezone

from supabase import Client, create_client

_SUPABASE_URL = os.environ.get("SUPABASE_URL")
_SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

_client: Client | None = None
if _SUPABASE_URL and _SUPABASE_SERVICE_KEY:
    _client = create_client(_SUPABASE_URL, _SUPABASE_SERVICE_KEY)


def is_configured() -> bool:
    return _client is not None


def record_order(session_id: str, persona: str, items: list[dict], total: float) -> None:
    if _client is None:
        return
    try:
        _client.table("orders").insert(
            {"session_id": session_id, "persona": persona, "items": items, "total": total}
        ).execute()
    except Exception:
        pass


def record_request(session_id: str, persona: str, request_type: str, details: str = "", notes: str = "") -> None:
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
