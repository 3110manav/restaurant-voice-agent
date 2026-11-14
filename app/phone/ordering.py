"""The rules of placing an order over the phone, enforced in code rather than left to the LLM:

  - nothing is placed until the order has been read back, and the customer has answered in a later turn
  - any change after the read-back means reading it back again
  - delivery needs an address, and the bill needs a WhatsApp number
  - the total is added up here, and the order is saved before anyone is told it's placed

The agent's `checkout` tool calls `checkout()` below (see build_tools' checkout_handler). What's said
at these steps is written here too and spoken as it is (`spoken_reply`, used by the agent's graph), so
items and totals can't be restated wrongly, and each order takes fewer LLM calls.
"""
import copy
import logging
import os
import secrets
import uuid

from langchain_core.tools import tool

from app.currency import format_price
from app.phone import messages, numbers, outbox, repository, upi

logger = logging.getLogger("sarthi.phone.ordering")

_REF_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I/L, which get misread
_SAVE_ATTEMPTS = 3


def _payment_ref() -> str:
    return "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))


def pay_link(token: str) -> str | None:
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    return f"{base}/pay/{token}" if base else None


class PhoneOrder:
    def __init__(
        self,
        store: dict,
        caller: str | None,
        persona: str,
        call_id: str | None = None,
        restaurant_id: str | None = None,
        session_id: str = "",
    ):
        self.store = store
        self.caller = caller
        self.persona = persona
        self.call_id = call_id
        self.restaurant_id = restaurant_id
        self.session_id = session_id
        self.whatsapp = numbers.whatsapp_number(caller)
        self.language = "hi"
        self.order_type: str | None = None
        self.address = ""
        self.turn = 0
        self.read_back: list[dict] | None = None
        self.read_back_turn = -1
        self.order_id: str | None = None
        self.callback_reason: str | None = None
        self.cart: list[dict] = []
        self.spoken: str | None = None  # this turn's reply, when these rules decided what to say

    def start_turn(self, language: str) -> None:
        self.language = language
        self.turn += 1
        self.spoken = None

    def spoken_reply(self) -> str | None:
        """What to say after this turn's tools ran, or None to let the LLM write it. Changing the
        cart after a read-back goes straight to a new read-back, so a stale total is never left standing."""
        if self.spoken is None and self.read_back is not None and self.read_back != self.cart and not self.order_id:
            self.prepare_read_back()
        return self.spoken

    def _say(self, hindi: str, english: str) -> None:
        self.spoken = hindi if self.language == "hi" else english

    # ---------------------------------------------------------------- tools --

    def tools(self, cart: list[dict]) -> list:
        self.cart = cart

        @tool
        def set_order_details(order_type: str, address: str = "", whatsapp_number: str = "") -> str:
            """Record whether this is "delivery" or "pickup", the delivery address exactly as the
            customer said it, and a WhatsApp number only if they gave a different one for the bill.
            """
            return self.set_details(order_type, address, whatsapp_number)

        @tool
        def read_back_order() -> str:
            """Read the whole order back to the customer and ask them to confirm. Use it once they've
            finished ordering and the order details are set.
            """
            return self.prepare_read_back()

        @tool
        def request_callback(reason: str) -> str:
            """Ask the store to call this customer back. Use it when they ask for a person, have a
            complaint, or you still can't understand them after two tries.
            """
            return self.request_callback(reason)

        return [set_order_details, read_back_order, request_callback]

    def set_details(self, order_type: str, address: str = "", whatsapp_number: str = "") -> str:
        kind = order_type.strip().lower()
        if kind not in ("delivery", "pickup"):
            return 'Order type must be "delivery" or "pickup". Ask the customer which they want.'
        if kind == "delivery" and not address.strip() and not self.address:
            return "Delivery needs an address. Ask the customer for it."
        self.order_type = kind
        if address.strip():
            self.address = address.strip()
        if whatsapp_number.strip():
            chosen = numbers.whatsapp_number(whatsapp_number)
            if not chosen:
                return "That isn't a valid ten digit mobile number. Ask the customer to repeat it."
            self.whatsapp = chosen
        self.read_back = None  # what was read back no longer describes the order
        return self.prepare_read_back()

    def _total(self) -> float:
        return sum(line["price"] * line["quantity"] for line in self.cart)

    def _blocker(self) -> str | None:
        if not self.cart:
            return "The cart is empty."
        if self.order_type is None:
            return "Ask whether this is delivery or pickup, then call set_order_details."
        if self.order_type == "delivery" and not self.address:
            return "Ask for the delivery address, then call set_order_details."
        if not self.whatsapp:
            return "This caller's number can't receive WhatsApp. Ask for a mobile number that has WhatsApp, then call set_order_details."
        return None

    def prepare_read_back(self) -> str:
        blocker = self._blocker()
        if blocker:
            return blocker
        self.read_back = copy.deepcopy(self.cart)
        self.read_back_turn = self.turn
        # Spaced, so "3210" is read digit by digit and not as a number in the thousands.
        total, ending = round(self._total()), " ".join(numbers.last_four(self.whatsapp))
        items = ", ".join(
            f"{line['quantity']} {line['name']}" + (f" {line['variant']}" if line.get("variant") else "")
            for line in self.cart
        )
        if self.order_type == "delivery":
            where_hi, where_en = f"{self.address} पर डिलीवरी", f"Delivery to {self.address}"
        else:
            where_hi, where_en = "दुकान से पिकअप", "Pickup from the store"
        self._say(
            f"आपका ऑर्डर: {items}। कुल {total} रुपये। {where_hi}। बिल और पेमेंट QR व्हाट्सएप पर {ending} वाले नंबर पर आएगा। ऑर्डर पक्का कर दूँ?",
            f"Your order: {items}. Total {total} rupees. {where_en}. "
            f"The bill and payment QR will come on WhatsApp to the number ending {ending}. Shall I place the order?",
        )
        return f"Read back to the customer: {self.spoken} Only call checkout after they say yes in their next message."

    def checkout(self) -> str:
        if self.order_id:
            self._say("ऑर्डर पक्का हो चुका है। बिल व्हाट्सएप पर है। धन्यवाद!", "Your order is already placed, and the bill is on WhatsApp. Thank you!")
            return "Order placed already."
        blocker = self._blocker()
        if blocker:
            return f"Order not placed yet. {blocker}"
        if self.read_back != self.cart:
            return "Order not placed yet. The order must be read back first. Call read_back_order."
        if self.read_back_turn >= self.turn:
            return "Order not placed yet. Read it back and wait for the customer to say yes in their next message."
        return self._save()

    def _build_order(self) -> tuple[dict, list[dict]]:
        order = {
            "id": str(uuid.uuid4()),
            "session_id": self.session_id or (self.call_id or ""),
            "persona": self.persona,
            "items": copy.deepcopy(self.cart),
            "total": self._total(),
            "restaurant_id": self.restaurant_id,
            "store_id": self.store["id"],
            "call_id": self.call_id,
            "customer_phone": self.whatsapp,
            "order_type": self.order_type,
            "address": self.address if self.order_type == "delivery" else None,
            "language": self.language,
            "payment_ref": _payment_ref(),
            "pay_token": secrets.token_urlsafe(16),
        }
        uri = upi.payment_uri(self.store, order["total"], order["payment_ref"])
        outgoing = [
            {"recipient": self.store["owner_whatsapp"], "kind": "owner_order", "body": messages.owner_order(order)},
            {
                "recipient": self.whatsapp,
                "kind": "customer_bill",
                "body": messages.customer_bill(order, self.store, uri, pay_link(order["pay_token"]), self.language),
            },
        ]
        return order, outgoing

    def _save(self) -> str:
        order, outgoing = self._build_order()
        for attempt in range(1, _SAVE_ATTEMPTS + 1):
            try:
                repository.place_order(order, outgoing)
                break
            except Exception:
                logger.exception("couldn't save phone order, attempt %s of %s", attempt, _SAVE_ATTEMPTS)
        else:
            # Never tell a customer an order is placed when it isn't. The store still has to hear about them.
            self.callback_reason = "their order couldn't be saved by the system"
            outbox.send_alert_now(
                self.store["owner_whatsapp"],
                f"An order couldn't be saved. Please call {self.whatsapp} right away.",
            )
            self._say(
                "माफ़ कीजिए, ऑर्डर सेव नहीं हो पाया। दुकान से आपको अभी फ़ोन आएगा।",
                "Sorry, I couldn't save your order because of a system problem. The store will call you right back.",
            )
            return "The order could NOT be saved because of a system problem. The store will call them back."
        self.order_id = order["id"]
        outbox.flush_in_background()
        self._say(
            "ऑर्डर पक्का हो गया। बिल और पेमेंट QR व्हाट्सएप पर भेज दिया है। धन्यवाद!",
            "Your order is placed. The bill and payment QR are on WhatsApp. Thank you!",
        )
        return f"Order placed: {order['payment_ref']}. Total: {format_price(order['total'])}."

    def request_callback(self, reason: str) -> str:
        if self.callback_reason:
            self._say("दुकान को बता दिया है, आपको जल्द फ़ोन आएगा।", "I've told the store, and they'll call you soon.")
            return "The store has already been asked to call back."
        self.callback_reason = reason.strip()[:200] or "the customer asked"
        body = messages.callback_alert(self.caller, self.callback_reason, self.store["name"])
        try:
            repository.queue_message(self.store["owner_whatsapp"], "callback_alert", body, call_id=self.call_id)
            outbox.flush_in_background()
        except Exception:
            logger.exception("couldn't queue the callback alert")
            outbox.send_alert_now(self.store["owner_whatsapp"], body["text"])
        self._say("ठीक है, दुकान को बता दिया है। आपको जल्द फ़ोन आएगा।", "Okay, I've told the store. They'll call you soon.")
        return "The store has been asked to call them back."
