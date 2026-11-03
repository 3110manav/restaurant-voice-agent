"""Supabase access for phone ordering (supabase/migrations/002_phone_ordering.sql). Unlike app/erp.py,
writes here raise: a customer has been told their order is placed, so a failure must be seen."""
from datetime import datetime, timezone

from app import db


class NotConfiguredError(RuntimeError):
    pass


def _c():
    client = db.get_client()
    if client is None:
        raise NotConfiguredError("Supabase isn't configured (SUPABASE_URL / SUPABASE_SERVICE_KEY)")
    return client


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first(result) -> dict | None:
    return result.data[0] if result.data else None


# ------------------------------------------------------------------- stores --


def store_for_number(number: str) -> dict | None:
    return _first(_c().table("phone_stores").select("*").eq("phone_number", number).limit(1).execute())


def get_store(store_id: str) -> dict | None:
    return _first(_c().table("phone_stores").select("*").eq("id", store_id).limit(1).execute())


def get_store_by_slug(slug: str) -> dict | None:
    return _first(_c().table("phone_stores").select("*").eq("slug", slug).limit(1).execute())


def save_store(fields: dict) -> dict:
    return _c().table("phone_stores").upsert(fields, on_conflict="slug").execute().data[0]


def assign_number(slug: str, number: str) -> None:
    """Point a dialled number at one store. A number can only answer as one store at a time."""
    _c().table("phone_stores").update({"phone_number": None}).eq("phone_number", number).execute()
    _c().table("phone_stores").update({"phone_number": number}).eq("slug", slug).execute()


# -------------------------------------------------------------------- calls --


def start_call(room: str, store_id: str, caller: str | None) -> str:
    row = _c().table("phone_calls").insert({"room": room, "store_id": store_id, "caller": caller}).execute()
    return row.data[0]["id"]


def update_call(call_id: str, **fields) -> None:
    _c().table("phone_calls").update(fields).eq("id", call_id).execute()


def list_calls(limit: int = 30) -> list[dict]:
    """Recent calls, each with its store's name, order and messages, for the test view."""
    calls = _c().table("phone_calls").select("*").order("started_at", desc=True).limit(limit).execute().data
    if not calls:
        return []
    ids = [call["id"] for call in calls]
    stores = {s["id"]: s["name"] for s in _c().table("phone_stores").select("id,name").execute().data}
    orders = _c().table("orders").select("*").in_("call_id", ids).execute().data
    messages = (
        _c().table("message_outbox").select("*").in_("call_id", ids).order("created_at").execute().data
    )
    for call in calls:
        call["store_name"] = stores.get(call["store_id"], "")
        call["order"] = next((o for o in orders if o.get("call_id") == call["id"]), None)
        call["messages"] = [m for m in messages if m.get("call_id") == call["id"]]
    return calls


# ------------------------------------------------------------------- orders --


def place_order(order: dict, messages: list[dict]) -> str:
    """Saves the order and queues its messages in one transaction."""
    return _c().rpc("place_phone_order", {"p_order": order, "p_messages": messages}).execute().data


def get_order(order_id: str) -> dict | None:
    return _first(_c().table("orders").select("*").eq("id", order_id).limit(1).execute())


def order_by_pay_token(token: str) -> dict | None:
    return _first(_c().table("orders").select("*").eq("pay_token", token).limit(1).execute())


def move_order(order_id: str, expected: dict, changes: dict) -> dict | None:
    """Apply `changes` only if the order still matches `expected`. None means another tap got there first."""
    query = _c().table("orders").update(changes).eq("id", order_id)
    for column, value in expected.items():
        query = query.in_(column, value) if isinstance(value, list) else query.eq(column, value)
    return _first(query.execute())


# ----------------------------------------------------------------- messages --


def queue_message(recipient: str, kind: str, body: dict, order_id: str | None = None, call_id: str | None = None) -> None:
    _c().table("message_outbox").insert(
        {"recipient": recipient, "kind": kind, "body": body, "order_id": order_id, "call_id": call_id}
    ).execute()


def due_messages(stale_before: str, limit: int = 20) -> list[dict]:
    """Messages to send now: pending ones whose time has come, and ones a crashed sender left behind."""
    pending = (
        _c().table("message_outbox").select("*").eq("status", "pending")
        .lte("next_attempt_at", now_iso()).order("created_at").limit(limit).execute().data
    )
    stranded = (
        _c().table("message_outbox").select("*").eq("status", "sending")
        .lt("claimed_at", stale_before).limit(limit).execute().data
    )
    return pending + stranded


def claim_message(message: dict) -> bool:
    """Only one sender wins a message, even with the API and the voice worker both sending."""
    won = (
        _c().table("message_outbox")
        .update({"status": "sending", "attempts": message["attempts"] + 1, "claimed_at": now_iso()})
        .eq("id", message["id"]).eq("status", message["status"]).eq("attempts", message["attempts"]).execute()
    )
    return bool(won.data)


def update_message(message_id: str, **fields) -> None:
    _c().table("message_outbox").update(fields).eq("id", message_id).execute()


def update_delivery(wa_message_id: str, delivery_status: str, error: str | None = None) -> None:
    fields = {"delivery_status": delivery_status}
    if error:
        fields["last_error"] = error
    _c().table("message_outbox").update(fields).eq("wa_message_id", wa_message_id).execute()
