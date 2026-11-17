"""Conversation transcripts: what each guest said and what the agent answered, kept so the owner can read it.

One row per turn in `conversation_turns` (supabase/migrations/005_conversation_turns.sql). Every channel goes through
RestaurantOrderingAgent.send, which calls record_turn, so typed chat, push-to-talk, browser calls, phone calls and
WhatsApp all land here the same way. Recording never gets in a conversation's way: it runs off the conversation's
thread, and any failure (the table not created yet, Supabase down) is logged once and ignored.

Turn off with SARTHI_STORE_TRANSCRIPTS=0. Reading is for owners and managers only (app/owner_api.py).
"""
import logging
import os
import re
import threading

from app import db

logger = logging.getLogger("sarthi.transcripts")
_warned = False
MAX_TEXT = 2000
_LIST_SCAN = 800  # how many recent turns are grouped into the list of conversations


def enabled() -> bool:
    return os.environ.get("SARTHI_STORE_TRANSCRIPTS", "1").strip().lower() not in ("0", "false", "no", "off")


def conversation_key(session_id: str) -> str:
    """The part of an agent's session id that is the guest's visit, so a call and the typed chat on the same page
    read as one conversation: "livekit:slug:UUID" (a call) and "slug:UUID:waiter" (the page) both become "UUID"."""
    parts = [p for p in re.split(r":", session_id or "") if p]
    parts = [p for p in parts if p != "livekit" and p not in ("waiter", "store", "quick_commerce", "online", "hotel")]
    return parts[-1] if parts else (session_id or "")


def record_turn(
    restaurant_id: str | None,
    session_id: str,
    channel: str,
    customer_text: str,
    agent_text: str,
    *,
    language: str | None = None,
    speech: str | None = None,
    latency_ms: float | None = None,
    table_no: str | None = None,
    caller_phone: str | None = None,
) -> None:
    """Save one turn in the background. Does nothing without a restaurant, a database, or anything said."""
    if not enabled() or not restaurant_id or not (agent_text or "").strip() or not (customer_text or "").strip():
        return
    row = {
        "restaurant_id": restaurant_id,
        "session_id": conversation_key(session_id),
        "channel": channel,
        "speech": speech,
        "language": language,
        "table_no": table_no,
        "caller_phone": caller_phone,
        "customer_text": customer_text.strip()[:MAX_TEXT],
        "agent_text": agent_text.strip()[:MAX_TEXT],
        "latency_ms": int(latency_ms) if latency_ms is not None else None,
    }
    threading.Thread(target=_insert, args=(row,), daemon=True).start()


def _insert(row: dict) -> None:
    global _warned
    client = db.get_client()
    if client is None:
        return
    try:
        client.table("conversation_turns").insert(row).execute()
    except Exception as exc:
        if not _warned:  # once: a missing table would otherwise log on every turn
            _warned = True
            logger.warning("couldn't save conversation turns (has migration 005 been run?): %s", str(exc)[:200])


def list_conversations(restaurant_id: str, limit: int = 50) -> list[dict]:
    """The latest conversations, newest first: when, how many turns, which channels, and how it began."""
    client = db.get_client()
    if client is None:
        return []
    rows = (
        client.table("conversation_turns").select("*").eq("restaurant_id", restaurant_id)
        .order("created_at", desc=True).limit(_LIST_SCAN).execute().data
    )
    grouped: dict[str, dict] = {}
    for row in rows:  # newest first, so the first row seen for a visit is its last turn
        entry = grouped.setdefault(row["session_id"], {
            "session_id": row["session_id"], "last_at": row["created_at"], "started_at": row["created_at"],
            "turns": 0, "channels": [], "table_no": row.get("table_no"), "caller_phone": row.get("caller_phone"),
            "preview": row["customer_text"],
        })
        entry["turns"] += 1
        entry["started_at"] = row["created_at"]
        entry["preview"] = row["customer_text"]  # ends as the oldest, i.e. how it began
        entry["table_no"] = entry["table_no"] or row.get("table_no")
        entry["caller_phone"] = entry["caller_phone"] or row.get("caller_phone")
        if row["channel"] not in entry["channels"]:
            entry["channels"].append(row["channel"])
    return list(grouped.values())[:limit]


def conversation_turns(restaurant_id: str, session_id: str) -> list[dict]:
    """Every turn of one conversation, in order."""
    client = db.get_client()
    if client is None:
        return []
    return (
        client.table("conversation_turns").select("*").eq("restaurant_id", restaurant_id)
        .eq("session_id", session_id).order("created_at").limit(1000).execute().data
    )
