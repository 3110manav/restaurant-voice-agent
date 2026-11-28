"""What a restaurant's owner sees and changes about their voice agent, in one place (the dashboard's "AI agent" tab):

  - the rule book: the edge cases only this restaurant has, which every call's agent reads (migration 010)
  - where order alerts go: the owner's WhatsApp number on the phone store, which they can point at another phone
  - which number bills come from: the restaurant's own WhatsApp Business number if Sarthi has connected one
    (store_channels), else Sarthi's shared number. Connecting a number needs Meta's ids and a token, so it is set
    up by Sarthi (`python -m app.phone.setup_store whatsapp ...`), and the owner only sees it here.

The rule book shapes how the agent talks, never what an order is: prices, the cart, the read-back and checkout
stay in code (app/phone/ordering.py), and the agent's prompt tells it so.
"""
import os
import re

from app.menu import repository as menu_repository
from app.phone import numbers, repository as phone_repository

RULES_LIMIT = 2000
_UPI_ID = re.compile(r"^[A-Za-z0-9._-]{2,256}@[A-Za-z][A-Za-z0-9.-]{1,63}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ConfigError(ValueError):
    pass


def clean_rules(text: str | None) -> str:
    """Tidy what the owner typed: no control characters, no trailing spaces, at most one blank line in a row."""
    text = _CONTROL.sub("", (text or "").replace("\r\n", "\n").replace("\r", "\n"))
    lines = [line.rstrip() for line in text.split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if len(text) > RULES_LIMIT:
        raise ConfigError(f"The rule book can be at most {RULES_LIMIT} characters (it is {len(text)}).")
    return text


def rules_for_call(restaurant: dict | None) -> str:
    """The house_rules variable a Samvaad call starts with. "none" (not empty) so the prompt reads naturally."""
    rules = ((restaurant or {}).get("agent_rules") or "").strip()
    return rules or "none"


def _pretty(whatsapp_digits: str | None) -> str | None:
    """9198XXXXXXXX -> +91 98XXX XXXXX. The owner's own number, shown to them in full."""
    if not whatsapp_digits:
        return None
    digits = "".join(ch for ch in whatsapp_digits if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        return f"+91 {digits[2:7]} {digits[7:]}"
    return f"+{digits}"


def _sender(restaurant: dict) -> dict:
    rows = (
        menu_repository._c().table("store_channels").select("display_number, enabled")
        .eq("restaurant_id", restaurant["id"]).eq("enabled", True).order("created_at").limit(1).execute().data
    )
    if rows:
        return {"own_number": True, "number": rows[0].get("display_number")}
    return {"own_number": False, "number": os.environ.get("WHATSAPP_DISPLAY_NUMBER") or None}


def view(restaurant: dict) -> dict:
    store = phone_repository.store_for_restaurant(restaurant["slug"])
    numbers_in = phone_repository.numbers_of_store(store["id"]) if store else []
    return {
        "rules": restaurant.get("agent_rules") or "",
        "rules_updated_at": restaurant.get("agent_rules_updated_at"),
        "rules_limit": RULES_LIMIT,
        "calls": (
            {
                "answering": bool(numbers_in),
                "calls_number": numbers_in[0] if numbers_in else None,
                "calls_numbers": numbers_in,  # every number that reaches this restaurant (the number mapper)
                "agent_name": store.get("agent_name"),
                "alert_whatsapp": _pretty(store.get("owner_whatsapp")),
                "upi_id": store.get("upi_id"),
                "upi_payee_name": store.get("upi_payee_name"),
            }
            if store else None
        ),
        "whatsapp_sender": _sender(restaurant),
    }


def _upi_fields(upi_id: str, payee: str | None, restaurant: dict) -> dict:
    """An emptied UPI ID clears it: bills then say pay on delivery or at pickup."""
    upi_id = upi_id.strip()
    if not upi_id:
        return {"upi_id": None, "upi_payee_name": None}
    if not _UPI_ID.match(upi_id):
        raise ConfigError("A UPI ID looks like name@bank (for example fusionkitchen@okhdfcbank).")
    payee = " ".join((payee or "").split())[:80] or restaurant["name"]
    return {"upi_id": upi_id, "upi_payee_name": payee}


def _new_store(restaurant: dict, owner_whatsapp: str) -> dict:
    """The phone store that lets this restaurant take orders by call, created the first time the owner saves where
    alerts go. It answers no number until Sarthi points one at it (setup_store use)."""
    slug = restaurant["slug"]
    if phone_repository.get_store_by_slug(slug):
        slug = f"{slug}-calls"
    return {
        "slug": slug, "name": restaurant["name"], "business_type": restaurant.get("business_type") or "restaurant",
        "agent_name": restaurant.get("agent_name") or "Kabir", "owner_whatsapp": owner_whatsapp,
        "restaurant_slug": restaurant["slug"],
    }


def update(
    restaurant: dict, rules: str | None = None, alert_whatsapp: str | None = None,
    upi_id: str | None = None, upi_payee_name: str | None = None,
) -> dict:
    """Saves what was sent (None = leave it as it is) and returns the new view."""
    store = phone_repository.store_for_restaurant(restaurant["slug"])
    fields: dict = {}
    if alert_whatsapp is not None:
        number = numbers.whatsapp_number(alert_whatsapp)
        if not number:
            raise ConfigError("Give a 10-digit Indian mobile number that has WhatsApp.")
        fields["owner_whatsapp"] = number
    if upi_id is not None:
        fields.update(_upi_fields(upi_id, upi_payee_name, restaurant))
    if fields:
        if store is not None:
            phone_repository.update_store(store["id"], fields)
        elif "owner_whatsapp" in fields:
            phone_repository.save_store({**_new_store(restaurant, fields["owner_whatsapp"]), **fields})
        else:
            raise ConfigError("First save the WhatsApp number that gets your order alerts.")
    if rules is not None:
        restaurant = menu_repository.update_restaurant(
            restaurant["id"], {"agent_rules": clean_rules(rules), "agent_rules_updated_at": phone_repository.now_iso()}
        )
    return view(restaurant)
