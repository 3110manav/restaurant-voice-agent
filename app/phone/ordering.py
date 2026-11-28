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
from app.customers.phone import normalize_phone
from app.phone import messages, numbers, outbox, repository, upi

logger = logging.getLogger("sarthi.phone.ordering")

_REF_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I/L, which get misread
_SAVE_ATTEMPTS = 3
_CONTACT = "Ask the guest the question below, then call set_order_details with their answer."


def _clean_name(raw: str | None) -> str:
    """A customer's name as it will show on the dashboard: one line, no digits (a number heard as a name is noise)."""
    name = " ".join((raw or "").split())[:60]
    return "" if any(ch.isdigit() for ch in name) else name


def _payment_ref() -> str:
    return "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))


def _short_address(address: str, words: int = 4) -> str:
    """The start of the address, enough for the guest to recognise it, in the read-back. They have just said it in
    full and it is saved in full; reading all of it back again took 7 s of a 2 minute call (scenario 2PBTR9)."""
    parts = address.replace(",", " ").split()
    return address.strip() if len(parts) <= words + 1 else " ".join(parts[:words])


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
        self.read_back_words: str | None = None  # what the guest heard at the last read-back
        self.read_back_details: tuple | None = None  # the order type, address, number and requests it described
        self.order_id: str | None = None
        self.callback_reason: str | None = None
        # Who this is, for the owner's dashboard. The caller ID from the phone network is verified; a number the
        # guest only told us is not (the caller of a browser demo is never verified, see SamvaadSession).
        self.customer_name = ""
        self.customer_id: str | None = None
        self.caller_verified = bool(caller)
        self.special_requests: list[str] = []  # wishes about the whole order; per-dish changes live on the cart lines
        # Samvaad asks for the guest's name and where the bill goes in ONE question, once, before the read-back,
        # so the read-back that follows is the only confirmation. The LiveKit agent doesn't (collect_contact off).
        self.collect_contact = False
        self.contact_asked = False
        self.bill_number_given = False  # the guest chose or confirmed the bill's number themselves
        self.cart: list[dict] = []
        self.spoken: str | None = None  # this turn's reply, when these rules decided what to say
        # The WhatsApp number is asked for once. A guest without one (or who won't give it) still gets their order:
        # it is saved and the store is told, only the bill isn't sent. An order is never lost for want of a number.
        self.whatsapp_asked = False
        self.total_unconfirmed = False  # the call transcript never had the total in it (see SamvaadSession.place)
        self.ticket_id: str | None = None  # the support ticket a call back opened (owner's Callbacks tab)

    @property
    def takes_upi(self) -> bool:
        """Whether the bill carries a UPI QR. A store without a UPI ID is paid on delivery or at pickup."""
        return bool(self.store.get("upi_id") and self.store.get("upi_payee_name"))

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
        def set_order_details(order_type: str, address: str = "", whatsapp_number: str = "", customer_name: str = "") -> str:
            """Record whether this is "delivery" or "pickup", the delivery address exactly as the
            customer said it, the customer's name if they gave it, and a WhatsApp number only if
            they gave a different one for the bill.
            """
            return self.set_details(order_type, address, whatsapp_number, customer_name)

        @tool
        def add_special_request(request: str) -> str:
            """Note a wish about the whole order that is not about one dish: "deliver after 8 pm", "no cutlery",
            "call when you arrive". A change to one dish ("biryani without beans") goes on that dish with add_note.
            """
            return self.add_special_request(request)

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

        return [set_order_details, add_special_request, read_back_order, request_callback]

    def special_text(self) -> str:
        return "; ".join(self.special_requests)

    def add_special_request(self, request: str) -> str:
        text = " ".join((request or "").split())[:200]
        if not text:
            return "Say what the request is (for example 'deliver after 8 pm')."
        if text.lower() not in (r.lower() for r in self.special_requests):
            if len(self.special_requests) >= 8:
                return "That is enough requests for one order. Tell the customer the store will call about anything else."
            self.special_requests.append(text)
        noted = f"Noted for the store: {text}. It is a request, not a promise: do not say it will definitely be done."
        if self.read_back is None:
            # Nothing was read back yet: just carry on. One read-back at the end will include it.
            return f"{noted} Tell the guest in a few words that it's noted, then carry on with the order. Do not read the order back now."
        self.read_back = None  # the guest heard an order without this request: they hear it once more, with it
        return f"{noted} " + self.prepare_read_back()

    def set_details(self, order_type: str, address: str = "", whatsapp_number: str = "", customer_name: str = "") -> str:
        kind = order_type.strip().lower()
        if kind not in ("delivery", "pickup"):
            return 'Order type must be "delivery" or "pickup". Ask the customer which they want.'
        if kind == "delivery" and not address.strip() and not self.address:
            return "Delivery needs an address. Ask the customer for it."
        if whatsapp_number.strip() and not any(ch.isdigit() for ch in whatsapp_number):
            whatsapp_number = ""  # "same", "isi number pe": the number they're calling from
        chosen = None
        if whatsapp_number.strip():
            chosen = numbers.whatsapp_number(whatsapp_number)
            if not chosen:
                return "That isn't a valid ten digit mobile number. Ask the customer to repeat it."
        before = (self.order_type, self.address, self.whatsapp)
        self.order_type = kind
        name = _clean_name(customer_name)
        if name:
            self.customer_name = messages.english(name)  # the dashboard and bills show it in English letters
        if address.strip():
            self.address = address.strip()
        if chosen:
            self.whatsapp = chosen
            self.bill_number_given = True
        if self.read_back is not None and (self.order_type, self.address, self.whatsapp) == before:
            # Only the name came in (or nothing new): what the guest heard still stands. Reading it again is
            # exactly the repetition callers find annoying.
            return "Saved. The order was already read back and has not changed: do not read it again. Wait for the guest's yes."
        self.read_back = None  # what was read back no longer describes the order
        return self.prepare_read_back()

    def _details(self) -> tuple:
        return (self.order_type, self.address, self.whatsapp, self.special_text())

    def already_read_back(self) -> bool:
        """The guest has heard this exact order (dishes, address, number and requests) and nothing has changed."""
        return (self.read_back is not None and not self.order_id and self.read_back == self.cart
                and self.read_back_details == self._details() and self.read_back_words is not None)

    def _total(self) -> float:
        return sum(line["price"] * line["quantity"] for line in self.cart)

    def _blocker(self) -> str | None:
        if not self.cart:
            return "The cart is empty."
        if self.order_type is None:
            return "Ask whether this is delivery or pickup, then call set_order_details."
        if self.order_type == "delivery" and not self.address:
            return "Ask for the delivery address, then call set_order_details."
        if self.collect_contact:
            return _CONTACT if self._needs_contact() else None
        if not self.whatsapp and not self.whatsapp_asked:
            return "This caller's number can't receive WhatsApp. Ask for a mobile number that has WhatsApp, then call set_order_details."
        return None

    def _needs_contact(self) -> bool:
        if not self.whatsapp:
            # Asked once. A guest without WhatsApp (or who won't say) still gets their order, only not the bill.
            return not self.contact_asked
        return not self.contact_asked and not (self.customer_name and self.bill_number_given)

    def _contact_question(self) -> tuple[str, str]:
        """The name and the bill's number, asked together and once. A guest who'd rather not give a name
        isn't asked again."""
        name = not self.customer_name and not self.contact_asked
        if not self.whatsapp:
            if name:
                return ("आपका नाम और व्हाट्सएप नंबर बता दीजिए? बिल उसी पर भेजूँगा।",
                        "May I have your name and your WhatsApp number for the bill?")
            return ("बिल व्हाट्सएप पर भेजना है। आपका व्हाट्सएप नंबर बता दीजिए?",
                    "I'll send the bill on WhatsApp. What's your WhatsApp number?")
        # The number they're calling from: not read out, the guest knows their own number (28 Nov feedback).
        if name:
            return ("आपका नाम बता दीजिए? और बिल व्हाट्सएप पर इसी नंबर पर भेज दूँ जिससे आप कॉल कर रहे हैं, या किसी और नंबर पर?",
                    "May I have your name? And shall I send the bill on WhatsApp to the number you're calling from, or another one?")
        return ("बिल व्हाट्सएप पर इसी नंबर पर भेज दूँ जिससे आप कॉल कर रहे हैं, या किसी और नंबर पर?",
                "Shall I send the bill on WhatsApp to the number you're calling from, or another one?")

    def _ask_contact(self) -> str:
        self._say(*self._contact_question())
        self.contact_asked = True
        hint = (
            " If the guest has no WhatsApp number or won't give one, call read_back_order: the order can still be "
            "placed, only the bill isn't sent."
        ) if not self.whatsapp else ""
        return f"{_CONTACT}{hint} Say exactly this to the guest: {self.spoken}"

    def _ask_for_whatsapp(self, blocker: str) -> None:
        """The exact question, so a voice agent asks for the number instead of stalling on the instruction."""
        if blocker == _CONTACT:
            self._ask_contact()
        elif not self.whatsapp and blocker.startswith("This caller's number"):
            self.whatsapp_asked = True
            self._say(
                "बिल के लिए अपना व्हाट्सएप नंबर बता दीजिए?",
                "What's your WhatsApp number for the bill?",
            )

    def _summary(self) -> tuple[str, str, int]:
        """The order in words (Hindi, English) and its total, worked out here so it's never restated wrongly."""
        items = ", ".join(
            f"{line['quantity']} {line['name']}" + (f" {line['variant']}" if line.get("variant") else "")
            + (f" ({line['note']})" if line.get("note") else "")
            for line in self.cart
        )
        if self.order_type == "delivery":
            where = _short_address(self.address)
            where_hi, where_en = f"{where} पर डिलीवरी", f"Delivery to {where}"
        else:
            where_hi, where_en = "दुकान से पिकअप", "Pickup from the store"
        total = round(self._total())
        extra_hi = f" विशेष अनुरोध: {self.special_text()}।" if self.special_requests else ""
        extra_en = f" Special request: {self.special_text()}." if self.special_requests else ""
        return (
            f"आपका ऑर्डर: {items}। कुल {total} रुपये। {where_hi}।{extra_hi}",
            f"Your order: {items}. Total {total} rupees. {where_en}.{extra_en}",
            total,
        )

    def prepare_read_back(self) -> str:
        blocker = self._blocker()
        if blocker == _CONTACT:
            return self._ask_contact()
        if blocker and blocker.startswith("This caller's number"):
            # Only the WhatsApp number is missing: ask for it in one short line. The full read-back follows once it
            # is given, so the order isn't read out twice. Asked once only: after that the order goes ahead without it.
            self._ask_for_whatsapp(blocker)
            return (
                f"{blocker} If the guest has no WhatsApp number or won't give one, call read_back_order: the order "
                f"can still be placed, only the bill isn't sent. Say exactly this to the guest: {self.spoken}"
            )
        if blocker:
            return blocker
        self.read_back = copy.deepcopy(self.cart)
        self.read_back_turn = self.turn
        hindi, english, _ = self._summary()
        if not self.whatsapp:
            self._say(
                f"{hindi} बिल व्हाट्सएप पर नहीं आ पाएगा, दुकान आपका ऑर्डर तैयार करेगी। ऑर्डर पक्का कर दूँ?",
                f"{english} I can't send the bill on WhatsApp, but the store will still prepare your order. "
                "Shall I place the order?",
            )
            return f"Read back to the customer: {self.spoken} Only call checkout after they say yes in their next message."
        bill_hi, bill_en = ("बिल और UPI ID", "bill and UPI ID") if self.takes_upi else ("बिल", "bill")
        if self.whatsapp == numbers.whatsapp_number(self.caller):
            # The number they're calling from: no digits to read out.
            to_hi, to_en = "इसी नंबर पर", "to this number"
        else:
            # A number the guest told us: read out in full, digit by digit, to catch a number misheard.
            number = numbers.spoken(self.whatsapp)
            to_hi, to_en = f"{number} नंबर पर", f"to {number}"
        name = self.customer_name if self.collect_contact else ""
        hi_name, en_name = (f"{name} जी, ", f"{name}, ") if name else ("", "")
        self._say(
            f"{hi_name}{hindi} {bill_hi} व्हाट्सएप पर {to_hi} आएगा। ऑर्डर पक्का कर दूँ?",
            f"{en_name}{english[0].lower() if en_name else english[0]}{english[1:]} The {bill_en} will come on WhatsApp {to_en}. Shall I place the order?",
        )
        self.read_back_words, self.read_back_details = self.spoken, self._details()
        return f"Read back to the customer: {self.spoken} Only call checkout after they say yes in their next message."

    def checkout(self) -> str:
        if self.order_id:
            self._say("ऑर्डर पक्का हो चुका है। बिल व्हाट्सएप पर है। धन्यवाद!", "Your order is already placed, and the bill is on WhatsApp. Thank you!")
            return "Order placed already."
        blocker = self._blocker()
        if blocker:
            self._ask_for_whatsapp(blocker)
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
            # +91..., like the customers table. Without a WhatsApp number, the caller ID still lets the store call back.
            "customer_phone": normalize_phone(self.whatsapp or self.caller) or self.whatsapp or self.caller,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name or None,
            "phone_verified": self.caller_verified,
            "channel": "call",
            "special_requests": self.special_text() or None,
            "order_type": self.order_type,
            "address": self.address if self.order_type == "delivery" else None,
            "language": self.language,
            "payment_ref": _payment_ref(),
            "pay_token": secrets.token_urlsafe(16),
        }
        uri = upi.payment_uri(self.store, order["total"], order["payment_ref"]) if self.takes_upi else None
        owner = messages.owner_order(order)
        if not self.whatsapp:
            owner["text"] += "\n\nNo WhatsApp number: the customer did NOT get a bill. Please confirm the order with them."
        if self.total_unconfirmed:
            owner["text"] += f"\n\nThe customer may not have heard this total. Please confirm {format_price(order['total'])} with them."
        outgoing = [{"recipient": self.store["owner_whatsapp"], "kind": "owner_order", "body": owner}]
        if self.whatsapp:
            outgoing.append({
                "recipient": self.whatsapp,
                "kind": "customer_bill",
                "body": messages.customer_bill(order, self.store, uri, pay_link(order["pay_token"]) if uri else None),
            })
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
            self._open_ticket(f"Order couldn't be saved ({format_price(order['total'])}): call them back to take it")
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
        if not self.whatsapp:
            self._say("ऑर्डर पक्का हो गया। दुकान आपका ऑर्डर तैयार करेगी। धन्यवाद!", "Your order is placed, and the store will prepare it. Thank you!")
        elif self.takes_upi:
            self._say(
                "ऑर्डर पक्का हो गया। बिल और UPI ID व्हाट्सएप पर भेज दिया है। धन्यवाद!",
                "Your order is placed. The bill and UPI ID are on WhatsApp. Thank you!",
            )
        else:
            # Short: what to pay and how is on the bill itself.
            self._say("ऑर्डर पक्का हो गया, बिल व्हाट्सएप पर भेज दिया है। धन्यवाद!", "Your order is placed, and the bill is on WhatsApp. Thank you!")
        return f"Order placed: {order['payment_ref']}. Total: {format_price(order['total'])}."

    def _open_ticket(self, reason: str) -> None:
        """A support ticket on the owner's dashboard (Callbacks tab), so a call back isn't lost in WhatsApp."""
        try:
            self.ticket_id = repository.open_ticket({
                "session_id": self.session_id or (self.call_id or ""),
                "persona": self.persona,
                "details": reason,
                "restaurant_id": self.restaurant_id,
                "call_id": self.call_id,
                "customer_id": self.customer_id,
                "order_id": self.order_id,
                "customer_phone": normalize_phone(self.whatsapp or self.caller) or self.whatsapp or self.caller,
            })
        except Exception:
            logger.exception("couldn't open a support ticket for call %s", self.call_id)

    def request_callback(self, reason: str) -> str:
        if self.callback_reason:
            self._say("दुकान को बता दिया है, आपको जल्द फ़ोन आएगा।", "I've told the store, and they'll call you soon.")
            return "The store has already been asked to call back."
        self.callback_reason = reason.strip()[:200] or "the customer asked"
        self._open_ticket(self.callback_reason)
        body = messages.callback_alert(self.whatsapp or self.caller, self.callback_reason, self.store["name"])
        try:
            repository.queue_message(self.store["owner_whatsapp"], "callback_alert", body, call_id=self.call_id)
            outbox.flush_in_background()
        except Exception:
            logger.exception("couldn't queue the callback alert")
            outbox.send_alert_now(self.store["owner_whatsapp"], body["text"])
        self._say("ठीक है, दुकान को बता दिया है। आपको जल्द फ़ोन आएगा।", "Okay, I've told the store. They'll call you soon.")
        return "The store has been asked to call them back."
