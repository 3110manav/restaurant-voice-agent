"""One phone call, from the first ring to hanging up: finds the store from the dialled number, builds
its agent, and keeps the log the test view shows. Knows nothing about LiveKit, so the voice worker
(app/voice/livekit_phone.py) and the typed simulator (app/phone/simulate.py) run exactly the same code.
"""
import logging
import time

from app.agent import language as lang
from app.agent.graph import AgentBusyError, RestaurantOrderingAgent
from app.menu.snapshot import LiveMenu, menu_cache
from app.phone import numbers, repository
from app.phone.catalog import StoreCatalog
from app.phone.ordering import PhoneOrder

logger = logging.getLogger("sarthi.phone.call")

MAX_FAILURES = 2
_PERSONA = {"kirana": "quick_commerce", "restaurant": "waiter"}


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
        self.persona = _PERSONA[store["business_type"]]
        self.turns: list[dict] = []
        self.metrics: list[dict] = []
        self.failures = 0
        self.closed = False
        self.call_id = repository.start_call(room, store["id"], numbers.canonical(caller))
        menu_store, restaurant_id = _menu_and_restaurant(store)
        self.order = PhoneOrder(
            store, numbers.canonical(caller), self.persona,
            call_id=self.call_id, restaurant_id=restaurant_id, session_id=room,
        )
        options = {"model": model} if model else {}
        self.agent = RestaurantOrderingAgent(
            session_id=room, menu_store=menu_store, persona=self.persona, phone=self.order, **options
        )
        self.agent.set_language("hi")

    @property
    def greeting(self) -> str:
        return lang.phone_greeting(self.agent.agent_name, self.store["name"])

    def take_turn(self, text: str) -> str:
        """Blocking. Always returns something to say: a caller must never be left in silence."""
        started = time.monotonic()
        try:
            reply = self.agent.send(text)
            self.failures = 0
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
