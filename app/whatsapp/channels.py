"""Which WhatsApp number belongs to which store, and the message log (see migration 003).

Reads and writes only: sending is client.py, deciding what to send is notify.py.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.menu.repository import _c, _read

logger = logging.getLogger("sarthi.whatsapp")

WINDOW = timedelta(hours=23)  # WhatsApp's customer-service window is 24h; stay safely inside it


@dataclass(frozen=True)
class Channel:
    id: str
    restaurant_id: str
    phone_number_id: str
    display_number: str | None = None
    token_env: str = "WHATSAPP_ACCESS_TOKEN"
    notify_numbers: tuple[str, ...] = field(default_factory=tuple)
    rx_numbers: tuple[str, ...] = field(default_factory=tuple)

    @staticmethod
    def from_row(row: dict) -> "Channel":
        return Channel(
            id=row["id"],
            restaurant_id=row["restaurant_id"],
            phone_number_id=row["phone_number_id"],
            display_number=row.get("display_number"),
            token_env=row.get("token_env") or "WHATSAPP_ACCESS_TOKEN",
            notify_numbers=tuple(row.get("notify_numbers") or ()),
            rx_numbers=tuple(row.get("rx_numbers") or ()),
        )

    def pharmacists(self) -> tuple[str, ...]:
        """Who gets prescription orders: the pharmacists, else the owners."""
        return self.rx_numbers or self.notify_numbers

    def staff(self) -> set[str]:
        """Every number allowed to send this store's order commands (confirm, reject, ready)."""
        return set(self.notify_numbers) | set(self.rx_numbers)


@_read
def channel_for_store(restaurant_id: str) -> Channel | None:
    """The store's WhatsApp channel (the first enabled one), or None when it has none."""
    rows = (
        _c().table("store_channels").select("*").eq("restaurant_id", restaurant_id).eq("enabled", True)
        .order("created_at").limit(1).execute().data
    )
    return Channel.from_row(rows[0]) if rows else None


@_read
def channel_by_phone_number_id(phone_number_id: str) -> Channel | None:
    """The channel a webhook message was sent to (Meta names the number by its id)."""
    rows = (
        _c().table("store_channels").select("*").eq("phone_number_id", phone_number_id).eq("enabled", True)
        .limit(1).execute().data
    )
    return Channel.from_row(rows[0]) if rows else None


def log_message(
    channel: Channel | None,
    restaurant_id: str | None,
    direction: str,
    peer: str,
    kind: str,
    body: str = "",
    status: str = "sent",
    wa_message_id: str | None = None,
    order_id: str | None = None,
    error: str | None = None,
) -> bool:
    """Record a message. Returns False only for an inbound message already seen (Meta retries a webhook
    until it gets a 200, so the same message can arrive twice); True otherwise, even if the log write fails."""
    row = {
        "restaurant_id": restaurant_id,
        "channel_id": channel.id if channel else None,
        "direction": direction,
        "peer": peer,
        "kind": kind,
        "body": (body or "")[:2000],
        "status": status,
        "wa_message_id": wa_message_id,
        "order_id": order_id,
        "error": (error or None) and error[:500],
    }
    try:
        _c().table("whatsapp_messages").insert(row).execute()
        return True
    except Exception as exc:
        if "duplicate key" in str(exc) or "23505" in str(exc):
            return False
        logger.warning("couldn't log a whatsapp message", exc_info=True)
        return True


@_read
def window_open(restaurant_id: str, peer: str) -> bool:
    """Has this customer messaged the store in the last 23 hours? If so a free-text reply is allowed;
    otherwise only an approved template can start the conversation."""
    since = (datetime.now(timezone.utc) - WINDOW).isoformat()
    rows = (
        _c().table("whatsapp_messages").select("id").eq("restaurant_id", restaurant_id).eq("peer", peer)
        .eq("direction", "in").gte("created_at", since).limit(1).execute().data
    )
    return bool(rows)


# ---------------------------------------------------------------- orders, as the chat sees them --


@_read
def order_by_code(restaurant_id: str, code: str) -> dict | None:
    rows = (
        _c().table("orders").select("*").eq("restaurant_id", restaurant_id).eq("short_code", code.upper())
        .order("created_at", desc=True).limit(1).execute().data
    )
    return rows[0] if rows else None


@_read
def latest_order_awaiting_prescription(restaurant_id: str, phone: str) -> dict | None:
    rows = (
        _c().table("orders").select("*").eq("restaurant_id", restaurant_id).eq("caller_phone", phone)
        .eq("status", "awaiting_prescription").order("created_at", desc=True).limit(1).execute().data
    )
    return rows[0] if rows else None


def set_order_status(order_id: str, status: str) -> None:
    _c().table("orders").update({"status": status}).eq("id", order_id).execute()


@_read
def latest_media_from(restaurant_id: str, peer: str) -> str | None:
    """The media id of the last photo this person sent the store (logged as "media:<id>|caption")."""
    rows = (
        _c().table("whatsapp_messages").select("body").eq("restaurant_id", restaurant_id).eq("peer", peer)
        .eq("direction", "in").in_("kind", ["image", "document"]).order("created_at", desc=True).limit(1).execute().data
    )
    body = rows[0]["body"] if rows else ""
    return body[len("media:"):].split("|", 1)[0] if body.startswith("media:") else None
