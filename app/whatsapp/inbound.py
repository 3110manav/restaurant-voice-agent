"""What happens when someone messages a store's WhatsApp number.

A customer's text goes to the same ordering agent as the web chat and the phone call (so it can take an
order and answer questions), with the sender's number as the verified identity: a returning customer is
recognised, and a saved address is never asked for. Their reply goes back as a WhatsApp message.

A photo goes to the order waiting for its prescription: the order moves on, and the pharmacist is told.

A message from the store's own staff that starts with a command ("confirm K7M2P", "reject K7M2P no stock",
"ready K7M2P", "show K7M2P") updates that order and tells the customer. Any other message from a staff
number is treated as a customer's chat, so an owner can try the whole flow from their own phone.
"""
import re
import threading
import time

from app.agent import language as lang
from app.agent.graph import AgentBusyError, RestaurantOrderingAgent, persona_for
from app.customers.session import start_session
from app.menu.snapshot import LiveMenu
from app.whatsapp import channels, client, notify
from app.whatsapp.channels import Channel

SESSION_TTL = 6 * 3600  # a WhatsApp chat can last for days; a cart idle this long starts fresh
_chats: dict[tuple[str, str], "_Chat"] = {}
_registry_lock = threading.Lock()

# The code is exactly five characters from the order-code alphabet (no 0, O, 1, I or L), so ordinary words
# in a chat ("ok thanks", "ready please") are never mistaken for a command.
COMMAND = re.compile(r"^\s*(confirm|accept|reject|decline|ready|dispatch|dispatched|show)\s+([A-HJKMNP-Z2-9]{5})\b[\s,:-]*(.*)$", re.I)
_ACTIONS = {
    "confirm": "confirmed", "accept": "confirmed",
    "reject": "rejected", "decline": "rejected",
    "ready": "out_for_delivery", "dispatch": "out_for_delivery", "dispatched": "out_for_delivery",
}


class _Chat:
    def __init__(self, agent: RestaurantOrderingAgent):
        self.agent, self.last_used, self.lock = agent, time.monotonic(), threading.Lock()


def _chat(store: dict, phone: str, language: str) -> _Chat:
    key = (store["id"], phone)
    now = time.monotonic()
    with _registry_lock:
        for k in [k for k, c in _chats.items() if now - c.last_used > SESSION_TTL]:
            del _chats[k]
        chat = _chats.get(key)
        if chat is None:
            agent = RestaurantOrderingAgent(
                session_id=f"wa:{store['slug']}:{phone}",
                menu_store=LiveMenu(store["slug"]),
                persona=persona_for(store),
                restaurant=store,
                customer=start_session(store, phone, None, language, verified=True),
            )
            agent.channel = "whatsapp"
            context_language = agent.customer.context.language if agent.customer else None
            agent.set_language(context_language or language)
            chat = _chats[key] = _Chat(agent)
        chat.last_used = now
        return chat


def reply_to_text(store: dict, phone: str, text: str) -> str:
    """The agent's reply to a customer's WhatsApp text."""
    chat = _chat(store, phone, "en")
    with chat.lock:  # two quick messages from one customer are handled one after the other
        if lang.has_devanagari(text):
            chat.agent.set_language("hi")
        try:
            return chat.agent.send(text)
        except AgentBusyError:
            return lang.line(chat.agent.language, "busy")


def handle_media(channel: Channel, store: dict, phone: str, media_id: str | None, caption: str) -> str:
    """A photo from a customer: it is the prescription for the order that is waiting for one."""
    language = _chat(store, phone, "en").agent.language
    order = channels.latest_order_awaiting_prescription(store["id"], phone)
    if order is None or not media_id:
        return lang.line(language, "rx_none")
    channels.set_order_status(order["id"], "prescription_received")
    who = f"{order.get('customer_name') or 'customer'} ({phone})"
    notify.prescription_arrived(channel, store, order, media_id, who)
    return lang.line(language, "rx_received").format(code=order.get("short_code") or "")


# ------------------------------------------------------------------------------- staff commands --

_UPDATE_TEXT = {
    "confirmed": "Good news: your order {code} at {store} is confirmed.",
    "rejected": "Sorry, {store} couldn't confirm your order {code}.{reason} Please call the store.",
    "out_for_delivery": "Your order {code} from {store} is on its way.",
}


def parse_command(text: str) -> tuple[str, str, str] | None:
    match = COMMAND.match(text or "")
    return (match.group(1).lower(), match.group(2).upper(), match.group(3).strip()) if match else None


def staff_command(channel: Channel, store: dict, staff_phone: str, command: tuple[str, str, str]) -> str:
    """Apply an owner's or pharmacist's command to an order; returns what to reply to them."""
    verb, code, rest = command
    order = channels.order_by_code(store["id"], code)
    if order is None:
        return f"I can't find an order with code {code}."
    if verb == "show":
        media = channels.latest_media_from(store["id"], order.get("caller_phone") or "")
        if not media:
            return f"There is no prescription photo yet for order {code}."
        client.send_image_by_id(channel, staff_phone, media, f"Prescription for order {code}", order["id"])
        return f"Here is the prescription for order {code}. Reply CONFIRM {code} or REJECT {code} <reason>."
    status = _ACTIONS[verb]
    channels.set_order_status(order["id"], status)
    reason = f" Reason: {rest}." if status == "rejected" and rest else ""
    text = _UPDATE_TEXT[status].format(code=code, store=store["name"], reason=reason)
    notify.tell_customer_update(channel, store, order, text)
    return f"Order {code} marked {status.replace('_', ' ')}, and the customer has been told."
