"""The Support tab's reads: tickets filtered and paged in the database, the tab's counts, and one ticket in full.

    list_tickets(restaurant, status, category, page)  one page of tickets, plus the counts at the top of the tab
    ticket_detail(restaurant, ticket_id)               one ticket with its history, order and call transcript
    callback_phone(restaurant_id, ticket_id)           the full number, only when the owner presses Call

Every filter is a database filter, so a restaurant with thousands of tickets gets the same small page. Waiting
tickets come urgent first, then the longest wait; resolved ones newest first. Writes are in app/phone/tickets.py.
"""
from datetime import datetime, timedelta, timezone

from app.customers.phone import normalize_phone
from app.db import retry_read
from app.menu.repository import _c
from app.owner_board import _who
from app.phone.messages import english
from app.phone.tickets import CATEGORIES, OPEN_STATES
from app.transcripts import call_transcript

PAGE_SIZE = 50
OVERDUE_MINUTES = 15
COUNT_SCAN = 5000  # waiting tickets read for the counts (id, urgency, time only)
IST = timezone(timedelta(hours=5, minutes=30))
STATUSES = ("waiting", "resolved", "all")


def _query(restaurant_id: str, columns: str = "*"):
    return _c().table("requests").select(columns).eq("restaurant_id", restaurant_id).eq("type", "callback")


def _in(table: str, column: str, values: list, columns: str = "*") -> list[dict]:
    values = [v for v in set(values) if v]
    return _c().table(table).select(columns).in_(column, values).execute().data if values else []


def _counts(restaurant_id: str) -> dict:
    now = datetime.now(timezone.utc)
    waiting = _query(restaurant_id, "id,priority,created_at").in_("status", list(OPEN_STATES)).limit(COUNT_SCAN).execute().data
    overdue_before = (now - timedelta(minutes=OVERDUE_MINUTES)).isoformat()
    midnight = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    resolved_today = _query(restaurant_id, "id").eq("status", "resolved").gte("resolved_at", midnight).limit(COUNT_SCAN).execute().data
    return {
        "waiting": len(waiting),
        "urgent": sum(t.get("priority") == "urgent" for t in waiting),
        "overdue": sum(str(t["created_at"]) < overdue_before for t in waiting),
        "resolved_today": len(resolved_today),
        "overdue_minutes": OVERDUE_MINUTES,
    }


def _row(r: dict, calls: dict, orders: dict, customers: dict) -> dict:
    call = calls.get(r.get("call_id")) or {}
    order = orders.get(r.get("order_id")) or {}
    phone = r.get("customer_phone") or call.get("caller")
    category = r.get("category") if r.get("category") in CATEGORIES else "speak_to_person"
    return {
        "id": r["id"],
        "status": r.get("status") or "open",
        "created_at": r["created_at"],
        "resolved_at": r.get("resolved_at"),
        "reason": english(r.get("details")) or "",
        "category": category,
        "category_label": CATEGORIES[category],
        "priority": "urgent" if r.get("priority") == "urgent" else "normal",
        "attempts": int(r.get("attempts") or 0),
        "resolution": r.get("resolution"),
        "customer": _who(customers.get(r.get("customer_id")), phone, bool(call.get("caller"))),
        "can_call": bool(phone),
        "order_ref": order.get("payment_ref"),
        "call_id": r.get("call_id"),
        "call_outcome": call.get("outcome"),
    }


@retry_read
def list_tickets(restaurant: dict, status: str = "waiting", category: str | None = None, page: int = 1) -> dict:
    rid = restaurant["id"]
    status = status if status in STATUSES else "waiting"
    page = max(1, int(page or 1))
    query = _query(rid)
    if status == "waiting":
        # 'urgent' sorts after 'normal', so descending puts urgent first; then the longest wait
        query = query.in_("status", list(OPEN_STATES)).order("priority", desc=True).order("created_at")
    elif status == "resolved":
        query = query.eq("status", "resolved").order("created_at", desc=True)
    else:
        query = query.order("created_at", desc=True)
    if category in CATEGORIES:
        query = query.eq("category", category)
    start = (page - 1) * PAGE_SIZE
    rows = query.range(start, start + PAGE_SIZE).execute().data  # one extra row says whether there is a next page
    has_more = len(rows) > PAGE_SIZE
    rows = rows[:PAGE_SIZE]
    calls = {c["id"]: c for c in _in("phone_calls", "id", [r.get("call_id") for r in rows], "id,caller,outcome")}
    orders = {o["id"]: o for o in _in("orders", "id", [r.get("order_id") for r in rows], "id,payment_ref")}
    customers = {c["id"]: c for c in _in("customers", "id", [r.get("customer_id") for r in rows], "id,name,phone")}
    return {
        "counts": _counts(rid),
        "tickets": [_row(r, calls, orders, customers) for r in rows],
        "page": page,
        "has_more": has_more,
    }


@retry_read
def ticket_detail(restaurant: dict, ticket_id: str) -> dict | None:
    rows = _query(restaurant["id"]).eq("id", ticket_id).limit(1).execute().data
    if not rows:
        return None
    r = rows[0]
    calls = {c["id"]: c for c in _in("phone_calls", "id", [r.get("call_id")], "id,caller,outcome,turns")}
    orders = {o["id"]: o for o in _in("orders", "id", [r.get("order_id")])}
    customers = {c["id"]: c for c in _in("customers", "id", [r.get("customer_id")], "id,name,phone")}
    row = _row(r, calls, orders, customers)
    order = orders.get(r.get("order_id"))
    row["order"] = ({"items": order.get("items") or [], "total": order.get("total"), "status": order.get("status")}
                    if order else None)
    row["activity"] = r.get("activity") or []
    row["transcript"] = call_transcript((calls.get(r.get("call_id")) or {}).get("turns"))
    return row


@retry_read
def callback_phone(restaurant_id: str, ticket_id: str) -> str | None:
    """The full number of one ticket: the only place a full number reaches the dashboard, one at a time."""
    rows = _query(restaurant_id, "customer_phone,call_id").eq("id", ticket_id).limit(1).execute().data
    if not rows:
        return None
    phone = rows[0].get("customer_phone")
    if not phone and rows[0].get("call_id"):
        call = _c().table("phone_calls").select("caller").eq("id", rows[0]["call_id"]).limit(1).execute().data
        phone = call[0].get("caller") if call else None
    return (normalize_phone(phone) or phone) if phone else None
