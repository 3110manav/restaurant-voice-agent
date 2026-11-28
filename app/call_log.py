"""The owner's Call log: every call to the restaurant, one day at a time, with what came of it and what was said.

    list_day(restaurant, day, outcome, page)  one page (50) of the day's calls, newest first, and the day's totals
    detail(restaurant, call_id)         one call: who, how long, its order, its ticket, and the transcript
    caller_phone(restaurant, call_id)   the full number, only when the owner presses Show number / Call

Every filter (day, outcome, page) is a database filter, so a busy restaurant gets the same small page; the totals
read only light columns. Reads retry once on a dropped connection. Days are India days (IST). Numbers are masked everywhere else, like the rest of the board. A call from Samvaad's
browser test bed has no caller ID: it says so ("Test call") and shows the number the guest gave, if any.
"""
from datetime import date, datetime, timedelta, timezone

from app.customers.phone import normalize_phone
from app.db import retry_read
from app.menu.repository import _c
from app.owner_board import mask_phone
from app.phone.messages import english
from app.phone.tickets import CATEGORIES
from app.transcripts import call_transcript

IST = timezone(timedelta(hours=5, minutes=30))
PAGE_SIZE = 50
TOTALS_SCAN = 20000  # a day's calls read for the totals, light columns only
EMPTY_TOTALS = {"calls": 0, "ordered": 0, "callback": 0, "no_order": 0, "test_calls": 0, "order_value": 0,
                "average_seconds": None, "total_minutes": 0}
OUTCOMES = {"ordered": "Ordered", "callback": "Needs a call back", "abandoned": "No order", "in_progress": "On the call"}


def today() -> date:
    return datetime.now(IST).date()


def _store_ids(restaurant: dict) -> list[str]:
    rows = _c().table("phone_stores").select("id").eq("restaurant_slug", restaurant.get("slug") or "").execute().data
    return [r["id"] for r in rows]


def _in(table: str, column: str, values: list, columns: str = "*") -> list[dict]:
    values = [v for v in set(values) if v]
    return _c().table(table).select(columns).in_(column, values).execute().data if values else []


