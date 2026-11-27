"""The words of every WhatsApp message. Totals and items come from the saved order, never from the LLM.

Every message is in English, the owner's and the customer's alike, whatever language the call was in: a bill is
read and forwarded, and a Hindi bill came out half translated ("पता: 1902, having Modi's face").
"""
from app.currency import format_price
from app.menu.translit import has_devanagari, to_roman

CAPTION_LIMIT = 1024  # WhatsApp's limit on an image caption


def _line(line: dict) -> str:
    name = f"{line['name']} ({line['variant']})" if line.get("variant") else line["name"]
    text = f"{line['quantity']} x {name} - {format_price(line['price'] * line['quantity'])}"
    # What the guest asked for on this dish ("without beans"): the kitchen reads it on the ticket.
    return f"{text}\n   Note: {line['note']}" if line.get("note") else text


def _item_lines(order: dict) -> str:
    lines = "\n".join(_line(line) for line in order["items"])
    # Wishes about the whole order sit right under the dishes, where the kitchen is already reading.
    return f"{lines}\nSpecial request: {order['special_requests']}" if order.get("special_requests") else lines


def english(text: str | None) -> str:
    """Text a guest said, in English letters for a WhatsApp message: speech-to-text sometimes writes an address or
    name in Hindi script ("बोरीवली वेस्ट"). The agent is asked to write them in English letters; this catches the rest."""
    if not text or not has_devanagari(text):
        return text or ""
    words = to_roman(text).split(" ")
    # Menus and maps end a word in "i", not "ee" (Borivali, not Boreevalee).
    return " ".join(w[:-2] + "i" if w.endswith("ee") else w for w in words).title()


def mobile(phone: str | None) -> str:
    """+919876543210 as +91 98765 43210, easy to read and tap; anything else as it is."""
    digits = "".join(ch for ch in phone or "" if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        return f"+91 {digits[2:7]} {digits[7:]}"
    return phone or "not available"


def _fulfilment(order: dict) -> str:
    if order["order_type"] == "pickup":
        return "Pickup from store"
    return f"Deliver to: {english(order['address'])}"


def owner_order(order: dict) -> dict:
    name = f"Name: {english(order['customer_name'])}\n" if order.get("customer_name") else ""
    text = (
        f"Order {order['payment_ref']}\n\n"
        f"{_item_lines(order)}\n\n"
        f"Total: {format_price(float(order['total']))}\n"
        f"{_fulfilment(order)}\n"
        f"{name}Mobile: {mobile(order.get('customer_phone'))}"
    )
    return {
        "type": "buttons",
        "text": text,
        "buttons": [
            {"id": f"accept:{order['id']}", "title": "Accept"},
            {"id": f"out_of_stock:{order['id']}", "title": "Out of stock"},
            {"id": f"paid:{order['id']}", "title": "Paid"},
        ],
    }


def customer_bill(order: dict, store: dict, upi_uri: str | None, pay_link: str | None) -> dict:
    total = format_price(float(order["total"]))
    text = f"{store['name']}\nOrder {order['payment_ref']}\n\n{_item_lines(order)}\n\nTotal: {total}\n{_fulfilment(order)}"
    if not upi_uri:  # a store without UPI set up: the bill is paid on delivery or at pickup
        return {"type": "text", "text": f"{text}\n\nPay on delivery or at pickup."}
    # The UPI ID as text, not a QR image: a guest pays from any UPI app by pasting it, and a text bill is what a
    # WhatsApp template can carry once the guest's 24-hour window has closed.
    upi_id, payee = store.get("upi_id"), store.get("upi_payee_name") or store["name"]
    return {"type": "text", "text": f"{text}\n\nPay {total} by UPI to {upi_id} ({payee})\nPut order {order['payment_ref']} in the note."}


def callback_alert(caller: str | None, reason: str, store_name: str) -> dict:
    who = caller or "a caller whose number wasn't available"
    return {
        "type": "text",
        "text": f"Please call back: {who}\nReason: {reason}\nCalled {store_name} just now.\n"
                "It's on your dashboard under Callbacks: mark it resolved once you've called.",
    }


_CUSTOMER_UPDATES = {
    "accepted": "{store}: your order {ref} is accepted. Thank you!",
    "out_of_stock": "{store}: sorry, an item in order {ref} is out of stock. Please don't pay this bill. The store will call you.",
    "paid": "{store}: payment received for order {ref}. Thank you!",
}


def customer_update(kind: str, store_name: str, ref: str) -> dict:
    wording = _CUSTOMER_UPDATES[kind]
    return {"type": "text", "text": wording.format(store=store_name, ref=ref)}


def owner_note(text: str) -> dict:
    return {"type": "text", "text": text}
