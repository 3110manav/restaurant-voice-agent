"""One phone call, from the first ring to hanging up: finds the store from the dialled number, builds
its agent, and keeps the log the test view shows. Knows nothing about LiveKit, so the voice worker
(app/voice/livekit_phone.py) and the typed simulator (app/phone/simulate.py) run exactly the same code.
"""
import logging
import time

from app import erp
from app.agent import language as lang
from app.agent.graph import AgentBusyError, RestaurantOrderingAgent
from app.customers.session import start_session
from app.menu.snapshot import LiveMenu, menu_cache
from app.phone import numbers, repository
from app.phone.catalog import StoreCatalog
from app.phone.ordering import PhoneOrder

logger = logging.getLogger("sarthi.phone.call")

MAX_FAILURES = 2
_PERSONA = {"kirana": "quick_commerce", "restaurant": "waiter"}
_STORE_TYPES = ("kirana", "pharmacy")


def is_database_store(store: dict) -> bool:
    """A kirana or pharmacy whose items live in the shop database (the `restaurants` and `dishes` tables), like
    the web stores. It gets the store agent: it recognises returning callers, applies the pharmacy's medical
    guardrails and prescription flow, and alerts the owner or pharmacist on WhatsApp (app/whatsapp).
    Every other phone store (a restaurant, or a kirana with a catalog file) follows the PhoneOrder flow in
    app/phone/ordering.py: read-back, bill and UPI QR on WhatsApp."""
    return store["business_type"] in _STORE_TYPES and bool(store.get("restaurant_slug"))


class _StoreOrder:
    """What a database store's call needs to report its outcome, in the shape PhoneCall expects."""

    def __init__(self, restaurant_id: str, call_id: str | None, session_id: str):
        self.restaurant_id, self.call_id, self.session_id = restaurant_id, call_id, session_id
        self.order_id: str | None = None
        self.callback_reason: str | None = None

    def request_callback(self, reason: str) -> None:
        self.callback_reason = reason
        erp.record_request(self.session_id, "store", "callback", reason, restaurant_id=self.restaurant_id)


def _menu_and_restaurant(store: dict) -> tuple[object, str | None]:
    if store["business_type"] == "kirana":
        return StoreCatalog(store["catalog"]), None
    menu = menu_cache.get(store["restaurant_slug"])
    if menu is None:
        raise LookupError(f"restaurant {store['restaurant_slug']!r} not found")
    return LiveMenu(store["restaurant_slug"]), menu.restaurant["id"]


class PhoneCall:
    def __init__(self, room: str, store: dict, caller: str | None, model: str | None = None):
        self.store = store
        self.database_store = is_database_store(store)
        self.persona = "store" if self.database_store else _PERSONA[store["business_type"]]
        self.turns: list[dict] = []
        self.metrics: list[dict] = []
        self.failures = 0
        self.closed = False
        self.call_id = repository.start_call(room, store["id"], numbers.canonical(caller))
        options = {"model": model} if model else {}
        if self.database_store:
            self._start_store_agent(room, store, caller, options)
        else:
            menu_store, restaurant_id = _menu_and_restaurant(store)
            self.order = PhoneOrder(
                store, numbers.canonical(caller), self.persona,
                call_id=self.call_id, restaurant_id=restaurant_id, session_id=room,
            )
            self.agent = RestaurantOrderingAgent(
                session_id=room, menu_store=menu_store, persona=self.persona, phone=self.order, **options
            )
        self.agent.set_language("hi")

    def _start_store_agent(self, room: str, store: dict, caller: str | None, options: dict) -> None:
        menu = menu_cache.get(store["restaurant_slug"])
        if menu is None:
            raise LookupError(f"store {store['restaurant_slug']!r} not found")
        restaurant = menu.restaurant
        self.order = _StoreOrder(restaurant["id"], self.call_id, room)
        # The caller ID on a real call is verified, so a known number is greeted by name and never asked for
        # an address it has already given.
        customer = start_session(restaurant, caller, None, "hi", verified=True)
        self.agent = RestaurantOrderingAgent(
            session_id=room, menu_store=LiveMenu(store["restaurant_slug"]), persona="store",
            restaurant=restaurant, customer=customer, live_call=True, **options,
        )
        self.agent.channel = "voice"
        self.agent.record_channel = "phone"

    @property
    def greeting(self) -> str:
        if self.database_store:
            return self.agent.opening_line(self.store["name"])
        return lang.phone_greeting(self.agent.agent_name, self.store["name"])

    def take_turn(self, text: str) -> str:
        """Blocking. Always returns something to say: a caller must never be left in silence."""
        started = time.monotonic()
        try:
            if self.database_store:  # the phone agent does this itself; the store agent is told
                self.agent.set_language(lang.caller_language(text, self.agent.language))
            reply = self.agent.send(text)
            self.failures = 0
            if self.database_store and self.agent._placed_this_turn:
                self.order.order_id = "placed"
        except AgentBusyError:
            reply = self._on_failure("the assistant was overloaded")
        except Exception:
            logger.exception("agent failed on call %s", self.call_id)
            reply = self._on_failure("the assistant had a technical problem")
        self.turns.append(
            {
                "caller": text,
                "agent": reply,
                "language": self.agent.language,
                "agent_ms": round((time.monotonic() - started) * 1000),
            }
        )
        self._save_log()
        return reply

    def _on_failure(self, reason: str) -> str:
        self.failures += 1
        language = self.agent.language
        if self.failures < MAX_FAILURES:
            return lang.line(language, "default")
        self.order.request_callback(reason)
        return lang.line(language, "phone_callback")

    def add_metric(self, metric: dict) -> None:
        self.metrics.append(metric)

    def _save_log(self) -> None:
        # Best effort, every turn, so a crash mid-call keeps what happened. Never gets in the call's way.
        try:
            repository.update_call(self.call_id, turns=self.turns, metrics=self.metrics)
        except Exception:
            logger.warning("couldn't update the log of call %s", self.call_id, exc_info=True)

    @property
    def outcome(self) -> str:
        if self.order.order_id:
            return "ordered"
        return "callback" if self.order.callback_reason else "abandoned"

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            repository.update_call(
                self.call_id, turns=self.turns, metrics=self.metrics,
                outcome=self.outcome, ended_at=repository.now_iso(),
            )
        except Exception:
            logger.exception("couldn't close the log of call %s", self.call_id)


def open_call(room: str, dialled: str | None, caller: str | None, model: str | None = None) -> PhoneCall | None:
    """The call for this dialled number, or None if no store answers on it."""
    number = numbers.canonical(dialled)
    store = repository.store_for_number(number) if number else None
    if store is None:
        logger.error("no store answers on the dialled number %s", number)
        return None
    return PhoneCall(room, store, caller, model=model)
