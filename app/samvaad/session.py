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
import logging
import os
import threading
import time
from dataclasses import dataclass, field

from app.agent.salesflow import HINT_PREFIX, SalesState, dessert_offer
from app.agent.tools import build_tools
from app.currency import format_price
from app.phone import numbers, repository
from app.phone.call import _menu_and_restaurant, is_database_store
from app.phone.ordering import PhoneOrder

logger = logging.getLogger("sarthi.samvaad")

SESSION_TTL_SECONDS = 3 * 60 * 60
# Reading the order back and hearing a yes takes a person several seconds. A checkout sooner than this after
# the read-back means the model chained the two tools without waiting for the guest, so it is refused.
MIN_CONFIRM_SECONDS = 3.0
_PERSONA = {"restaurant": "waiter", "kirana": "quick_commerce"}


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
    last_used: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        self.menu, restaurant_id = _menu_and_restaurant(self.store)
        persona = _PERSONA[self.store["business_type"]]
        try:
            self.call_id = repository.start_call(
                f"samvaad:{self.interaction_id}", self.store["id"], numbers.canonical(self.caller)
            )
        except Exception:
            logger.warning("couldn't log the start of Samvaad call %s", self.interaction_id, exc_info=True)
        self.order = PhoneOrder(
            self.store, numbers.canonical(self.caller), persona,
            call_id=self.call_id, restaurant_id=restaurant_id, session_id=f"samvaad:{self.interaction_id}",
        )
        self.order.language = self.language
        self.order.tools(self.cart)  # binds the cart: the order and the tools share one list
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

    def _reply(self, result: str, **extra) -> dict:
        body = {"result": result, **self.snapshot(), **extra}
        if self.order.spoken:
            body["say"] = self.order.spoken  # exact words for read-backs and confirmations: totals never restated
        return body

    # --------------------------------------------------------------- tools --

    def start_variables(self) -> dict:
        store = self.store
        return {
            "store_slug": store["slug"],
            "store_name": store["name"],
            "agent_name": store.get("agent_name") or "Kabir",
            "store_type": store["business_type"],
            "caller_known": bool(self.order.whatsapp),
        }

    def search_menu(self, query: str, language: str | None = None) -> dict:
        self._turn(language)
        return self._reply(self._tool("search_menu", {"query": query}))

    def item_details(self, name: str, language: str | None = None) -> dict:
        self._turn(language)
        return self._reply(self._tool("get_item_details", {"name": name}))

    def add(self, items: list[dict], language: str | None = None) -> dict:
        self._turn(language)
        lines = [
            {"name": str(i.get("name", "")).strip(), "quantity": int(i.get("quantity") or 1),
             "variant": str(i.get("variant") or "").strip()}
            for i in items if str(i.get("name", "")).strip()
        ]
        if not lines:
            return self._reply("No item name was given. Ask the guest what they would like.")
        return self._reply(self._tool("add_to_cart", {"items": lines}))

    def remove(self, name: str, quantity: int = 1, variant: str = "", language: str | None = None) -> dict:
        self._turn(language)
        return self._reply(self._tool("remove_from_cart", {"name": name, "quantity": quantity, "variant": variant}))

    def view(self, language: str | None = None) -> dict:
        self._turn(language)
        return self._reply(self._tool("view_cart", {}))

    def _dessert_first(self) -> dict | None:
        """Once, just before the order is read back: a dessert suggestion (decided in code, app/agent/salesflow.py)."""
        if self.order.order_id or self.order._blocker() is not None:
            return None
        offer = dessert_offer(self.sales, self.menu.menu, self.menu.get, self.cart)
        if not offer:
            return None
        self.order.read_back, self.order.spoken = None, None
        return self._reply(
            f"{HINT_PREFIX}before reading the order back, ask in one short, friendly line whether they would like to "
            f"end with a dessert: {' or '.join(offer.desserts)}. Do not mention prices. If they want one, add it with "
            "add_to_cart; either way, then call read_back_order.]"
        )

    def set_details(self, order_type: str, address: str = "", whatsapp_number: str = "", language: str | None = None) -> dict:
        self._turn(language)
        result = self.order.set_details(order_type, address, whatsapp_number)
        held = self._dessert_first()
        if held:
            return held
        if self.order.read_back is not None:
            self.read_back_at = time.monotonic()
        return self._reply(result)

    def read_back(self, language: str | None = None) -> dict:
        self._turn(language)
        held = self._dessert_first()
        if held:
            return held
        result = self.order.prepare_read_back()
        if self.order.read_back is not None:
            self.read_back_at = time.monotonic()
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
        result = self.order.checkout()
        return self._reply(result, order_id=self.order.order_id)

    def callback(self, reason: str, language: str | None = None) -> dict:
        self._turn(language)
        return self._reply(self.order.request_callback(reason))

    def close(self, transcript=None, extra: dict | None = None) -> None:
        if not self.call_id:
            return
        outcome = "ordered" if self.order.order_id else ("callback" if self.order.callback_reason else "abandoned")
        fields = {"outcome": outcome, "ended_at": repository.now_iso()}
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
            interaction_id=interaction_id, store=row, caller=caller, language=_language(language), channel=channel
        )
        with self._lock:
            return self._sessions.setdefault(interaction_id, session)

    def pop(self, interaction_id: str) -> SamvaadSession | None:
        with self._lock:
            return self._sessions.pop(interaction_id, None)


sessions = SessionRegistry()
