"""The owner's "Calls & Orders" board: each order with who placed it, what they asked for, where it goes and
the call it came from, plus the carts callers left behind and the drop-off numbers.

One backend call returns it already joined and already masked. Phone numbers never leave here in full: the
board is meant to be shown to people (a demo, a buyer, a manager), so hiding a number is done on the server and
not left to the page.
"""
from datetime import datetime, timedelta, timezone

from app.customers.phone import normalize_phone
from app.db import retry_read
from app.menu.repository import _c
from app.phone.messages import english

ORDER_LIMIT = 100
CART_LIMIT = 50
FUNNEL_DAYS = 30
# Never sent to a browser, masked or not: a payment link token lets anyone pay (or look at) the order.
_PRIVATE_ORDER_FIELDS = {"pay_token", "customer_phone", "caller_phone", "address_snapshot"}


def mask_phone(raw: str | None) -> str | None:
    """+919876542828 -> '+91 ••••• 2828'. Enough to tell two callers apart, not enough to call them."""
    if not raw:
        return None
    phone = normalize_phone(raw)
    if phone is None:
        digits = "".join(ch for ch in raw if ch.isdigit())
        return f"••••• {digits[-4:]}" if len(digits) >= 4 else "hidden"
    country = "+91" if phone.startswith("+91") else phone[:3]
    return f"{country} ••••• {phone[-4:]}"


def _channel(order: dict) -> str:
    if order.get("channel"):
        return order["channel"]
    if order.get("table_no"):
        return "table"
    if order.get("call_id") or order.get("order_type") or str(order.get("session_id", "")).startswith(("samvaad:", "livekit:")):
        return "call"
    return "web"


def _address(order: dict) -> str | None:
    if order.get("address"):
        return english(order["address"])
    snapshot = order.get("address_snapshot") or {}
    return english(snapshot.get("line")) or None if isinstance(snapshot, dict) else None


def _who(customer: dict | None, raw_phone: str | None, verified: bool, orders: int = 0) -> dict:
    return {
        # In English letters, like everything on the board: older calls saved names as heard ("ऋत्विक दोषी").
        "name": english((customer or {}).get("name")) or None,
        "phone": mask_phone((customer or {}).get("phone") or raw_phone),
        "verified": bool(verified),
        "orders": orders,  # in the window shown; more than one means a returning customer
    }


def owner_order(order: dict) -> dict:
    """An order without the fields an owner's browser should never receive."""
    return {k: v for k, v in order.items() if k not in _PRIVATE_ORDER_FIELDS}


def _in(table: str, column: str, values: list, columns: str = "*") -> list[dict]:
    values = [v for v in set(values) if v]
    return _c().table(table).select(columns).in_(column, values).execute().data if values else []


@retry_read
def build(restaurant: dict) -> dict:
    """The Calls & orders board: the latest ORDER_LIMIT orders and CART_LIMIT dropped carts, whatever the volume.
    Support tickets have their own paged endpoint (app/support.py); transcripts load per call (app/call_log.py)."""
    client = _c()
    rid = restaurant["id"]
    orders = (
        client.table("orders").select("*").eq("restaurant_id", rid)
        .order("created_at", desc=True).limit(ORDER_LIMIT).execute().data
    )
    customers = {c["id"]: c for c in _in("customers", "id", [o.get("customer_id") for o in orders])}
    calls = {c["id"]: c for c in _in("phone_calls", "id", [o.get("call_id") for o in orders], "id,outcome,started_at,ended_at")}
    # only the requests on the orders shown, however many a busy restaurant has in all
    requests = _in("requests", "order_id", [o["id"] for o in orders], "id,order_id,type,details,status,created_at")
    by_order: dict[str, list[dict]] = {}
    for r in requests:
        if r.get("order_id"):
            by_order.setdefault(r["order_id"], []).append(
                {k: r.get(k) for k in ("id", "type", "details", "status", "created_at")}
            )
    seen: dict[str, int] = {}
    for o in orders:
        key = o.get("customer_id") or o.get("customer_phone") or o.get("caller_phone")
        if key:
            seen[key] = seen.get(key, 0) + 1

    board = []
    for o in orders:
        key = o.get("customer_id") or o.get("customer_phone") or o.get("caller_phone")
        call = calls.get(o.get("call_id")) or {}
        row = owner_order(o)
        row.update(
            channel=_channel(o),
            fulfilment=o.get("order_type") or o.get("fulfilment"),
            address=_address(o),
            special_requests=english(o.get("special_requests")) or None,
            customer=_who(customers.get(o.get("customer_id")), o.get("customer_phone") or o.get("caller_phone"),
                          o.get("phone_verified"), seen.get(key, 0) if key else 0),
            requests=by_order.get(o["id"], []),
            call=({"id": call["id"], "outcome": call.get("outcome"), "started_at": call.get("started_at"),
                   "ended_at": call.get("ended_at")}
                  if call else None),
        )
        board.append(row)

    cart_rows = (
        client.table("carts").select("*").eq("restaurant_id", rid).in_("status", ["abandoned", "expired"])
        .order("last_activity_at", desc=True).limit(CART_LIMIT).execute().data
    )
    cart_customers = {c["id"]: c for c in _in("customers", "id", [c.get("customer_id") for c in cart_rows])}
    dropped = [
        {
            "id": c["id"], "status": c["status"], "opened_at": c["opened_at"], "last_activity_at": c["last_activity_at"],
            "items": c["items"], "total": c["total"], "fulfilment": c.get("fulfilment"), "address": english(c.get("address")) or None,
            "special_requests": english(c.get("special_requests")) or None, "recovery_attempts": c.get("recovery_attempts", 0),
            "closed_reason": c.get("closed_reason"),
            "customer": _who(cart_customers.get(c.get("customer_id")), c.get("customer_phone"), c.get("phone_verified")),
        }
        for c in cart_rows
        if c.get("items") and c.get("closed_reason") != "empty"
    ]

    stores = client.table("phone_stores").select("id").eq("restaurant_slug", restaurant["slug"]).execute().data
    since = (datetime.now(timezone.utc) - timedelta(days=FUNNEL_DAYS)).date().isoformat()
    funnel = (
        client.table("call_funnel").select("*").in_("store_id", [s["id"] for s in stores]).gte("day", since)
        .order("day", desc=True).execute().data
        if stores else []
    )
    return {"orders": board, "dropped_carts": dropped, "funnel": funnel}

