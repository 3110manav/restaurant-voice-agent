"""Supabase reads and writes for customers and their addresses (see migration 002).

Everything is per store: a customer row belongs to one restaurant_id, and the same phone
number at another store is a different customer.
"""
import logging

# The shared Supabase client and the retry-once wrapper for stale idle connections.
from app.menu.repository import _c, _read

logger = logging.getLogger("sarthi.customers")


@_read
def customer_context(restaurant_id: str, phone: str) -> dict | None:
    """One round trip: customer, saved address, order count and last order. None if unknown."""
    return _c().rpc("customer_context", {"p_restaurant_id": restaurant_id, "p_phone": phone}).execute().data


def save_details(restaurant_id: str, phone: str, name: str | None, language: str, address: dict) -> tuple[str, str]:
    """Create or update the customer and make `address` their default. Returns (customer_id, address_id).

    `address` has line (required), and optionally area, landmark and pincode. The previous
    default address is kept as history, just no longer the default.
    """
    client = _c()
    fields = {"restaurant_id": restaurant_id, "phone": phone, "language": language}
    if name:
        fields["name"] = name
    customer = client.table("customers").upsert(fields, on_conflict="restaurant_id,phone").execute().data[0]
    client.table("customer_addresses").update({"is_default": False}).eq("customer_id", customer["id"]).eq(
        "is_default", True
    ).execute()
    row = {
        "customer_id": customer["id"],
        "restaurant_id": restaurant_id,
        "line": address["line"],
        "area": address.get("area") or None,
        "landmark": address.get("landmark") or None,
        "pincode": address.get("pincode") or None,
        "is_default": True,
    }
    created = client.table("customer_addresses").insert(row).execute().data[0]
    return customer["id"], created["id"]


def ensure_customer(
    restaurant_id: str, phone: str, name: str | None, language: str = "en", overwrite_name: bool = True
) -> str:
    """The customer's id, creating them if this is their first call. `phone` is E.164. A name is saved when given;
    with overwrite_name False (a number the caller only told us, so it may not be theirs) it fills a blank name
    but never replaces one."""
    client = _c()

    def find() -> dict | None:
        rows = (
            client.table("customers").select("id,name").eq("restaurant_id", restaurant_id).eq("phone", phone)
            .limit(1).execute().data
        )
        return rows[0] if rows else None

    existing = find()
    if existing is None:
        try:
            fields = {"restaurant_id": restaurant_id, "phone": phone, "language": language if language in ("en", "hi") else "en"}
            if name:
                fields["name"] = name
            return client.table("customers").insert(fields).execute().data[0]["id"]
        except Exception:
            existing = find()  # another call created them a moment ago
            if existing is None:
                raise
    if name and name != existing.get("name") and (overwrite_name or not existing.get("name")):
        client.table("customers").update({"name": name}).eq("id", existing["id"]).execute()
    return existing["id"]


def forget(restaurant_id: str, phone: str) -> None:
    """Delete a customer and blank the personal details on their past orders (a deletion request)."""
    _c().rpc("forget_customer", {"p_restaurant_id": restaurant_id, "p_phone": phone}).execute()
