"""One Sarvam Samvaad conversation (a browser call or a phone call), as our side sees it.

Samvaad runs the conversation itself: it hears the guest, its LLM decides what to do, and it speaks. What it
cannot know is the store's menu, prices, cart and order rules, so every action is an API tool that lands here.
One generic Samvaad agent serves every restaurant: the store comes from the call (an agent variable set by the
browser, the dialled number, or SAMVAAD_DEFAULT_STORE), never from the agent's prompt.

The rules are the ones phone orders already follow (app/phone/ordering.py), reused as they are:
  - the cart, menu matching, sizes and the waiter's suggestions are the agent tools' (app/agent/tools.py)
  - nothing is placed until the order has been read back and the guest has said yes
  - totals are added up in code, the order is saved before anyone is told, and WhatsApp gets the bill

Sessions live in this process's memory, keyed by Samvaad's interaction id, for up to SESSION_TTL_SECONDS.
That is enough for one API instance; running several needs the cart moved to the database first.
"""
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field

from app.agent import promotions
from app.agent.salesflow import HINT_PREFIX, SalesState, dessert_offer
from app import agent_config
from app.agent.tools import build_tools
from app.currency import format_price
from app.customers import repository as customers
from app.customers.phone import normalize_phone
from app.menu import repository as menu_repository
from app.menu.snapshot import _sound
from app.phone import carts, numbers, repository
from app.phone.call import _menu_and_restaurant, is_database_store
from app.phone.ordering import PhoneOrder

logger = logging.getLogger("sarthi.samvaad")

SESSION_TTL_SECONDS = 3 * 60 * 60
CART_REFRESH_SECONDS = 60  # an unchanged cart is saved again at most this often, to keep its "last active" time fresh
CUSTOMER_RETRY_SECONDS = 30  # after a failed customer save, wait this long before trying again
# Reading the order back and hearing a yes takes a person several seconds. A checkout sooner than this after
# the read-back means the model chained the two tools without waiting for the guest, so it is refused.
MIN_CONFIRM_SECONDS = 3.0
_PERSONA = {"restaurant": "waiter", "kirana": "quick_commerce"}
_NOT_FOUND = re.compile(r"^Couldn't find '(.+)' on the menu\.")
_COULD_MEAN = re.compile(r"^'(.+)' could mean: (.+)\. Ask the customer which one they want\.$")


def _names_every_word(said: str, options: list[str]) -> bool:
    """Whether the dishes offered for a name all contain every word of it ("chicken pizza" → BBQ Chicken
    Pizza), so the guest only has to pick a version. Words compare by sound, so Hindi script matches too."""
    words = set(_sound(said).split())
    return bool(words) and all(words <= set(_sound(option).split()) for option in options)


class StoreNotFound(LookupError):
    pass


def _language(value: str | None) -> str:
    """Samvaad names languages ("Hindi", "English", "hi-IN"); the order rules speak "hi" or "en"."""
    text = (value or "").strip().lower()
    return "en" if text.startswith("en") else "hi"


def find_store(store: str | None = None, called_number: str | None = None) -> dict:
    """The phone store this conversation is for: by slug, else by the dialled number, else the default."""
    row = None
    slug = (store or "").strip()
    if slug:
        row = repository.get_store_by_slug(slug)
    if row is None and called_number:
        number = numbers.canonical(called_number)
        row = repository.store_for_number(number) if number else None
    if row is None and not slug:
        default = os.environ.get("SAMVAAD_DEFAULT_STORE", "").strip()
        row = repository.get_store_by_slug(default) if default else None
    if row is None:
        raise StoreNotFound(f"no store for slug={slug!r} number={called_number!r}")
    if is_database_store(row):
        # Kirana and pharmacy stores in the shop database follow the store agent's flow (prescriptions,
        # saved addresses), which is not wired to Samvaad yet. Restaurants and catalog kiranas are.
        raise StoreNotFound(f"store {row['slug']!r} is a database store, not supported over Samvaad yet")
    return row


