"""One guest session at one table, held next to the session's waiter (app/main.py).

It keeps every round sent to the kitchen, which the bill adds up, the dishes added from a
suggestion (the upsell the monthly report credits) and the turn tracker's moments. Each change is
written to `table_sessions` as it happens. Those writes are best effort, like app/erp.py's
request log: a database hiccup must not stop a guest from ordering or paying. The kitchen ticket
itself is not written here; app/erp.py saves orders, and its caller checks that the save worked.
"""
import logging
import threading
from datetime import datetime, timezone

from app.table import repository, service

logger = logging.getLogger("sarthi.table")

MAX_SUGGESTIONS = 2  # suggestion cards per table session, accepted or not, so guests don't feel pushed


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TableState:
    def __init__(self, restaurant: dict, session_id: str, table_no: str | None):
        self.restaurant = restaurant
        self.restaurant_id: str = restaurant["id"]
        self.session_id = session_id
        self.table_no = table_no
        self.row_id: str | None = None
        self.ordered: list[dict] = []
        self.rounds = 0
        self.moments: dict[str, str] = {}
        self.people = 1
        self.upsell_total = 0.0
        self.suggested: set[str] = set()  # dish ids added from a suggestion card, not yet sent
        self.suggestions_shown: set[str] = set()
        self.payment_method: str | None = None
        self.rating: int | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ persistence --

    @classmethod
    def open(cls, restaurant: dict, session_id: str, table_no: str | None) -> "TableState":
        """The table session for this guest: read back after a server restart, else started now."""
        state = cls(restaurant, session_id, table_no)
        try:
            row = repository.find_session(state.restaurant_id, session_id)
        except Exception:
            logger.exception("couldn't read table session %s", session_id)
            row = None
        if row:
            state._load(row)
        else:
            state.moments["seated_at"] = _now()
            state._write({})
        return state

    def _load(self, row: dict) -> None:
        self.row_id = row.get("id")
        self.table_no = self.table_no or row.get("table_no")
        self.ordered = list(row.get("ordered") or [])
        self.rounds = int(row.get("rounds") or 0)
        self.people = int(row.get("people") or 1)
        self.upsell_total = float(row.get("upsell_total") or 0)
        self.payment_method = row.get("payment_method")
        self.rating = row.get("rating")
        self.moments = {m: row[m] for m in service.MOMENTS if row.get(m)}

    def _write(self, fields: dict) -> None:
        try:
            if self.row_id:
                repository.update_session(self.restaurant_id, self.row_id, fields)
                return
            row = repository.create_session(
                {
                    "restaurant_id": self.restaurant_id,
                    "session_id": self.session_id,
                    "table_no": self.table_no,
                    "people": self.people,
                    "rounds": self.rounds,
                    "ordered": self.ordered,
                    "upsell_total": self.upsell_total,
                    **self.moments,
                    **fields,
                }
            )
            if row:
                self.row_id = row.get("id")
        except Exception:
            logger.exception("couldn't save table session %s", self.session_id)

    def _mark(self, moment: str) -> None:
        """Records a turn tracker moment once. The write keeps an earlier value (staff may have
        recorded it from the owner console first)."""
        if moment in self.moments:
            return
        self.moments[moment] = _now()
        if not self.row_id:
            self._write({})
            return
        try:
            repository.set_moment(self.restaurant_id, self.row_id, moment, self.moments[moment])
        except Exception:
            logger.exception("couldn't save %s for table session %s", moment, self.session_id)

    # ---------------------------------------------------------------- events --

    def record_round(self, lines: list[dict]) -> int:
        """A round just reached the kitchen (from the Send button, the chat or a voice call)."""
        if not lines:
            return self.rounds
        with self._lock:
            self.ordered = service.merge_lines(self.ordered, lines)
            self.rounds += 1
            upsell = sum(float(l["price"]) * int(l["quantity"]) for l in lines if l["id"] in self.suggested)
            self.upsell_total += upsell
            self.suggested -= {l["id"] for l in lines}
            fields = {
                "ordered": self.ordered,
                "rounds": self.rounds,
                "upsell_total": self.upsell_total,
                "bill_total": self.bill()["total"],
            }
        self._write(fields)
        self._mark("first_order_at")
        return self.rounds

    def suggestion_added(self, dish_id: str) -> None:
        self.suggested.add(dish_id)
        self.suggestions_shown.add(dish_id)

    def suggestion_dismissed(self, dish_id: str) -> None:
        self.suggestions_shown.add(dish_id)

    def food_served(self) -> None:
        self._mark("food_served_at")

    def request_bill(self, people: int) -> dict:
        self.people = min(max(int(people or 1), 1), 50)
        bill = self.bill()
        self._write({"people": self.people, "bill_total": bill["total"]})
        self._mark("bill_requested_at")
        return bill

    def pay(self, method: str, name: str | None, phone: str | None, offers_opt_in: bool) -> None:
        """The guest chose how to pay. Staff confirm the money arrived (a plain UPI link can't tell
        us), which is when the session is marked paid; see app/owner_api.py."""
        self.payment_method = method
        self._mark("bill_requested_at")
        fields = {"payment_method": method}
        if name:
            fields["guest_name"] = name
        if phone:
            fields["guest_phone"] = phone
            try:
                repository.save_customer(self.restaurant_id, phone, name, offers_opt_in, _now())
            except Exception:
                logger.exception("couldn't save customer for table session %s", self.session_id)
        self._write(fields)

    def rate(self, rating: int, feedback: str | None) -> None:
        self.rating = rating
        fields = {"rating": rating}
        if feedback:
            fields["feedback"] = feedback
        self._write(fields)

    # ----------------------------------------------------------------- reads --

    def bill(self) -> dict:
        return service.bill(self.ordered, float(self.restaurant.get("gst_rate") or 5), self.people)

    def view(self) -> dict:
        return {
            "table_no": self.table_no,
            "rounds": self.rounds,
            "ordered": self.ordered,
            "food_served": "food_served_at" in self.moments,
            "bill_requested": "bill_requested_at" in self.moments,
            "payment_method": self.payment_method,
            "rating": self.rating,
            "people": self.people,
        }
