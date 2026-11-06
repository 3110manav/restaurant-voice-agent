"""Who gets told what when an order is placed.

  ordinary order            -> the owner's WhatsApp ("new order"), and the caller gets a confirmation
  prescription order        -> the pharmacist's WhatsApp, and either
        path "whatsapp"        the customer is asked to send a photo of the prescription, or
        path "pharmacist"      the pharmacist is asked to call the customer

An alert to staff is a template unless they have messaged the shop number in the last 23 hours (then it is plain
text). A message to the customer is free text when they messaged us in the last 23 hours, else a template.

Two safety rules:
  - A customer is messaged only if their number is verified (a real call's caller ID), or, on a demo store, if the
    number they typed has itself messaged the store first (that is their consent, and proves it is theirs).
  - Alerts to one store are capped per hour, so a flood of fake web orders cannot spam the owner.
"""
import logging
import os
import threading
import time
from collections import defaultdict, deque

from app.whatsapp import channels, client
from app.whatsapp.channels import Channel

logger = logging.getLogger("sarthi.whatsapp")

TEMPLATES = {
    "order_alert": os.environ.get("WHATSAPP_TPL_ORDER_ALERT", "sarthi_order_alert"),
    "rx_alert": os.environ.get("WHATSAPP_TPL_RX_ALERT", "sarthi_rx_order"),
    "order_confirmation": os.environ.get("WHATSAPP_TPL_ORDER_CONFIRMATION", "sarthi_order_confirmation"),
    "rx_request": os.environ.get("WHATSAPP_TPL_RX_REQUEST", "sarthi_rx_request"),
    "order_update": os.environ.get("WHATSAPP_TPL_ORDER_UPDATE", "sarthi_order_update"),
    "rx_received": os.environ.get("WHATSAPP_TPL_RX_RECEIVED", "sarthi_rx_received"),
}

MAX_ALERTS_PER_HOUR = int(os.environ.get("WHATSAPP_MAX_ALERTS_PER_HOUR", "60"))
_alerts: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def _within_limit(restaurant_id: str) -> bool:
    now = time.monotonic()
    with _lock:
        window = _alerts[restaurant_id]
        while window and now - window[0] > 3600:
            window.popleft()
        if len(window) >= MAX_ALERTS_PER_HOUR:
            return False
        window.append(now)
        return True


def items_summary(lines: list[dict]) -> str:
    parts = []
    for line in lines:
        label = f"{line['name']} ({line['variant']})" if line.get("variant") else line["name"]
        parts.append(f"{line['quantity']} x {label}" + (" [Rx]" if line.get("rx") else ""))
    return ", ".join(parts)


def _money(total: float) -> str:
    return f"Rs {round(total)}"


def _who(order: dict) -> str:
    name, phone = order.get("customer_name"), order.get("phone")
    if name and phone:
        return f"{name} ({phone})"
    return name or phone or "a customer"


def _destination(order: dict) -> str:
    if order.get("fulfilment") == "pickup":
        return "Pickup from the store"
    if order.get("fulfilment") == "dine_in":
        return "Eating in"
    return f"Deliver to: {order.get('address') or 'address not given'}"


def order_placed(store: dict, order: dict) -> None:
    """Tell the right people about a newly placed order. Runs in a background thread; never raises."""
    try:
        channel = channels.channel_for_store(store["id"])
        if channel is None:
            logger.info("store %s has no WhatsApp channel; order %s is in the dashboard only", store.get("slug"), order["code"])
            return
        if not _within_limit(store["id"]):
            logger.warning("alert limit reached for %s; order %s not announced", store.get("slug"), order["code"])
            return
        _alert_staff(channel, order, store["id"])
        _tell_customer(channel, store, order)
    except Exception:
        logger.warning("couldn't announce order %s", order.get("code"), exc_info=True)


