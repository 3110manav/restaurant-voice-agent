"""Support tickets: what a caller needs from a person at the restaurant, and what staff did about it.

A ticket is a `requests` row of type 'callback' (migration 012), with a category, an urgency, a history and a
resolution (migration 015). Kabir opens one with request_callback, and one opens on its own when an order can't
be saved. The owner works it from the Support tab: call, note an unanswered call, add a note, resolve (optionally
telling the customer on WhatsApp), reopen.

Before migration 015 the extra columns don't exist: tickets still open and resolve, without the history.
"""
import logging
import re
from datetime import datetime, timezone

from app.menu.repository import _c
from app.phone import repository
from app.phone.messages import english

logger = logging.getLogger("sarthi.phone.tickets")

CATEGORIES = {
    "complaint": "Complaint",
    "refund": "Refund",
    "booking": "Table booking",
    "order_status": "Where is my order",
    "order_change": "Change an order",
    "speak_to_person": "Wants a person",
    "order_failed": "Order not saved",
    "other": "Other",
}
OPEN_STATES = ("open", "in_progress")
_NEW_COLUMNS = ("category", "priority", "attempts", "activity", "resolution")

# Words a caller (or Kabir's summary of them) uses, in English, Hinglish and Hindi script. First match wins, so the
# more specific categories come first.
_RULES = [
    ("refund", r"refund|money back|paise wapas|पैसे वापस|रिफंड|charged twice|double payment"),
    ("booking", r"\btable\b|book|reserv|बुक|टेबल|seats?\b|party of"),
    ("order_status", r"where is|kab aayega|kab ayega|kahan hai|status|late|delay|not (yet )?(come|arrived|delivered)|"
                     r"कब आएगा|कहाँ है|देर|अभी तक"),
    ("order_change", r"change (my|the) order|cancel|add (to|in) (my|the) order|address change|बदल|कैंसल"),
    ("complaint", r"complain|wrong|missing|cold|bad|stale|spoil|hair|insect|not good|kharab|galat|thanda|"
                  r"शिकायत|गलत|ख़राब|खराब|ठंडा|allerg"),
]
_URGENT = re.compile(
    r"wrong|missing|allerg|sick|ill\b|vomit|hair|insect|cockroach|spoil|stale|kharab|galat|urgent|abhi|right now|"
    r"immediately|angry|गलत|ख़राब|खराब|एलर्जी|अभी|couldn.t be saved|not saved",
    re.I,
)


def classify(reason: str, category: str | None = None) -> tuple[str, str]:
    """(category, priority) for a ticket. A category Kabir sent is kept when it is one we know."""
    text = (reason or "").lower()
    chosen = (category or "").strip().lower().replace(" ", "_")
    if chosen not in CATEGORIES:
        chosen = next((name for name, pattern in _RULES if re.search(pattern, text, re.I)), "speak_to_person")
    urgent = chosen == "order_failed" or (chosen != "booking" and bool(_URGENT.search(text)))
    return chosen, "urgent" if urgent else "normal"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def event(kind: str, text: str = "", by: str | None = None) -> dict:
    return {"at": _now(), "kind": kind, "text": text, "by": by}


def new_ticket_fields(reason: str, category: str | None = None) -> dict:
    """The columns a new ticket starts with (the caller's words in English letters, like the rest of the board)."""
    reason = english(reason) or reason
    chosen, priority = classify(reason, category)
    return {
        "details": reason,
        "category": chosen,
        "priority": priority,
        "attempts": 0,
        "activity": [event("opened", reason, "Kabir")],
    }


def insert(row: dict) -> str | None:
    """Save a ticket; before migrations 015/012 the newer columns are dropped and it is saved without them."""
    row = {"type": "callback", "status": "open", **row}
    try:
        return _c().table("requests").insert(row).execute().data[0]["id"]
    except Exception:
        older = {k: v for k, v in row.items() if k not in _NEW_COLUMNS}
        if older == row:
            return repository.open_ticket(row)
        logger.warning("saving a ticket without its category and history: has migration 015 been run?")
        return repository.open_ticket(older)