@dataclass
class SamvaadSession:
    interaction_id: str
    store: dict
    caller: str | None
    language: str
    channel: str  # "browser" or "phone"
    menu: object = None
    order: PhoneOrder = None
    cart: list[dict] = field(default_factory=list)
    call_id: str | None = None
    read_back_at: float | None = None
    sales: SalesState = field(default_factory=SalesState)
    restaurant_id: str | None = None
    customer_id: str | None = None
    restore: bool = False  # a tool call arrived with no session (the API restarted): pick the saved cart back up
    last_used: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        self.menu, restaurant_id = _menu_and_restaurant(self.store)
        self.restaurant_id = restaurant_id
        self._cart_key: str | None = None
        self._cart_saved_at = 0.0
        self._customer_key: tuple | None = None
        self._customer_failed_at = 0.0
        self._won_back = False
        self.sales = SalesState(settings=promotions.settings(getattr(self.menu, "restaurant", None)))
        persona = _PERSONA[self.store["business_type"]]
        try:
            self.call_id = repository.start_call(
                f"samvaad:{self.interaction_id}", self.store["id"], numbers.canonical(self.caller), self.interaction_id
            )
        except Exception:
            logger.warning("couldn't log the start of Samvaad call %s", self.interaction_id, exc_info=True)
        self.order = PhoneOrder(
            self.store, numbers.canonical(self.caller), persona,
            call_id=self.call_id, restaurant_id=restaurant_id, session_id=f"samvaad:{self.interaction_id}",
        )
        self.order.language = self.language
        # A browser demo's "caller" is whatever the page said; only a phone call's comes from the network.
        self.order.caller_verified = bool(numbers.canonical(self.caller)) and self.channel == "phone"
        self.order.collect_contact = True  # name and the bill's number in one question, so one read-back is enough
        self.order.tools(self.cart)  # binds the cart: the order and the tools share one list
        if self.restore:
            self._restore()
        self._tools = {
            t.name: t
            for t in build_tools(
                self.cart, self.menu, session_id=self.order.session_id, persona=persona,
                restaurant_id=restaurant_id, sales=self.sales, checkout_handler=self.order.checkout,
            )
        }

    # ------------------------------------------------------------- helpers --

    def _turn(self, language: str | None = None) -> None:
        """Each tool call counts as a turn for the order rules (a read-back and its yes are never the same)."""
        self.last_used = time.monotonic()
        if language:
            self.language = _language(language)
        self.order.start_turn(self.language)

    def _tool(self, name: str, args: dict) -> str:
        return self._tools[name].invoke(args)

    def snapshot(self) -> dict:
        total = sum(line["price"] * line["quantity"] for line in self.cart)
        summary = ", ".join(
            f"{line['quantity']} x {line['name']}" + (f" ({line['variant']})" if line.get("variant") else "")
            for line in self.cart
        )
        return {
            "cart_summary": summary or "empty",
            "cart_total": format_price(total) if self.cart else format_price(0),
            "cart": [dict(line) for line in self.cart],
            "order_placed": bool(self.order.order_id),
        }

    # ------------------------------------------------- saving the cart --

    def _identity(self) -> tuple[str | None, bool]:
        """(the user ID, whether the network vouched for it): the caller ID, else the number given for the bill."""
        caller = numbers.canonical(self.caller)
        if caller:
            return caller, self.order.caller_verified
        return normalize_phone(self.order.whatsapp), False

    def _ensure_customer(self) -> None:
        """Make sure this caller is a customer of the store, with the name they gave. Best effort: a database
        problem costs the link to the customer, never the call."""
        if not self.restaurant_id:
            return
        phone, verified = self._identity()
        if not phone:
            return
        key = (phone, self.order.customer_name)
        if key == self._customer_key or time.monotonic() - self._customer_failed_at < CUSTOMER_RETRY_SECONDS:
            return
        try:
            self.customer_id = customers.ensure_customer(
                self.restaurant_id, phone, self.order.customer_name or None, self.language, overwrite_name=verified
            )
            self._customer_key = key
            self._customer_failed_at = 0.0
            self.order.customer_id = self.customer_id
            if self.call_id:
                repository.update_call(self.call_id, customer_id=self.customer_id)
        except Exception:
            self._customer_failed_at = time.monotonic()
            logger.warning("couldn't link call %s to a customer", self.interaction_id, exc_info=True)

    def _cart_row(self, status: str) -> dict:
        phone, verified = self._identity()
        ordered = status == "ordered"
        return {
            "interaction_id": self.interaction_id,
            "restaurant_id": self.restaurant_id,
            "store_id": self.store["id"],
            "call_id": self.call_id,
            "customer_id": self.customer_id,
            "customer_phone": phone,
            "customer_name": self.order.customer_name or None,
            "phone_verified": verified,
            "channel": "call",
            "language": self.language,
            "items": [dict(line) for line in self.cart],
            "total": sum(line["price"] * line["quantity"] for line in self.cart),
            "fulfilment": self.order.order_type,
            "address": self.order.address or None,
            "special_requests": self.order.special_text() or None,
            "status": status,
            "order_id": self.order.order_id,
            "closed_at": repository.now_iso() if ordered else None,
            "closed_reason": "ordered" if ordered else None,
            "last_activity_at": repository.now_iso(),
        }

    def _persist(self, status: str | None = None) -> None:
        """Save the cart (off the call's path) unless nothing changed. `status` is for the end of a call;
        otherwise a cart is 'ordered' once the order exists and 'open' until then."""
        if not (self.cart or self.order.special_requests or self.order.order_id):
            return  # nothing worth keeping yet
        self._ensure_customer()
        row = self._cart_row(status or ("ordered" if self.order.order_id else "open"))
        key = json.dumps({k: v for k, v in row.items() if k != "last_activity_at"}, sort_keys=True, default=str)
        now = time.monotonic()
        if key != self._cart_key or now - self._cart_saved_at >= CART_REFRESH_SECONDS:
            self._cart_key, self._cart_saved_at = key, now
            carts.run_later(carts.save, row)
        if self.order.order_id and not self._won_back and self.restaurant_id and row["customer_phone"]:
            self._won_back = True
            carts.run_later(carts.mark_recovered, self.restaurant_id, row["customer_phone"], self.order.order_id)

    def _restore(self) -> None:
        """Pick a call's saved cart back up after the API restarted mid-call. The read-back starts again, so the
        guest hears the real order once more instead of a yes being counted against a cart they can't remember."""
        row = carts.load(self.interaction_id)
        if not row or row.get("order_id") or row.get("status") not in ("open", "abandoned"):
            return
        self.cart[:] = [dict(line) for line in row.get("items") or []]
        self.order.order_type = row.get("fulfilment")
        self.order.address = row.get("address") or ""
        self.order.customer_name = row.get("customer_name") or ""
        self.order.contact_asked = bool(self.order.customer_name)  # a saved name means that question was answered
        self.order.special_requests = [r for r in (row.get("special_requests") or "").split("; ") if r]
        self.customer_id = row.get("customer_id")
        self.order.customer_id = self.customer_id
        if not self.call_id and row.get("call_id"):
            self.call_id = self.order.call_id = row["call_id"]
        logger.info("restored the cart of call %s (%d lines)", self.interaction_id, len(self.cart))

    def _reply(self, result: str, **extra) -> dict:
        self._persist()
        body = {"result": result, **self.snapshot(), **extra}
        if self.order.spoken:
            body["say"] = self.order.spoken  # exact words for read-backs and confirmations: totals never restated
            if self.order.spoken not in result:
                # Samvaad's response template is often just {{result}}, which would hide "say" from its LLM.
                body["result"] = f"{result}\nSay exactly this to the guest: {self.order.spoken}"
        return body

    # --------------------------------------------------------------- tools --

    def _house_rules(self) -> str:
        """This restaurant's rule book, read fresh at the start of each call so an owner's edit applies to the next
        call. A database problem costs the rules for this call, never the call."""
        if not self.restaurant_id:
            return "none"
        try:
            return agent_config.rules_for_call(menu_repository.get_restaurant(self.restaurant_id))
        except Exception:
            logger.warning("couldn't read the rule book for call %s", self.interaction_id, exc_info=True)
            return "none"

    def start_variables(self) -> dict:
        store = self.store
        return {
            "store_slug": store["slug"],
            "store_name": store["name"],
            "agent_name": store.get("agent_name") or "Kabir",
            "store_type": store["business_type"],
            "caller_known": bool(self.order.whatsapp),
            "house_rules": self._house_rules(),
        }

    def search_menu(self, query: str, language: str | None = None) -> dict:
        self._turn(language)
        result = self._tool("search_menu", {"query": query})
        if result.lstrip().startswith("- "):
            # Samvaad's LLM sometimes searched for a dish the guest ordered and then never added it.
            result += (
                "\nThese are the only matching dishes on the menu; never suggest or promise a dish that is not in a "
                "tool result. If the guest asked for one of these by name, call add_to_cart for it with its exact "
                "name. If they asked for a dish that is not in this list, tell them it is not on the menu and offer "
                "these instead; never add a different dish in its place unless they agree."
            )
        return self._reply(result)

    def item_details(self, name: str, language: str | None = None) -> dict:
        self._turn(language)
        return self._reply(self._tool("get_item_details", {"name": name}))

    def add(self, items: list[dict], language: str | None = None) -> dict:
        self._turn(language)
        lines = [
            {"name": str(i.get("name", "")).strip(), "quantity": int(i.get("quantity") or 1),
             "variant": str(i.get("variant") or "").strip(), "note": str(i.get("note") or "").strip()}
            for i in items if str(i.get("name", "")).strip()
        ]
        if not lines:
            return self._reply("No item name was given. Ask the guest what they would like.")
        before = {(line["id"], line.get("variant")): line["quantity"] for line in self.cart}
        result = self._tool("add_to_cart", {"items": lines})
        return self._reply(self._not_on_menu(result, before))

    def _not_on_menu(self, result: str, before: dict) -> str:
        """Samvaad's LLM told guests "added" for dishes the menu doesn't have (a real call: Veg Kolhapuri,
        Paneer Lababdar, Buttermilk). A dish that isn't on the menu gets exact words to say instead, with the
        closest dishes we do have, and the dishes that did go in are confirmed in the same sentence."""
        missing, kept = [], []
        for line in result.splitlines():
            found = _NOT_FOUND.match(line)
            close = _COULD_MEAN.match(line)
            if found:
                missing.append(found.group(1))
            elif close and not _names_every_word(close.group(1), close.group(2).split(", ")):
                # "Shahi Paneer" offered Paneer Tikka Masala: a different dish, not a choice between versions of it.
                missing.append(close.group(1))
            else:
                kept.append(line)
        if not missing:
            return result
        added = [
            f"{line['quantity'] - before.get((line['id'], line.get('variant')), 0)} {line['name']}"
            + (f" {line['variant']}" if line.get("variant") else "")
            for line in self.cart
            if line["quantity"] > before.get((line["id"], line.get("variant")), 0)
        ]
        alternatives = []
        for name in missing:
            for dish in self.menu.search(name, k=3):
                if dish["name"] not in alternatives and len(alternatives) < 3:
                    alternatives.append(dish["name"])
        names = ", ".join(missing)
        if self.language == "hi":
            words = (f"{', '.join(added)} जोड़ दिया। " if added else "") + f"माफ़ कीजिए, {names} हमारे मेन्यू में नहीं है।"
            words += f" इसकी जगह {', '.join(alternatives)} ले सकते हैं।" if alternatives else ""
        else:
            words = (f"I've added {', '.join(added)}. " if added else "") + f"Sorry, {names} isn't on our menu."
            words += f" Instead, you could have {', '.join(alternatives)}." if alternatives else ""
        self.order.spoken = words
        kept.insert(0, f"NOT ADDED, not on the menu: {names}. Never tell the guest these were added.")
        return "\n".join(kept)

    def add_note(self, name: str, note: str, variant: str = "", language: str | None = None) -> dict:
        """A change to a dish already in the cart ("biryani without beans"). It is saved on that cart line, so
        it is read back, shown to the owner and printed on the kitchen's WhatsApp ticket."""
        self._turn(language)
        return self._reply(self._tool("add_note", {"name": name, "note": note, "variant": variant}))

    def remove(self, name: str, quantity: int = 1, variant: str = "", language: str | None = None) -> dict:
        self._turn(language)
        return self._reply(self._tool("remove_from_cart", {"name": name, "quantity": quantity, "variant": variant}))

    def view(self, language: str | None = None) -> dict:
        self._turn(language)
        return self._reply(self._tool("view_cart", {}))

    def _dessert_first(self) -> dict | None:
        """Once, just before the order is read back: a dessert suggestion (decided in code, app/agent/salesflow.py)."""
        if (self.order.order_id or self.order._blocker() is not None or self.order.read_back is None
                or self.order.read_back_turn != self.order.turn):
            return None  # only in place of a read-back that is about to be said, never over a question
        offer = dessert_offer(self.sales, self.menu.menu, self.menu.get, self.cart)
        if not offer:
            return None
        self.order.read_back, self.order.spoken = None, None
        return self._reply(
            f"{HINT_PREFIX}before reading the order back, ask in one short, friendly line whether they would like to "
            f"end with a dessert: {' or '.join(offer.desserts)}. Do not mention prices. If they want one, add it with "
            "add_to_cart; either way, then call read_back_order.]"
        )

    def _mark_read_back(self) -> None:
        """When the guest was read the order this turn (a yes is only counted a few seconds after it)."""
        if self.order.read_back is not None and self.order.read_back_turn == self.order.turn:
            self.read_back_at = time.monotonic()

    def add_special_request(self, request: str, language: str | None = None) -> dict:
        self._turn(language)
        result = self.order.add_special_request(request)
        self._mark_read_back()
        return self._reply(result)

    def set_details(
        self, order_type: str, address: str = "", whatsapp_number: str = "", language: str | None = None,
        customer_name: str = "",
    ) -> dict:
        self._turn(language)
        result = self.order.set_details(order_type, address, whatsapp_number, customer_name)
        held = self._dessert_first()
        if held:
            return held
        self._mark_read_back()
        return self._reply(result)

    def read_back(self, language: str | None = None) -> dict:
        self._turn(language)
        result = self.order.prepare_read_back()
        held = self._dessert_first()
        if held:
            return held
        self._mark_read_back()
        return self._reply(result)

    def place(self, language: str | None = None) -> dict:
        self._turn(language)
        if (
            not self.order.order_id
            and self.read_back_at is not None
            and self.order.read_back == self.cart
            and time.monotonic() - self.read_back_at < MIN_CONFIRM_SECONDS
        ):
            return self._reply(
                "Order not placed yet. Read the order back to the guest and wait for them to say yes, then call checkout."
            )
        self._ensure_customer()  # so the order is saved with who ordered it
        result = self.order.checkout()
        return self._reply(result, order_id=self.order.order_id)

    def callback(self, reason: str, language: str | None = None) -> dict:
        self._turn(language)
        return self._reply(self.order.request_callback(reason))

    def close(self, transcript=None, extra: dict | None = None) -> None:
        if not self.order.order_id:
            self._persist(status="abandoned")  # items in the cart and no order: the store can win this caller back
        if not self.call_id:
            return
        outcome = "ordered" if self.order.order_id else ("callback" if self.order.callback_reason else "abandoned")
        fields = {"outcome": outcome, "ended_at": repository.now_iso()}
        if extra and extra.get("end_reason"):
            fields["end_reason"] = str(extra["end_reason"])[:100]
        if transcript:
            fields["turns"] = transcript if isinstance(transcript, list) else [{"transcript": str(transcript)}]
        if extra:
            fields["metrics"] = [extra]
        try:
            repository.update_call(self.call_id, **fields)
        except Exception:
            logger.warning("couldn't close the log of Samvaad call %s", self.interaction_id, exc_info=True)