def _alert_staff(channel: Channel, order: dict, store_id: str) -> None:
    """Tell the owner (or the pharmacist). Plain text if they have messaged the shop number in the last 23 hours
    (their window is open, so no template and no per-message charge), otherwise the approved template."""
    items = items_summary(order["lines"])
    oid = order.get("order_id")
    if order.get("rx_path"):
        if order["rx_path"] == "whatsapp":
            how = "the customer will send the prescription on WhatsApp, and the order waits for it."
        else:
            how = f"the customer wants to speak to the pharmacist first. Please call {order.get('phone') or 'them (no number given)'}."
        params = [order["code"], _who(order), items, how]
        text = f"Order {params[0]} from {params[1]} needs a prescription check. Items: {items}. Status: {how} Reply with CONFIRM or REJECT followed by the order code once it is checked."
        template, numbers = TEMPLATES["rx_alert"], channel.pharmacists()
    else:
        params = [order["code"], _who(order), items, _money(order["total"]), _destination(order)]
        text = f"New order {params[0]} from {params[1]}: {items}. Total {params[3]}. {params[4]}. Reply with CONFIRM or REJECT followed by the order code."
        template, numbers = TEMPLATES["order_alert"], channel.notify_numbers
    for number in numbers:
        if channels.window_open(store_id, number):
            client.send_text(channel, number, text, oid)
        else:
            client.send_template(channel, number, template, params, oid)


def _tell_customer(channel: Channel, store: dict, order: dict) -> None:
    """Message the customer about their order, but not when they are already chatting with us on WhatsApp (the
    agent's own reply covers that).

    Who may be messaged: a VERIFIED number (a real call's caller ID), or, on a demo store, a typed number that has
    itself messaged the store's WhatsApp first. WhatsApp requires a customer's consent before a business writes
    to them, and a number typed into a web page is no consent: sending to strangers' numbers gets a business
    number reported and restricted. A customer who sends "hi" first has opted in, and it also proves the number
    is theirs. Inside their 24-hour window the message is free text; otherwise it is a template.
    """
    phone = order.get("phone")
    if not phone or order.get("channel") == "whatsapp":
        return
    in_window = channels.window_open(store["id"], phone)
    if not order.get("phone_verified") and not (store.get("demo_mode") and in_window):
        return
    name = order.get("customer_name") or "there"
    oid = order.get("order_id")
    code, items = order["code"], items_summary(order["lines"])
    if order.get("rx_path") == "pharmacist":
        return  # the pharmacist rings them; nothing to send
    if order.get("rx_path") == "whatsapp":
        if in_window:
            client.send_text(channel, phone, f"Hi {name}, your order {code} at {store['name']} includes a prescription medicine. Please send a clear photo of the prescription here so our pharmacist can confirm it.", oid)
        else:
            client.send_template(channel, phone, TEMPLATES["rx_request"], [name, code, store["name"]], oid)
    elif in_window:
        client.send_text(channel, phone, f"Hi {name}, thanks for ordering from {store['name']}. Your order {code}: {items}. Total {_money(order['total'])}. We will update you when the store confirms it.", oid)
    else:
        client.send_template(channel, phone, TEMPLATES["order_confirmation"], [name, code, store["name"], items, _money(order["total"])], oid)


def tell_customer_update(channel: Channel, store: dict, order: dict, text: str) -> None:
    """A status update for the customer (confirmed, rejected, on its way): free text if their window is
    open, else the order-update template."""
    phone = order.get("caller_phone")
    if not phone:
        return
    if channels.window_open(store["id"], phone):
        client.send_text(channel, phone, text, order.get("id"))
    else:
        name = order.get("customer_name") or "there"
        client.send_template(channel, phone, TEMPLATES["order_update"], [name, order.get("short_code") or "-", text], order.get("id"))


def prescription_arrived(channel: Channel, store: dict, order: dict, media_id: str, who: str) -> None:
    """A customer sent the prescription photo for `order`: pass it to the pharmacist. A photo can only be sent
    as free text-style media inside the pharmacist's open window; otherwise they get a template asking them to
    reply SHOW <code>, and that reply opens the window."""
    code = order.get("short_code") or "-"
    for number in channel.pharmacists():
        if channels.window_open(store["id"], number):
            client.send_image_by_id(channel, number, media_id, f"Prescription for order {code} from {who}", order.get("id"))
        else:
            client.send_template(channel, number, TEMPLATES["rx_received"], [code, who], order.get("id"))