class TicketError(ValueError):
    pass


def _load(restaurant_id: str, ticket_id: str) -> dict:
    rows = (
        _c().table("requests").select("*").eq("id", ticket_id).eq("restaurant_id", restaurant_id)
        .eq("type", "callback").limit(1).execute().data
    )
    if not rows:
        raise TicketError("Ticket not found")
    return rows[0]


ACTIONS = ("start", "no_answer", "note", "resolve", "reopen", "urgent", "normal", "category")


def act(restaurant_id: str, ticket_id: str, action: str, *, note: str = "", category: str | None = None,
        notify_customer: bool = False, store_name: str = "", by: str | None = None) -> dict:
    """One thing staff did on a ticket. Returns the updated ticket row."""
    if action not in ACTIONS:
        raise TicketError(f"Unknown action {action!r}")
    ticket = _load(restaurant_id, ticket_id)
    note = " ".join((note or "").split())[:500]
    status = ticket.get("status") or "open"
    history = list(ticket.get("activity") or [])
    fields: dict = {}
    message = None

    if action == "start":
        fields["status"] = "in_progress"
        history.append(event("started", note, by))
    elif action == "no_answer":
        fields["attempts"] = int(ticket.get("attempts") or 0) + 1
        fields["status"] = "in_progress" if status == "open" else status
        history.append(event("no_answer", note, by))
        if notify_customer:
            message = f"{store_name}: we tried to call you about your request and couldn't reach you. We'll try again soon."
    elif action == "note":
        if not note:
            raise TicketError("Write the note first")
        history.append(event("note", note, by))
    elif action == "resolve":
        fields.update(status="resolved", resolved_at=_now(), resolution=note or None)
        history.append(event("resolved", note, by))
        if notify_customer:
            message = f"{store_name}: your request has been taken care of. Thank you for your patience!"
    elif action == "reopen":
        if status in OPEN_STATES:
            raise TicketError("This ticket is already open")
        fields.update(status="open", resolved_at=None)
        history.append(event("reopened", note, by))
    elif action in ("urgent", "normal"):
        fields["priority"] = action
        history.append(event("priority", "Marked urgent" if action == "urgent" else "Marked normal", by))
    elif action == "category":
        if category not in CATEGORIES:
            raise TicketError("Pick a category from the list")
        fields["category"] = category
        history.append(event("category", CATEGORIES[category], by))

    if message and not (ticket.get("customer_phone") or ticket.get("call_id")):
        raise TicketError("No number on this ticket to send a WhatsApp to")
    fields["activity"] = history
    try:
        rows = _c().table("requests").update(fields).eq("id", ticket_id).eq("restaurant_id", restaurant_id).execute().data
    except Exception as exc:
        if action != "resolve":
            raise TicketError("Run migration 015_ticket_actions.sql to use this action") from exc
        rows = _c().table("requests").update({"status": "resolved", "resolved_at": fields["resolved_at"]}).eq(
            "id", ticket_id).eq("restaurant_id", restaurant_id).execute().data  # before 015: resolve still works
    if message:
        _tell_customer(ticket, message)
    return rows[0] if rows else {**ticket, **fields}


def _tell_customer(ticket: dict, text: str) -> None:
    phone = ticket.get("customer_phone")
    if not phone and ticket.get("call_id"):
        call = _c().table("phone_calls").select("caller").eq("id", ticket["call_id"]).limit(1).execute().data
        phone = call[0].get("caller") if call else None
    if not phone:
        raise TicketError("No number on this ticket to send a WhatsApp to")
    # Through the outbox, from the restaurant's own WhatsApp number when it has one (found from the call).
    repository.queue_message(phone, "ticket_update", {"type": "text", "text": text},
                             order_id=ticket.get("order_id"), call_id=ticket.get("call_id"))
    from app.phone import outbox

    outbox.flush_in_background()
