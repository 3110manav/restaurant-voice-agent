"""Supabase reads and writes for the table QR pilot: table sessions and the customer list
(supabase/migrations/003_table_pilot.sql).

Like app/menu/repository.py, calls raise when something goes wrong; app/table/state.py decides
which guest-side writes are best effort. Every call returns empty results when Supabase isn't
configured, so a local run without a database still serves the guest flow.
"""
from app import db


def _c():
    return db.get_client()


# ------------------------------------------------------------ table sessions --


def find_session(restaurant_id: str, session_id: str) -> dict | None:
    client = _c()
    if client is None:
        return None
    rows = (
        client.table("table_sessions").select("*")
        .eq("restaurant_id", restaurant_id).eq("session_id", session_id).limit(1).execute().data
    )
    return rows[0] if rows else None


def create_session(row: dict) -> dict | None:
    client = _c()
    if client is None:
        return None
    return client.table("table_sessions").insert(row).execute().data[0]


def update_session(restaurant_id: str, row_id: str, fields: dict) -> dict | None:
    client = _c()
    if client is None:
        return None
    rows = (
        client.table("table_sessions").update(fields)
        .eq("id", row_id).eq("restaurant_id", restaurant_id).execute().data
    )
    return rows[0] if rows else None


def set_moment(restaurant_id: str, row_id: str, moment: str, value: str, extra: dict | None = None) -> dict | None:
    """Records one of the turn tracker's moments only if it isn't recorded yet, so a guest's tap and
    a staff member's tap on the same moment keep whichever came first."""
    client = _c()
    if client is None:
        return None
    rows = (
        client.table("table_sessions").update({moment: value, **(extra or {})})
        .eq("id", row_id).eq("restaurant_id", restaurant_id).is_(moment, "null").execute().data
    )
    return rows[0] if rows else None


def list_sessions_since(restaurant_id: str, since_iso: str, until_iso: str | None = None) -> list[dict]:
    client = _c()
    if client is None:
        return []
    query = (
        client.table("table_sessions").select("*")
        .eq("restaurant_id", restaurant_id).gte("seated_at", since_iso)
    )
    if until_iso:
        query = query.lt("seated_at", until_iso)
    return query.order("seated_at", desc=True).limit(2000).execute().data


# ----------------------------------------------------------------- customers --


def save_customer(restaurant_id: str, phone: str, name: str | None, offers_opt_in: bool, now_iso: str) -> dict | None:
    """Adds the guest to the restaurant's list, or counts another visit. Turning offers on or off
    always follows what the guest chose this time."""
    client = _c()
    if client is None:
        return None
    rows = (
        client.table("customers").select("*")
        .eq("restaurant_id", restaurant_id).eq("phone", phone).limit(1).execute().data
    )
    if rows:
        existing = rows[0]
        fields = {
            "visits": int(existing.get("visits") or 0) + 1,
            "last_visit_at": now_iso,
            "offers_opt_in": offers_opt_in,
        }
        if name:
            fields["name"] = name
        updated = (
            client.table("customers").update(fields)
            .eq("id", existing["id"]).eq("restaurant_id", restaurant_id).execute().data
        )
        return updated[0] if updated else None
    row = {
        "restaurant_id": restaurant_id,
        "phone": phone,
        "name": name or None,
        "offers_opt_in": offers_opt_in,
        "visits": 1,
        "first_seen_at": now_iso,
        "last_visit_at": now_iso,
    }
    return client.table("customers").insert(row).execute().data[0]


def get_customer(restaurant_id: str, customer_id: str) -> dict | None:
    client = _c()
    if client is None:
        return None
    rows = (
        client.table("customers").select("*")
        .eq("id", customer_id).eq("restaurant_id", restaurant_id).limit(1).execute().data
    )
    return rows[0] if rows else None


def list_sessions_for_phone(restaurant_id: str, phone: str, limit: int = 20) -> list[dict]:
    """A customer's past visits: the table sessions where they gave this number at the bill."""
    client = _c()
    if client is None:
        return []
    return (
        client.table("table_sessions").select("*")
        .eq("restaurant_id", restaurant_id).eq("guest_phone", phone)
        .order("seated_at", desc=True).limit(limit).execute().data
    )


def list_customers(restaurant_id: str, limit: int = 500) -> list[dict]:
    client = _c()
    if client is None:
        return []
    return (
        client.table("customers").select("*").eq("restaurant_id", restaurant_id)
        .order("last_visit_at", desc=True).limit(limit).execute().data
    )


# -------------------------------------------------------------------- orders --


def count_orders_between(restaurant_id: str, start_iso: str, end_iso: str) -> int:
    client = _c()
    if client is None:
        return 0
    rows = (
        client.table("orders").select("id")
        .eq("restaurant_id", restaurant_id).gte("created_at", start_iso).lt("created_at", end_iso)
        .limit(10000).execute().data
    )
    return len(rows)
