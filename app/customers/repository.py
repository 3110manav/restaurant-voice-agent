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


def forget(restaurant_id: str, phone: str) -> None:
    """Delete a customer and blank the personal details on their past orders (a deletion request)."""
    _c().rpc("forget_customer", {"p_restaurant_id": restaurant_id, "p_phone": phone}).execute()