def _seconds(call: dict) -> float | None:
    """How long the call lasted: Sarvam's own figure when it sent one, else from the call's start and end."""
    for metric in call.get("metrics") or []:
        if isinstance(metric, dict):
            for key in ("call_length", "duration"):
                try:
                    if metric.get(key) not in (None, ""):
                        return round(float(metric[key]), 1)
                except (TypeError, ValueError):
                    pass
    try:
        start = datetime.fromisoformat(str(call["started_at"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(call["ended_at"]).replace("Z", "+00:00"))
        return round((end - start).total_seconds(), 1)
    except (KeyError, TypeError, ValueError):
        return None


def _who(call: dict, order: dict | None, customer: dict | None) -> dict:
    """Who called, as the owner should read it: the caller ID if the phone network gave one; else (a browser test
    call) the number the guest gave for the bill, marked as given."""
    caller = call.get("caller")
    given = (order or {}).get("customer_phone")
    name = (order or {}).get("customer_name") or (customer or {}).get("name")
    return {
        "name": english(name) or None,
        "phone": mask_phone(caller or given),
        "source": "caller_id" if caller else ("given" if given else "none"),
        "test_call": not caller,
    }


def _day_range(day: date) -> tuple[str, str]:
    start = datetime(day.year, day.month, day.day, tzinfo=IST)
    return start.isoformat(), (start + timedelta(days=1)).isoformat()


def _calls_of_day(stores: list[str], day: date, columns: str):
    start, end = _day_range(day)
    return _c().table("phone_calls").select(columns).in_("store_id", stores).gte("started_at", start).lt("started_at", end)


def _totals(restaurant: dict, stores: list[str], day: date) -> dict:
    """The day's numbers from light columns only (no transcripts), so a busy day costs little."""
    calls = _calls_of_day(stores, day, "id,outcome,caller,metrics,started_at,ended_at").limit(TOTALS_SCAN).execute().data
    start, end = _day_range(day)
    orders = (
        _c().table("orders").select("total,call_id").eq("restaurant_id", restaurant["id"])
        .gte("created_at", start).lt("created_at", end).limit(TOTALS_SCAN).execute().data
    )
    lengths = [s for s in (_seconds(c) for c in calls) if s]
    return {
        "calls": len(calls),
        "ordered": sum(c.get("outcome") == "ordered" for c in calls),
        "callback": sum(c.get("outcome") == "callback" for c in calls),
        "no_order": sum(c.get("outcome") == "abandoned" for c in calls),
        "test_calls": sum(not c.get("caller") for c in calls),
        "order_value": sum(float(o.get("total") or 0) for o in orders if o.get("call_id")),
        "average_seconds": round(sum(lengths) / len(lengths)) if lengths else None,
        "total_minutes": round(sum(lengths) / 60, 1) if lengths else 0,
    }


def _linked(restaurant: dict, calls: list[dict]) -> tuple[dict, dict, dict]:
    ids = [c["id"] for c in calls]
    orders = {o["call_id"]: o for o in _in("orders", "call_id", ids) if o.get("restaurant_id") == restaurant["id"]}
    tickets = {t["call_id"]: t for t in _in("requests", "call_id", ids) if t.get("type") == "callback"}
    customer_ids = [c.get("customer_id") for c in calls] + [o.get("customer_id") for o in orders.values()]
    customers = {c["id"]: c for c in _in("customers", "id", customer_ids)}
    return orders, tickets, customers


def _summary_row(call: dict, order: dict | None, ticket: dict | None, customers: dict) -> dict:
    lines = call_transcript(call.get("turns"))
    customer = customers.get(call.get("customer_id")) or customers.get((order or {}).get("customer_id"))
    first_words = next((line["text"] for line in lines if line["role"] == "user"), "")
    outcome = call.get("outcome") or "in_progress"
    return {
        "id": call["id"],
        "started_at": call["started_at"],
        "ended_at": call.get("ended_at"),
        "seconds": _seconds(call),
        "outcome": outcome,
        "outcome_label": OUTCOMES.get(outcome, outcome),
        "caller": _who(call, order, customer),
        "order": ({"ref": order.get("payment_ref"), "total": order.get("total"),
                   "dishes": sum(int(line.get("quantity") or 1) for line in order.get("items") or [])} if order else None),
        "ticket": ({"category": CATEGORIES.get(ticket.get("category") or "", "Wants a person"),
                    "status": ticket.get("status") or "open", "urgent": ticket.get("priority") == "urgent"}
                   if ticket else None),
        "turns": sum(1 for line in lines if line["role"] == "user"),
        "preview": first_words[:140],
    }


@retry_read
def list_day(restaurant: dict, day: date | None = None, outcome: str = "all", page: int = 1) -> dict:
    """One page of a day's calls, newest first, filtered by outcome in the database, and the whole day's totals."""
    day = day or today()
    page = max(1, int(page or 1))
    stores = _store_ids(restaurant)
    base = {"day": day.isoformat(), "today": today().isoformat(), "page": page}
    if not stores:
        return {**base, "totals": dict(EMPTY_TOTALS), "calls": [], "has_more": False}
    query = _calls_of_day(stores, day, "*")
    if outcome in OUTCOMES:
        query = query.eq("outcome", outcome)
    start = (page - 1) * PAGE_SIZE
    calls = query.order("started_at", desc=True).range(start, start + PAGE_SIZE).execute().data  # +1 row: a next page?
    has_more = len(calls) > PAGE_SIZE
    calls = calls[:PAGE_SIZE]
    orders, tickets, customers = _linked(restaurant, calls)
    rows = [_summary_row(c, orders.get(c["id"]), tickets.get(c["id"]), customers) for c in calls]
    return {**base, "totals": _totals(restaurant, stores, day), "calls": rows, "has_more": has_more}


def _call(restaurant: dict, call_id: str) -> dict | None:
    rows = _c().table("phone_calls").select("*").eq("id", call_id).limit(1).execute().data
    return rows[0] if rows and rows[0]["store_id"] in _store_ids(restaurant) else None


@retry_read
def detail(restaurant: dict, call_id: str) -> dict | None:
    call = _call(restaurant, call_id)
    if call is None:
        return None
    orders, tickets, customers = _linked(restaurant, [call])
    order, ticket = orders.get(call["id"]), tickets.get(call["id"])
    row = _summary_row(call, order, ticket, customers)
    if order:
        row["order"].update(items=order.get("items") or [], status=order.get("status"),
                            fulfilment=order.get("order_type"), address=english(order.get("address")) or None)
    if ticket:
        row["ticket"].update(reason=english(ticket.get("details")) or "")
    row["end_reason"] = call.get("end_reason")
    row["transcript"] = call_transcript(call.get("turns"))
    return row


@retry_read
def caller_phone(restaurant: dict, call_id: str) -> str | None:
    """The full number of one call (caller ID, else the number the guest gave), for Show number and Call."""
    call = _call(restaurant, call_id)
    if call is None:
        return None
    phone = call.get("caller")
    if not phone:
        orders = _c().table("orders").select("customer_phone").eq("call_id", call_id).limit(1).execute().data
        phone = orders[0].get("customer_phone") if orders else None
    return (normalize_phone(phone) or phone) if phone else None


def parse_day(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None