class SessionRegistry:
    def __init__(self, ttl: float = SESSION_TTL_SECONDS):
        self.ttl = ttl
        self._sessions: dict[str, SamvaadSession] = {}
        self._lock = threading.Lock()

    def _sweep(self) -> None:
        cutoff = time.monotonic() - self.ttl
        for key in [k for k, s in self._sessions.items() if s.last_used < cutoff]:
            self._sessions.pop(key, None)

    def get(self, interaction_id: str) -> SamvaadSession | None:
        with self._lock:
            return self._sessions.get(interaction_id)

    def open(
        self,
        interaction_id: str,
        store: str | None = None,
        called_number: str | None = None,
        caller: str | None = None,
        language: str | None = None,
        channel: str = "phone",
        restore: bool = False,
    ) -> SamvaadSession:
        """The session for this interaction, started if it is new. A tool call that arrives without a start
        (the on_start hook failed, or this process restarted) starts one too, from the store it names."""
        with self._lock:
            self._sweep()
            existing = self._sessions.get(interaction_id)
            if existing is not None:
                return existing
        row = find_store(store, called_number)
        session = SamvaadSession(
            interaction_id=interaction_id, store=row, caller=caller, language=_language(language), channel=channel,
            restore=restore,
        )
        with self._lock:
            return self._sessions.setdefault(interaction_id, session)

    def pop(self, interaction_id: str) -> SamvaadSession | None:
        with self._lock:
            return self._sessions.pop(interaction_id, None)


sessions = SessionRegistry()
