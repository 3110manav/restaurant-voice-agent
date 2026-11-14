"""The words of every WhatsApp message. Totals and items come from the saved order, never from the LLM.

The owner's messages are in English with the button labels WhatsApp shows; customers get the language
their call was in.
"""
from app.currency import format_price

CAPTION_LIMIT = 1024  # WhatsApp's limit on an image caption


def _line(line: dict) -> str:
    name = f"{line['name']} ({line['variant']})" if line.get("variant") else line["name"]
    return f"{line['quantity']} x {name} - {format_price(line['price'] * line['quantity'])}"


def _item_lines(order: dict) -> str:
    return "\n".join(_line(line) for line in order["items"])


def _fulfilment(order: dict, language: str = "en") -> str:
    if order["order_type"] == "pickup":
        return "दुकान से ले जाएँगे" if language == "hi" else "Pickup from store"
    return f"{'पता' if language == 'hi' else 'Deliver to'}: {order['address']}"


def owner_order(order: dict) -> dict:
    customer = order.get("customer_phone") or "number not available"
    text = (
        f"New phone order {order['payment_ref']}\n\n"
        f"{_item_lines(order)}\n\n"
        f"Total: {format_price(float(order['total']))}\n"
        f"{_fulfilment(order)}\n"
        f"Customer: {customer}"
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


def customer_bill(order: dict, store: dict, upi_uri: str, pay_link: str | None, language: str) -> dict:
    total = format_price(float(order["total"]))
    if language == "hi":
        pay = f"QR स्कैन करके {total} दीजिए।" + (f"\nइसी फ़ोन से देने के लिए: {pay_link}" if pay_link else "")
        text = f"{store['name']}\nऑर्डर {order['payment_ref']}\n\n{_item_lines(order)}\n\nकुल: {total}\n{_fulfilment(order, 'hi')}"
    else:
        pay = f"Scan the QR to pay {total}." + (f"\nPaying from this phone? {pay_link}" if pay_link else "")
        text = f"{store['name']}\nOrder {order['payment_ref']}\n\n{_item_lines(order)}\n\nTotal: {total}\n{_fulfilment(order)}"
    caption = f"{text}\n\n{pay}"
    if len(caption) <= CAPTION_LIMIT:
        return {"type": "qr", "upi_uri": upi_uri, "caption": caption}
    # A very long order: the outbox sends the bill as a text first, then the QR.
    return {"type": "qr", "upi_uri": upi_uri, "caption": pay, "text_first": text}


def callback_alert(caller: str | None, reason: str, store_name: str) -> dict:
    who = caller or "a caller whose number wasn't available"
    return {"type": "text", "text": f"Please call back: {who}\nReason: {reason}\nCalled {store_name} just now."}


_CUSTOMER_UPDATES = {
    "accepted": {
        "en": "{store}: your order {ref} is accepted. Thank you!",
        "hi": "{store}: आपका ऑर्डर {ref} स्वीकार हो गया है। धन्यवाद!",
    },
    "out_of_stock": {
        "en": "{store}: sorry, an item in order {ref} is out of stock. Please don't pay this bill. The store will call you.",
        "hi": "{store}: माफ़ कीजिए, ऑर्डर {ref} का एक सामान उपलब्ध नहीं है। कृपया यह बिल न चुकाएँ। दुकान से आपको फ़ोन आएगा।",
    },
    "paid": {
        "en": "{store}: payment received for order {ref}. Thank you!",
        "hi": "{store}: ऑर्डर {ref} का भुगतान मिल गया। धन्यवाद!",
    },
}


def customer_update(kind: str, store_name: str, ref: str, language: str) -> dict:
    wording = _CUSTOMER_UPDATES[kind]["hi" if language == "hi" else "en"]
    return {"type": "text", "text": wording.format(store=store_name, ref=ref)}


def owner_note(text: str) -> dict:
    return {"type": "text", "text": text}
